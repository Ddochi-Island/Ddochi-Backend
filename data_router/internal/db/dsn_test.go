package db

import (
	"os"
	"path/filepath"
	"testing"
)

func TestParseTNSAgainstRealWallet(t *testing.T) {
	// repo-relative path: services/data_router → ../../wallet_v2
	wd, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	wallet := filepath.Join(wd, "..", "..", "..", "..", "wallet_v2")
	if _, err := os.Stat(filepath.Join(wallet, "tnsnames.ora")); err != nil {
		t.Skipf("wallet not present at %s: %v", wallet, err)
	}

	cases := []struct {
		alias   string
		host    string
		port    int
		service string
	}{
		{"univdb1_tp", "adb.ap-chuncheon-1.oraclecloud.com", 1522, "g811795cbee2b00_univdb1_tp.adb.oraclecloud.com"},
		{"univdb1_high", "adb.ap-chuncheon-1.oraclecloud.com", 1522, "g811795cbee2b00_univdb1_high.adb.oraclecloud.com"},
		{"UNIVDB1_LOW", "adb.ap-chuncheon-1.oraclecloud.com", 1522, "g811795cbee2b00_univdb1_low.adb.oraclecloud.com"},
	}
	for _, c := range cases {
		got, err := ParseTNS(wallet, c.alias)
		if err != nil {
			t.Errorf("ParseTNS(%s): %v", c.alias, err)
			continue
		}
		if got.Host != c.host || got.Port != c.port || got.ServiceName != c.service {
			t.Errorf("ParseTNS(%s) = %+v, want host=%s port=%d svc=%s", c.alias, got, c.host, c.port, c.service)
		}
		if got.Protocol != "tcps" {
			t.Errorf("ParseTNS(%s) protocol=%s, want tcps", c.alias, got.Protocol)
		}
	}
}

func TestParseTNSUnknownAlias(t *testing.T) {
	wd, _ := os.Getwd()
	wallet := filepath.Join(wd, "..", "..", "..", "..", "wallet_v2")
	if _, err := os.Stat(filepath.Join(wallet, "tnsnames.ora")); err != nil {
		t.Skip("wallet not present")
	}
	if _, err := ParseTNS(wallet, "does_not_exist"); err == nil {
		t.Fatal("want error for unknown alias")
	}
}

func TestStripTNSCommentsAndWS(t *testing.T) {
	in := "alias = (description= # this is a comment\n(protocol=tcps))\r\n# whole line\nother = (x=y)"
	out := stripTNSCommentsAndWS(in)
	if contains(out, "comment") || contains(out, "whole line") {
		t.Fatalf("comments not stripped: %q", out)
	}
	if !contains(out, "alias") || !contains(out, "other") {
		t.Fatalf("aliases lost: %q", out)
	}
}

func contains(s, sub string) bool {
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}
