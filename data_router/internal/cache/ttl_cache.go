// Package cache implements the short-lived (1–2s by default) read cache.
//
// Why this exists: the dominant load shape we expect from data_router is
// many caller services polling the same dashboard / status queries on
// short intervals. Without coalescing, ten dashboards refreshing once a
// second is ten DB round-trips per second per query. With a 1.5s TTL +
// singleflight, it collapses to ~0.7 DB round-trips per second — and any
// thundering-herd burst around an expiry is collapsed into one DB call.
//
// The cache is bounded by entry count with random-victim eviction; we
// don't need strict LRU because TTLs are short (≤5s by default) and
// entries die naturally. Random eviction is O(1) and avoids LRU's lock
// hot-path under high concurrency.
package cache

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"sync"
	"time"

	"golang.org/x/sync/singleflight"
)

type entry struct {
	value     []byte
	expiresAt time.Time
}

type Cache struct {
	mu      sync.RWMutex
	entries map[string]entry
	max     int

	sf singleflight.Group
}

func New(maxEntries int) *Cache {
	return &Cache{entries: make(map[string]entry, 1024), max: maxEntries}
}

// Key builds a stable hash for a cacheable request.
// Inputs are normalized via JSON (deterministic enough for our use; we
// don't allow maps in args, only positional slices).
func Key(op string, sql string, args []any) string {
	h := sha256.New()
	h.Write([]byte(op))
	h.Write([]byte{0})
	h.Write([]byte(sql))
	h.Write([]byte{0})
	if len(args) > 0 {
		b, _ := json.Marshal(args)
		h.Write(b)
	}
	return hex.EncodeToString(h.Sum(nil))
}

// Get returns the cached bytes if present and unexpired.
func (c *Cache) Get(key string) ([]byte, bool) {
	c.mu.RLock()
	e, ok := c.entries[key]
	c.mu.RUnlock()
	if !ok || time.Now().After(e.expiresAt) {
		return nil, false
	}
	return e.value, true
}

// Set stores value with TTL. Evicts a random victim when at capacity to
// keep insertion O(1). Caller is responsible for cloning value if it
// will be mutated after Set.
func (c *Cache) Set(key string, value []byte, ttl time.Duration) {
	if ttl <= 0 {
		return
	}
	c.mu.Lock()
	if len(c.entries) >= c.max {
		// random eviction — pick first key from map iteration
		for k := range c.entries {
			delete(c.entries, k)
			break
		}
	}
	c.entries[key] = entry{value: value, expiresAt: time.Now().Add(ttl)}
	c.mu.Unlock()
}

// Do is the singleflight wrapper: only one caller per key actually runs
// fn; others wait and receive the same result. Use for cache misses to
// collapse thundering herds.
//
// coalesced=true means this response was shared with at least one other
// concurrent caller (singleflight's "shared" flag). Note that the caller
// whose fn actually executed will ALSO see coalesced=true if followers
// joined while fn ran — singleflight cannot distinguish executor vs.
// follower retroactively, only "was this value handed to multiple
// callers?". For the data_router's use case (telling callers via
// Meta.Coalesced whether they paid for a coalesced response) that's the
// correct semantic.
func (c *Cache) Do(key string, fn func() ([]byte, time.Duration, error)) (val []byte, coalesced bool, err error) {
	v, err, shared := c.sf.Do(key, func() (any, error) {
		// Re-check cache inside leader scope: a previous leader may have
		// just finished and populated the cache, which would make this
		// fn a wasted DB call. Cheap insurance.
		if cached, ok := c.Get(key); ok {
			return cachedResult{val: cached}, nil
		}
		v, ttl, err := fn()
		if err != nil {
			return nil, err
		}
		c.Set(key, v, ttl)
		return cachedResult{val: v}, nil
	})
	if err != nil {
		return nil, shared, err
	}
	return v.(cachedResult).val, shared, nil
}

type cachedResult struct{ val []byte }

// Sweep removes expired entries. Called periodically; not strictly
// required for correctness (Get checks expiry) but keeps memory bounded
// in steady state.
func (c *Cache) Sweep() (removed int) {
	c.mu.Lock()
	defer c.mu.Unlock()
	now := time.Now()
	for k, e := range c.entries {
		if now.After(e.expiresAt) {
			delete(c.entries, k)
			removed++
		}
	}
	return removed
}

func (c *Cache) Size() int {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return len(c.entries)
}

