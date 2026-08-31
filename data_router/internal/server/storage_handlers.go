// storage_handlers.go wires Router + UploadQueue into HTTP. Endpoints:
//
//   POST   /v1/storage/upload         — multipart or octet-stream upload
//                                       Spools to disk, enqueues as a Job,
//                                       sync-waits up to wait_ms (default
//                                       30s) for the worker to finish.
//   GET    /v1/storage/jobs/{id}      — job state by id
//   GET    /v1/storage/jobs           — recent + active jobs (dashboard)
//   GET    /v1/storage/queue          — queue stats (depth, lag, totals)
//   GET    /v1/storage/url?id=<id>    — signed/PAR download URL
//   GET    /v1/storage/meta?id=<id>   — object metadata
//   DELETE /v1/storage/object?id=<id> — delete object
//   GET    /v1/storage/blob/{token}   — direct download for block backend
//   GET    /v1/storage/usage          — capacity + next-upload backend
//
// Async vs sync upload: callers can pass `wait_ms=0` to get an immediate
// 202 with a job_id, then poll `/v1/storage/jobs/{id}`. Default behavior
// (no wait_ms) is to block up to UPLOAD_QUEUE_DEFAULT_WAIT_MS for the
// worker to finish — same UX as the old direct-PUT path.
package server

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"time"

	"github.com/redesign2/services/data_router/internal/api"
	"github.com/redesign2/services/data_router/internal/logx"
	"github.com/redesign2/services/data_router/internal/storage"
	"github.com/redesign2/services/data_router/internal/uploadq"
)

type StorageHandlers struct {
	router         *storage.Router
	maxUploadBytes int64
	signSecret     []byte
	blockBackend   storage.Backend

	// Upload queue (optional). When nil, the upload handler returns 503
	// — STORAGE_ENABLED implies an upload queue.
	uploadq            *uploadq.Queue
	spoolDir           string
	defaultWaitMs      int
	maxWaitMs          int
}

type StorageOpts struct {
	Router         *storage.Router
	BlockBackend   storage.Backend
	SignSecret     []byte
	MaxUploadBytes int64
	UploadQueue    *uploadq.Queue
	SpoolDir       string
	DefaultWaitMs  int
	MaxWaitMs      int
}

func NewStorageHandlers(opts StorageOpts) *StorageHandlers {
	return &StorageHandlers{
		router:         opts.Router,
		maxUploadBytes: opts.MaxUploadBytes,
		signSecret:     opts.SignSecret,
		blockBackend:   opts.BlockBackend,
		uploadq:        opts.UploadQueue,
		spoolDir:       opts.SpoolDir,
		defaultWaitMs:  opts.DefaultWaitMs,
		maxWaitMs:      opts.MaxWaitMs,
	}
}

func (h *StorageHandlers) Register(mux *http.ServeMux) {
	mux.HandleFunc("POST /v1/storage/upload", h.upload)
	mux.HandleFunc("GET /v1/storage/url", h.downloadURL)
	mux.HandleFunc("GET /v1/storage/meta", h.meta)
	mux.HandleFunc("DELETE /v1/storage/object", h.delete)
	mux.HandleFunc("GET /v1/storage/blob/{token}", h.serveBlob)
	mux.HandleFunc("GET /v1/storage/usage", h.usage)

	mux.HandleFunc("GET /v1/storage/jobs", h.listJobs)
	mux.HandleFunc("GET /v1/storage/jobs/{id}", h.getJob)
	mux.HandleFunc("GET /v1/storage/queue", h.queueStats)
}

// ─── upload ─────────────────────────────────────────────────────

