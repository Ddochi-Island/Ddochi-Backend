// Package server is the HTTP layer. It accepts caller requests, builds
// queue tasks, blocks on the worker's response channel, and writes back
// JSON. Endpoints:
//
//   POST /v1/exec     — main entry point (one Op per call)
//   GET  /healthz     — liveness (always 200 if process is up)
//   GET  /readyz      — readiness (200 only if DB pool is healthy)
//   GET  /metrics     — Prometheus-style text exposition
//   GET  /stats       — JSON snapshot for human dashboards
//
// All POSTs require Authorization: Bearer <INTERNAL_API_TOKEN> (when
// configured). Health endpoints stay open so orchestrators can probe.
package server

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"time"

	"github.com/redesign2/services/data_router/internal/api"
	"github.com/redesign2/services/data_router/internal/breaker"
	"github.com/redesign2/services/data_router/internal/cache"
	"github.com/redesign2/services/data_router/internal/config"
	"github.com/redesign2/services/data_router/internal/db"
	"github.com/redesign2/services/data_router/internal/idem"
	"github.com/redesign2/services/data_router/internal/logx"
	"github.com/redesign2/services/data_router/internal/metrics"
	"github.com/redesign2/services/data_router/internal/queue"
	"github.com/redesign2/services/data_router/internal/storage"
	"github.com/redesign2/services/data_router/internal/uploadq"
)

type Server struct {
	cfg     *config.Config
	q       *queue.PriorityQueue
	pool    *db.Pool
	cache   *cache.Cache
	idem    *idem.Store
	breaker *breaker.Breaker
	metrics *metrics.Registry
	storage *StorageHandlers

	httpSrv *http.Server
}

// Optional configures Server with optional subsystems. Storage may be
// nil when STORAGE_ENABLED=0 (tests, DB-only deployments).
type Optional struct {
	Storage      *storage.Router
	BlockBackend storage.Backend
	SignSecret   []byte
	UploadQueue  *uploadq.Queue
}

func New(
	cfg *config.Config,
	q *queue.PriorityQueue,
	pool *db.Pool,
	c *cache.Cache,
	i *idem.Store,
	br *breaker.Breaker,
	m *metrics.Registry,
	opt Optional,
) *Server {
	s := &Server{
		cfg: cfg, q: q, pool: pool, cache: c, idem: i, breaker: br, metrics: m,
	}
	if opt.Storage != nil {
		s.storage = NewStorageHandlers(StorageOpts{
			Router:         opt.Storage,
			BlockBackend:   opt.BlockBackend,
			SignSecret:     opt.SignSecret,
			MaxUploadBytes: cfg.Storage.MaxUploadBytes,
			UploadQueue:    opt.UploadQueue,
			SpoolDir:       cfg.Storage.UploadQueueSpoolDir,
			DefaultWaitMs:  cfg.Storage.UploadQueueDefaultWaitMs,
			MaxWaitMs:      cfg.Storage.UploadQueueMaxWaitMs,
		})
	}

	mux := http.NewServeMux()
	mux.HandleFunc("POST /v1/exec", s.handleExec)
	mux.HandleFunc("GET /healthz", s.handleHealthz)
	mux.HandleFunc("GET /readyz", s.handleReadyz)
	mux.HandleFunc("GET /metrics", s.handleMetrics)
	mux.HandleFunc("GET /stats", s.handleStats)
	if s.storage != nil {
		s.storage.Register(mux)
	}

	var h http.Handler = mux
	h = limitBodyMW(cfg.HTTP.MaxBodyBytes)(h)
	h = authMW(cfg.HTTP.AuthToken)(h)
	h = accessLogMW(h)
	h = recoverMW(h)
	h = requestIDMW(h)

	s.httpSrv = &http.Server{
		Addr:              cfg.HTTP.Addr,
		Handler:           h,
		ReadHeaderTimeout: cfg.HTTP.ReadHeaderTO,
		ReadTimeout:       cfg.HTTP.ReadTO,
		WriteTimeout:      cfg.HTTP.WriteTO,
		IdleTimeout:       cfg.HTTP.IdleTO,
	}
	return s
}

