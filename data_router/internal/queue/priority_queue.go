// Package queue implements the 3-lane priority queue that sits between the
// HTTP layer and the DB workers.
//
// Goals (in order of importance):
//
//   1. Stability — bounded total size, lane reservations so a flood of low/
//      normal traffic can never starve high. Backpressure surfaces as a
//      "queue_full" rejection, not as unbounded memory growth or latency.
//
//   2. Fairness — within a lane, FIFO across callers, but a per-caller cap
//      stops one noisy caller from monopolizing a lane. Combined with
//      reservations, this means: high traffic for caller A doesn't push
//      out caller B's normal-priority work.
//
//   3. Speed — push and pop are O(1) (linked-list deque per lane); no
//      heap, no per-item locks. One mutex protects the whole structure;
//      contention is bounded because workers wait on a condvar, not a
//      hot-spin loop.
//
// The queue is unaware of the DB; tasks carry a result channel that the
// worker writes to after execution. Callers wait on that channel (with
// a context for cancellation/timeout).
package queue

import (
	"context"
	"errors"
	"sync"
	"time"

	"github.com/redesign2/services/data_router/internal/api"
)

var (
	ErrQueueFull    = errors.New("queue: full")
	ErrCallerLimit  = errors.New("queue: per-caller limit reached")
	ErrShuttingDown = errors.New("queue: shutting down")
)

// Task is what a worker pops and executes. The HTTP handler builds it,
// pushes it, then blocks on Result.
type Task struct {
	ID           string
	Caller       string
	Priority     api.Priority
	EnqueuedAt   time.Time
	Deadline     time.Time
	Req          *api.Request
	Result       chan TaskResult // buffered (1) so the worker never blocks publishing
	Ctx          context.Context // canceled when caller bails out (HTTP disconnect / timeout)
}

type TaskResult struct {
	Resp *api.Response
	Err  error
}

// PriorityQueue is the 3-lane bounded queue.
type PriorityQueue struct {
	mu       sync.Mutex
	cond     *sync.Cond
	lanes    [3]*deque // [high, normal, low]
	laneRR   [3]map[string]int // per-caller counts, used for the per-lane fairness scan

	totalCount   int
	perCaller    map[string]int

	cap          int
	highRes      int  // reserved slots for high
	normalRes    int  // reserved slots for normal (and high may also use)
	perCallerCap int

	closed bool
}

func New(capacity, highReserved, normalReserved, perCallerCap int) *PriorityQueue {
	q := &PriorityQueue{
		lanes: [3]*deque{newDeque(), newDeque(), newDeque()},
		laneRR: [3]map[string]int{
			make(map[string]int), make(map[string]int), make(map[string]int),
		},
		perCaller:    make(map[string]int),
		cap:          capacity,
		highRes:      highReserved,
		normalRes:    normalReserved,
		perCallerCap: perCallerCap,
	}
	q.cond = sync.NewCond(&q.mu)
	return q
}

// Push admits a task or returns an error explaining the rejection.
//
// Admission control:
//   - low: only if total < (cap - highRes - normalRes)
//   - normal: only if total < (cap - highRes)
//   - high: only if total < cap
// This guarantees space for higher-priority work even when lower lanes
// are jammed. Within those caps, per-caller cap prevents one caller from
// taking over a lane.
func (q *PriorityQueue) Push(t *Task) error {
	q.mu.Lock()
	defer q.mu.Unlock()
	if q.closed {
		return ErrShuttingDown
	}
	if !q.admit(t.Priority) {
		return ErrQueueFull
	}
	if q.perCaller[t.Caller] >= q.perCallerCap {
		return ErrCallerLimit
	}
	idx := laneIndex(t.Priority)
	q.lanes[idx].pushBack(t)
	q.laneRR[idx][t.Caller]++
	q.perCaller[t.Caller]++
	q.totalCount++
	q.cond.Signal()
	return nil
}

// Pop blocks until a task is available or ctx is done. Returns (nil, ctx.Err())
// on cancellation; returns (nil, ErrShuttingDown) after Close.
//
// Pop expires deadlines lazily — when it walks a lane it drops tasks whose
// Deadline has passed and signals the caller via the task's Result channel
// with a timeout error. This avoids a separate sweeper goroutine.
func (q *PriorityQueue) Pop(ctx context.Context) (*Task, error) {
	q.mu.Lock()
	defer q.mu.Unlock()

	// Wake-on-cancel: spawn a watcher that signals once when ctx is done.
	// Allocates a goroutine per blocked Pop, but Pop is only called by
	// long-lived worker goroutines so this is bounded by Worker.Concurrency.
	stop := make(chan struct{})
	go func() {
		select {
		case <-ctx.Done():
			q.mu.Lock()
			q.cond.Broadcast()
			q.mu.Unlock()
		case <-stop:
		}
	}()
	defer close(stop)

	for {
		if q.closed {
			return nil, ErrShuttingDown
		}
		if err := ctx.Err(); err != nil {
			return nil, err
		}

		now := time.Now()
		for laneIdx := 0; laneIdx < 3; laneIdx++ {
			if t := q.popEligible(laneIdx, now); t != nil {
				return t, nil
			}
		}

		q.cond.Wait()
	}
}

