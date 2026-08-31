// Package db handles all communication with the Oracle Autonomous Database.
//
// dsn.go specifically: we read tnsnames.ora out of the wallet directory,
// extract host/port/service for the requested service alias, and build
// the go-ora connection URL with SSL + wallet parameters.
//
// We don't depend on an Oracle Instant Client; go-ora is pure Go and
// understands the TCPS + wallet handshake on its own. The wallet path
// just has to point at a directory containing tnsnames.ora and the
// cwallet.sso (auto-login wallet).
package db

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"

	go_ora "github.com/sijms/go-ora/v2"
)

// TNSEntry is the fields we extract from a tnsnames.ora descriptor.
type TNSEntry struct {
	Alias       string
	Host        string
	Port        int
	ServiceName string
	Protocol    string // expected "tcps" for ADB
}

// ParseTNS reads tnsnames.ora and returns the entry matching alias.
// Comparison is case-insensitive. The TNS format permits whitespace,
// newlines and comments freely, so we strip those before regexing.
func ParseTNS(walletDir, alias string) (*TNSEntry, error) {
	path := filepath.Join(walletDir, "tnsnames.ora")
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read tnsnames.ora: %w", err)
	}
	body := stripTNSCommentsAndWS(string(raw))

	// Each entry looks like:  alias = (description=...)(connect_data=...)...
	// We split on top-level "alias =" boundaries. Aliases are word-like.
	// Descriptors can themselves contain "=" inside parens, so we walk
	// the string and segment by paren depth.
	entries := splitTNSEntries(body)
	want := strings.ToLower(strings.TrimSpace(alias))
	for _, e := range entries {
		if strings.ToLower(e.alias) == want {
			parsed, err := parseDescriptor(e.alias, e.descriptor)
			if err != nil {
				return nil, fmt.Errorf("parse descriptor for %s: %w", e.alias, err)
			}
			return parsed, nil
		}
	}
	return nil, fmt.Errorf("alias %q not found in %s", alias, path)
}

func stripTNSCommentsAndWS(s string) string {
	// Drop # comments to end-of-line.
	out := make([]byte, 0, len(s))
	inComment := false
	for i := 0; i < len(s); i++ {
		ch := s[i]
		if inComment {
			if ch == '\n' {
				inComment = false
				out = append(out, ' ')
			}
			continue
		}
		if ch == '#' {
			inComment = true
			continue
		}
		if ch == '\r' || ch == '\n' || ch == '\t' {
			out = append(out, ' ')
			continue
		}
		out = append(out, ch)
	}
	return string(out)
}

type tnsEntry struct {
	alias      string
	descriptor string
}

// splitTNSEntries walks the file and collects (alias, "(descriptor)") pairs
// at paren depth 0. An alias is the identifier preceding "=" at depth 0.
func splitTNSEntries(s string) []tnsEntry {
	var entries []tnsEntry
	depth := 0
	i := 0
	for i < len(s) {
		// skip whitespace
		for i < len(s) && s[i] == ' ' {
			i++
		}
		if i >= len(s) {
			break
		}
		// read an identifier
		start := i
		for i < len(s) && isIdentChar(s[i]) {
			i++
		}
		alias := s[start:i]
		// skip whitespace + '='
		for i < len(s) && s[i] == ' ' {
			i++
		}
		if i >= len(s) || s[i] != '=' {
			// not an alias declaration; advance one char to avoid loop lock
			if i < len(s) {
				i++
			}
			continue
		}
		i++ // consume '='
		for i < len(s) && s[i] == ' ' {
			i++
		}
		if i >= len(s) || s[i] != '(' {
			continue
		}
		// capture balanced paren block
		descStart := i
		for i < len(s) {
			switch s[i] {
			case '(':
				depth++
			case ')':
				depth--
			}
			i++
			if depth == 0 {
				break
			}
		}
		entries = append(entries, tnsEntry{alias: alias, descriptor: s[descStart:i]})
	}
	return entries
}

func isIdentChar(b byte) bool {
	return (b >= 'a' && b <= 'z') || (b >= 'A' && b <= 'Z') || (b >= '0' && b <= '9') || b == '_' || b == '-' || b == '.'
}

// reKV matches a `(KEY = VALUE)` pair where VALUE has no parens.
var reKV = regexp.MustCompile(`\(\s*([A-Za-z_]+)\s*=\s*([^()=\s][^()]*?)\s*\)`)

func parseDescriptor(alias, desc string) (*TNSEntry, error) {
	out := &TNSEntry{Alias: alias}
	for _, m := range reKV.FindAllStringSubmatch(desc, -1) {
		k := strings.ToLower(m[1])
		v := strings.TrimSpace(m[2])
		switch k {
		case "host":
			out.Host = v
		case "port":
			n, err := strconv.Atoi(v)
			if err != nil {
				return nil, fmt.Errorf("port %q: %w", v, err)
			}
			out.Port = n
		case "service_name":
			out.ServiceName = v
		case "protocol":
			out.Protocol = strings.ToLower(v)
		}
	}
	if out.Host == "" || out.Port == 0 || out.ServiceName == "" {
		return nil, fmt.Errorf("incomplete descriptor: host=%q port=%d service=%q", out.Host, out.Port, out.ServiceName)
	}
	return out, nil
}

// BuildConnString produces the go-ora connection URL for ADB with mTLS
// wallet auth. WALLET param points at the wallet directory; go-ora reads
// cwallet.sso for the client cert + key pair.
func BuildConnString(user, password string, tns *TNSEntry, walletDir, walletPassword string) string {
	// go-ora option keys are case-sensitive and space-separated. ADB
	// requires SSL=enable + verified server DN — the wallet's truststore
	// holds the cert chain, so SSL Verify=true is the safe default.
	opts := map[string]string{
		"SSL":        "enable",
		"SSL Verify": "true",
		"WALLET":     walletDir,
	}
	if walletPassword != "" {
		opts["WALLET PASSWORD"] = walletPassword
	}
	return go_ora.BuildUrl(tns.Host, tns.Port, tns.ServiceName, user, password, opts)
}