func (s *Server) ListenAndServe() error { return s.httpSrv.ListenAndServe() }

func (s *Server) Shutdown(ctx context.Context) error { return s.httpSrv.Shutdown(ctx) }

// ──────────────── handlers ────────────────

func (s *Server) handleExec(w http.ResponseWriter, r *http.Request) {
	rid := RequestIDOf(r)
	s.metrics.ReqTotal.Inc()

	var req api.Request
	dec := json.NewDecoder(r.Body)
	dec.DisallowUnknownFields()
	if err := dec.Decode(&req); err != nil {
		var maxErr *http.MaxBytesError
		if errors.As(err, &maxErr) {
			s.writeErr(w, http.StatusRequestEntityTooLarge, rid, api.CodePayloadTooLarge, "body too large", false)
			return
		}
		s.writeErr(w, http.StatusBadRequest, rid, api.CodeBadRequest, "invalid json: "+err.Error(), false)
		return
	}
	if err := validateRequest(&req); err != nil {
		s.writeErr(w, http.StatusBadRequest, rid, api.CodeBadRequest, err.Error(), false)
		return
	}
	s.normalizeRequest(&req)

	// Idempotent fast-path *before* enqueueing — we don't want to spend
	// queue capacity on a cached duplicate. Read-cache fast-path is also
	// here so dashboard polls don't even occupy the queue.
	if isCachedQuery(&req) {
		key := cache.Key(string(req.Op), req.Stmt.SQL, req.Stmt.Args)
		if cached, ok := s.cache.Get(key); ok {
			s.metrics.ReqCacheHit.Inc()
			s.writeCached(w, rid, cached, true, false)
			s.metrics.ReqOK.Inc()
			s.metrics.ObserveCaller(req.Caller, true)
			return
		}
	}
	if isWrite(req.Op) && req.IdempotencyKey != "" {
		// Peek without claiming leadership — only a strict cache hit short-circuits.
		// We don't call Begin here because that would acquire the leader slot
		// without ever calling Complete. The worker handles the full dance.
	}

	timeout := s.timeoutFor(&req)
	deadline := time.Now().Add(timeout)
	ctx, cancel := context.WithDeadline(r.Context(), deadline)
	defer cancel()

	t := &queue.Task{
		ID:         rid,
		Caller:     req.Caller,
		Priority:   req.Priority,
		EnqueuedAt: time.Now(),
		Deadline:   deadline,
		Req:        &req,
		Result:     make(chan queue.TaskResult, 1),
		Ctx:        ctx,
	}

	if err := s.q.Push(t); err != nil {
		s.metrics.ObserveCaller(req.Caller, false)
		switch {
		case errors.Is(err, queue.ErrQueueFull), errors.Is(err, queue.ErrCallerLimit):
			s.metrics.ReqQueueFull.Inc()
			s.writeErr(w, http.StatusServiceUnavailable, rid, api.CodeQueueFull, err.Error(), true)
		case errors.Is(err, queue.ErrShuttingDown):
			s.writeErr(w, http.StatusServiceUnavailable, rid, api.CodeShuttingDown, "shutting down", true)
		default:
			s.writeErr(w, http.StatusInternalServerError, rid, api.CodeInternal, err.Error(), false)
		}
		return
	}

	select {
	case res := <-t.Result:
		if res.Err != nil {
			if errors.Is(res.Err, context.DeadlineExceeded) || errors.Is(res.Err, queue.ErrDeadlineExceeded) {
				s.metrics.ReqTimeout.Inc()
				s.metrics.ObserveCaller(req.Caller, false)
				s.writeErr(w, http.StatusGatewayTimeout, rid, api.CodeTimeout, "request exceeded timeout in queue", true)
				return
			}
			if errors.Is(res.Err, queue.ErrShuttingDown) {
				s.metrics.ObserveCaller(req.Caller, false)
				s.writeErr(w, http.StatusServiceUnavailable, rid, api.CodeShuttingDown, "shutting down", true)
				return
			}
			s.metrics.ReqErr.Inc()
			s.metrics.ObserveCaller(req.Caller, false)
			s.writeErr(w, http.StatusInternalServerError, rid, api.CodeInternal, res.Err.Error(), false)
			return
		}
		resp := res.Resp
		if resp.Meta.RequestID == "" {
			resp.Meta.RequestID = rid
		}
		resp.Meta.TotalMs = time.Since(t.EnqueuedAt).Milliseconds()
		if resp.Meta.ServerTime == "" {
			resp.Meta.ServerTime = time.Now().UTC().Format(time.RFC3339Nano)
		}
		ok := resp.Status == "ok"
		if ok {
			s.metrics.ReqOK.Inc()
		} else {
			s.metrics.ReqErr.Inc()
		}
		s.metrics.ObserveCaller(req.Caller, ok)
		statusCode := http.StatusOK
		if !ok {
			statusCode = http.StatusBadGateway // executor-returned error => upstream (DB) didn't satisfy us
		}
		s.writeJSON(w, statusCode, resp)
	case <-r.Context().Done():
		// Caller hung up. Worker will still finish the task, but result
		// goes to a channel nobody listens on (buffered, so safe).
		s.metrics.ObserveCaller(req.Caller, false)
		// don't write — connection is gone
	}
}

