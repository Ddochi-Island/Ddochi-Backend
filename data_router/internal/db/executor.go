// executor.go translates a high-level api.Request into one or more
// database/sql calls and produces a fully-formed api.Response.
//
// Stability rules:
//   - Every call has a context derived from the caller's deadline; we
//     never run a DB call without a deadline.
//   - We classify errors into "infrastructural" (breaker should care)
//     vs "application" (caller's problem). Only the former is reported
//     to the breaker.
//   - FetchLimit is enforced — we read at most FetchLimit+1 rows and
//     report Truncated=true if we hit the cap, so callers can detect
//     missing data instead of silently getting a clipped result set.
package db

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"strings"
	"time"

	"github.com/redesign2/services/data_router/internal/api"
)

type Executor struct {
	pool         *Pool
	defaultFetch int
	maxFetch     int
}

func NewExecutor(p *Pool, defaultFetch, maxFetch int) *Executor {
	return &Executor{pool: p, defaultFetch: defaultFetch, maxFetch: maxFetch}
}

// Run executes req under ctx and returns a response. The response Meta
// is partially populated (ExecMs); the caller fills in QueuedMs/TotalMs.
//
// classify() returns true for errors that should feed the circuit
// breaker — caller checks `infra` to decide whether to Report(false).
func (e *Executor) Run(ctx context.Context, req *api.Request) (resp *api.Response, infra bool) {
	start := time.Now()
	resp = &api.Response{}
	defer func() {
		resp.Meta.ExecMs = time.Since(start).Milliseconds()
	}()

	switch req.Op {
	case api.OpQuery:
		return e.runQuery(ctx, req)
	case api.OpExec:
		return e.runExec(ctx, req)
	case api.OpTx:
		return e.runTx(ctx, req)
	case api.OpProc:
		// Treated like exec for now; OUT params would need named binds we
		// don't yet expose in the API. Add when first caller needs them.
		return e.runExec(ctx, req)
	case api.OpPing:
		err := e.pool.DB.PingContext(ctx)
		if err != nil {
			r := &api.Response{Status: "error", Error: errInfo(err)}
			return r, isInfraErr(err)
		}
		return &api.Response{Status: "ok"}, false
	default:
		return errResp(api.CodeBadRequest, fmt.Sprintf("unknown op %q", req.Op), false), false
	}
}

func (e *Executor) runQuery(ctx context.Context, req *api.Request) (*api.Response, bool) {
	if req.Stmt == nil {
		return errResp(api.CodeBadRequest, "stmt required for query", false), false
	}
	limit := e.fetchLimit(req.Stmt.FetchLimit)

	rows, err := e.pool.DB.QueryContext(ctx, req.Stmt.SQL, req.Stmt.Args...)
	if err != nil {
		return errResp(api.CodeOracleError, err.Error(), isRetryable(err)), isInfraErr(err)
	}
	defer rows.Close()

	cols, err := rows.Columns()
	if err != nil {
		return errResp(api.CodeOracleError, err.Error(), isRetryable(err)), isInfraErr(err)
	}
	colKinds := detectColumnKinds(rows, len(cols))

	// Pre-allocate scan targets reused across rows.
	scanBuf := make([]any, len(cols))
	scanPtrs := make([]any, len(cols))
	for i := range scanBuf {
		scanPtrs[i] = &scanBuf[i]
	}

	out := make([]json.RawMessage, 0, 64)
	truncated := false
	for rows.Next() {
		if len(out) >= limit {
			truncated = true
			break
		}
		if err := rows.Scan(scanPtrs...); err != nil {
			return errResp(api.CodeOracleError, err.Error(), isRetryable(err)), isInfraErr(err)
		}
		row := make([]any, len(cols))
		for i, v := range scanBuf {
			if colKinds[i] == colJSON {
				row[i] = normalizeJSON(v)
			} else {
				row[i] = normalizeScalar(v)
			}
		}
		b, err := json.Marshal(row)
		if err != nil {
			return errResp(api.CodeInternal, "row marshal: "+err.Error(), false), false
		}
		out = append(out, b)
	}
	if err := rows.Err(); err != nil {
		return errResp(api.CodeOracleError, err.Error(), isRetryable(err)), isInfraErr(err)
	}

	return &api.Response{
		Status:    "ok",
		Columns:   cols,
		Rows:      out,
		Truncated: truncated,
	}, false
}

