package server

import (
	"context"
	"crypto/rand"
	"crypto/subtle"
	"encoding/hex"
	"net/http"
	"runtime/debug"
	"strings"
	"time"

	"github.com/redesign2/services/data_router/internal/logx"
)

type ctxKey int

const (
	ctxRequestID ctxKey = iota
)

func newRequestID() string {
	var b [12]byte
	if _, err := rand.Read(b[:]); err != nil {
		return "00000000"
	}
	return hex.EncodeToString(b[:])
}

func RequestIDOf(r *http.Request) string {
	if v, _ := r.Context().Value(ctxRequestID).(string); v != "" {
		return v
	}
	return ""
}

// requestID assigns/echoes X-Request-Id and stashes it in the context.
func requestIDMW(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		rid := r.Header.Get("X-Request-Id")
		if rid == "" {
			rid = newRequestID()
		}
		w.Header().Set("X-Request-Id", rid)
		ctx := context.WithValue(r.Context(), ctxRequestID, rid)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

// recoverMW catches panics, logs them with stack, and returns 500.
func recoverMW(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer func() {
			if rec := recover(); rec != nil {
				logx.L().Error("http.panic",
					"err", rec,
					"path", r.URL.Path,
					"method", r.Method,
					"request_id", RequestIDOf(r),
					"stack", string(debug.Stack()),
				)
				http.Error(w, `{"status":"error","error":{"code":"internal","message":"server error","retryable":false}}`, http.StatusInternalServerError)
			}
		}()
		next.ServeHTTP(w, r)
	})
}

// accessLogMW logs after the response is written. Skip for /metrics +
// /healthz to keep logs quiet under heavy probe traffic.
func accessLogMW(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/metrics" || r.URL.Path == "/healthz" || r.URL.Path == "/readyz" {
			next.ServeHTTP(w, r)
			return
		}
		start := time.Now()
		sw := &statusWriter{ResponseWriter: w, status: 200}
		next.ServeHTTP(sw, r)
		logx.L().Info("http.req",
			"method", r.Method,
			"path", r.URL.Path,
			"status", sw.status,
			"bytes", sw.bytes,
			"ms", time.Since(start).Milliseconds(),
			"request_id", RequestIDOf(r),
			"remote", r.RemoteAddr,
		)
	})
}

type statusWriter struct {
	http.ResponseWriter
	status int
	bytes  int
}

func (sw *statusWriter) WriteHeader(s int) {
	sw.status = s
	sw.ResponseWriter.WriteHeader(s)
}

func (sw *statusWriter) Write(b []byte) (int, error) {
	n, err := sw.ResponseWriter.Write(b)
	sw.bytes += n
	return n, err
}

// authMW enforces Authorization: Bearer <token> against the configured
// shared secret using constant-time comparison. Empty token disables
// auth (logged at boot as a warning).
func authMW(token string) func(http.Handler) http.Handler {
	expected := []byte("Bearer " + token)
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if token == "" {
				next.ServeHTTP(w, r)
				return
			}
			// /healthz + /readyz remain unauthenticated for orchestrators.
			if r.URL.Path == "/healthz" || r.URL.Path == "/readyz" {
				next.ServeHTTP(w, r)
				return
			}
			h := r.Header.Get("Authorization")
			if !strings.HasPrefix(h, "Bearer ") || subtle.ConstantTimeCompare([]byte(h), expected) != 1 {
				http.Error(w, `{"status":"error","error":{"code":"unauthorized","message":"missing or invalid bearer token","retryable":false}}`, http.StatusUnauthorized)
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}

// limitBody wraps r.Body in a MaxBytesReader so a malicious / buggy
// caller can't exhaust memory by streaming a huge JSON.
//
// Storage uploads bypass this middleware — they apply their own
// (larger) limit at the storage handler level. Without the skip, every
// upload would 413 at the middleware before reaching the handler.
func limitBodyMW(max int64) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.Method == http.MethodPost && r.URL.Path == "/v1/storage/upload" {
				next.ServeHTTP(w, r)
				return
			}
			r.Body = http.MaxBytesReader(w, r.Body, max)
			next.ServeHTTP(w, r)
		})
	}
}
