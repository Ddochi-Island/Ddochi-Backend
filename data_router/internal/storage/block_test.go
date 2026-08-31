package storage

import (
	"bytes"
	"context"
	"crypto/rand"
	"io"
	"strings"
	"testing"
)

func newTestBlockBackend(t *testing.T) *BlockBackend {
	t.Helper()
	root := t.TempDir()
	secret := make([]byte, 32)
	_, _ = rand.Read(secret)
	bb, err := NewBlockBackend(BlockOpts{
		Root:             root,
		URLBase:          "https://router.test",
		URLPathPrefix:    "/v1/storage/blob",
		URLSigningSecret: secret,
	})
	if err != nil {
		t.Fatalf("NewBlockBackend: %v", err)
	}
	return bb
}

func TestBlockPutGetRoundTrip(t *testing.T) {
	bb := newTestBlockBackend(t)
	payload := []byte("hello, blob")
	meta, err := bb.Put(context.Background(), bytes.NewReader(payload), PutOpts{
		ContentType: "text/plain",
		Size:        int64(len(payload)),
	})
	if err != nil {
		t.Fatal(err)
	}
	if meta.Size != int64(len(payload)) {
		t.Errorf("size %d, want %d", meta.Size, len(payload))
	}
	if meta.SHA256 == "" {
		t.Error("missing sha256")
	}
	if meta.Backend != BackendBlock {
		t.Errorf("backend=%s", meta.Backend)
	}

	rc, m2, err := bb.Get(context.Background(), meta.Key)
	if err != nil {
		t.Fatal(err)
	}
	defer rc.Close()
	if m2.SHA256 != meta.SHA256 {
		t.Errorf("sha mismatch: %s vs %s", m2.SHA256, meta.SHA256)
	}
	got, _ := io.ReadAll(rc)
	if string(got) != string(payload) {
		t.Errorf("got %q, want %q", got, payload)
	}
}

func TestBlockUsageTracksPutsAndDeletes(t *testing.T) {
	bb := newTestBlockBackend(t)
	if u, _ := bb.UsageBytes(context.Background()); u != 0 {
		t.Fatalf("initial usage = %d", u)
	}
	// 3 uploads
	var keys []string
	for i := 0; i < 3; i++ {
		m, err := bb.Put(context.Background(), strings.NewReader("12345"), PutOpts{Size: 5})
		if err != nil {
			t.Fatal(err)
		}
		keys = append(keys, m.Key)
	}
	got, _ := bb.UsageBytes(context.Background())
	if got != 15 {
		t.Errorf("after 3 puts: %d, want 15", got)
	}
	if err := bb.Delete(context.Background(), keys[0]); err != nil {
		t.Fatal(err)
	}
	got, _ = bb.UsageBytes(context.Background())
	if got != 10 {
		t.Errorf("after 1 delete: %d, want 10", got)
	}
	// idempotent delete
	if err := bb.Delete(context.Background(), keys[0]); err != nil {
		t.Fatal(err)
	}
}

func TestBlockNotFound(t *testing.T) {
	bb := newTestBlockBackend(t)
	_, _, err := bb.Get(context.Background(), "ab/nonexistent.png")
	if err != ErrNotFound {
		t.Errorf("got %v, want ErrNotFound", err)
	}
	_, err = bb.Head(context.Background(), "ab/nonexistent.png")
	if err != ErrNotFound {
		t.Errorf("Head: got %v, want ErrNotFound", err)
	}
}

func TestBlockDownloadURLContainsToken(t *testing.T) {
	bb := newTestBlockBackend(t)
	m, err := bb.Put(context.Background(), strings.NewReader("x"), PutOpts{Size: 1})
	if err != nil {
		t.Fatal(err)
	}
	url, exp, err := bb.DownloadURL(context.Background(), m.Key, 0)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.HasPrefix(url, "https://router.test/v1/storage/blob/") {
		t.Errorf("unexpected url: %s", url)
	}
	if exp.IsZero() {
		t.Error("missing expiry")
	}
}

func TestBlockKeyTraversalGuard(t *testing.T) {
	bb := newTestBlockBackend(t)
	// Forged key trying to escape root.
	abs := bb.absPath("../../etc/passwd")
	if !strings.HasPrefix(abs, bb.root) {
		t.Errorf("absPath escaped root: %s (root=%s)", abs, bb.root)
	}
}
