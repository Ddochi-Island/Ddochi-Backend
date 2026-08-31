// block.go is the local-filesystem backend.
//
// Files are stored under <root>/<shard>/<uuid><.ext>, where <shard> is
// the first 2 hex chars of the UUID. The fan-out keeps any one
// directory's entry count manageable on stock filesystems (ext4/xfs).
//
// Metadata sidecar: each file <name> has a sibling <name>.meta.json
// holding the original ContentType + SHA256 + size. We don't trust
// filesystem mtime for created_at — we capture it from the upload time
// and persist it. Sidecar reads happen on Get/Head; stale sidecars
// (file deleted but meta left behind) are tolerated and treated as
// missing.
//
// Atomicity: writes go to "<dst>.tmp" then os.Rename to <dst>. The
// rename is atomic on POSIX; on Windows it is atomic when the target
// doesn't pre-exist (we use unique UUID names so this is fine).
package storage

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path"
	"path/filepath"
	"strings"
	"sync/atomic"
	"time"
)

type BlockBackend struct {
	root string

	urlBase    string // e.g. "https://router.internal:8080" — used to build download URLs
	urlSecret  []byte // HMAC key for signed URLs
	urlPathPfx string // e.g. "/v1/storage/blob"

	// usage cache: scanning the tree on every check would be wasteful.
	// Workers update Atomically on Put/Delete; we re-scan on startup and
	// every refreshEvery as a backstop for drift.
	usageBytes atomic.Int64
	healthy    atomic.Bool
}

type BlockOpts struct {
	Root            string
	URLBase         string
	URLPathPrefix   string
	URLSigningSecret []byte
}

// NewBlockBackend opens or creates the root directory and bootstraps
// the usage counter by walking the tree. The walk is one-time per
// process and runs on the boot path; it's bounded by the number of
// stored files, which is much smaller than total bytes.
func NewBlockBackend(opts BlockOpts) (*BlockBackend, error) {
	if opts.Root == "" {
		return nil, errors.New("block: root path required")
	}
	if len(opts.URLSigningSecret) < 16 {
		return nil, errors.New("block: signing secret must be >= 16 bytes")
	}
	if err := os.MkdirAll(opts.Root, 0o750); err != nil {
		return nil, fmt.Errorf("block: mkdir root: %w", err)
	}
	pfx := opts.URLPathPrefix
	if pfx == "" {
		pfx = "/v1/storage/blob"
	}
	b := &BlockBackend{
		root:       opts.Root,
		urlBase:    strings.TrimRight(opts.URLBase, "/"),
		urlSecret:  opts.URLSigningSecret,
		urlPathPfx: pfx,
	}
	if err := b.initUsage(); err != nil {
		return nil, err
	}
	b.healthy.Store(true)
	return b, nil
}

func (b *BlockBackend) Name() string { return BackendBlock }

func (b *BlockBackend) Healthy(_ context.Context) bool { return b.healthy.Load() }

func (b *BlockBackend) UsageBytes(_ context.Context) (int64, error) {
	return b.usageBytes.Load(), nil
}

// initUsage walks the root once at boot to compute total bytes. Sidecar
// .meta.json files are counted too; their size is small and including
// them keeps the math consistent with disk reality.
func (b *BlockBackend) initUsage() error {
	var total int64
	err := filepath.WalkDir(b.root, func(p string, d os.DirEntry, err error) error {
		if err != nil {
			return nil // tolerate broken dir entries
		}
		if d.IsDir() {
			return nil
		}
		info, err := d.Info()
		if err != nil {
			return nil
		}
		total += info.Size()
		return nil
	})
	if err != nil {
		return fmt.Errorf("block: walk root: %w", err)
	}
	b.usageBytes.Store(total)
	return nil
}

// newKey returns a key of the form "<shard>/<uuid><.ext>". Shard is the
// first 2 chars of the uuid hex; the uuid is 16 bytes of crypto/rand.
func newKey(contentType string) string {
	var raw [16]byte
	_, _ = rand.Read(raw[:])
	id := hex.EncodeToString(raw[:])
	shard := id[:2]
	ext := extFromContentType(contentType)
	return shard + "/" + id + ext
}

func extFromContentType(ct string) string {
	switch strings.ToLower(strings.SplitN(ct, ";", 2)[0]) {
	case "image/png":
		return ".png"
	case "image/jpeg":
		return ".jpg"
	case "image/webp":
		return ".webp"
	case "image/gif":
		return ".gif"
	case "image/heic":
		return ".heic"
	case "application/pdf":
		return ".pdf"
	case "application/json":
		return ".json"
	case "text/plain":
		return ".txt"
	}
	return ""
}

func (b *BlockBackend) absPath(key string) string {
	// Block keys we generate look like "ab/<uuid>.png" — never absolute,
	// never contain "..". We still defensively clean and guard against
	// paths that try to escape the root in case a malicious or buggy
	// caller forges a key.
	clean := path.Clean("/" + key)[1:]
	return filepath.Join(b.root, filepath.FromSlash(clean))
}

