package storage

import (
	"context"
	"errors"
	"io"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

// fakeBackend is an in-memory test double used to drive Router selection
// logic without standing up real storage.
type fakeBackend struct {
	name    string
	usage   atomic.Int64
	healthy bool
	puts    atomic.Int32
}

func (f *fakeBackend) Name() string { return f.name }
func (f *fakeBackend) Healthy(_ context.Context) bool { return f.healthy }
func (f *fakeBackend) UsageBytes(_ context.Context) (int64, error) { return f.usage.Load(), nil }
func (f *fakeBackend) Put(_ context.Context, body io.Reader, opts PutOpts) (ObjectMeta, error) {
	b, _ := io.ReadAll(body)
	f.usage.Add(int64(len(b)))
	f.puts.Add(1)
	return ObjectMeta{ID: f.name + ":k", Backend: f.name, Key: "k", Size: int64(len(b))}, nil
}
func (f *fakeBackend) Get(_ context.Context, _ string) (io.ReadCloser, ObjectMeta, error) {
	return nil, ObjectMeta{}, errors.New("unused")
}
func (f *fakeBackend) Head(_ context.Context, _ string) (ObjectMeta, error) {
	return ObjectMeta{}, errors.New("unused")
}
func (f *fakeBackend) Delete(_ context.Context, _ string) error { return nil }
func (f *fakeBackend) DownloadURL(_ context.Context, _ string, _ time.Duration) (string, time.Time, error) {
	return "", time.Time{}, nil
}

func TestRouterPicksPrimaryBelowThreshold(t *testing.T) {
	primary := &fakeBackend{name: BackendOCI, healthy: true}
	primary.usage.Store(1 * 1024 * 1024 * 1024) // 1 GiB
	fb := &fakeBackend{name: BackendBlock, healthy: true}
	r := NewRouter(primary, fb, 8*1024*1024*1024) // 8 GiB threshold

	got := r.Pick(context.Background(), 10*1024*1024)
	if got.Name() != BackendOCI {
		t.Errorf("got %s, want primary", got.Name())
	}
}

func TestRouterFallsBackAtOrAboveThreshold(t *testing.T) {
	primary := &fakeBackend{name: BackendOCI, healthy: true}
	primary.usage.Store(8 * 1024 * 1024 * 1024) // exactly at threshold
	fb := &fakeBackend{name: BackendBlock, healthy: true}
	r := NewRouter(primary, fb, 8*1024*1024*1024)

	got := r.Pick(context.Background(), 0)
	if got.Name() != BackendBlock {
		t.Errorf("got %s, want fallback", got.Name())
	}
}

func TestRouterFallsBackWhenExpectedSizeWouldOverflow(t *testing.T) {
	primary := &fakeBackend{name: BackendOCI, healthy: true}
	primary.usage.Store(7*1024*1024*1024 + 900*1024*1024) // 7.9 GiB
	fb := &fakeBackend{name: BackendBlock, healthy: true}
	r := NewRouter(primary, fb, 8*1024*1024*1024)

	// 200 MiB upload would push past 8 GiB → fallback
	got := r.Pick(context.Background(), 200*1024*1024)
	if got.Name() != BackendBlock {
		t.Errorf("got %s, want fallback", got.Name())
	}
}

func TestRouterUsageReportNextUploadGoesTo(t *testing.T) {
	primary := &fakeBackend{name: BackendOCI, healthy: true}
	primary.usage.Store(2 * 1024 * 1024 * 1024)
	fb := &fakeBackend{name: BackendBlock, healthy: true}
	r := NewRouter(primary, fb, 8*1024*1024*1024)
	rep := r.Usage(context.Background())
	if rep.NextUploadGoesTo != BackendOCI {
		t.Errorf("got %s", rep.NextUploadGoesTo)
	}
	if rep.PrimaryUsedBytes != 2*1024*1024*1024 {
		t.Errorf("primary used %d", rep.PrimaryUsedBytes)
	}
}

func TestRouterPutGoesThroughPicked(t *testing.T) {
	primary := &fakeBackend{name: BackendOCI, healthy: true}
	fb := &fakeBackend{name: BackendBlock, healthy: true}
	primary.usage.Store(0)
	r := NewRouter(primary, fb, 1024)

	// small upload — primary
	_, err := r.Put(context.Background(), strings.NewReader("hello"), PutOpts{Size: 5})
	if err != nil {
		t.Fatal(err)
	}
	if primary.puts.Load() != 1 || fb.puts.Load() != 0 {
		t.Errorf("primary=%d fb=%d", primary.puts.Load(), fb.puts.Load())
	}

	// crank usage above threshold → next goes to fallback
	primary.usage.Store(2048)
	_, err = r.Put(context.Background(), strings.NewReader("hi"), PutOpts{Size: 2})
	if err != nil {
		t.Fatal(err)
	}
	if fb.puts.Load() != 1 {
		t.Errorf("fb expected 1, got %d", fb.puts.Load())
	}
}

func TestRouterResolveDecodesIDs(t *testing.T) {
	primary := &fakeBackend{name: BackendOCI, healthy: true}
	fb := &fakeBackend{name: BackendBlock, healthy: true}
	r := NewRouter(primary, fb, 1<<30)

	if be, key, err := r.Resolve("o:bucket/path/to/file.png"); err != nil {
		t.Errorf("oci: %v", err)
	} else if be.Name() != BackendOCI || key != "path/to/file.png" {
		t.Errorf("oci resolve: be=%s key=%s", be.Name(), key)
	}
	if be, key, err := r.Resolve("b:ab/uuid.png"); err != nil {
		t.Errorf("block: %v", err)
	} else if be.Name() != BackendBlock || key != "ab/uuid.png" {
		t.Errorf("block resolve: be=%s key=%s", be.Name(), key)
	}
	if _, _, err := r.Resolve("garbage"); err == nil {
		t.Error("garbage should fail")
	}
}
