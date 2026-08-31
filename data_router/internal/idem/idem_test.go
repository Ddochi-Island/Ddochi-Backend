package idem

import (
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func TestEmptyKeyIsAlwaysLeader(t *testing.T) {
	s := New(time.Minute, 100)
	cached, leader, wait := s.Begin("c", "")
	if cached != nil || !leader || wait != nil {
		t.Fatalf("empty key: cached=%v leader=%v wait_nil=%v", cached, leader, wait == nil)
	}
}

func TestLeaderCompletesAndCacheReturns(t *testing.T) {
	s := New(time.Minute, 100)
	cached, leader, wait := s.Begin("svc", "k1")
	if cached != nil || !leader || wait != nil {
		t.Fatalf("first call: cached=%v leader=%v wait_nil=%v", cached, leader, wait == nil)
	}
	s.Complete("svc", "k1", []byte("done"))

	cached, leader, wait = s.Begin("svc", "k1")
	if leader || wait != nil {
		t.Fatalf("second call: leader=%v wait_nil=%v", leader, wait == nil)
	}
	if string(cached) != "done" {
		t.Fatalf("cached=%s", cached)
	}
}

func TestFollowerWaitsForLeader(t *testing.T) {
	s := New(time.Minute, 100)
	_, leader, _ := s.Begin("svc", "k")
	if !leader {
		t.Fatal("expected leader")
	}

	var got []byte
	done := make(chan struct{})
	go func() {
		_, isLead, wait := s.Begin("svc", "k")
		if isLead || wait == nil {
			t.Errorf("follower: leader=%v wait_nil=%v", isLead, wait == nil)
			return
		}
		got = wait()
		close(done)
	}()

	time.Sleep(20 * time.Millisecond)
	s.Complete("svc", "k", []byte("payload"))

	select {
	case <-done:
	case <-time.After(500 * time.Millisecond):
		t.Fatal("follower did not unblock")
	}
	if string(got) != "payload" {
		t.Fatalf("got=%s", got)
	}
}

func TestAbortLetsRetryProceed(t *testing.T) {
	s := New(time.Minute, 100)
	_, leader, _ := s.Begin("svc", "k")
	if !leader {
		t.Fatal("first should be leader")
	}
	s.Abort("svc", "k")
	cached, isLead, _ := s.Begin("svc", "k")
	if cached != nil || !isLead {
		t.Fatalf("after abort: cached=%v leader=%v", cached, isLead)
	}
}

func TestKeysScopedByCaller(t *testing.T) {
	s := New(time.Minute, 100)
	_, l1, _ := s.Begin("svc1", "shared")
	_, l2, _ := s.Begin("svc2", "shared")
	if !l1 || !l2 {
		t.Fatalf("expected both leaders, l1=%v l2=%v", l1, l2)
	}
}

func TestSweepRemovesExpired(t *testing.T) {
	s := New(30*time.Millisecond, 100)
	_, _, _ = s.Begin("c", "k")
	s.Complete("c", "k", []byte("x"))
	time.Sleep(50 * time.Millisecond)
	rm := s.Sweep()
	if rm != 1 {
		t.Fatalf("removed %d", rm)
	}
}

// Stress: many concurrent followers should all see the same response and
// the leader's fn should run exactly once.
func TestConcurrentFollowersSingleExecution(t *testing.T) {
	s := New(time.Minute, 100)
	const N = 30
	var executions int32
	var wg sync.WaitGroup
	results := make([][]byte, N)
	wg.Add(N)
	start := make(chan struct{})

	for i := 0; i < N; i++ {
		go func(i int) {
			defer wg.Done()
			<-start
			cached, leader, wait := s.Begin("svc", "k")
			if cached != nil {
				results[i] = cached
				return
			}
			if leader {
				atomic.AddInt32(&executions, 1)
				time.Sleep(30 * time.Millisecond)
				s.Complete("svc", "k", []byte("ans"))
				results[i] = []byte("ans")
				return
			}
			results[i] = wait()
		}(i)
	}
	close(start)
	wg.Wait()

	if executions != 1 {
		t.Fatalf("executions=%d, want 1", executions)
	}
	for i, r := range results {
		if string(r) != "ans" {
			t.Fatalf("worker %d: %s", i, r)
		}
	}
}
