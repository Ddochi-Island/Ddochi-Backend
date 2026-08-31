// signed.go produces and verifies HMAC tokens used as block-storage
// download URLs. The router itself serves block files at
// /v1/storage/blob/<token> and validates the token before reading the
// file.
//
// Token format (one URL-safe base64 envelope):
//
//   base64url( key_b64 "." exp "." sig_b64 )
//
// where:
//   key_b64 = base64url(key)        — encoded so a key containing '.' / '/'
//                                     can't break the inner Split.
//   exp     = decimal unix seconds
//   sig_b64 = base64url(HMAC-SHA256(secret, key + "|" + exp))
//
// HMAC-SHA256 with a constant-time compare on verify; no timing attack
// surface. The secret never leaves the router process.
package storage

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"strconv"
	"strings"
	"time"
)

func SignBlockToken(secret []byte, key string, expires time.Time) string {
	exp := strconv.FormatInt(expires.Unix(), 10)
	mac := hmac.New(sha256.New, secret)
	mac.Write([]byte(key))
	mac.Write([]byte{'|'})
	mac.Write([]byte(exp))
	sig := mac.Sum(nil)
	body := base64.RawURLEncoding.EncodeToString([]byte(key)) +
		"." + exp + "." + base64.RawURLEncoding.EncodeToString(sig)
	return base64.RawURLEncoding.EncodeToString([]byte(body))
}

// VerifyBlockToken returns the key carried by a valid, unexpired token.
// All errors collapse to ErrUnauthorized so handlers don't expose which
// check failed.
func VerifyBlockToken(secret []byte, token string) (key string, err error) {
	body, err := base64.RawURLEncoding.DecodeString(token)
	if err != nil {
		return "", ErrUnauthorized
	}
	parts := strings.SplitN(string(body), ".", 3)
	if len(parts) != 3 {
		return "", ErrUnauthorized
	}
	keyB64, expStr, sigB64 := parts[0], parts[1], parts[2]
	keyBytes, err := base64.RawURLEncoding.DecodeString(keyB64)
	if err != nil {
		return "", ErrUnauthorized
	}
	exp, err := strconv.ParseInt(expStr, 10, 64)
	if err != nil {
		return "", ErrUnauthorized
	}
	if time.Now().Unix() > exp {
		return "", ErrUnauthorized
	}
	gotSig, err := base64.RawURLEncoding.DecodeString(sigB64)
	if err != nil {
		return "", ErrUnauthorized
	}
	mac := hmac.New(sha256.New, secret)
	mac.Write(keyBytes)
	mac.Write([]byte{'|'})
	mac.Write([]byte(expStr))
	if !hmac.Equal(gotSig, mac.Sum(nil)) {
		return "", ErrUnauthorized
	}
	return string(keyBytes), nil
}