func (h *StorageHandlers) upload(w http.ResponseWriter, r *http.Request) {
	rid := RequestIDOf(r)
	if h.uploadq == nil {
		h.writeErr(w, http.StatusServiceUnavailable, rid, "upload_queue_disabled",
			"upload queue not configured", false)
		return
	}

	caller := r.Header.Get("X-Caller")
	if caller == "" {
		caller = "unknown"
	}
	priority := api.Priority(r.URL.Query().Get("priority"))

	waitMs := h.defaultWaitMs
	if v := r.URL.Query().Get("wait_ms"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n >= 0 {
			waitMs = n
		}
	}
	if waitMs > h.maxWaitMs {
		waitMs = h.maxWaitMs
	}

	body, contentType, declaredSize, closer, err := h.openUploadBody(r)
	if err != nil {
		h.writeErr(w, http.StatusBadRequest, rid, api.CodeBadRequest, err.Error(), false)
		return
	}
	defer closer()
	_ = declaredSize // size known after spool; declared is only a hint

	// Spool with an upper bound. We use a request-scoped ctx so a caller
	// disconnect during upload terminates the copy promptly.
	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Minute)
	defer cancel()
	spoolPath, size, sha, err := uploadq.Spool(ctx, body, h.spoolDir, h.maxUploadBytes)
	if err != nil {
		if errors.Is(err, uploadq.ErrPayloadTooLarge) {
			h.writeErr(w, http.StatusRequestEntityTooLarge, rid, api.CodePayloadTooLarge,
				fmt.Sprintf("upload exceeds %d bytes", h.maxUploadBytes), false)
			return
		}
		logx.L().Error("storage.spool", "err", err, "request_id", rid)
		h.writeErr(w, http.StatusInternalServerError, rid, api.CodeInternal, err.Error(), false)
		return
	}

	job := uploadq.NewJob(rid, caller, priority, spoolPath, contentType, sha, size)
	if err := h.uploadq.Push(job); err != nil {
		// Spool already on disk — reclaim before bailing.
		_ = os.Remove(spoolPath)
		switch {
		case errors.Is(err, uploadq.ErrQueueFull), errors.Is(err, uploadq.ErrCallerLimit):
			h.writeErr(w, http.StatusServiceUnavailable, rid, api.CodeQueueFull, err.Error(), true)
		case errors.Is(err, uploadq.ErrShutdown):
			h.writeErr(w, http.StatusServiceUnavailable, rid, api.CodeShuttingDown, "shutting down", true)
		default:
			h.writeErr(w, http.StatusInternalServerError, rid, api.CodeInternal, err.Error(), false)
		}
		return
	}

	if waitMs == 0 {
		// Async: caller polls /v1/storage/jobs/{id}.
		h.writeJSON(w, http.StatusAccepted, map[string]any{
			"status":     "queued",
			"job_id":     job.ID,
			"request_id": rid,
		})
		return
	}

	// Sync wait with timeout.
	timer := time.NewTimer(time.Duration(waitMs) * time.Millisecond)
	defer timer.Stop()
	select {
	case <-job.Done():
		snap := job.Snapshot()
		switch snap.Status {
		case uploadq.StatusCompleted:
			h.writeJSON(w, http.StatusCreated, map[string]any{
				"status":      "ok",
				"meta":        snap.Result,
				"job_id":      snap.ID,
				"queued_ms":   snap.QueuedMs,
				"transfer_ms": snap.TransferMs,
				"request_id":  rid,
			})
		default:
			h.writeJSON(w, http.StatusBadGateway, map[string]any{
				"status": "error",
				"error": map[string]any{
					"code":      "upload_failed",
					"message":   snap.ErrorMsg,
					"retryable": true,
				},
				"job_id":      snap.ID,
				"request_id":  rid,
				"queued_ms":   snap.QueuedMs,
				"transfer_ms": snap.TransferMs,
			})
		}
	case <-timer.C:
		// Worker still running — return current status; caller polls.
		snap := job.Snapshot()
		h.writeJSON(w, http.StatusAccepted, map[string]any{
			"status":     string(snap.Status),
			"job_id":     snap.ID,
			"request_id": rid,
			"hint":       fmt.Sprintf("not finished after %dms; poll /v1/storage/jobs/%s", waitMs, snap.ID),
		})
	}
}

