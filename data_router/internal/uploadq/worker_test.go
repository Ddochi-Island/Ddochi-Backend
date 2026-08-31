package uploadq

import (
	"context"
	"errors"
	"io"
	"os"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/redesign2/services/data_router/internal/api"
	"github.com/redesign2/services/data_router/internal/storage"
)

// fakeBackend records Put calls; useful for asserting the worker
// actually invoked storage with the expected SHA + size.
type fakeBackend struct {
	puts atomic.Int32
	last storage.PutOpts
}

func (f *fakeBackend) Name() string { return "fake" }
func (f *fakeBackend) Healthy(_ context.Context) bool { return true }
func (f *fakeBackend) UsageBytes(_ context.Context) (int64, error) { return 0, nil }
func (f *fakeBackend) Put(_ context.Context, body io.Reader, opts storage.PutOpts) (storage.ObjectMeta, error) {
	f.puts.Add(1)
	f.last = opts
	return storage.ObjectMeta{
		ID: "fake:k", Backend: "fake", Key: "k", Size: opts.Size, SHA256: opts.SHA256,
	}, nil
}
func (f *fakeBackend) Get(_ context.Context, _ string) (io.ReadCloser, storage.ObjectMeta, error) {
	return nil, storage.ObjectMeta{}, errors.New("unused")
}
func (f *fakeBackend) Head(_ context.Context, _ string) (storage.ObjectMeta, error) {
	return storage.ObjectMeta{}, errors.New("unused")
}
func (f *fakeBackend) Delete(_ context.Context, _ string) error { return nil }
func (f *fakeBackend) DownloadURL(_ context.Context, _ string, _ time.Duration) (string, time.Time, error) {
	return "", time.Time{}, nil
}

func TestWorkerProcessesQueueEndToEnd(t *testing.T) {
	q := New(10, 5, 10)
	be := &fakeBackend{}
	router := storage.NewRouter(be, nil, 1<<30)

	dir := t.TempDir()
	// Spool a real file so the worker has something to open.
	path, size, sha, err := Spool(context.Background(), strings.NewReader("payload"), dir, 1024)
	if err != nil {
		t.Fatal(err)
	}

	job := NewJob("j1", "tester", api.PriorityNormal, path, "text/plain", sha, size)
	if err := q.Push(job); err != nil {
		t.Fatal(err)
	}

	worker := NewWorker(q, router, 1)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	worker.Start(ctx)

	select {
	case <-job.Done():
	case <-time.After(2 * time.Second):
		t.Fatal("worker did not finish job")
	}
	snap := job.Snapshot()
	if snap.Status != StatusCompleted {
		t.Fatalf("status=%s err=%s", snap.Status, snap.ErrorMsg)
	}
	if be.puts.Load() != 1 {
		t.Fatalf("puts=%d", be.puts.Load())
	}
	if be.last.SHA256 != sha {
		t.Errorf("backend got sha %q, want %q", be.last.SHA256, sha)
	}
	if be.last.Size != size {
		t.Errorf("backend got size %d, want %d", be.last.Size, size)
	}
	// spool should be deleted
	if _, err := os.Stat(path); !os.IsNotExist(err) {
		t.Errorf("spool not deleted: err=%v", err)
	}

	cancel()
	worker.Wait()
}

func TestWorkerMarksFailedOnBackendError(t *testing.T) {
	q := New(10, 5, 10)
	be := &errBackend{}
	router := storage.NewRouter(be, nil, 1<<30)

	dir := t.TempDir()
	path, size, sha, _ := Spool(context.Background(), strings.NewReader("x"), dir, 1024)
	job := NewJob("j1", "tester", api.PriorityNormal, path, "text/plain", sha, size)
	_ = q.Push(job)

	worker := NewWorker(q, router, 1)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	worker.Start(ctx)

	select {
	case <-job.Done():
	case <-time.After(2 * time.Second):
		t.Fatal("worker did not finish job")
	}
	snap := job.Snapshot()
	if snap.Status != StatusFailed {
		t.Fatalf("status=%s, want failed", snap.Status)
	}
	if snap.ErrorMsg == "" {
		t.Error("expected error message")
	}
	cancel()
	worker.Wait()
}

type errBackend struct{ fakeBackend }

func (e *errBackend) Put(_ context.Context, _ io.Reader, _ storage.PutOpts) (storage.ObjectMeta, error) {
	return storage.ObjectMeta{}, errors.New("backend down")
}
