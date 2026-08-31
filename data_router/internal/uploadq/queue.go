// queue.go is a 3-lane priority queue for upload Jobs, plus an in-memory
// registry that supports both per-id lookup (`/v1/storage/jobs/{id}`)
// and a bounded ring buffer of recent terminals for the dashboard.
//
// Architecturally identical to internal/queue/priority_queue.go but the
// element type is *Job and there's no per-task deadline (uploads run
// to completion or shutdown, with no per-job timeout — that lives at
// the worker level if we ever need it).
//
// Concurrency model: one mutex protects everything. Push/Pop are O(1);
// the worker calls Pop in a loop and HTTP handlers call Push.
package uploadq

import (
	"context"
	"errors"
	"sync"
	"time"

	"github.com/redesign2/services/data_router/internal/api"
)

var (
	ErrQueueFull   = errors.New("uploadq: queue full")
	ErrCallerLimit = errors.New("uploadq: per-caller limit reached")
	ErrShutdown    = errors.New("uploadq: shutting down")
)

type Queue struct {
	mu   sync.Mutex
	cond *sync.Cond

	lanes [3]*deque

	perCaller map[string]int

	capacity     int
	perCallerCap int

	// jobs holds every Job we know about — queued, processing, or
	// recently terminal. Ring-buffer eviction below keeps it bounded.
	jobs map[string]*Job

	// recent is a fixed-size ring of terminal jobs for the dashboard.
	// Index recentIdx points to the next write slot.
	recent     []*Job
	recentSize int
	recentIdx  int

	// totals so the dashboard can show lifetime counters cheaply.
	pushed    uint64
	completed uint64
	failed    uint64

	closed bool
}

// New constructs a Queue with the given total capacity (across lanes),
// per-caller cap, and recent-terminals ring size.
func New(capacity, perCallerCap, recentSize int) *Queue {
	if recentSize < 1 {
		recentSize = 100
	}
	q := &Queue{
		lanes:        [3]*deque{newDeque(), newDeque(), newDeque()},
		perCaller:    make(map[string]int),
		capacity:     capacity,
		perCallerCap: perCallerCap,
		jobs:         make(map[string]*Job, 256),
		recent:       make([]*Job, recentSize),
		recentSize:   recentSize,
	}
	q.cond = sync.NewCond(&q.mu)
	return q
}

// NewJob exposes the Job constructor without leaking it from the
// package. Returns a job in StatusQueued, ready for Push.
func NewJob(id, caller string, priority api.Priority, spool, contentType, sha string, size int64) *Job {
	return newJob(id, caller, priority, spool, contentType, sha, size)
}

// Push enqueues job. Rejects with ErrQueueFull when total queued >=
// capacity, or ErrCallerLimit when the caller's queued count >=
// perCallerCap. Both protect us from a runaway uploader monopolizing
// the worker.
func (q *Queue) Push(job *Job) error {
	q.mu.Lock()
	defer q.mu.Unlock()
	if q.closed {
		return ErrShutdown
	}
	if q.totalQueuedLocked() >= q.capacity {
		return ErrQueueFull
	}
	if q.perCaller[job.Caller] >= q.perCallerCap {
		return ErrCallerLimit
	}
	idx := laneIndex(job.Priority)
	q.lanes[idx].pushBack(job)
	q.perCaller[job.Caller]++
	q.jobs[job.ID] = job
	q.pushed++
	q.cond.Signal()
	return nil
}

// Pop blocks until a job is available or ctx is cancelled. Returns
// (nil, ErrShutdown) after Close. Per-caller counters decrement here.
func (q *Queue) Pop(ctx context.Context) (*Job, error) {
	q.mu.Lock()
	defer q.mu.Unlock()

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
			return nil, ErrShutdown
		}
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		for laneIdx := 0; laneIdx < 3; laneIdx++ {
			d := q.lanes[laneIdx]
			if d.len > 0 {
				job := d.popFront()
				q.perCaller[job.Caller]--
				if q.perCaller[job.Caller] <= 0 {
					delete(q.perCaller, job.Caller)
				}
				return job, nil
			}
		}
		q.cond.Wait()
	}
}

// RecordTerminal moves job into the recent-ring and updates lifetime
// counters. Worker calls this after marking the job completed/failed.
func (q *Queue) RecordTerminal(job *Job) {
	q.mu.Lock()
	defer q.mu.Unlock()

	// Evict the slot we're about to overwrite from the per-id registry,
	// unless that slot still holds a non-terminal job (shouldn't happen,
	// but be defensive).
	if old := q.recent[q.recentIdx]; old != nil {
		if old.Status == StatusCompleted || old.Status == StatusFailed || old.Status == StatusShutdown {
			delete(q.jobs, old.ID)
		}
	}
	q.recent[q.recentIdx] = job
	q.recentIdx = (q.recentIdx + 1) % q.recentSize

	switch job.Status {
	case StatusCompleted:
		q.completed++
	case StatusFailed, StatusShutdown:
		q.failed++
	}
}

