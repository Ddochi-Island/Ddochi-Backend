// worker.go consumes Jobs from the Queue and performs the actual
// transfer to OCI Object Storage (or block, when the router decides).
//
// Concurrency: configurable, but defaults to 1 on e2-micro because
//   - Multiple parallel TLS handshakes burst CPU on a 2-vCPU shared box
//   - The 10 GiB OCI free tier is sized for sequential traffic; bursting
//     5 parallel uploads doesn't make the wall-clock faster, just spikier
//   - Sequential simplifies reasoning about per-caller fairness
package uploadq

import (
	"context"
	"errors"
	"os"
	"sync"

	"github.com/redesign2/services/data_router/internal/logx"
	"github.com/redesign2/services/data_router/internal/storage"
)

type Worker struct {
	q      *Queue
	router *storage.Router

	concurrency int
	wg          sync.WaitGroup
}

func NewWorker(q *Queue, router *storage.Router, concurrency int) *Worker {
	if concurrency < 1 {
		concurrency = 1
	}
	return &Worker{q: q, router: router, concurrency: concurrency}
}

// Start launches concurrency goroutines. Cancel ctx (or Close the
// queue) to stop them. Wait blocks until all exit.
func (w *Worker) Start(ctx context.Context) {
	for i := 0; i < w.concurrency; i++ {
		w.wg.Add(1)
		go w.run(ctx, i)
	}
}

func (w *Worker) Wait() { w.wg.Wait() }

func (w *Worker) run(ctx context.Context, id int) {
	defer w.wg.Done()
	log := logx.With("uploadq.worker", id)
	for {
		job, err := w.q.Pop(ctx)
		if err != nil {
			if errors.Is(err, ErrShutdown) || errors.Is(err, context.Canceled) {
				log.Info("uploadq.worker.exit", "reason", err.Error())
				return
			}
			continue
		}
		w.process(ctx, job)
	}
}

// process opens the spool file, hands it to the storage router, and
// records the terminal status. Spool deletion happens BEFORE the
// terminal mark so any HTTP handler waiting on Done() sees the file
// already gone (avoids a test-time race and matches the contract that
// "completed = the bytes are now in storage, the spool is reclaimed").
func (w *Worker) process(ctx context.Context, job *Job) {
	job.markProcessing()

	f, openErr := os.Open(job.SpoolPath)
	if openErr != nil {
		_ = removeIfExists(job.SpoolPath)
		job.markFailed(openErr)
		w.q.RecordTerminal(job)
		return
	}

	meta, putErr := w.router.Put(ctx, f, storage.PutOpts{
		ContentType: job.ContentType,
		Size:        job.Size,
		SHA256:      job.SHA256,
	})
	_ = f.Close()
	_ = removeIfExists(job.SpoolPath)

	if putErr != nil {
		job.markFailed(putErr)
	} else {
		job.markCompleted(meta)
	}
	w.q.RecordTerminal(job)
}

func removeIfExists(p string) error {
	if p == "" {
		return nil
	}
	err := os.Remove(p)
	if err != nil && !os.IsNotExist(err) {
		return err
	}
	return nil
}
