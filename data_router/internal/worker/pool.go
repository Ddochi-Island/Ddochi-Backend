// Package worker is the consumer side of the priority queue.
//
// One Pool runs N goroutines, each in a Pop→execute loop. Workers are
// the only goroutines that talk to the DB executor; everything else
// (HTTP handlers, callers) only enqueues. This keeps DB concurrency
// strictly bounded by Worker.Concurrency, which we configure to match
// the DB connection pool size.
//
// The worker performs the following dance on each task:
//
//   1. Check the circuit breaker. If open, fail fast.
//   2. For OpQuery with CacheTTL > 0: try the TTL cache + singleflight.
//      Cache hit / coalesce → no DB call; the Run() leader pays the cost.
//   3. For writes with IdempotencyKey: ask the idem store; if a previous
//      response is cached, return it; if another caller is in flight,
//      block on its completion.
//   4. Run the executor with a deadline derived from the task's overall
//      deadline.
//   5. Report success/failure to the breaker (only for infra errors) and
//      publish to the task's Result channel.
package worker

import (
	"context"
	"encoding/json"
	"errors"
	"sync"
	"time"

	"github.com/redesign2/services/data_router/internal/api"
	"github.com/redesign2/services/data_router/internal/breaker"
	"github.com/redesign2/services/data_router/internal/cache"
	"github.com/redesign2/services/data_router/internal/db"
	"github.com/redesign2/services/data_router/internal/idem"
	"github.com/redesign2/services/data_router/internal/logx"
	"github.com/redesign2/services/data_router/internal/metrics"
	"github.com/redesign2/services/data_router/internal/queue"
)

type Pool struct {
	q       *queue.PriorityQueue
	exec    *db.Executor
	cache   *cache.Cache
	idem    *idem.Store
	breaker *breaker.Breaker
	metrics *metrics.Registry

	concurrency int
	wg          sync.WaitGroup
}

func NewPool(
	q *queue.PriorityQueue,
	exec *db.Executor,
	c *cache.Cache,
	i *idem.Store,
	br *breaker.Breaker,
	m *metrics.Registry,
	concurrency int,
) *Pool {
	return &Pool{
		q: q, exec: exec, cache: c, idem: i, breaker: br, metrics: m,
		concurrency: concurrency,
	}
}

// Start launches workers. Returns immediately; cancel ctx (or Close the
// queue) to stop them. Wait() blocks until all workers exit.
func (p *Pool) Start(ctx context.Context) {
	for i := 0; i < p.concurrency; i++ {
		p.wg.Add(1)
		go p.run(ctx, i)
	}
}

func (p *Pool) Wait() { p.wg.Wait() }

func (p *Pool) run(ctx context.Context, id int) {
	defer p.wg.Done()
	log := logx.With("worker", id)
	for {
		t, err := p.q.Pop(ctx)
		if err != nil {
			if errors.Is(err, queue.ErrShuttingDown) || errors.Is(err, context.Canceled) {
				log.Info("worker.exit", "reason", err.Error())
				return
			}
			// Transient — keep looping
			continue
		}
		p.handle(t)
	}
}

