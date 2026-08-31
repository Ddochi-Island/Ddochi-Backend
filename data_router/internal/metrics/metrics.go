// Package metrics is a tiny, dependency-free counter/gauge registry
// surfaced as text/plain at /metrics. It's intentionally not Prometheus
// client_golang — keeps the dep footprint small. The output format is a
// subset of the Prometheus exposition format so a sidecar exporter can
// scrape it directly.
package metrics

import (
	"fmt"
	"sort"
	"strings"
	"sync"
	"sync/atomic"
)

type Counter struct{ v atomic.Int64 }

func (c *Counter) Add(delta int64) { c.v.Add(delta) }
func (c *Counter) Inc()            { c.v.Add(1) }
func (c *Counter) Get() int64      { return c.v.Load() }

type Gauge struct{ v atomic.Int64 }

func (g *Gauge) Set(v int64)       { g.v.Store(v) }
func (g *Gauge) Inc()              { g.v.Add(1) }
func (g *Gauge) Dec()              { g.v.Add(-1) }
func (g *Gauge) Get() int64        { return g.v.Load() }

// Registry holds the metrics we expose. Adding a metric is one line —
// initialize in New(), reference from call sites.
type Registry struct {
	mu sync.RWMutex

	// Request counters
	ReqTotal       *Counter
	ReqOK          *Counter
	ReqErr         *Counter
	ReqQueueFull   *Counter
	ReqTimeout     *Counter
	ReqBreakerOpen *Counter
	ReqCacheHit    *Counter
	ReqIdemHit     *Counter
	ReqCoalesced   *Counter

	// DB-level
	DBExecTotal *Counter
	DBExecErr   *Counter

	// Gauges (updated periodically by callers)
	QueueDepthHigh   *Gauge
	QueueDepthNormal *Gauge
	QueueDepthLow    *Gauge
	QueueOldestHigh  *Gauge
	QueueOldestNorm  *Gauge
	QueueOldestLow   *Gauge
	CacheSize        *Gauge
	IdemSize         *Gauge
	BreakerState     *Gauge // 0=closed,1=open,2=half-open
	DBHealthy        *Gauge // 0/1

	// Custom labelled counters keyed by caller — bounded by callers
	// reporting their identity (we cap distinct labels via the caller).
	caller   map[string]int64
	callerOK map[string]int64
}

func New() *Registry {
	return &Registry{
		ReqTotal:         &Counter{},
		ReqOK:            &Counter{},
		ReqErr:           &Counter{},
		ReqQueueFull:     &Counter{},
		ReqTimeout:       &Counter{},
		ReqBreakerOpen:   &Counter{},
		ReqCacheHit:      &Counter{},
		ReqIdemHit:       &Counter{},
		ReqCoalesced:     &Counter{},
		DBExecTotal:      &Counter{},
		DBExecErr:        &Counter{},
		QueueDepthHigh:   &Gauge{},
		QueueDepthNormal: &Gauge{},
		QueueDepthLow:    &Gauge{},
		QueueOldestHigh:  &Gauge{},
		QueueOldestNorm:  &Gauge{},
		QueueOldestLow:   &Gauge{},
		CacheSize:        &Gauge{},
		IdemSize:         &Gauge{},
		BreakerState:     &Gauge{},
		DBHealthy:        &Gauge{},
		caller:           make(map[string]int64),
		callerOK:         make(map[string]int64),
	}
}

func (r *Registry) ObserveCaller(name string, ok bool) {
	if name == "" {
		name = "_unknown"
	}
	r.mu.Lock()
	r.caller[name]++
	if ok {
		r.callerOK[name]++
	}
	// Bound cardinality. If somehow a caller starts emitting random
	// names, drop the smallest entries.
	if len(r.caller) > 256 {
		// best-effort: drop one arbitrary key with the smallest count
		var victim string
		var min int64 = -1
		for k, v := range r.caller {
			if min < 0 || v < min {
				min = v
				victim = k
			}
		}
		delete(r.caller, victim)
		delete(r.callerOK, victim)
	}
	r.mu.Unlock()
}

func (r *Registry) Render() string {
	r.mu.RLock()
	defer r.mu.RUnlock()

	var b strings.Builder
	emitCounter := func(name, help string, c *Counter) {
		fmt.Fprintf(&b, "# HELP %s %s\n# TYPE %s counter\n%s %d\n", name, help, name, name, c.Get())
	}
	emitGauge := func(name, help string, g *Gauge) {
		fmt.Fprintf(&b, "# HELP %s %s\n# TYPE %s gauge\n%s %d\n", name, help, name, name, g.Get())
	}

	emitCounter("data_router_requests_total", "Total requests received.", r.ReqTotal)
	emitCounter("data_router_requests_ok", "Successful requests.", r.ReqOK)
	emitCounter("data_router_requests_err", "Failed requests.", r.ReqErr)
	emitCounter("data_router_requests_queue_full", "Rejected: queue full.", r.ReqQueueFull)
	emitCounter("data_router_requests_timeout", "Failed: timeout.", r.ReqTimeout)
	emitCounter("data_router_requests_breaker_open", "Rejected: breaker open.", r.ReqBreakerOpen)
	emitCounter("data_router_requests_cache_hit", "Served from cache.", r.ReqCacheHit)
	emitCounter("data_router_requests_idem_hit", "Served from idempotency cache.", r.ReqIdemHit)
	emitCounter("data_router_requests_coalesced", "Served by riding on a singleflight leader.", r.ReqCoalesced)
	emitCounter("data_router_db_exec_total", "DB executions actually issued.", r.DBExecTotal)
	emitCounter("data_router_db_exec_err", "DB executions returning an error.", r.DBExecErr)

	emitGauge("data_router_queue_depth_high", "Tasks queued in high lane.", r.QueueDepthHigh)
	emitGauge("data_router_queue_depth_normal", "Tasks queued in normal lane.", r.QueueDepthNormal)
	emitGauge("data_router_queue_depth_low", "Tasks queued in low lane.", r.QueueDepthLow)
	emitGauge("data_router_queue_oldest_high_ms", "Oldest task age in high lane.", r.QueueOldestHigh)
	emitGauge("data_router_queue_oldest_normal_ms", "Oldest task age in normal lane.", r.QueueOldestNorm)
	emitGauge("data_router_queue_oldest_low_ms", "Oldest task age in low lane.", r.QueueOldestLow)
	emitGauge("data_router_cache_size", "Entries in TTL cache.", r.CacheSize)
	emitGauge("data_router_idem_size", "Entries in idempotency store.", r.IdemSize)
	emitGauge("data_router_breaker_state", "Breaker state (0=closed,1=open,2=half).", r.BreakerState)
	emitGauge("data_router_db_healthy", "1 if last health probe ok.", r.DBHealthy)

	// per-caller request totals (rendered after summary metrics for stability)
	keys := make([]string, 0, len(r.caller))
	for k := range r.caller {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	if len(keys) > 0 {
		fmt.Fprintln(&b, "# HELP data_router_caller_requests Total requests by caller.")
		fmt.Fprintln(&b, "# TYPE data_router_caller_requests counter")
		for _, k := range keys {
			fmt.Fprintf(&b, "data_router_caller_requests{caller=%q} %d\n", k, r.caller[k])
		}
		fmt.Fprintln(&b, "# HELP data_router_caller_requests_ok Successful requests by caller.")
		fmt.Fprintln(&b, "# TYPE data_router_caller_requests_ok counter")
		for _, k := range keys {
			fmt.Fprintf(&b, "data_router_caller_requests_ok{caller=%q} %d\n", k, r.callerOK[k])
		}
	}
	return b.String()
}
