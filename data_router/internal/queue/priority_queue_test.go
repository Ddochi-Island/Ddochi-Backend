package queue

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"testing"
	"time"

	"github.com/redesign2/services/data_router/internal/api"
)

func mkTask(id, caller string, p api.Priority, deadline time.Duration) *Task {
	t := &Task{
		ID:         id,
		Caller:     caller,
		Priority:   p,
		EnqueuedAt: time.Now(),
		Result:     make(chan TaskResult, 1),
		Ctx:        context.Background(),
	}
	if deadline > 0 {
		t.Deadline = time.Now().Add(deadline)
	}
	return t
}

func TestPushPopFIFO(t *testing.T) {
	q := New(100, 10, 30, 50)
	for i := 0; i < 5; i++ {
		if err := q.Push(mkTask("t"+string(rune('0'+i)), "c", api.PriorityNormal, time.Second)); err != nil {
			t.Fatalf("push %d: %v", i, err)
		}
	}
	ctx := context.Background()
	for i := 0; i < 5; i++ {
		got, err := q.Pop(ctx)
		if err != nil {
			t.Fatalf("pop %d: %v", i, err)
		}
		want := "t" + string(rune('0'+i))
		if got.ID != want {
			t.Fatalf("pop %d: got %s, want %s", i, got.ID, want)
		}
	}
}

func TestPriorityOrder(t *testing.T) {
	q := New(100, 10, 30, 50)
	if err := q.Push(mkTask("low", "c", api.PriorityLow, time.Second)); err != nil {
		t.Fatal(err)
	}
	if err := q.Push(mkTask("normal", "c", api.PriorityNormal, time.Second)); err != nil {
		t.Fatal(err)
	}
	if err := q.Push(mkTask("high", "c", api.PriorityHigh, time.Second)); err != nil {
		t.Fatal(err)
	}
	ctx := context.Background()
	want := []string{"high", "normal", "low"}
	for _, w := range want {
		got, err := q.Pop(ctx)
		if err != nil {
			t.Fatal(err)
		}
		if got.ID != w {
			t.Fatalf("got %s, want %s", got.ID, w)
		}
	}
}

func TestAdmissionLaneReservations(t *testing.T) {
	// cap=10, high=2, normal=3 → low admitted only when total < 5
	q := New(10, 2, 3, 100)

	// fill 5 low tasks → next low must be rejected
	for i := 0; i < 5; i++ {
		if err := q.Push(mkTask("l", "c", api.PriorityLow, time.Second)); err != nil {
			t.Fatalf("low push %d: %v", i, err)
		}
	}
	if err := q.Push(mkTask("l_extra", "c", api.PriorityLow, time.Second)); !errors.Is(err, ErrQueueFull) {
		t.Fatalf("low overflow: want ErrQueueFull, got %v", err)
	}

	// normal still admitted up to (cap - high) = 8 total → 3 more normals
	for i := 0; i < 3; i++ {
		if err := q.Push(mkTask("n", "c", api.PriorityNormal, time.Second)); err != nil {
			t.Fatalf("normal push %d: %v", i, err)
		}
	}
	if err := q.Push(mkTask("n_extra", "c", api.PriorityNormal, time.Second)); !errors.Is(err, ErrQueueFull) {
		t.Fatalf("normal overflow: want ErrQueueFull, got %v", err)
	}

	// high admitted up to cap=10 → 2 more
	for i := 0; i < 2; i++ {
		if err := q.Push(mkTask("h", "c", api.PriorityHigh, time.Second)); err != nil {
			t.Fatalf("high push %d: %v", i, err)
		}
	}
	if err := q.Push(mkTask("h_extra", "c", api.PriorityHigh, time.Second)); !errors.Is(err, ErrQueueFull) {
		t.Fatalf("high overflow: want ErrQueueFull, got %v", err)
	}
}

func TestPerCallerCap(t *testing.T) {
	q := New(100, 10, 30, 3) // per-caller = 3
	for i := 0; i < 3; i++ {
		if err := q.Push(mkTask("a", "noisy", api.PriorityNormal, time.Second)); err != nil {
			t.Fatal(err)
		}
	}
	if err := q.Push(mkTask("a4", "noisy", api.PriorityNormal, time.Second)); !errors.Is(err, ErrCallerLimit) {
		t.Fatalf("want ErrCallerLimit, got %v", err)
	}
	// other caller still admitted
	if err := q.Push(mkTask("b", "quiet", api.PriorityNormal, time.Second)); err != nil {
		t.Fatalf("quiet caller blocked: %v", err)
	}
}

func TestPopBlocksUntilPush(t *testing.T) {
	q := New(10, 1, 3, 5)
	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()

	got := make(chan *Task, 1)
	go func() {
		tk, err := q.Pop(ctx)
		if err == nil {
			got <- tk
		}
	}()

	time.Sleep(20 * time.Millisecond)
	if err := q.Push(mkTask("x", "c", api.PriorityNormal, time.Second)); err != nil {
		t.Fatal(err)
	}

	select {
	case tk := <-got:
		if tk.ID != "x" {
			t.Fatalf("got %s", tk.ID)
		}
	case <-time.After(150 * time.Millisecond):
		t.Fatal("Pop did not return after Push")
	}
}

