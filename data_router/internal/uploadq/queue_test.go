package uploadq

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/redesign2/services/data_router/internal/api"
)

func mkJob(id, caller string, p api.Priority) *Job {
	return NewJob(id, caller, p, "/tmp/spool-"+id, "image/png", "deadbeef", 100)
}

func TestPushPopFIFO(t *testing.T) {
	q := New(10, 5, 50)
	for i := 0; i < 5; i++ {
		if err := q.Push(mkJob("j"+string(rune('0'+i)), "c", api.PriorityNormal)); err != nil {
			t.Fatalf("push: %v", err)
		}
	}
	for i := 0; i < 5; i++ {
		got, err := q.Pop(context.Background())
		if err != nil {
			t.Fatal(err)
		}
		want := "j" + string(rune('0'+i))
		if got.ID != want {
			t.Fatalf("got %s, want %s", got.ID, want)
		}
	}
}

func TestPriorityOrder(t *testing.T) {
	q := New(10, 5, 50)
	_ = q.Push(mkJob("low", "c", api.PriorityLow))
	_ = q.Push(mkJob("normal", "c", api.PriorityNormal))
	_ = q.Push(mkJob("high", "c", api.PriorityHigh))
	for _, w := range []string{"high", "normal", "low"} {
		got, _ := q.Pop(context.Background())
		if got.ID != w {
			t.Fatalf("got %s, want %s", got.ID, w)
		}
	}
}

func TestQueueFull(t *testing.T) {
	q := New(2, 5, 10)
	if err := q.Push(mkJob("a", "c", api.PriorityNormal)); err != nil {
		t.Fatal(err)
	}
	if err := q.Push(mkJob("b", "c", api.PriorityNormal)); err != nil {
		t.Fatal(err)
	}
	if err := q.Push(mkJob("c", "c", api.PriorityNormal)); !errors.Is(err, ErrQueueFull) {
		t.Fatalf("want ErrQueueFull, got %v", err)
	}
}

func TestPerCallerCap(t *testing.T) {
	q := New(100, 2, 10)
	if err := q.Push(mkJob("a1", "noisy", api.PriorityNormal)); err != nil {
		t.Fatal(err)
	}
	if err := q.Push(mkJob("a2", "noisy", api.PriorityNormal)); err != nil {
		t.Fatal(err)
	}
	if err := q.Push(mkJob("a3", "noisy", api.PriorityNormal)); !errors.Is(err, ErrCallerLimit) {
		t.Fatalf("want ErrCallerLimit, got %v", err)
	}
	if err := q.Push(mkJob("b1", "quiet", api.PriorityNormal)); err != nil {
		t.Fatalf("quiet caller blocked: %v", err)
	}
}

func TestPopBlocksUntilPush(t *testing.T) {
	q := New(10, 5, 10)
	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()
	got := make(chan *Job, 1)
	go func() {
		j, err := q.Pop(ctx)
		if err == nil {
			got <- j
		}
	}()
	time.Sleep(20 * time.Millisecond)
	_ = q.Push(mkJob("x", "c", api.PriorityNormal))
	select {
	case j := <-got:
		if j.ID != "x" {
			t.Fatalf("got %s", j.ID)
		}
	case <-time.After(150 * time.Millisecond):
		t.Fatal("Pop did not return after Push")
	}
}

func TestCloseUnblocksWaitersAndDrains(t *testing.T) {
	q := New(10, 5, 10)
	job := mkJob("pending", "c", api.PriorityNormal)
	_ = q.Push(job)
	q.Close()
	select {
	case <-job.Done():
		snap := job.Snapshot()
		if snap.Status != StatusShutdown {
			t.Fatalf("want StatusShutdown, got %s", snap.Status)
		}
	case <-time.After(200 * time.Millisecond):
		t.Fatal("close did not mark pending job")
	}
	if err := q.Push(mkJob("late", "c", api.PriorityNormal)); !errors.Is(err, ErrShutdown) {
		t.Fatalf("post-close push: want ErrShutdown, got %v", err)
	}
}

func TestRecordTerminalAndRecentSnapshot(t *testing.T) {
	q := New(10, 5, 3) // recent ring of 3
	for i := 0; i < 5; i++ {
		j := mkJob("j"+string(rune('0'+i)), "c", api.PriorityNormal)
		j.markCompleted(stubMeta(j.ID))
		q.RecordTerminal(j)
	}
	recent := q.RecentSnapshot(10)
	if len(recent) != 3 {
		t.Fatalf("recent len=%d, want 3 (ring size)", len(recent))
	}
	want := []string{"j4", "j3", "j2"}
	for i := range recent {
		if recent[i].ID != want[i] {
			t.Fatalf("recent[%d]=%s, want %s", i, recent[i].ID, want[i])
		}
	}
}

func TestStatsReflectActivity(t *testing.T) {
	q := New(100, 50, 100)
	for i := 0; i < 3; i++ {
		_ = q.Push(mkJob("h"+string(rune('0'+i)), "x", api.PriorityHigh))
	}
	for i := 0; i < 5; i++ {
		_ = q.Push(mkJob("n"+string(rune('0'+i)), "y", api.PriorityNormal))
	}
	s := q.Stats()
	if s.LaneSizes[0] != 3 || s.LaneSizes[1] != 5 || s.LaneSizes[2] != 0 {
		t.Fatalf("lanes %v", s.LaneSizes)
	}
	if s.Total != 8 {
		t.Fatalf("total %d", s.Total)
	}
	if s.DistinctCallers != 2 {
		t.Fatalf("callers %d", s.DistinctCallers)
	}
	if s.Pushed != 8 {
		t.Fatalf("pushed %d", s.Pushed)
	}
}

func TestConcurrentPushPopNoLoss(t *testing.T) {
	q := New(2000, 1000, 100)
	const N = 500
	var pushed, popped sync.WaitGroup
	pushed.Add(N)
	for i := 0; i < N; i++ {
		go func(i int) {
			defer pushed.Done()
			j := mkJob("j"+string(rune('0'+i%10))+string(rune('0'+(i/10)%10))+string(rune('0'+(i/100)%10))+":"+string(rune('0'+i%2)), "c", api.PriorityNormal)
			j.ID = j.ID + ":" + string(rune('A'+(i%26)))
			_ = q.Push(j)
		}(i)
	}
	pushed.Wait()

	var consumed int
	popped.Add(1)
	go func() {
		defer popped.Done()
		ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()
		for {
			j, err := q.Pop(ctx)
			if err != nil {
				return
			}
			consumed++
			j.markCompleted(stubMeta(j.ID))
			q.RecordTerminal(j)
			if consumed == N {
				return
			}
		}
	}()
	popped.Wait()
	if consumed != N {
		t.Fatalf("consumed %d, want %d", consumed, N)
	}
}

func TestActiveSnapshotFiltersTerminals(t *testing.T) {
	q := New(10, 5, 10)
	_ = q.Push(mkJob("a", "c", api.PriorityNormal))
	_ = q.Push(mkJob("b", "c", api.PriorityNormal))
	job, _ := q.Pop(context.Background())
	job.markProcessing()
	active := q.ActiveSnapshot()
	if len(active) != 2 {
		t.Fatalf("active len=%d, want 2 (1 queued + 1 processing)", len(active))
	}
	job.markCompleted(stubMeta(job.ID))
	q.RecordTerminal(job)
	active = q.ActiveSnapshot()
	if len(active) != 1 {
		t.Fatalf("active len=%d after terminal, want 1", len(active))
	}
	if active[0].Status != StatusQueued {
		t.Fatalf("active[0].status=%s", active[0].Status)
	}
}
