// Package idem is the idempotency cache for write operations.
//
// Callers can attach an Idempotency-Key (typically a UUID generated at
// the originating action). For exec/tx/proc, the router caches the
// response under (caller, key) for the configured window. A duplicate
// request with the same key returns the cached response without
// re-executing — making caller retries safe even for mutations.
//
// Concurrent duplicates: the second caller arrives while the first is
// still in flight and joins a pending wait. The leader publishes the
// result via Complete; followers wake up and read the same response.
// This guarantees one execution per key per window.
//
// In-memory only. A data_router restart loses the window; acceptable
// for a single-instance gateway. For multi-replica deployments, swap
// for a shared store (Oracle table with TTL, or Redis).
package idem

import (
	"sync"
	"time"
)

type entry struct {
	resp      []byte
	expiresAt time.Time
}

type pending struct {
	done chan struct{}
	resp []byte
}

type Store struct {
	mu      sync.Mutex
	done    map[string]entry    // completed responses, TTL'd
	wip     map[string]*pending // in-flight leaders
	max     int
	window  time.Duration
}

func New(window time.Duration, max int) *Store {
	return &Store{
		done:   make(map[string]entry, 256),
		wip:    make(map[string]*pending),
		max:    max,
		window: window,
	}
}

func compositeKey(caller, key string) string { return caller + "\x00" + key }

// Begin returns one of three outcomes:
//   1. cached non-nil, isLeader=false, wait=nil — return cached resp directly.
//   2. cached nil, isLeader=false, wait!=nil    — block on wait() to receive
//      the in-flight leader's eventual response.
//   3. cached nil, isLeader=true, wait=nil      — caller is the leader; must
//      execute and call Complete or Abort.
//
// Empty key short-circuits to leader with no caching.
func (s *Store) Begin(caller, key string) (cached []byte, isLeader bool, wait func() []byte) {
	if key == "" {
		return nil, true, nil
	}
	full := compositeKey(caller, key)
	s.mu.Lock()
	if e, ok := s.done[full]; ok && time.Now().Before(e.expiresAt) {
		s.mu.Unlock()
		return e.resp, false, nil
	}
	if p, ok := s.wip[full]; ok {
		s.mu.Unlock()
		return nil, false, func() []byte {
			<-p.done
			return p.resp
		}
	}
	if len(s.done) >= s.max {
		now := time.Now()
		for k, e := range s.done {
			if now.After(e.expiresAt) {
				delete(s.done, k)
				break
			}
		}
	}
	p := &pending{done: make(chan struct{})}
	s.wip[full] = p
	s.mu.Unlock()
	return nil, true, nil
}

// Complete publishes the leader's response to followers and caches it
// for the configured window. Call once per leader Begin().
func (s *Store) Complete(caller, key string, resp []byte) {
	if key == "" {
		return
	}
	full := compositeKey(caller, key)
	s.mu.Lock()
	p := s.wip[full]
	delete(s.wip, full)
	s.done[full] = entry{resp: resp, expiresAt: time.Now().Add(s.window)}
	s.mu.Unlock()
	if p != nil {
		p.resp = resp
		close(p.done)
	}
}

// Abort releases the leader slot without caching. The next retry will
// re-execute. Call this when the leader's request fails.
func (s *Store) Abort(caller, key string) {
	if key == "" {
		return
	}
	full := compositeKey(caller, key)
	s.mu.Lock()
	p := s.wip[full]
	delete(s.wip, full)
	s.mu.Unlock()
	if p != nil {
		close(p.done) // resp stays nil; followers see nil and retry
	}
}

// Sweep evicts expired entries. Call from a periodic ticker.
func (s *Store) Sweep() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	now := time.Now()
	removed := 0
	for k, e := range s.done {
		if now.After(e.expiresAt) {
			delete(s.done, k)
			removed++
		}
	}
	return removed
}

func (s *Store) Size() (done, wip int) {
	s.mu.Lock()
	defer s.mu.Unlock()
	return len(s.done), len(s.wip)
}
