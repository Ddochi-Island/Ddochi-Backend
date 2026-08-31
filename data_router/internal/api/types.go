// Package api defines the wire format spoken between caller services and
// the data router. The shapes here are the single contract — any change is
// a breaking change for every caller, so add fields, never remove or repurpose.
package api

import (
	"encoding/json"
	"time"
)

// Op is the kind of database operation the caller wants performed.
type Op string

const (
	OpQuery Op = "query"  // SELECT or any cursor-returning statement; rows + columns come back
	OpExec  Op = "exec"   // single DML / DDL / PL/SQL block; returns rows-affected
	OpTx    Op = "tx"     // ordered list of Statements executed in one transaction
	OpProc  Op = "proc"   // PL/SQL stored procedure call (named binds in Args)
	OpPing  Op = "ping"   // health probe — short-circuits the queue
)

// Priority controls which lane a request lands in. Lanes are drained
// high → normal → low; within a lane it's FIFO with per-caller fairness.
type Priority string

const (
	PriorityHigh   Priority = "high"
	PriorityNormal Priority = "normal"
	PriorityLow    Priority = "low"
)

// Statement is one unit of SQL with positional or named bind args.
// Args may contain JSON-native types (string, number, bool, null) plus the
// special tagged forms produced by EncodeArg below for raw bytes / time.
type Statement struct {
	SQL  string `json:"sql"`
	Args []any  `json:"args,omitempty"`

	// FetchLimit caps the number of rows returned for this statement.
	// 0 means "use server default (DefaultFetchLimit)". The router will
	// always cap to MaxFetchLimit regardless of caller value — this
	// protects memory when a caller forgets a WHERE clause.
	FetchLimit int `json:"fetch_limit,omitempty"`
}

// Request is what callers POST to /v1/exec.
type Request struct {
	// Caller identifies the originating service. Used for fairness, rate
	// limiting, and audit logs. Required. Free-form short string.
	Caller string `json:"caller"`

	Op   Op       `json:"op"`
	Stmt *Statement `json:"stmt,omitempty"` // for query|exec|proc

	// Statements is used only for OpTx — executed in order in one transaction.
	Statements []Statement `json:"statements,omitempty"`

	Priority Priority `json:"priority,omitempty"` // default normal

	// CacheTTLMs: if > 0 and Op==OpQuery, identical (op, sql, args) within
	// this window returns the cached response without hitting the DB.
	// Recommended 1000–2000 for hot dashboards. Ignored for non-query ops.
	CacheTTLMs int `json:"cache_ttl_ms,omitempty"`

	// IdempotencyKey: for writes (exec|tx|proc), the router caches the
	// response keyed on (Caller, IdempotencyKey) for IdempotencyWindowMs.
	// A retry with the same key returns the cached result without
	// re-executing — safe for at-least-once delivery from callers.
	IdempotencyKey string `json:"idempotency_key,omitempty"`

	// TimeoutMs caps total time (queue + execution). 0 → server default.
	// The router will always cap to MaxTimeoutMs.
	TimeoutMs int `json:"timeout_ms,omitempty"`
}

// Response is what /v1/exec returns. Always JSON; always has Status.
type Response struct {
	Status   string  `json:"status"`             // "ok" | "error" | "rejected"
	Error    *ErrInfo `json:"error,omitempty"`

	// For OpQuery
	Columns []string          `json:"columns,omitempty"`
	Rows    []json.RawMessage `json:"rows,omitempty"` // each row = JSON array, ordered by Columns
	Truncated bool            `json:"truncated,omitempty"` // true if FetchLimit hit

	// For OpExec / OpTx / OpProc
	RowsAffected int64 `json:"rows_affected,omitempty"`
	Out          map[string]any `json:"out,omitempty"` // proc OUT params

	// Meta — always populated.
	Meta Meta `json:"meta"`
}

// ErrInfo carries enough detail for callers to decide retry/abort.
// Code is a stable machine-readable token; Message is for logs.
type ErrInfo struct {
	Code    string `json:"code"`    // e.g. "queue_full", "timeout", "db_unavailable", "bad_request", "ora_xxxxx"
	Message string `json:"message"`
	OraCode int    `json:"ora_code,omitempty"` // numeric Oracle error if applicable
	Retryable bool `json:"retryable"`
}

type Meta struct {
	RequestID    string `json:"request_id"`
	QueuedMs     int64  `json:"queued_ms"`     // time spent in queue
	ExecMs       int64  `json:"exec_ms"`       // time inside DB call
	TotalMs      int64  `json:"total_ms"`
	CacheHit     bool   `json:"cache_hit,omitempty"`
	IdempotentHit bool  `json:"idempotent_hit,omitempty"`
	Lane         string `json:"lane,omitempty"`
	Coalesced    bool   `json:"coalesced,omitempty"` // true if this request was served by a singleflight leader
	ServerTime   string `json:"server_time"`         // RFC3339Nano
}

// NowMeta builds a Meta with ServerTime set to now.
func NowMeta(reqID string) Meta {
	return Meta{RequestID: reqID, ServerTime: time.Now().UTC().Format(time.RFC3339Nano)}
}

// Stable error codes — keep in sync with documentation in README.
const (
	CodeBadRequest      = "bad_request"
	CodeUnauthorized    = "unauthorized"
	CodeQueueFull       = "queue_full"
	CodeTimeout         = "timeout"
	CodeDBUnavailable   = "db_unavailable"
	CodeBreakerOpen     = "breaker_open"
	CodeInternal        = "internal"
	CodeShuttingDown    = "shutting_down"
	CodeOracleError     = "oracle_error"
	CodePayloadTooLarge = "payload_too_large"
)