// popEligible removes the oldest non-expired task from lane laneIdx.
// Expired tasks are flushed out with timeout responses as it scans.
func (q *PriorityQueue) popEligible(laneIdx int, now time.Time) *Task {
	d := q.lanes[laneIdx]
	for d.len > 0 {
		t := d.popFront()
		q.laneRR[laneIdx][t.Caller]--
		if q.laneRR[laneIdx][t.Caller] <= 0 {
			delete(q.laneRR[laneIdx], t.Caller)
		}
		q.perCaller[t.Caller]--
		if q.perCaller[t.Caller] <= 0 {
			delete(q.perCaller, t.Caller)
		}
		q.totalCount--

		if !t.Deadline.IsZero() && now.After(t.Deadline) {
			// expired in queue — fail the caller and keep scanning
			t.publish(TaskResult{Err: ctxDeadlineExceeded})
			continue
		}
		if t.Ctx != nil && t.Ctx.Err() != nil {
			// caller already gave up; drop silently
			continue
		}
		return t
	}
	return nil
}

func (q *PriorityQueue) Close() {
	q.mu.Lock()
	q.closed = true
	q.cond.Broadcast()
	// Drain & fail the remaining tasks so callers don't hang.
	for laneIdx := 0; laneIdx < 3; laneIdx++ {
		d := q.lanes[laneIdx]
		for d.len > 0 {
			t := d.popFront()
			t.publish(TaskResult{Err: ErrShuttingDown})
		}
	}
	q.mu.Unlock()
}

// Stats is a snapshot for /metrics and /healthz.
type Stats struct {
	High, Normal, Low int
	Total             int
	OldestLagMs       [3]int64
	Callers           int
}

func (q *PriorityQueue) Stats() Stats {
	q.mu.Lock()
	defer q.mu.Unlock()
	now := time.Now()
	s := Stats{
		High:    q.lanes[0].len,
		Normal:  q.lanes[1].len,
		Low:     q.lanes[2].len,
		Total:   q.totalCount,
		Callers: len(q.perCaller),
	}
	for i := 0; i < 3; i++ {
		if h := q.lanes[i].peekFront(); h != nil {
			s.OldestLagMs[i] = now.Sub(h.EnqueuedAt).Milliseconds()
		}
	}
	return s
}

func (q *PriorityQueue) admit(p api.Priority) bool {
	low := q.cap - q.highRes - q.normalRes
	switch p {
	case api.PriorityHigh:
		return q.totalCount < q.cap
	case api.PriorityNormal, "":
		return q.totalCount < q.cap-q.highRes
	case api.PriorityLow:
		return q.totalCount < low
	default:
		return q.totalCount < q.cap-q.highRes // unknown → treat as normal
	}
}

func laneIndex(p api.Priority) int {
	switch p {
	case api.PriorityHigh:
		return 0
	case api.PriorityLow:
		return 2
	default:
		return 1
	}
}

func (t *Task) publish(r TaskResult) {
	// Result is buffered(1); never blocks. If somehow the receiver isn't
	// listening (e.g. handler returned), the send still succeeds and the
	// channel is GC'd.
	select {
	case t.Result <- r:
	default:
	}
}

// Sentinel error so callers / handlers can map back to api.CodeTimeout
// without importing context. Re-exported as queue.ErrDeadlineExceeded.
var ctxDeadlineExceeded = context.DeadlineExceeded
var ErrDeadlineExceeded = context.DeadlineExceeded

// ───────────────────── deque (singly-linked, FIFO) ─────────────────────

type dnode struct {
	t    *Task
	next *dnode
}

type deque struct {
	head, tail *dnode
	len        int
}

func newDeque() *deque { return &deque{} }

func (d *deque) pushBack(t *Task) {
	n := &dnode{t: t}
	if d.tail == nil {
		d.head = n
		d.tail = n
	} else {
		d.tail.next = n
		d.tail = n
	}
	d.len++
}

func (d *deque) popFront() *Task {
	if d.head == nil {
		return nil
	}
	n := d.head
	d.head = n.next
	if d.head == nil {
		d.tail = nil
	}
	d.len--
	return n.t
}

func (d *deque) peekFront() *Task {
	if d.head == nil {
		return nil
	}
	return d.head.t
}
