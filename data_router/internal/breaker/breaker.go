// Package breaker is a small circuit breaker tuned for "DB is unavailable"
// scenarios — TNS errors, connection refused, ORA-12541, listener down,
// wallet/SSL failures, ADB scaling pauses.
//
// We don't trip on individual ORA errors that signal application-level
// problems (ORA-00001 unique violation, ORA-00942 table missing, etc.) —
// those mean the request is bad, not the DB. The executor classifies
// errors and only feeds infrastructural failures into the breaker.
//
// State machine:
//
//   closed   ── failure ratio breach in last N samples ──▶  open
//   open     ── OpenDuration elapsed                   ──▶  half-open
//   half-open ── one trial succeeds                    ──▶  closed
//   half-open ── one trial fails                       ──▶  open (timer reset)
//
// In half-open, only one request is allowed through at a time. Allow()
// returns false for the rest, so the queue/handler responds fast with
// CodeBreakerOpen instead of stacking attempts.
package breaker

import (
	"sync"
	"time"
)

type State int

const (
	StateClosed State = iota
	StateOpen
	StateHalfOpen
)

func (s State) String() string {
	switch s {
	case StateClosed:
		return "closed"
	case StateOpen:
		return "open"
	case StateHalfOpen:
		return "half-open"
	}
	return "unknown"
}

type Breaker struct {
	mu sync.Mutex

	state          State
	openedAt       time.Time
	halfOpenInUse  bool

	window     []bool // sliding sample buffer; true = success
	windowSize int
	windowIdx  int
	windowFull bool

	failureRatio float64
	minSamples   int
	openDuration time.Duration
}

func New(windowSize int, failureRatio float64, minSamples int, openDuration time.Duration) *Breaker {
	if windowSize < 1 {
		windowSize = 1
	}
	return &Breaker{
		windowSize:   windowSize,
		failureRatio: failureRatio,
		minSamples:   minSamples,
		openDuration: openDuration,
		window:       make([]bool, windowSize),
	}
}

// Allow returns false when the breaker is open (or half-open with a
// trial already in flight). The caller should fail fast with
// CodeBreakerOpen.
func (b *Breaker) Allow() bool {
	b.mu.Lock()
	defer b.mu.Unlock()
	switch b.state {
	case StateClosed:
		return true
	case StateOpen:
		if time.Since(b.openedAt) >= b.openDuration {
			b.state = StateHalfOpen
			b.halfOpenInUse = true
			return true
		}
		return false
	case StateHalfOpen:
		if b.halfOpenInUse {
			return false
		}
		b.halfOpenInUse = true
		return true
	}
	return false
}

// Report feeds the result of an Allow()'d call. Pass true on success and
// false on infrastructural failure (the executor decides which is which).
func (b *Breaker) Report(success bool) {
	b.mu.Lock()
	defer b.mu.Unlock()

	if b.state == StateHalfOpen {
		b.halfOpenInUse = false
		if success {
			b.transition(StateClosed)
		} else {
			b.transition(StateOpen)
		}
		return
	}

	b.window[b.windowIdx] = success
	b.windowIdx = (b.windowIdx + 1) % b.windowSize
	if b.windowIdx == 0 {
		b.windowFull = true
	}

	if b.state == StateClosed && b.shouldTrip() {
		b.transition(StateOpen)
	}
}

func (b *Breaker) shouldTrip() bool {
	n := b.windowSize
	if !b.windowFull {
		n = b.windowIdx
	}
	if n < b.minSamples {
		return false
	}
	failures := 0
	for i := 0; i < n; i++ {
		if !b.window[i] {
			failures++
		}
	}
	return float64(failures)/float64(n) >= b.failureRatio
}

func (b *Breaker) transition(to State) {
	b.state = to
	switch to {
	case StateOpen:
		b.openedAt = time.Now()
	case StateClosed:
		// Reset sample window so we don't immediately re-trip on stale failures.
		for i := range b.window {
			b.window[i] = false
		}
		b.windowIdx = 0
		b.windowFull = false
	}
}

func (b *Breaker) State() State {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.state
}