// ─── jobs / queue ──────────────────────────────────────────────

func (h *StorageHandlers) getJob(w http.ResponseWriter, r *http.Request) {
	rid := RequestIDOf(r)
	if h.uploadq == nil {
		h.writeErr(w, http.StatusNotFound, rid, "upload_queue_disabled", "upload queue not configured", false)
		return
	}
	id := r.PathValue("id")
	job := h.uploadq.Get(id)
	if job == nil {
		h.writeErr(w, http.StatusNotFound, rid, "not_found", "job not found or evicted", false)
		return
	}
	snap := job.Snapshot()
	h.writeJSON(w, http.StatusOK, map[string]any{
		"job":        snap,
		"request_id": rid,
	})
}

func (h *StorageHandlers) listJobs(w http.ResponseWriter, r *http.Request) {
	rid := RequestIDOf(r)
	if h.uploadq == nil {
		h.writeErr(w, http.StatusNotFound, rid, "upload_queue_disabled", "upload queue not configured", false)
		return
	}
	limit := 100
	if v := r.URL.Query().Get("limit"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 && n <= 1000 {
			limit = n
		}
	}
	stats := h.uploadq.Stats()
	active := h.uploadq.ActiveSnapshot()
	recent := h.uploadq.RecentSnapshot(limit)
	h.writeJSON(w, http.StatusOK, map[string]any{
		"queue":      stats,
		"active":     active,
		"recent":     recent,
		"request_id": rid,
		"server_time": time.Now().UTC().Format(time.RFC3339Nano),
	})
}

func (h *StorageHandlers) queueStats(w http.ResponseWriter, r *http.Request) {
	rid := RequestIDOf(r)
	if h.uploadq == nil {
		h.writeErr(w, http.StatusNotFound, rid, "upload_queue_disabled", "upload queue not configured", false)
		return
	}
	stats := h.uploadq.Stats()
	h.writeJSON(w, http.StatusOK, map[string]any{
		"queue":       stats,
		"request_id":  rid,
		"server_time": time.Now().UTC().Format(time.RFC3339Nano),
	})
}

// ─── url / meta / delete ───────────────────────────────────────

func (h *StorageHandlers) downloadURL(w http.ResponseWriter, r *http.Request) {
	rid := RequestIDOf(r)
	id := r.URL.Query().Get("id")
	ttl, _ := strconv.Atoi(r.URL.Query().Get("ttl_seconds"))
	if ttl <= 0 {
		ttl = 60
	}

	be, key, err := h.router.Resolve(id)
	if err != nil {
		h.writeErr(w, http.StatusBadRequest, rid, api.CodeBadRequest, err.Error(), false)
		return
	}
	url, exp, err := be.DownloadURL(r.Context(), key, time.Duration(ttl)*time.Second)
	if err != nil {
		logx.L().Error("storage.url", "err", err, "id", id)
		h.writeErr(w, http.StatusBadGateway, rid, "storage_url_failed", err.Error(), true)
		return
	}
	h.writeJSON(w, http.StatusOK, map[string]any{
		"status":     "ok",
		"url":        url,
		"expires_at": exp.UTC().Format(time.RFC3339),
		"backend":    be.Name(),
		"request_id": rid,
	})
}

func (h *StorageHandlers) meta(w http.ResponseWriter, r *http.Request) {
	rid := RequestIDOf(r)
	id := r.URL.Query().Get("id")
	be, key, err := h.router.Resolve(id)
	if err != nil {
		h.writeErr(w, http.StatusBadRequest, rid, api.CodeBadRequest, err.Error(), false)
		return
	}
	m, err := be.Head(r.Context(), key)
	if err != nil {
		if errors.Is(err, storage.ErrNotFound) {
			h.writeErr(w, http.StatusNotFound, rid, "not_found", "object not found", false)
			return
		}
		h.writeErr(w, http.StatusBadGateway, rid, "storage_head_failed", err.Error(), true)
		return
	}
	h.writeJSON(w, http.StatusOK, map[string]any{
		"status": "ok", "meta": m, "request_id": rid,
	})
}

