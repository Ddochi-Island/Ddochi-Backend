// Package storage is the second backend the data_router speaks to.
//
// Two physical stores:
//
//   1. OCI Object Storage (primary)  — durable, presigned URLs (PARs), 10 GiB
//      free tier. Caller services download directly from OS over the public
//      endpoint via short-lived PAR URLs minted by the router.
//
//   2. Block filesystem (fallback)   — local mount on the data_router host
//      (typically an OCI Block Volume attached to the VM). Used when the
//      OS bucket is approaching the free-tier ceiling. Files are served by
//      the router itself via HMAC-signed URLs since block volumes have no
//      HTTP frontdoor of their own.
//
// Per-upload routing decision is made by Router.Pick() from current OS
// usage vs. a configured threshold. Once stored, an object never moves
// across backends — its ObjectID encodes the backend and is permanent.
//
// ObjectID format (caller stores this verbatim in the DB):
//
//   o:<bucket>/<key>     — OCI Object Storage
//   b:<shard>/<uuid.ext> — Block filesystem
//
// We encode the backend into the id so the router can dispatch reads
// without a DB round-trip and without an extra "backend" column being
// strictly required (though the schema delta does add one for analytics).
package storage

import (
	"context"
	"errors"
	"io"
	"time"
)

var (
	ErrNotFound       = errors.New("storage: object not found")
	ErrPayloadTooLarge = errors.New("storage: payload exceeds limit")
	ErrUnauthorized    = errors.New("storage: signature invalid or expired")
	ErrBackendDown     = errors.New("storage: backend unavailable")
)

// ObjectMeta is the metadata we surface to callers. Size is authoritative
// (filled by the backend after the upload completes); ContentType and
// SHA256 are best-effort (computed during streaming for block, set from
// the OCI response for OS).
type ObjectMeta struct {
	ID          string    `json:"id"`           // canonical "o:..." or "b:..." form
	Backend     string    `json:"backend"`      // "oci_os" | "block"
	Bucket      string    `json:"bucket,omitempty"` // populated for oci_os only
	Key         string    `json:"key"`          // backend-specific key
	Size        int64     `json:"size"`
	ContentType string    `json:"content_type,omitempty"`
	SHA256      string    `json:"sha256,omitempty"`
	CreatedAt   time.Time `json:"created_at"`
}

// PutOpts is what the caller hands to a backend at upload time.
// Size is allowed to be -1 when the request is chunked (we'll discover
// it after streaming completes), but providing a known size lets the OCI
// backend issue a single-shot PUT instead of a multipart upload.
//
// SHA256 (if non-empty) tells the backend "I already computed this; use
// it instead of recomputing." The uploadq spool path computes the hash
// while writing to disk, so handing it through avoids a second pass over
// the bytes inside the OCI backend.
type PutOpts struct {
	ContentType string
	Size        int64
	SHA256      string
}

// Backend is the contract every storage tier implements. Methods take a
// context so a caller hangup propagates through to the underlying SDK
// call and we don't burn time on a doomed transfer.
type Backend interface {
	Name() string

	// Put writes body. Returns the canonical ObjectMeta including the
	// permanent ObjectID that callers should store in the DB.
	Put(ctx context.Context, body io.Reader, opts PutOpts) (ObjectMeta, error)

	// Get streams the object body. Caller MUST Close the returned reader.
	// For block storage this opens an os.File; for OCI it wraps an HTTP
	// response body.
	Get(ctx context.Context, key string) (io.ReadCloser, ObjectMeta, error)

	// Head returns metadata without transferring bytes. Cheap.
	Head(ctx context.Context, key string) (ObjectMeta, error)

	Delete(ctx context.Context, key string) error

	// DownloadURL returns a URL the caller can use directly without
	// involving the router again. For OCI this is a PAR; for block this
	// is a router-relative HMAC-signed path.
	DownloadURL(ctx context.Context, key string, ttl time.Duration) (url string, expiresAt time.Time, err error)

	// UsageBytes returns total bytes currently held by the backend, used
	// by the Router to decide when to fall back. Implementations should
	// cache aggressively to avoid hitting backend rate limits.
	UsageBytes(ctx context.Context) (int64, error)

	Healthy(ctx context.Context) bool
}
