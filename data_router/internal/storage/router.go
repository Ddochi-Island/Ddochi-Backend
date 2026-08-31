// router.go is the storage equivalent of a load balancer with one rule:
// "OCI Object Storage if there's room under the free-tier ceiling,
// otherwise Block Storage." Once a backend is chosen for an upload it's
// permanent — the ObjectID encodes the backend and we never migrate.
//
// The selector is intentionally simple: a cached used-bytes value vs. a
// configured threshold. We don't try to predict spike behavior or
// reserve capacity for in-flight uploads — the threshold is set well
// below the actual ceiling (default 80% of 10 GiB = 8 GiB) so a few
// concurrent multi-MB uploads can't push us past the real limit between
// usage refreshes.
package storage

import (
	"context"
	"errors"
	"io"
	"sync/atomic"
	"time"

	"github.com/redesign2/services/data_router/internal/logx"
)

type Router struct {
	primary   Backend // OCI Object Storage
	fallback  Backend // Block

	thresholdBytes int64

	primaryAvailable atomic.Bool
}

func NewRouter(primary, fallback Backend, thresholdBytes int64) *Router {
	r := &Router{primary: primary, fallback: fallback, thresholdBytes: thresholdBytes}
	r.primaryAvailable.Store(primary != nil)
	return r
}

// Pick returns the backend a new upload should target. expectedSize may
// be -1 when the caller doesn't know it ahead of time; in that case we
// simply check current usage against the threshold (a partial guarantee
// — see file-level comment).
func (r *Router) Pick(ctx context.Context, expectedSize int64) Backend {
	if r.primary == nil || !r.primaryAvailable.Load() {
		return r.fallback
	}
	if r.fallback == nil {
		return r.primary
	}
	used, err := r.primary.UsageBytes(ctx)
	if err != nil {
		// Stay on primary; the next refresh will retry. The free-tier
		// limit isn't catastrophic to overshoot briefly — OCI returns a
		// quota error and we'd surface it to the caller. Better than
		// proactively dumping every upload onto block storage when the
		// usage poller has a hiccup.
		logx.L().Warn("storage.usage_unknown", "err", err)
		return r.primary
	}
	if expectedSize < 0 {
		expectedSize = 0
	}
	if used+expectedSize >= r.thresholdBytes {
		logx.L().Info("storage.fallback",
			"used", used, "threshold", r.thresholdBytes, "expected", expectedSize,
		)
		return r.fallback
	}
	return r.primary
}

// Put streams body via the picked backend.
func (r *Router) Put(ctx context.Context, body io.Reader, opts PutOpts) (ObjectMeta, error) {
	be := r.Pick(ctx, opts.Size)
	if be == nil {
		return ObjectMeta{}, errors.New("storage: no backend available")
	}
	return be.Put(ctx, body, opts)
}

// Resolve returns the right backend for an existing object id.
func (r *Router) Resolve(id string) (Backend, string, error) {
	backend, _, key, err := Decode(id)
	if err != nil {
		return nil, "", err
	}
	switch backend {
	case BackendOCI:
		if r.primary == nil {
			return nil, "", errors.New("storage: primary backend not configured")
		}
		return r.primary, key, nil
	case BackendBlock:
		if r.fallback == nil {
			return nil, "", errors.New("storage: block backend not configured")
		}
		return r.fallback, key, nil
	}
	return nil, "", errors.New("storage: unknown backend in id")
}

// UsageReport is the JSON shape returned by /v1/storage/usage. Callers
// (and humans inspecting the dashboard) can read whether new uploads
// will land in OS or block from this single endpoint.
type UsageReport struct {
	PrimaryName       string `json:"primary"`
	PrimaryUsedBytes  int64  `json:"primary_used_bytes"`
	PrimaryHealthy    bool   `json:"primary_healthy"`
	FallbackName      string `json:"fallback"`
	FallbackUsedBytes int64  `json:"fallback_used_bytes"`
	FallbackHealthy   bool   `json:"fallback_healthy"`
	ThresholdBytes    int64  `json:"threshold_bytes"`
	NextUploadGoesTo  string `json:"next_upload_goes_to"`
	GeneratedAt       string `json:"generated_at"`
}

func (r *Router) Usage(ctx context.Context) UsageReport {
	rep := UsageReport{
		ThresholdBytes: r.thresholdBytes,
		GeneratedAt:    time.Now().UTC().Format(time.RFC3339Nano),
	}
	if r.primary != nil {
		rep.PrimaryName = r.primary.Name()
		rep.PrimaryHealthy = r.primary.Healthy(ctx)
		if u, err := r.primary.UsageBytes(ctx); err == nil {
			rep.PrimaryUsedBytes = u
		}
	}
	if r.fallback != nil {
		rep.FallbackName = r.fallback.Name()
		rep.FallbackHealthy = r.fallback.Healthy(ctx)
		if u, err := r.fallback.UsageBytes(ctx); err == nil {
			rep.FallbackUsedBytes = u
		}
	}
	be := r.Pick(ctx, 0)
	if be != nil {
		rep.NextUploadGoesTo = be.Name()
	}
	return rep
}