// Get returns the Job with the given id, or nil if unknown / evicted.
func (q *Queue) Get(id string) *Job {
	q.mu.Lock()
	defer q.mu.Unlock()
	return q.jobs[id]
}

// Close drains pending jobs (each gets markShutdown so HTTP waiters
// unblock with a "shutdown" status) and rejects further Push calls.
func (q *Queue) Close() {
	q.mu.Lock()
	q.closed = true
	q.cond.Broadcast()
	for _, d := range q.lanes {
		for d.len > 0 {
			job := d.popFront()
			job.markShutdown()
			q.recent[q.recentIdx] = job
			q.recentIdx = (q.recentIdx + 1) % q.recentSize
			q.failed++
		}
	}
	q.mu.Unlock()
}

// ─── stats ─────────────────────────────────────────────────────────

type Stats struct {
	LaneSizes       [3]int
	OldestLagMs     [3]int64
	Total           int
	DistinctCallers int
	Capacity        int
	PerCallerCap    int
	Pushed          uint64
	Completed       uint64
	Failed          uint64
}

// Stats returns a coherent snapshot for /v1/storage/queue.
func (q *Queue) Stats() Stats {
	q.mu.Lock()
	defer q.mu.Unlock()
	now := time.Now()
	s := Stats{
		Capacity:        q.capacity,
		PerCallerCap:    q.perCallerCap,
		DistinctCallers: len(q.perCaller),
		Pushed:          q.pushed,
		Completed:       q.completed,
		Failed:          q.failed,
	}
	for i := 0; i < 3; i++ {
		s.LaneSizes[i] = q.lanes[i].len
		s.Total += q.lanes[i].len
		if h := q.lanes[i].peekFront(); h != nil {
			s.OldestLagMs[i] = now.Sub(h.CreatedAt).Milliseconds()
		}
	}
	return s
}

// RecentSnapshot returns up to N terminal jobs newest-first. JSON-safe
// view structs; never holds the queue lock past the copy.
func (q *Queue) RecentSnapshot(limit int) []JobView {
	q.mu.Lock()
	defer q.mu.Unlock()
	if limit <= 0 || limit > q.recentSize {
		limit = q.recentSize
	}
	out := make([]JobView, 0, limit)
	idx := (q.recentIdx - 1 + q.recentSize) % q.recentSize
	for i := 0; i < q.recentSize && len(out) < limit; i++ {
		if j := q.recent[idx]; j != nil {
			out = append(out, j.Snapshot())
		}
		idx = (idx - 1 + q.recentSize) % q.recentSize
	}
	return out
}

// ActiveSnapshot returns currently-queued + currently-processing jobs.
// Useful for the dashboard's "in flight" panel.
func (q *Queue) ActiveSnapshot() []JobView {
	q.mu.Lock()
	jobs := make([]*Job, 0, len(q.jobs))
	for _, j := range q.jobs {
		jobs = append(jobs, j)
	}
	q.mu.Unlock()
	out := make([]JobView, 0, len(jobs))
	for _, j := range jobs {
		v := j.Snapshot()
		if v.Status == StatusQueued || v.Status == StatusProcessing {
			out = append(out, v)
		}
	}
	return out
}

// ─── helpers ──────────────────────────────────────────────────────

func (q *Queue) totalQueuedLocked() int {
	return q.lanes[0].len + q.lanes[1].len + q.lanes[2].len
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

// minimal singly-linked deque
type dnode struct {
	job  *Job
	next *dnode
}

type deque struct {
	head, tail *dnode
	len        int
}

func newDeque() *deque { return &deque{} }

func (d *deque) pushBack(j *Job) {
	n := &dnode{job: j}
	if d.tail == nil {
		d.head = n
		d.tail = n
	} else {
		d.tail.next = n
		d.tail = n
	}
	d.len++
}

func (d *deque) popFront() *Job {
	if d.head == nil {
		return nil
	}
	n := d.head
	d.head = n.next
	if d.head == nil {
		d.tail = nil
	}
	d.len--
	return n.job
}

func (d *deque) peekFront() *Job {
	if d.head == nil {
		return nil
	}
	return d.head.job
}
