package db

import (
	"context"
	"encoding/json"
	"errors"
	"net"
	"testing"
	"time"
)

func TestNormalizeScalarTime(t *testing.T) {
	in := time.Date(2026, 4, 30, 12, 0, 0, 0, time.FixedZone("KST", 9*3600))
	out := normalizeScalar(in)
	s, ok := out.(string)
	if !ok {
		t.Fatalf("want string, got %T", out)
	}
	// Round-trip parses and is in UTC
	parsed, err := time.Parse(time.RFC3339Nano, s)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if parsed.Location().String() != "UTC" {
		t.Fatalf("not UTC: %s", parsed.Location())
	}
}

func TestNormalizeScalarPassThrough(t *testing.T) {
	if normalizeScalar(nil) != nil {
		t.Fatal("nil")
	}
	if v := normalizeScalar(int64(42)); v != int64(42) {
		t.Fatalf("int: %v", v)
	}
	if v := normalizeScalar("abc"); v != "abc" {
		t.Fatalf("str: %v", v)
	}
}

func TestNormalizeJSONValid(t *testing.T) {
	cases := []struct {
		name string
		in   any
		want string
	}{
		{"object", []byte(`{"a":1}`), `{"a":1}`},
		{"array", []byte(`[1,2,3]`), `[1,2,3]`},
		{"string-value", []byte(`"x"`), `"x"`},
		{"string-typed", `{"k":"v"}`, `{"k":"v"}`},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			out := normalizeJSON(c.in)
			rm, ok := out.(json.RawMessage)
			if !ok {
				t.Fatalf("want json.RawMessage, got %T", out)
			}
			if string(rm) != c.want {
				t.Fatalf("got %s, want %s", rm, c.want)
			}
		})
	}
}

func TestNormalizeJSONInvalidFallsBack(t *testing.T) {
	bad := []byte{0x00, 0x01, 0x02}
	out := normalizeJSON(bad)
	if _, isRaw := out.(json.RawMessage); isRaw {
		t.Fatal("invalid bytes should not become RawMessage")
	}
}

func TestNormalizeJSONNilEmpty(t *testing.T) {
	if normalizeJSON(nil) != nil {
		t.Fatal("nil")
	}
	if normalizeJSON([]byte{}) != nil {
		t.Fatal("empty bytes should be nil")
	}
	if normalizeJSON("") != nil {
		t.Fatal("empty string should be nil")
	}
}

// Critical: the scan buffer is reused across rows. Without copying, every
// json.RawMessage in the result would alias the same backing array and
// the final JSON output would all read like the last row's bytes.
func TestNormalizeJSONCopiesBytes(t *testing.T) {
	buf := []byte(`{"v":1}`)
	out := normalizeJSON(buf)
	rm := out.(json.RawMessage)
	// mutate the original
	buf[5] = '9'
	if string(rm) == string(buf) {
		t.Fatalf("RawMessage aliases caller buffer: rm=%s buf=%s", rm, buf)
	}
}

func TestIsInfraErrTransport(t *testing.T) {
	if !isInfraErr(context.DeadlineExceeded) {
		t.Fatal("deadline should be infra")
	}
	if !isInfraErr(&net.OpError{Op: "dial", Err: errors.New("connection refused")}) {
		t.Fatal("net.OpError should be infra")
	}
	if isInfraErr(nil) {
		t.Fatal("nil")
	}
}

func TestIsInfraErrOraCodes(t *testing.T) {
	cases := []string{
		"ORA-12541: TNS:no listener",
		"ORA-03113: end-of-file",
		"ORA-12170: Connect timeout",
		"ORA-01092: ORACLE instance terminated",
	}
	for _, c := range cases {
		if !isInfraErr(errors.New(c)) {
			t.Errorf("%s: should be infra", c)
		}
	}
}

func TestIsInfraErrAppErrorsAreNot(t *testing.T) {
	// app-level errors must NOT trip the breaker
	cases := []string{
		"ORA-00001: unique constraint violated",
		"ORA-00942: table or view does not exist",
		"ORA-01400: cannot insert NULL",
		"ORA-02291: integrity constraint",
	}
	for _, c := range cases {
		if isInfraErr(errors.New(c)) {
			t.Errorf("%s: should NOT be infra", c)
		}
	}
}

func TestIsRetryableTransientLocks(t *testing.T) {
	cases := []string{
		"ORA-00060: deadlock detected",
		"ORA-00054: resource busy",
		"ORA-08177: can't serialize access",
	}
	for _, c := range cases {
		if !isRetryable(errors.New(c)) {
			t.Errorf("%s: should be retryable", c)
		}
	}
}
