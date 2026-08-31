package breaker

import (
	"testing"
	"time"
)

func TestClosedAllowsAll(t *testing.T) {
	b := New(10, 0.5, 5, time.Second)
	for i := 0; i < 100; i++ {
		if !b.Allow() {
			t.Fatalf("closed should allow, iter %d", i)
		}
		b.Report(true)
	}
	if b.State() != StateClosed {
		t.Fatal("state changed")
	}
}

func TestTripsOnFailureRatio(t *testing.T) {
	b := New(10, 0.5, 5, time.Second)
	// 6 failures out of 10 → trips
	for i := 0; i < 4; i++ {
		b.Allow()
		b.Report(true)
	}
	for i := 0; i < 6; i++ {
		b.Allow()
		b.Report(false)
	}
	if b.State() != StateOpen {
		t.Fatalf("state=%v, want open", b.State())
	}
	if b.Allow() {
		t.Fatal("open should reject")
	}
}

func TestRespectsMinSamples(t *testing.T) {
	b := New(10, 0.5, 5, time.Second)
	// only 3 samples — below minimum, even if all failures
	for i := 0; i < 3; i++ {
		b.Allow()
		b.Report(false)
	}
	if b.State() != StateClosed {
		t.Fatalf("state=%v, want closed (below min samples)", b.State())
	}
}

func TestHalfOpenAfterDuration(t *testing.T) {
	b := New(10, 0.5, 5, 30*time.Millisecond)
	for i := 0; i < 10; i++ {
		b.Allow()
		b.Report(false)
	}
	if b.State() != StateOpen {
		t.Fatal("expected open")
	}
	if b.Allow() {
		t.Fatal("open should reject")
	}
	time.Sleep(50 * time.Millisecond)
	if !b.Allow() {
		t.Fatal("after open duration should allow trial")
	}
	if b.State() != StateHalfOpen {
		t.Fatalf("state=%v, want half-open", b.State())
	}
}

func TestHalfOpenSingleTrialOnly(t *testing.T) {
	b := New(10, 0.5, 5, 20*time.Millisecond)
	for i := 0; i < 10; i++ {
		b.Allow()
		b.Report(false)
	}
	time.Sleep(30 * time.Millisecond)
	if !b.Allow() {
		t.Fatal("trial 1 should pass")
	}
	if b.Allow() {
		t.Fatal("trial 2 should be blocked while trial 1 in flight")
	}
}

func TestHalfOpenSuccessClosesBreaker(t *testing.T) {
	b := New(10, 0.5, 5, 20*time.Millisecond)
	for i := 0; i < 10; i++ {
		b.Allow()
		b.Report(false)
	}
	time.Sleep(30 * time.Millisecond)
	if !b.Allow() {
		t.Fatal("trial should be allowed")
	}
	b.Report(true)
	if b.State() != StateClosed {
		t.Fatalf("state=%v, want closed after successful trial", b.State())
	}
	// After closing, breaker should not immediately re-trip from old samples.
	if !b.Allow() {
		t.Fatal("after close should allow")
	}
}

func TestHalfOpenFailureReopens(t *testing.T) {
	b := New(10, 0.5, 5, 20*time.Millisecond)
	for i := 0; i < 10; i++ {
		b.Allow()
		b.Report(false)
	}
	time.Sleep(30 * time.Millisecond)
	if !b.Allow() {
		t.Fatal("trial allowed")
	}
	b.Report(false)
	if b.State() != StateOpen {
		t.Fatalf("state=%v, want open after failed trial", b.State())
	}
}
