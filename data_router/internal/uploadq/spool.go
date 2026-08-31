// spool.go drains an HTTP request body to a local temp file while
// computing SHA-256 in one streaming pass. The result is a path the
// worker can re-open later.
//
// Why this matters on e2-micro: the alternative (buffering the body in
// memory until the worker is ready) holds the full upload in RAM, and
// 5 concurrent 10 MB uploads would consume half the box's memory.
// Streaming to disk keeps the hot path at ~64 KB regardless of upload
// size or queue depth.
package uploadq

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"os"
)

// ErrPayloadTooLarge mirrors http.MaxBytesError but keeps uploadq's
// public surface free of net/http imports.
var ErrPayloadTooLarge = errors.New("uploadq: payload exceeds limit")

// Spool reads from body into a fresh file under dir, returning the path
// + computed size + sha256. Bounded by maxBytes — anything over returns
// ErrPayloadTooLarge AND deletes the partial file.
//
// The spool file is created with mode 0640. The caller (worker) is
// responsible for deletion after upload, success or failure.
func Spool(ctx context.Context, body io.Reader, dir string, maxBytes int64) (path string, size int64, sha string, err error) {
	if err := os.MkdirAll(dir, 0o750); err != nil {
		return "", 0, "", fmt.Errorf("spool: mkdir: %w", err)
	}
	f, err := os.CreateTemp(dir, "spool-*")
	if err != nil {
		return "", 0, "", fmt.Errorf("spool: create: %w", err)
	}
	cleanup := func() {
		_ = f.Close()
		_ = os.Remove(f.Name())
	}

	h := sha256.New()
	limited := io.LimitReader(body, maxBytes+1) // +1 so we can detect overflow
	written, err := io.Copy(io.MultiWriter(f, h), wrapCtx(ctx, limited))
	if err != nil {
		cleanup()
		return "", 0, "", fmt.Errorf("spool: copy: %w", err)
	}
	if written > maxBytes {
		cleanup()
		return "", 0, "", ErrPayloadTooLarge
	}
	if err := f.Sync(); err != nil {
		cleanup()
		return "", 0, "", fmt.Errorf("spool: fsync: %w", err)
	}
	name := f.Name()
	if err := f.Close(); err != nil {
		_ = os.Remove(name)
		return "", 0, "", fmt.Errorf("spool: close: %w", err)
	}
	return name, written, hex.EncodeToString(h.Sum(nil)), nil
}

// wrapCtx makes Read return ctx.Err() so a caller hangup mid-upload
// terminates the copy promptly.
type ctxReader struct {
	ctx context.Context
	r   io.Reader
}

func (cr *ctxReader) Read(p []byte) (int, error) {
	if err := cr.ctx.Err(); err != nil {
		return 0, err
	}
	return cr.r.Read(p)
}

func wrapCtx(ctx context.Context, r io.Reader) io.Reader {
	return &ctxReader{ctx: ctx, r: r}
}
