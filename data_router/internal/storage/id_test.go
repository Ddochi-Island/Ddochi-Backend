package storage

import "testing"

func TestEncodeDecodeRoundTrip(t *testing.T) {
	cases := []struct {
		name   string
		id     string
		backend, bucket, key string
	}{
		{"oci nested key", "o:univ_attachments/2026/04/uuid.png", BackendOCI, "univ_attachments", "2026/04/uuid.png"},
		{"oci flat key", "o:b/k", BackendOCI, "b", "k"},
		{"block", "b:ab/abc.png", BackendBlock, "", "ab/abc.png"},
		{"block deeply nested", "b:ab/cd/ef/long-key.bin", BackendBlock, "", "ab/cd/ef/long-key.bin"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			be, bk, k, err := Decode(c.id)
			if err != nil {
				t.Fatalf("decode: %v", err)
			}
			if be != c.backend || bk != c.bucket || k != c.key {
				t.Fatalf("decode: be=%s bucket=%s key=%s", be, bk, k)
			}
		})
	}
	if got := EncodeOCI("univ_attachments", "2026/04/uuid.png"); got != "o:univ_attachments/2026/04/uuid.png" {
		t.Errorf("encode oci: %s", got)
	}
	if got := EncodeBlock("ab/abc.png"); got != "b:ab/abc.png" {
		t.Errorf("encode block: %s", got)
	}
}

func TestDecodeRejectsMalformed(t *testing.T) {
	cases := []string{"", "garbage", "o:nobucketslashkey", "o:", "b:", "x:foo"}
	for _, c := range cases {
		if _, _, _, err := Decode(c); err == nil {
			t.Errorf("%q: expected error", c)
		}
	}
}
