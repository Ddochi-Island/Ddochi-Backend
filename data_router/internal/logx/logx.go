// Package logx is a thin wrapper over slog that gives every component the
// same JSON-structured logger and lets us swap the destination later
// (stdout → OCI Logging) without touching call sites.
package logx

import (
	"log/slog"
	"os"
	"strings"
	"sync/atomic"
)

var def atomic.Pointer[slog.Logger]

func init() {
	level := slog.LevelInfo
	if v := strings.ToLower(os.Getenv("LOG_LEVEL")); v != "" {
		switch v {
		case "debug":
			level = slog.LevelDebug
		case "warn", "warning":
			level = slog.LevelWarn
		case "error":
			level = slog.LevelError
		}
	}
	h := slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: level})
	def.Store(slog.New(h).With("svc", "data_router"))
}

func L() *slog.Logger { return def.Load() }

// With returns a derived logger with extra fields.
func With(args ...any) *slog.Logger { return def.Load().With(args...) }