func (s *Server) handleHealthz(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_, _ = w.Write([]byte(`{"status":"ok"}`))
}

func (s *Server) handleReadyz(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	if !s.pool.Healthy() {
		w.WriteHeader(http.StatusServiceUnavailable)
		_, _ = w.Write([]byte(`{"status":"not_ready","reason":"db_unhealthy"}`))
		return
	}
	if s.breaker.State() == breaker.StateOpen {
		w.WriteHeader(http.StatusServiceUnavailable)
		_, _ = w.Write([]byte(`{"status":"not_ready","reason":"breaker_open"}`))
		return
	}
	_, _ = w.Write([]byte(`{"status":"ready"}`))
}

func (s *Server) handleMetrics(w http.ResponseWriter, _ *http.Request) {
	// Refresh gauges before rendering so consumers see a coherent snapshot.
	st := s.q.Stats()
	s.metrics.QueueDepthHigh.Set(int64(st.High))
	s.metrics.QueueDepthNormal.Set(int64(st.Normal))
	s.metrics.QueueDepthLow.Set(int64(st.Low))
	s.metrics.QueueOldestHigh.Set(st.OldestLagMs[0])
	s.metrics.QueueOldestNorm.Set(st.OldestLagMs[1])
	s.metrics.QueueOldestLow.Set(st.OldestLagMs[2])
	s.metrics.CacheSize.Set(int64(s.cache.Size()))
	done, wip := s.idem.Size()
	s.metrics.IdemSize.Set(int64(done + wip))
	s.metrics.BreakerState.Set(int64(s.breaker.State()))
	if s.pool.Healthy() {
		s.metrics.DBHealthy.Set(1)
	} else {
		s.metrics.DBHealthy.Set(0)
	}

	w.Header().Set("Content-Type", "text/plain; version=0.0.4")
	_, _ = w.Write([]byte(s.metrics.Render()))
}

func (s *Server) handleStats(w http.ResponseWriter, _ *http.Request) {
	st := s.q.Stats()
	done, wip := s.idem.Size()
	out := map[string]any{
		"queue": map[string]any{
			"high":           st.High,
			"normal":         st.Normal,
			"low":            st.Low,
			"total":          st.Total,
			"oldest_lag_ms":  st.OldestLagMs,
			"distinct_callers": st.Callers,
		},
		"cache":   map[string]any{"size": s.cache.Size()},
		"idem":    map[string]any{"done": done, "wip": wip},
		"breaker": map[string]any{"state": s.breaker.State().String()},
		"db":      map[string]any{"healthy": s.pool.Healthy()},
	}
	s.writeJSON(w, http.StatusOK, out)
}