func TestPopRespectsCancel(t *testing.T) {
	q := New(10, 1, 3, 5)
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() {
		_, err := q.Pop(ctx)
		done <- err
	}()
	time.Sleep(20 * time.Millisecond)
	cancel()
	select {
	case err := <-done:
		if !errors.Is(err, context.Canceled) {
			t.Fatalf("want Canceled, got %v", err)
		}
	case <-time.After(500 * time.Millisecond):
		t.Fatal("Pop did not unblock on ctx cancel")
	}
}

func TestDeadlineExpiredTaskFlushedOnPop(t *testing.T) {
	q := New(10, 1, 3, 5)
	expired := mkTask("expired", "c", api.PriorityNormal, 0)
	expired.Deadline = time.Now().Add(-time.Second) // past
	fresh := mkTask("fresh", "c", api.PriorityNormal, time.Second)

	if err := q.Push(expired); err != nil {
		t.Fatal(err)
	}
	if err := q.Push(fresh); err != nil {
		t.Fatal(err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()
	got, err := q.Pop(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if got.ID != "fresh" {
		t.Fatalf("expected fresh, got %s", got.ID)
	}
	// expired task should have received timeout error on its Result chan
	select {
	case res := <-expired.Result:
		if res.Err == nil {
			t.Fatal("expired task got nil error")
		}
	default:
		t.Fatal("expired task did not receive notification")
	}
}

func TestCloseDrainsPending(t *testing.T) {
	q := New(10, 1, 3, 5)
	tk := mkTask("t", "c", api.PriorityNormal, time.Second)
	if err := q.Push(tk); err != nil {
		t.Fatal(err)
	}
	q.Close()
	select {
	case res := <-tk.Result:
		if !errors.Is(res.Err, ErrShuttingDown) {
			t.Fatalf("want ErrShuttingDown, got %v", res.Err)
		}
	case <-time.After(200 * time.Millisecond):
		t.Fatal("queue.Close did not drain pending")
	}
	// further pushes rejected
	if err := q.Push(mkTask("late", "c", api.PriorityNormal, time.Second)); !errors.Is(err, ErrShuttingDown) {
		t.Fatalf("post-close push: want ErrShuttingDown, got %v", err)
	}
}

func TestStatsSnapshot(t *testing.T) {
	q := New(100, 10, 30, 50)
	for i := 0; i < 4; i++ {
		_ = q.Push(mkTask("h", "x", api.PriorityHigh, time.Second))
	}
	for i := 0; i < 6; i++ {
		_ = q.Push(mkTask("n", "y", api.PriorityNormal, time.Second))
	}
	for i := 0; i < 2; i++ {
		_ = q.Push(mkTask("l", "z", api.PriorityLow, time.Second))
	}
	s := q.Stats()
	if s.High != 4 || s.Normal != 6 || s.Low != 2 || s.Total != 12 {
		t.Fatalf("counts: %+v", s)
	}
	if s.Callers != 3 {
		t.Fatalf("callers: %d", s.Callers)
	}
}

// Verifies the queue is safe under concurrent push and pop and that no task
// is ever delivered twice or lost. Uses many goroutines with small bursts.
func TestConcurrentPushPop(t *testing.T) {
	q := New(2000, 100, 300, 2000)
	const producers = 8
	const perProd = 200
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	produced := make(map[string]int)
	var mu sync.Mutex

	var wg sync.WaitGroup
	for p := 0; p < producers; p++ {
		wg.Add(1)
		go func(pid int) {
			defer wg.Done()
			for i := 0; i < perProd; i++ {
				id := fmt.Sprintf("p%d:%d", pid, i) // globally unique
				mu.Lock()
				produced[id]++
				mu.Unlock()
				caller := fmt.Sprintf("caller-%d", pid)
				if err := q.Push(mkTask(id, caller, api.PriorityNormal, 5*time.Second)); err != nil {
					t.Errorf("push: %v", err)
					return
				}
			}
		}(p)
	}

	consumed := make(map[string]int)
	consumeDone := make(chan struct{})
	go func() {
		for {
			tk, err := q.Pop(ctx)
			if err != nil {
				close(consumeDone)
				return
			}
			consumed[tk.ID]++
			if len(consumed) == producers*perProd {
				close(consumeDone)
				return
			}
		}
	}()

	wg.Wait()
	select {
	case <-consumeDone:
	case <-time.After(3 * time.Second):
		t.Fatalf("consume did not finish; consumed=%d produced=%d", len(consumed), producers*perProd)
	}
	if len(consumed) != producers*perProd {
		t.Fatalf("consumed %d, produced %d", len(consumed), producers*perProd)
	}
	for id, n := range produced {
		if consumed[id] != n {
			t.Fatalf("id %s: produced %d, consumed %d", id, n, consumed[id])
		}
	}
}