func (h *StorageHandlers) delete(w http.ResponseWriter, r *http.Request) {
	rid := RequestIDOf(r)
	id := r.URL.Query().Get("id")
	be, key, err := h.router.Resolve(id)
	if err != nil {
		h.writeErr(w, http.StatusBadRequest, rid, api.CodeBadRequest, err.Error(), false)
		return
	}
	if err := be.Delete(r.Context(), key); err != nil {
		h.writeErr(w, http.StatusBadGateway, rid, "storage_delete_failed", err.Error(), true)
		return
	}
	h.writeJSON(w, http.StatusOK, map[string]any{"status": "ok", "deleted": true, "request_id": rid})
}

// ─── blob serve (block backend only) ─────────────────────────────

func (h *StorageHandlers) serveBlob(w http.ResponseWriter, r *http.Request) {
	if h.blockBackend == nil {
		http.Error(w, "block backend not configured", http.StatusNotFound)
		return
	}
	token := r.PathValue("token")
	key, err := storage.VerifyBlockToken(h.signSecret, token)
	if err != nil {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return
	}
	rc, meta, err := h.blockBackend.Get(r.Context(), key)
	if err != nil {
		if errors.Is(err, storage.ErrNotFound) {
			http.Error(w, "not found", http.StatusNotFound)
			return
		}
		http.Error(w, "read error", http.StatusInternalServerError)
		return
	}
	defer rc.Close()
	if meta.ContentType != "" {
		w.Header().Set("Content-Type", meta.ContentType)
	} else if ct := mime.TypeByExtension(filepath.Ext(meta.Key)); ct != "" {
		w.Header().Set("Content-Type", ct)
	} else {
		w.Header().Set("Content-Type", "application/octet-stream")
	}
	if meta.Size > 0 {
		w.Header().Set("Content-Length", strconv.FormatInt(meta.Size, 10))
	}
	w.Header().Set("Cache-Control", "private, max-age=300")
	if _, err := io.Copy(w, rc); err != nil {
		logx.L().Debug("storage.blob.copy_aborted", "err", err)
	}
}

func (h *StorageHandlers) usage(w http.ResponseWriter, r *http.Request) {
	h.writeJSON(w, http.StatusOK, h.router.Usage(r.Context()))
}

// ─── helpers ─────────────────────────────────────────────────────

// openUploadBody returns a streaming body + detected content-type +
// declared size (or -1) + a closer the handler must call. Handles both
// multipart/form-data (picks the first "file" part) and raw octet-stream.
func (h *StorageHandlers) openUploadBody(r *http.Request) (io.Reader, string, int64, func(), error) {
	ct := r.Header.Get("Content-Type")
	mediaType, params, _ := mime.ParseMediaType(ct)
	switch mediaType {
	case "multipart/form-data":
		boundary, ok := params["boundary"]
		if !ok {
			return nil, "", -1, func() {}, errors.New("multipart boundary missing")
		}
		mr, err := h.openMultipart(r, boundary)
		if err != nil {
			return nil, "", -1, func() {}, fmt.Errorf("multipart: %w", err)
		}
		return mr.body, mr.contentType, mr.size, mr.close, nil
	default:
		body := http.MaxBytesReader(nil, r.Body, h.maxUploadBytes)
		size := int64(-1)
		if cl := r.Header.Get("Content-Length"); cl != "" {
			if n, err := strconv.ParseInt(cl, 10, 64); err == nil {
				size = n
			}
		}
		return body, ct, size, func() {}, nil
	}
}

func (h *StorageHandlers) writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}

func (h *StorageHandlers) writeErr(w http.ResponseWriter, status int, rid, code, msg string, retryable bool) {
	h.writeJSON(w, status, &api.Response{
		Status: "error",
		Error:  &api.ErrInfo{Code: code, Message: msg, Retryable: retryable},
		Meta:   api.NowMeta(rid),
	})
}