func (e *Executor) runExec(ctx context.Context, req *api.Request) (*api.Response, bool) {
	if req.Stmt == nil {
		return errResp(api.CodeBadRequest, "stmt required for exec/proc", false), false
	}
	res, err := e.pool.DB.ExecContext(ctx, req.Stmt.SQL, req.Stmt.Args...)
	if err != nil {
		return errResp(api.CodeOracleError, err.Error(), isRetryable(err)), isInfraErr(err)
	}
	rows, _ := res.RowsAffected() // err is non-nil only on drivers that don't support it
	return &api.Response{Status: "ok", RowsAffected: rows}, false
}

func (e *Executor) runTx(ctx context.Context, req *api.Request) (*api.Response, bool) {
	if len(req.Statements) == 0 {
		return errResp(api.CodeBadRequest, "statements required for tx", false), false
	}
	tx, err := e.pool.DB.BeginTx(ctx, nil)
	if err != nil {
		return errResp(api.CodeOracleError, err.Error(), isRetryable(err)), isInfraErr(err)
	}
	var totalRows int64
	for i, st := range req.Statements {
		res, err := tx.ExecContext(ctx, st.SQL, st.Args...)
		if err != nil {
			_ = tx.Rollback()
			msg := fmt.Sprintf("statement %d: %s", i, err.Error())
			return errResp(api.CodeOracleError, msg, isRetryable(err)), isInfraErr(err)
		}
		rc, _ := res.RowsAffected()
		totalRows += rc
	}
	if err := tx.Commit(); err != nil {
		return errResp(api.CodeOracleError, "commit: "+err.Error(), isRetryable(err)), isInfraErr(err)
	}
	return &api.Response{Status: "ok", RowsAffected: totalRows}, false
}

func (e *Executor) fetchLimit(asked int) int {
	if asked <= 0 {
		asked = e.defaultFetch
	}
	if asked > e.maxFetch {
		asked = e.maxFetch
	}
	return asked
}

// normalizeScalar converts driver-returned values into JSON-friendly
// shapes. Oracle's go-ora hands us:
//   - string for VARCHAR2/NVARCHAR2/CLOB (small)
//   - []byte for RAW/BLOB
//   - int64/float64 for NUMBER (driver chooses based on scale)
//   - time.Time for DATE/TIMESTAMP
//   - nil for NULL
func normalizeScalar(v any) any {
	switch x := v.(type) {
	case nil:
		return nil
	case []byte:
		// JSON encodes []byte as base64 — fine for callers expecting bytes.
		return x
	case time.Time:
		return x.UTC().Format(time.RFC3339Nano)
	default:
		return v
	}
}

// columnKind narrows column types we want to special-case during row
// marshaling. Anything else falls through to normalizeScalar.
type columnKind uint8

const (
	colDefault columnKind = iota
	colJSON
)

// detectColumnKinds inspects each column's database type name and tags
// JSON columns so the row marshaler can passthrough their bytes as raw
// JSON instead of base64-encoding them.
//
// Oracle 21c+ native JSON columns report DatabaseTypeName == "JSON".
// We're permissive about variants ("JSON_OBJECT", "JSON_ARRAY") in case
// the driver surfaces synthesized constructors. ColumnTypes() can fail
// (rare); on error we return an all-default slice of the requested
// length so callers can index safely without bounds-check ceremony.
func detectColumnKinds(rows *sql.Rows, n int) []columnKind {
	kinds := make([]columnKind, n)
	cts, err := rows.ColumnTypes()
	if err != nil {
		return kinds
	}
	for i, ct := range cts {
		if i >= n {
			break
		}
		switch strings.ToUpper(ct.DatabaseTypeName()) {
		case "JSON", "JSON_OBJECT", "JSON_ARRAY":
			kinds[i] = colJSON
		}
	}
	return kinds
}