func (p *Pool) handle(t *queue.Task) {
	queuedMs := time.Since(t.EnqueuedAt).Milliseconds()
	lane := string(t.Priority)
	if lane == "" {
		lane = string(api.PriorityNormal)
	}

	// Build the execution context. If the task already has a context
	// (from the HTTP handler) we honor its deadline; otherwise we cap
	// at the deadline we stamped at enqueue time.
	ctx := t.Ctx
	if ctx == nil {
		ctx = context.Background()
	}
	if !t.Deadline.IsZero() {
		c, cancel := context.WithDeadline(ctx, t.Deadline)
		defer cancel()
		ctx = c
	}

	// Breaker gate.
	if !p.breaker.Allow() {
		p.metrics.ReqBreakerOpen.Inc()
		p.publish(t, &api.Response{
			Status: "error",
			Error: &api.ErrInfo{
				Code: api.CodeBreakerOpen,
				Message: "database circuit breaker is open; retry shortly",
				Retryable: true,
			},
			Meta: api.Meta{QueuedMs: queuedMs, Lane: lane},
		}, nil)
		return
	}

	// Read-cache + singleflight path.
	if t.Req.Op == api.OpQuery && t.Req.CacheTTLMs > 0 && t.Req.Stmt != nil {
		ttl := time.Duration(t.Req.CacheTTLMs) * time.Millisecond
		key := cache.Key(string(t.Req.Op), t.Req.Stmt.SQL, t.Req.Stmt.Args)
		if cached, ok := p.cache.Get(key); ok {
			p.metrics.ReqCacheHit.Inc()
			p.deliverCached(t, cached, queuedMs, lane, true, false)
			p.breaker.Report(true) // not an actual call but breaker should treat this as healthy traffic
			return
		}
		// Singleflight: a single goroutine actually runs the DB call.
		// `coalesced=true` means at least one other caller rode on the
		// same response (might include us if we were the executor and
		// followers joined while we ran).
		bytes, coalesced, err := p.cache.Do(key, func() ([]byte, time.Duration, error) {
			resp, infra := p.exec.Run(ctx, t.Req)
			p.afterExec(infra, resp)
			b, err := json.Marshal(resp)
			if err != nil {
				return nil, 0, err
			}
			if resp.Status != "ok" {
				return b, 0, nil // negative result not cached; signal via ttl=0
			}
			return b, ttl, nil
		})
		if err != nil {
			p.publishErr(t, api.CodeInternal, err.Error(), false, queuedMs, lane)
			return
		}
		p.deliverCached(t, bytes, queuedMs, lane, false, coalesced)
		return
	}

	// Idempotency path for writes.
	if isWrite(t.Req.Op) && t.Req.IdempotencyKey != "" {
		cached, isLeader, wait := p.idem.Begin(t.Req.Caller, t.Req.IdempotencyKey)
		if cached != nil {
			p.metrics.ReqIdemHit.Inc()
			p.deliverCached(t, cached, queuedMs, lane, false, false)
			p.breaker.Report(true)
			return
		}
		if !isLeader && wait != nil {
			resp := wait()
			if resp != nil {
				p.metrics.ReqIdemHit.Inc()
				p.deliverCached(t, resp, queuedMs, lane, false, true)
				p.breaker.Report(true)
				return
			}
			// Leader aborted; fall through and execute fresh.
		}
		// Leader path
		resp, infra := p.exec.Run(ctx, t.Req)
		p.afterExec(infra, resp)
		b, _ := json.Marshal(resp)
		if resp.Status == "ok" {
			p.idem.Complete(t.Req.Caller, t.Req.IdempotencyKey, b)
		} else {
			p.idem.Abort(t.Req.Caller, t.Req.IdempotencyKey)
		}
		p.publish(t, resp, &api.Meta{QueuedMs: queuedMs, Lane: lane})
		return
	}

	// Plain path
	resp, infra := p.exec.Run(ctx, t.Req)
	p.afterExec(infra, resp)
	p.publish(t, resp, &api.Meta{QueuedMs: queuedMs, Lane: lane})
}

func (p *Pool) afterExec(infra bool, resp *api.Response) {
	p.metrics.DBExecTotal.Inc()
	if resp.Status != "ok" {
		p.metrics.DBExecErr.Inc()
	}
	p.breaker.Report(resp.Status == "ok" && !infra)
}

func (p *Pool) deliverCached(t *queue.Task, raw []byte, queuedMs int64, lane string, cacheHit bool, coalesced bool) {
	var resp api.Response
	if err := json.Unmarshal(raw, &resp); err != nil {
		p.publishErr(t, api.CodeInternal, "decode cached: "+err.Error(), false, queuedMs, lane)
		return
	}
	// Always overwrite RequestID — followers riding on the singleflight
	// leader otherwise inherit the leader's request_id, which breaks
	// caller-side log correlation.
	resp.Meta.RequestID = t.ID
	resp.Meta.QueuedMs = queuedMs
	resp.Meta.Lane = lane
	resp.Meta.CacheHit = cacheHit
	resp.Meta.Coalesced = coalesced
	resp.Meta.ServerTime = time.Now().UTC().Format(time.RFC3339Nano)
	if coalesced {
		p.metrics.ReqCoalesced.Inc()
	}
	t.Result <- queue.TaskResult{Resp: &resp}
}

func (p *Pool) publish(t *queue.Task, resp *api.Response, meta *api.Meta) {
	if resp.Meta.RequestID == "" {
		resp.Meta = api.NowMeta(t.ID)
	}
	if meta != nil {
		resp.Meta.QueuedMs = meta.QueuedMs
		resp.Meta.Lane = meta.Lane
	}
	t.Result <- queue.TaskResult{Resp: resp}
}

func (p *Pool) publishErr(t *queue.Task, code, msg string, retryable bool, queuedMs int64, lane string) {
	resp := &api.Response{
		Status: "error",
		Error:  &api.ErrInfo{Code: code, Message: msg, Retryable: retryable},
		Meta:   api.Meta{QueuedMs: queuedMs, Lane: lane},
	}
	p.publish(t, resp, nil)
}

func isWrite(op api.Op) bool {
	switch op {
	case api.OpExec, api.OpTx, api.OpProc:
		return true
	}
	return false
}
