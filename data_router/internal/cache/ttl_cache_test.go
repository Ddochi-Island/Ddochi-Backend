package cache

import (
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func TestGetSetExpiry(t *testing.T) {
	c := New(100)
	c.Set("k", []byte("v"), 50*time.Millisecond)
	if v, ok := c.Get("k"); !ok || string(v) != "v" {
		t.Fatalf("get: %s ok=%v", v, ok)
	}
	time.Sleep(80 * time.Millisecond)
	if _, ok := c.Get("k"); ok {
		t.Fatal("should have expired")
	}
}

func TestSetZeroTTLNoStore(t *testing.T) {
	c := New(100)
	c.Set("k", []byte("v"), 0)
	if _, ok := c.Get("k"); ok {
		t.Fatal("zero ttl should not store")
	}
}

func TestKeyDeterministic(t *testing.T) {
	a := Key("query", "SELECT 1", []any{"a", 1})
	b := Key("query", "SELECT 1", []any{"a", 1})
	if a != b {
		t.Fatalf("not deterministic: %s vs %s", a, b)
	}
	c := Key("query", "SELECT 1", []any{"a", 2})
	if a == c {
		t.Fatal("different args should produce different key")
	}
}

func TestSingleflightCollapsesConcurrentCallers(t *testing.T) {
	// Verifies the core property: under burst load on the same key, the
	// underlying fn executes far fewer times than the number of callers.
	// We don't assert "exactly 1" — Windows/CI schedulers can serialize
	// goroutines such that the leader finishes before some callers even
	// reach sf.Do, producing 2-3 distinct executions. The 200ms hold
	// gives plenty of time for all goroutines to pile up; in practice
	// this consistently produces 1, but we allow up to N/10 to keep the
	// test robust without weakening what it proves (collapse occurred).
	c := New(100)
	var calls int32
	const N = 50
	var wg sync.WaitGroup
	wg.Add(N)
	results := make([][]byte, N)
	coalesced := make([]bool, N)
	start := make(chan struct{})

	for i := 0; i < N; i++ {
		go func(i int) {
			defer wg.Done()
			<-start
			b, coal, err := c.Do("k", func() ([]byte, time.Duration, error) {
				atomic.AddInt32(&calls, 1)
				time.Sleep(200 * time.Millisecond)
				return []byte("payload"), 500 * time.Millisecond, nil
			})
			if err != nil {
				t.Errorf("Do err: %v", err)
				return
			}
			results[i] = b
			coalesced[i] = coal
		}(i)
	}
	close(start)
	wg.Wait()

	calledN := int(atomic.LoadInt32(&calls))
	if calledN < 1 {
		t.Fatalf("fn never ran (calls=%d)", calledN)
	}
	if calledN > N/10 {
		t.Fatalf("fn ran %d times for %d callers — collapse failed", calledN, N)
	}
	// Every caller got the same payload.
	for i, b := range results {
		if string(b) != "payload" {
			t.Fatalf("result %d: %s", i, b)
		}
	}
	coalCount := 0
	for _, v := range coalesced {
		if v {
			coalCount++
		}
	}
	// At least N - calledN callers must report coalesced=true (each
	// distinct fn execution can produce at most one non-coalesced caller).
	if coalCount < N-calledN {
		t.Fatalf("coalesced=%d, want >= %d (calls=%d)", coalCount, N-calledN, calledN)
	}

	// Post-burst the cache must be hot.
	if v, ok := c.Get("k"); !ok || string(v) != "payload" {
		t.Fatal("post-Do cache miss")
	}
}

func TestSingleflightPropagatesError(t *testing.T) {
	c := New(100)
	_, _, err := c.Do("k", func() ([]byte, time.Duration, error) {
		return nil, 0, errSentinel
	})
	if err == nil {
		t.Fatal("want error")
	}
}

func TestSweepRemovesExpired(t *testing.T) {
	c := New(100)
	c.Set("k1", []byte("v"), 30*time.Millisecond)
	c.Set("k2", []byte("v"), time.Hour)
	time.Sleep(50 * time.Millisecond)
	rm := c.Sweep()
	if rm != 1 {
		t.Fatalf("removed %d", rm)
	}
	if c.Size() != 1 {
		t.Fatalf("size %d", c.Size())
	}
}

func TestEvictionAtCap(t *testing.T) {
	c := New(2)
	c.Set("a", []byte("1"), time.Hour)
	c.Set("b", []byte("2"), time.Hour)
	c.Set("c", []byte("3"), time.Hour) // forces eviction
	if c.Size() != 2 {
		t.Fatalf("size after eviction: %d", c.Size())
	}
}

type sentinelErr struct{}

func (sentinelErr) Error() string { return "sentinel" }

var errSentinel = sentinelErr{}