// normalizeJSON returns the value as a json.RawMessage when it parses
// as valid JSON. For invalid bytes (which shouldn't happen for native
// JSON columns but might for legacy VARCHAR2-stored JSON) we fall back
// to normalizeScalar so we never lose data.
func normalizeJSON(v any) any {
	switch x := v.(type) {
	case nil:
		return nil
	case []byte:
		if len(x) == 0 {
			return nil
		}
		if json.Valid(x) {
			// Copy: scan buffer is reused across rows; without copying,
			// every row would alias the same backing array and the final
			// JSON output would all read like the last row's bytes.
			cp := make([]byte, len(x))
			copy(cp, x)
			return json.RawMessage(cp)
		}
		return x // base64 fallback via default JSON encoding of []byte
	case string:
		if x == "" {
			return nil
		}
		if json.Valid([]byte(x)) {
			return json.RawMessage(x)
		}
		return x
	default:
		return v
	}
}


// ─────────────────── error classification ───────────────────

// isInfraErr decides whether an error reflects a DB-side outage worthy
// of feeding the circuit breaker. We err on the side of "yes" only for
// clearly transport-level signals.
func isInfraErr(err error) bool {
	if err == nil {
		return false
	}
	if errors.Is(err, sql.ErrConnDone) || errors.Is(err, sql.ErrTxDone) {
		return true
	}
	if errors.Is(err, context.DeadlineExceeded) {
		// Could be a slow query (caller fault) or DB unresponsive (infra).
		// Treat as infra — repeated timeouts are exactly what the breaker
		// is for. False positives only delay traffic for OpenDuration.
		return true
	}
	var nerr net.Error
	if errors.As(err, &nerr) {
		return true
	}
	msg := err.Error()
	// Common transport-level Oracle errors.
	for _, s := range []string{
		"ORA-12541", // listener does not currently know of service
		"ORA-12543", // TNS:destination host unreachable
		"ORA-12545", // Connect failed because target host or object does not exist
		"ORA-12560", // TNS:protocol adapter error
		"ORA-12170", // TNS:Connect timeout
		"ORA-03113", // end-of-file on communication channel
		"ORA-03114", // not connected to ORACLE
		"ORA-03135", // connection lost contact
		"ORA-01089", // immediate shutdown in progress
		"ORA-01090", // shutdown in progress
		"ORA-01092", // ORACLE instance terminated
		"ORA-25408", // can not safely replay call
		"ORA-28000", // account locked (treat as infra so we don't hammer)
	} {
		if strings.Contains(msg, s) {
			return true
		}
	}
	return false
}

// isRetryable hints to the caller whether this specific request is
// worth retrying with the same payload. Application errors aren't.
func isRetryable(err error) bool {
	if err == nil {
		return false
	}
	if isInfraErr(err) {
		return true
	}
	msg := err.Error()
	for _, s := range []string{
		"ORA-00060", // deadlock detected
		"ORA-00054", // resource busy NOWAIT
		"ORA-08177", // can't serialize access (serializable txn)
		"ORA-04068", // existing state of packages discarded
	} {
		if strings.Contains(msg, s) {
			return true
		}
	}
	return false
}

func errResp(code, msg string, retryable bool) *api.Response {
	return &api.Response{
		Status: "error",
		Error: &api.ErrInfo{
			Code: code, Message: msg, Retryable: retryable,
		},
	}
}

func errInfo(err error) *api.ErrInfo {
	return &api.ErrInfo{
		Code:      api.CodeOracleError,
		Message:   err.Error(),
		Retryable: isRetryable(err),
	}
}
