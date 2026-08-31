// Package uploadq decouples HTTP upload reception from the actual
// transfer to OCI Object Storage. The flow is:
//
//   HTTP body  ── stream ──▶  spool file on local disk
//                                 │
//                                 ▼
//                            priority queue (3 lanes, bounded)
//                                 │
//                                 ▼
//                            worker(s) — small N for e2-micro
//                                 │
//                                 ▼
//                            storage.Router.Put → OCI / block
//
// Why this exists, given the storage layer already works:
//
//   1. Memory pressure on e2-micro (1 GB RAM). Without a spool, every
//      in-flight 10 MB upload sits in RAM until the OCI PUT finishes.
//      With spool, only ~64 KB streaming buffer per upload + the small
//      Job struct.
//
//   2. Backpressure with priority. When 50 board uploads land at once,
//      we want high-priority ones to jump the queue and we want to
//      protect a slow OCI from receiving 50 parallel TLS handshakes.
//      Single-worker (default) processes one at a time; a small pool
//      can be configured if OCI pipeline depth becomes the bottleneck.
//
//   3. Observability for a future dashboard. Every upload becomes a
//      Job with a status, timing breakdown, and error message. The
//      dashboard tracks queue depth, recent throughput, per-caller
//      stats — none of which exist with sync upload.
//
// The Job struct is the unit of work; everything else in this package
// produces, schedules, or consumes Jobs.
package uploadq

import (
	"sync"
	"time"

	"github.com/redesign2/services/data_router/internal/api"
	"github.com/redesign2/services/data_router/internal/storage"
)

// JobStatus is the lifecycle of an upload job. Strings are stable —
// callers (dashboards, polling clients) match on these values.
type JobStatus string

const (
	StatusQueued     JobStatus = "queued"
	StatusProcessing JobStatus = "processing"
	StatusCompleted  JobStatus = "completed"
	StatusFailed     JobStatus = "failed"
	StatusShutdown   JobStatus = "shutdown" // queue closed before processing
)

// Job carries enough state for the worker to perform the upload AND
// for the dashboard to show what happened.
//
// Mutation rules:
//   - Created in StatusQueued by the HTTP handler (Push)
//   - Mutated to StatusProcessing by the worker (one-shot)
//   - Mutated to StatusCompleted/StatusFailed by the worker (one-shot)
//   - After terminal status, the worker calls close(done); waiters wake
//
// All field access goes through the mutex. Snapshot() returns a value
// copy safe to JSON-encode without races.
type Job struct {
	mu sync.Mutex

	// Identity / scheduling — set at creation, never mutated.
	ID       string       `json:"id"`
	Caller   string       `json:"caller"`
	Priority api.Priority `json:"priority"`

	// Upload artifact — set at creation, only the worker mutates
	// SpoolPath to "" after deletion.
	SpoolPath   string `json:"-"` // local path; intentionally not in JSON
	Size        int64  `json:"size"`
	ContentType string `json:"content_type,omitempty"`
	SHA256      string `json:"sha256,omitempty"`

	// Lifecycle
	Status      JobStatus `json:"status"`
	CreatedAt   time.Time `json:"created_at"`
	StartedAt   time.Time `json:"started_at,omitempty"`
	CompletedAt time.Time `json:"completed_at,omitempty"`

	// Result (terminal)
	Result   *storage.ObjectMeta `json:"result,omitempty"`
	ErrorMsg string              `json:"error,omitempty"`

	// done is closed exactly once when the job reaches a terminal status.
	// Callers waiting synchronously block on it.
	done chan struct{}
}

func newJob(id, caller string, priority api.Priority, spool, ct, sha string, size int64) *Job {
	if priority == "" {
		priority = api.PriorityNormal
	}
	return &Job{
		ID:          id,
		Caller:      caller,
		Priority:    priority,
		SpoolPath:   spool,
		Size:        size,
		ContentType: ct,
		SHA256:      sha,
		Status:      StatusQueued,
		CreatedAt:   time.Now().UTC(),
		done:        make(chan struct{}),
	}
}

// Done returns a channel closed when the job reaches a terminal status.
func (j *Job) Done() <-chan struct{} { return j.done }

// markProcessing flips status to StatusProcessing and stamps StartedAt.
// Called once by the worker just before invoking the storage backend.
func (j *Job) markProcessing() {
	j.mu.Lock()
	j.Status = StatusProcessing
	j.StartedAt = time.Now().UTC()
	j.mu.Unlock()
}

// markCompleted records the successful upload meta and closes done.
func (j *Job) markCompleted(meta storage.ObjectMeta) {
	j.mu.Lock()
	j.Status = StatusCompleted
	j.Result = &meta
	j.CompletedAt = time.Now().UTC()
	j.mu.Unlock()
	close(j.done)
}

// markFailed records the error and closes done. Called on any non-
// recoverable upload failure.
func (j *Job) markFailed(err error) {
	j.mu.Lock()
	j.Status = StatusFailed
	if err != nil {
		j.ErrorMsg = err.Error()
	}
	j.CompletedAt = time.Now().UTC()
	j.mu.Unlock()
	close(j.done)
}

// markShutdown is the variant for jobs drained at queue close.
func (j *Job) markShutdown() {
	j.mu.Lock()
	if j.Status == StatusQueued || j.Status == StatusProcessing {
		j.Status = StatusShutdown
		j.ErrorMsg = "queue closed before processing"
		j.CompletedAt = time.Now().UTC()
	}
	j.mu.Unlock()
	// Channel may already be closed if the worker raced to mark it; guard:
	defer func() { _ = recover() }()
	close(j.done)
}

// JobView is the serializable, mutex-free shape of a Job. Returned by
// Snapshot() so callers can JSON-encode without dragging the mutex
// through a value copy (which `go vet` rightly complains about).
type JobView struct {
	ID          string              `json:"id"`
	Caller      string              `json:"caller"`
	Priority    api.Priority        `json:"priority"`
	Size        int64               `json:"size"`
	ContentType string              `json:"content_type,omitempty"`
	SHA256      string              `json:"sha256,omitempty"`
	Status      JobStatus           `json:"status"`
	CreatedAt   time.Time           `json:"created_at"`
	StartedAt   time.Time           `json:"started_at,omitempty"`
	CompletedAt time.Time           `json:"completed_at,omitempty"`
	Result      *storage.ObjectMeta `json:"result,omitempty"`
	ErrorMsg    string              `json:"error,omitempty"`
	QueuedMs    int64               `json:"queued_ms"`
	TransferMs  int64               `json:"transfer_ms"`
}

// Snapshot returns a value copy of the job state, safe to serialize.
func (j *Job) Snapshot() JobView {
	j.mu.Lock()
	defer j.mu.Unlock()
	v := JobView{
		ID:          j.ID,
		Caller:      j.Caller,
		Priority:    j.Priority,
		Size:        j.Size,
		ContentType: j.ContentType,
		SHA256:      j.SHA256,
		Status:      j.Status,
		CreatedAt:   j.CreatedAt,
		StartedAt:   j.StartedAt,
		CompletedAt: j.CompletedAt,
		Result:      j.Result,
		ErrorMsg:    j.ErrorMsg,
	}
	if !j.StartedAt.IsZero() {
		v.QueuedMs = j.StartedAt.Sub(j.CreatedAt).Milliseconds()
	}
	if !j.StartedAt.IsZero() && !j.CompletedAt.IsZero() {
		v.TransferMs = j.CompletedAt.Sub(j.StartedAt).Milliseconds()
	}
	return v
}