// Put streams body to disk while computing SHA-256 in one pass and
// writing a metadata sidecar atomically.
func (b *BlockBackend) Put(ctx context.Context, body io.Reader, opts PutOpts) (ObjectMeta, error) {
	key := newKey(opts.ContentType)
	dst := b.absPath(key)
	if err := os.MkdirAll(filepath.Dir(dst), 0o750); err != nil {
		return ObjectMeta{}, fmt.Errorf("block: mkdir shard: %w", err)
	}
	tmp := dst + ".tmp"
	f, err := os.OpenFile(tmp, os.O_CREATE|os.O_WRONLY|os.O_EXCL, 0o640)
	if err != nil {
		return ObjectMeta{}, fmt.Errorf("block: create tmp: %w", err)
	}
	cleanup := func() {
		_ = f.Close()
		_ = os.Remove(tmp)
	}

	h := sha256.New()
	written, err := io.Copy(io.MultiWriter(f, h), wrapCtx(ctx, body))
	if err != nil {
		cleanup()
		return ObjectMeta{}, fmt.Errorf("block: copy: %w", err)
	}
	if err := f.Sync(); err != nil {
		cleanup()
		return ObjectMeta{}, fmt.Errorf("block: fsync: %w", err)
	}
	if err := f.Close(); err != nil {
		_ = os.Remove(tmp)
		return ObjectMeta{}, fmt.Errorf("block: close tmp: %w", err)
	}

	meta := ObjectMeta{
		ID:          EncodeBlock(key),
		Backend:     BackendBlock,
		Key:         key,
		Size:        written,
		ContentType: opts.ContentType,
		SHA256:      hex.EncodeToString(h.Sum(nil)),
		CreatedAt:   time.Now().UTC(),
	}

	// Persist sidecar BEFORE the file rename so a crash doesn't leave a
	// file with no metadata. If the sidecar write fails we abort.
	if err := writeSidecar(dst+".meta.json", meta); err != nil {
		_ = os.Remove(tmp)
		return ObjectMeta{}, err
	}
	if err := os.Rename(tmp, dst); err != nil {
		_ = os.Remove(tmp)
		_ = os.Remove(dst + ".meta.json")
		return ObjectMeta{}, fmt.Errorf("block: rename: %w", err)
	}
	b.usageBytes.Add(written)
	return meta, nil
}

func writeSidecar(path string, m ObjectMeta) error {
	tmp := path + ".tmp"
	f, err := os.OpenFile(tmp, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o640)
	if err != nil {
		return fmt.Errorf("block: sidecar create: %w", err)
	}
	if err := json.NewEncoder(f).Encode(&m); err != nil {
		_ = f.Close()
		_ = os.Remove(tmp)
		return fmt.Errorf("block: sidecar encode: %w", err)
	}
	if err := f.Close(); err != nil {
		_ = os.Remove(tmp)
		return fmt.Errorf("block: sidecar close: %w", err)
	}
	return os.Rename(tmp, path)
}

func readSidecar(path string) (ObjectMeta, error) {
	f, err := os.Open(path)
	if err != nil {
		return ObjectMeta{}, err
	}
	defer f.Close()
	var m ObjectMeta
	if err := json.NewDecoder(f).Decode(&m); err != nil {
		return ObjectMeta{}, fmt.Errorf("block: sidecar decode: %w", err)
	}
	return m, nil
}

func (b *BlockBackend) Get(ctx context.Context, key string) (io.ReadCloser, ObjectMeta, error) {
	abs := b.absPath(key)
	meta, err := b.Head(ctx, key)
	if err != nil {
		return nil, ObjectMeta{}, err
	}
	f, err := os.Open(abs)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return nil, ObjectMeta{}, ErrNotFound
		}
		return nil, ObjectMeta{}, err
	}
	return f, meta, nil
}

func (b *BlockBackend) Head(_ context.Context, key string) (ObjectMeta, error) {
	dst := b.absPath(key)
	info, err := os.Stat(dst)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return ObjectMeta{}, ErrNotFound
		}
		return ObjectMeta{}, err
	}
	meta, err := readSidecar(dst + ".meta.json")
	if err != nil && !errors.Is(err, os.ErrNotExist) {
		return ObjectMeta{}, err
	}
	if errors.Is(err, os.ErrNotExist) {
		// Fall back to filesystem-only metadata — the object is still
		// usable, we just don't have ContentType/SHA. Better than 500.
		meta = ObjectMeta{
			ID:        EncodeBlock(key),
			Backend:   BackendBlock,
			Key:       key,
			CreatedAt: info.ModTime().UTC(),
		}
	}
	meta.Size = info.Size()
	return meta, nil
}

func (b *BlockBackend) Delete(_ context.Context, key string) error {
	dst := b.absPath(key)
	info, err := os.Stat(dst)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return nil // idempotent
		}
		return err
	}
	if err := os.Remove(dst); err != nil && !errors.Is(err, os.ErrNotExist) {
		return err
	}
	_ = os.Remove(dst + ".meta.json")
	b.usageBytes.Add(-info.Size())
	return nil
}

func (b *BlockBackend) DownloadURL(_ context.Context, key string, ttl time.Duration) (string, time.Time, error) {
	if ttl <= 0 {
		ttl = 60 * time.Second
	}
	if ttl > 5*time.Minute {
		ttl = 5 * time.Minute
	}
	expires := time.Now().Add(ttl).UTC()
	tok := SignBlockToken(b.urlSecret, key, expires)
	url := b.urlBase + b.urlPathPfx + "/" + tok
	return url, expires, nil
}

// ─── helpers ───

// wrapCtx wraps an io.Reader so Read returns ctx.Err() when the context
// is canceled mid-stream. Used to make Put cancelable promptly when an
// HTTP client disconnects during upload.
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
