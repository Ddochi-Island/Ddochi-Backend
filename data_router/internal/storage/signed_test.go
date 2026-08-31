package storage

import (
	"crypto/rand"
	"strings"
	"testing"
	"time"
)

func TestSignVerifyRoundTrip(t *testing.T) {
	secret := make([]byte, 32)
	_, _ = rand.Read(secret)
	tok := SignBlockToken(secret, "ab/abc.png", time.Now().Add(time.Minute))
	got, err := VerifyBlockToken(secret, tok)
	if err != nil {
		t.Fatalf("verify: %v", err)
	}
	if got != "ab/abc.png" {
		t.Fatalf("key=%q", got)
	}
}

func TestExpiredTokenRejected(t *testing.T) {
	secret := make([]byte, 32)
	_, _ = rand.Read(secret)
	tok := SignBlockToken(secret, "k", time.Now().Add(-time.Minute))
	if _, err := VerifyBlockToken(secret, tok); err != ErrUnauthorized {
		t.Errorf("expired: got %v, want ErrUnauthorized", err)
	}
}

func TestTamperedTokenRejected(t *testing.T) {
	secret := make([]byte, 32)
	_, _ = rand.Read(secret)
	tok := SignBlockToken(secret, "k", time.Now().Add(time.Minute))
	// Flip a character in the middle.
	if len(tok) < 10 {
		t.Skip("token too short to mutate")
	}
	tampered := tok[:len(tok)/2] + flipChar(tok[len(tok)/2:len(tok)/2+1]) + tok[len(tok)/2+1:]
	if _, err := VerifyBlockToken(secret, tampered); err != ErrUnauthorized {
		t.Errorf("tampered: got %v, want ErrUnauthorized", err)
	}
}

func TestWrongSecretRejected(t *testing.T) {
	s1 := make([]byte, 32)
	s2 := make([]byte, 32)
	_, _ = rand.Read(s1)
	_, _ = rand.Read(s2)
	tok := SignBlockToken(s1, "k", time.Now().Add(time.Minute))
	if _, err := VerifyBlockToken(s2, tok); err != ErrUnauthorized {
		t.Errorf("wrong secret: got %v, want ErrUnauthorized", err)
	}
}

func TestMalformedTokenRejected(t *testing.T) {
	cases := []string{"", "not-base64-!@#$", "a.b", strings.Repeat("z", 200)}
	for _, c := range cases {
		if _, err := VerifyBlockToken([]byte("x"), c); err == nil {
			t.Errorf("malformed %q: nil error", c)
		}
	}
}

func flipChar(s string) string {
	if len(s) == 0 {
		return s
	}
	b := []byte(s)
	if b[0] == 'a' {
		b[0] = 'b'
	} else {
		b[0] = 'a'
	}
	return string(b)
}