// ──────────────── helpers ────────────────

func isCachedQuery(req *api.Request) bool {
	return req.Op == api.OpQuery && req.CacheTTLMs > 0 && req.Stmt != nil
}

func isWrite(op api.Op) bool {
	return op == api.OpExec || op == api.OpTx || op == api.OpProc
}

func validateRequest(req *api.Request) error {
	if req.Caller == "" {
		return errors.New("caller is required")
	}
	if len(req.Caller) > 64 {
		return errors.New("caller too long")
	}
	switch req.Op {
	case api.OpQuery, api.OpExec, api.OpProc:
		if req.Stmt == nil || req.Stmt.SQL == "" {
			return errors.New("stmt.sql is required for this op")
		}
	case api.OpTx:
		if len(req.Statements) == 0 {
			return errors.New("statements required for tx")
		}
		for i, st := range req.Statements {
			if st.SQL == "" {
				return fmt.Errorf("statements[%d].sql required", i)
			}
		}
	case api.OpPing:
		// no fields required
	default:
		return fmt.Errorf("unknown op %q", req.Op)
	}
	switch req.Priority {
	case "", api.PriorityHigh, api.PriorityNormal, api.PriorityLow:
	default:
		return fmt.Errorf("unknown priority %q", req.Priority)
	}
	return nil
}

func (s *Server) normalizeRequest(req *api.Request) {
	if req.Priority == "" {
		req.Priority = api.PriorityNormal
	}
	if req.Stmt != nil {
		if req.Stmt.FetchLimit <= 0 {
			req.Stmt.FetchLimit = s.cfg.Limits.DefaultFetchLimit
		}
		if req.Stmt.FetchLimit > s.cfg.Limits.MaxFetchLimit {
			req.Stmt.FetchLimit = s.cfg.Limits.MaxFetchLimit
		}
	}
	if req.CacheTTLMs > 0 {
		max := int(s.cfg.Cache.MaxTTL / time.Millisecond)
		if req.CacheTTLMs > max {
			req.CacheTTLMs = max
		}
	}
}

func (s *Server) timeoutFor(req *api.Request) time.Duration {
	t := req.TimeoutMs
	if t <= 0 {
		t = s.cfg.Limits.DefaultTimeoutMs
	}
	if t > s.cfg.Limits.MaxTimeoutMs {
		t = s.cfg.Limits.MaxTimeoutMs
	}
	return time.Duration(t) * time.Millisecond
}

func (s *Server) writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(body); err != nil {
		logx.L().Error("http.write_json", "err", err)
	}
}

func (s *Server) writeErr(w http.ResponseWriter, status int, rid, code, msg string, retryable bool) {
	resp := &api.Response{
		Status: "error",
		Error:  &api.ErrInfo{Code: code, Message: msg, Retryable: retryable},
		Meta:   api.NowMeta(rid),
	}
	s.writeJSON(w, status, resp)
}

func (s *Server) writeCached(w http.ResponseWriter, rid string, raw []byte, cacheHit, coalesced bool) {
	var resp api.Response
	if err := json.Unmarshal(raw, &resp); err != nil {
		s.writeErr(w, http.StatusInternalServerError, rid, api.CodeInternal, "decode cached: "+err.Error(), false)
		return
	}
	resp.Meta.RequestID = rid
	resp.Meta.CacheHit = cacheHit
	resp.Meta.Coalesced = coalesced
	resp.Meta.ServerTime = time.Now().UTC().Format(time.RFC3339Nano)
	s.writeJSON(w, http.StatusOK, &resp)
}

