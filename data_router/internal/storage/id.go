package storage

import (
	"errors"
	"strings"
)

// ID encoding scheme:
//   "o:<bucket>/<key>"   — OCI Object Storage. <key> may itself contain '/'.
//   "b:<key>"            — Block filesystem; <key> is a relative path under
//                          BlockBackend.root.
//
// Encode/Decode below are the only places allowed to construct or parse
// these strings; everything else passes them around opaquely.

const (
	BackendOCI   = "oci_os"
	BackendBlock = "block"

	prefixOCI   = "o:"
	prefixBlock = "b:"
)

func EncodeOCI(bucket, key string) string {
	return prefixOCI + bucket + "/" + key
}

func EncodeBlock(key string) string {
	return prefixBlock + key
}

// Decode reverses Encode. Returns the backend tag, bucket (empty for
// block), and key. The id format is intentionally easy to grep for in
// logs and DB queries.
func Decode(id string) (backend, bucket, key string, err error) {
	switch {
	case strings.HasPrefix(id, prefixOCI):
		rest := id[len(prefixOCI):]
		i := strings.IndexByte(rest, '/')
		if i <= 0 || i == len(rest)-1 {
			return "", "", "", errors.New("storage: malformed oci id")
		}
		return BackendOCI, rest[:i], rest[i+1:], nil
	case strings.HasPrefix(id, prefixBlock):
		rest := id[len(prefixBlock):]
		if rest == "" {
			return "", "", "", errors.New("storage: empty block id")
		}
		return BackendBlock, "", rest, nil
	default:
		return "", "", "", errors.New("storage: unknown id scheme (want 'o:' or 'b:')")
	}
}
