package uploadq

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"os"
	"strings"
	"testing"
)

func TestSpoolWritesFileAndComputesSHA(t *testing.T) {
	dir := t.TempDir()
	payload := []byte("hello world")
	path, size, sha, err := Spool(context.Background(), bytes.NewReader(payload), dir, 1024)
	if err != nil {
		t.Fatal(err)
	}
	defer os.Remove(path)
	if size != int64(len(payload)) {
		t.Errorf("size %d, want %d", size, len(payload))
	}
	expectedHash := sha256.Sum256(payload)
	if sha != hex.EncodeToString(expectedHash[:]) {
		t.Errorf("sha %s, want %s", sha, hex.EncodeToString(expectedHash[:]))
	}
	got, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if string(got) != string(payload) {
		t.Errorf("file content mismatch")
	}
}

func TestSpoolRejectsTooLarge(t *testing.T) {
	dir := t.TempDir()
	_, _, _, err := Spool(context.Background(), strings.NewReader("hello world"), dir, 5)
	if !errors.Is(err, ErrPayloadTooLarge) {
		t.Fatalf("want ErrPayloadTooLarge, got %v", err)
	}
	// no leftover spool files
	entries, _ := os.ReadDir(dir)
	for _, e := range entries {
		if !e.IsDir() {
			t.Errorf("leftover file: %s", e.Name())
		}
	}
}

func TestSpoolRespectsContextCancel(t *testing.T) {
	dir := t.TempDir()
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	_, _, _, err := Spool(ctx, bytes.NewReader([]byte("x")), dir, 1024)
	if err == nil {
		t.Fatal("expected error from cancelled context")
	}
}

func TestSpoolEmptyBody(t *testing.T) {
	dir := t.TempDir()
	path, size, sha, err := Spool(context.Background(), bytes.NewReader(nil), dir, 1024)
	if err != nil {
		t.Fatal(err)
	}
	defer os.Remove(path)
	if size != 0 {
		t.Errorf("size %d, want 0", size)
	}
	emptySha := sha256.Sum256(nil)
	if sha != hex.EncodeToString(emptySha[:]) {
		t.Errorf("sha mismatch")
	}
}
