// oci_os.go is the OCI Object Storage backend.
//
// Auth resolution order:
//   1. Instance Principal (preferred when running on an OCI VM):
//      OS_AUTH_MODE=instance_principal
//   2. API Key from a config file path: OS_AUTH_MODE=config_file
//      with OCI_CONFIG_FILE / OCI_PROFILE.
//   3. Inline API Key from env: OS_AUTH_MODE=env (PEM in OCI_PRIVATE_KEY,
//      and tenancy/user/fingerprint/region as separate vars).
//
// Bucket bootstrap: at boot we ensure the configured bucket exists in
// the configured namespace+compartment. Idempotent — if the bucket is
// already there we just verify access. On the free tier this is the
// "ToothiSeom-data" bucket (or whatever you named it).
//
// Downloads: callers receive Pre-Authenticated Request (PAR) URLs with
// short TTLs. PARs are issued by OCI server-side; they don't need our
// signing key. Listing existing PARs is rate-limited, so we don't try
// to reuse — every call to DownloadURL mints a fresh PAR. PARs persist
// in OCI's PAR registry until they expire; that's harmless.
//
// Usage tracking: list-objects on a free-tier bucket of <100k objects
// is fast, but counts against the free-tier API quota. We cache the
// total in memory and only refresh every UsageRefreshEvery (default
// 60s). Put/Delete adjust the cached counter atomically in between.
package storage

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/oracle/oci-go-sdk/v65/common"
	"github.com/oracle/oci-go-sdk/v65/common/auth"
	"github.com/oracle/oci-go-sdk/v65/objectstorage"
)

type OCIOpts struct {
	Namespace     string
	Bucket        string
	Compartment   string // OCID of compartment that owns the bucket
	AuthMode      string // "instance_principal" | "config_file" | "env"
	ConfigFile    string // for config_file mode; empty → ~/.oci/config
	Profile       string // for config_file mode; empty → DEFAULT
	Region        string // override for env mode

	UsageRefreshEvery time.Duration // default 60s
	PARMaxTTL         time.Duration // default 5m
}

type OCIBackend struct {
	cfg    OCIOpts
	client objectstorage.ObjectStorageClient

	usageBytes atomic.Int64
	usageMu    sync.Mutex
	usageNext  time.Time

	healthy atomic.Bool
}

// NewOCIBackend builds the SDK client, authenticates, ensures the bucket
// exists, and seeds the usage counter. Boot path; failures here cause
// data_router to refuse to start so we don't silently dispatch uploads
// to a misconfigured backend.
func NewOCIBackend(ctx context.Context, opts OCIOpts) (*OCIBackend, error) {
	if opts.Namespace == "" {
		return nil, errors.New("oci: namespace required")
	}
	if opts.Bucket == "" {
		return nil, errors.New("oci: bucket required")
	}
	if opts.Compartment == "" {
		return nil, errors.New("oci: compartment OCID required (for ensure-bucket)")
	}
	if opts.UsageRefreshEvery == 0 {
		opts.UsageRefreshEvery = 60 * time.Second
	}
	if opts.PARMaxTTL == 0 {
		opts.PARMaxTTL = 5 * time.Minute
	}

	prov, err := buildAuthProvider(opts)
	if err != nil {
		return nil, fmt.Errorf("oci: auth: %w", err)
	}
	client, err := objectstorage.NewObjectStorageClientWithConfigurationProvider(prov)
	if err != nil {
		return nil, fmt.Errorf("oci: client: %w", err)
	}
	if opts.Region != "" {
		client.SetRegion(opts.Region)
	}

	b := &OCIBackend{cfg: opts, client: client}

	if err := b.ensureBucket(ctx); err != nil {
		return nil, fmt.Errorf("oci: ensure bucket: %w", err)
	}
	if _, err := b.refreshUsage(ctx); err != nil {
		// Don't fail boot on a transient list error; the next refresh
		// will retry. We do leave usage at 0 which means the router
		// could over-pick OCI briefly — a deliberate, bounded risk.
		b.usageBytes.Store(0)
	}
	b.healthy.Store(true)
	return b, nil
}

func buildAuthProvider(opts OCIOpts) (common.ConfigurationProvider, error) {
	switch strings.ToLower(opts.AuthMode) {
	case "", "instance_principal":
		return auth.InstancePrincipalConfigurationProvider()
	case "config_file":
		path := opts.ConfigFile
		if path == "" {
			home, _ := os.UserHomeDir()
			path = filepath.Join(home, ".oci", "config")
		}
		profile := opts.Profile
		if profile == "" {
			profile = "DEFAULT"
		}
		return common.ConfigurationProviderFromFileWithProfile(path, profile, "")
	case "env":
		// Standard OCI SDK env vars: OCI_TENANCY_OCID, OCI_USER_OCID,
		// OCI_FINGERPRINT, OCI_PRIVATE_KEY, OCI_REGION.
		tenancy := os.Getenv("OCI_TENANCY_OCID")
		user := os.Getenv("OCI_USER_OCID")
		fp := os.Getenv("OCI_FINGERPRINT")
		key := os.Getenv("OCI_PRIVATE_KEY")
		region := opts.Region
		if region == "" {
			region = os.Getenv("OCI_REGION")
		}
		if tenancy == "" || user == "" || fp == "" || key == "" || region == "" {
			return nil, errors.New("oci: env auth requires OCI_TENANCY_OCID, OCI_USER_OCID, OCI_FINGERPRINT, OCI_PRIVATE_KEY, OCI_REGION")
		}
		return common.NewRawConfigurationProvider(tenancy, user, region, fp, key, nil), nil
	}
	return nil, fmt.Errorf("oci: unknown auth mode %q", opts.AuthMode)
}

func (b *OCIBackend) Name() string                    { return BackendOCI }
func (b *OCIBackend) Healthy(_ context.Context) bool  { return b.healthy.Load() }

// ensureBucket creates the bucket if it doesn't exist; otherwise just
// verifies we can read its head. Distinguishes 404 (create) from any
// other error (fail boot).
func (b *OCIBackend) ensureBucket(ctx context.Context) error {
	_, err := b.client.HeadBucket(ctx, objectstorage.HeadBucketRequest{
		NamespaceName: &b.cfg.Namespace,
		BucketName:    &b.cfg.Bucket,
	})
	if err == nil {
		return nil
	}
	// Distinguish 404 from auth/permission errors via the service error.
	if svcErr, ok := common.IsServiceError(err); ok && svcErr.GetHTTPStatusCode() == http.StatusNotFound {
		_, err := b.client.CreateBucket(ctx, objectstorage.CreateBucketRequest{
			NamespaceName: &b.cfg.Namespace,
			CreateBucketDetails: objectstorage.CreateBucketDetails{
				Name:          &b.cfg.Bucket,
				CompartmentId: &b.cfg.Compartment,
				PublicAccessType: objectstorage.CreateBucketDetailsPublicAccessTypeNopublicaccess,
				StorageTier:      objectstorage.CreateBucketDetailsStorageTierStandard,
				Versioning:       objectstorage.CreateBucketDetailsVersioningDisabled,
			},
		})
		if err != nil {
			return fmt.Errorf("create bucket: %w", err)
		}
		return nil
	}
	return fmt.Errorf("head bucket: %w", err)
}

func (b *OCIBackend) UsageBytes(ctx context.Context) (int64, error) {
	b.usageMu.Lock()
	if time.Now().Before(b.usageNext) {
		b.usageMu.Unlock()
		return b.usageBytes.Load(), nil
	}
	b.usageMu.Unlock()
	return b.refreshUsage(ctx)
}

func (b *OCIBackend) refreshUsage(ctx context.Context) (int64, error) {
	b.usageMu.Lock()
	defer b.usageMu.Unlock()

	var total int64
	var pageToken *string
	for {
		resp, err := b.client.ListObjects(ctx, objectstorage.ListObjectsRequest{
			NamespaceName: &b.cfg.Namespace,
			BucketName:    &b.cfg.Bucket,
			Fields:        common.String("size"),
			Start:         pageToken,
		})
		if err != nil {
			return b.usageBytes.Load(), err
		}
		for _, o := range resp.Objects {
			if o.Size != nil {
				total += *o.Size
			}
		}
		if resp.NextStartWith == nil || *resp.NextStartWith == "" {
			break
		}
		pageToken = resp.NextStartWith
	}
	b.usageBytes.Store(total)
	b.usageNext = time.Now().Add(b.cfg.UsageRefreshEvery)
	return total, nil
}

// Put uploads body. The OCI SDK needs an io.ReadSeeker with known
// length, so the cheap fast-path is "body is already a seekable file
// (the uploadq spool) and we know size + sha256". Otherwise we buffer
// to a temp file and compute the hash while writing.
func (b *OCIBackend) Put(ctx context.Context, body io.Reader, opts PutOpts) (ObjectMeta, error) {
	key := newKey(opts.ContentType)

	var (
		uploadBody io.ReadSeeker
		size       int64
		sum        string
		cleanup    func()
	)

	if seeker, ok := body.(io.ReadSeeker); ok && opts.Size > 0 && opts.SHA256 != "" {
		// Fast path: spool file from uploadq. We trust the caller's
		// SHA256 (it was computed while writing the spool). Just rewind
		// in case the caller already read past offset 0.
		if _, err := seeker.Seek(0, io.SeekStart); err != nil {
			return ObjectMeta{}, fmt.Errorf("oci: rewind: %w", err)
		}
		uploadBody = seeker
		size = opts.Size
		sum = opts.SHA256
		cleanup = func() {}
	} else {
		tmp, err := bufferToTempWithHash(body, opts.Size)
		if err != nil {
			return ObjectMeta{}, err
		}
		uploadBody = tmp.f
		size = tmp.size
		sum = tmp.sum
		cleanup = tmp.cleanup
	}
	defer cleanup()

	req := objectstorage.PutObjectRequest{
		NamespaceName: &b.cfg.Namespace,
		BucketName:    &b.cfg.Bucket,
		ObjectName:    &key,
		ContentLength: &size,
		PutObjectBody: ioReadSeekCloser(uploadBody),
	}
	if opts.ContentType != "" {
		req.ContentType = &opts.ContentType
	}
	if _, err := b.client.PutObject(ctx, req); err != nil {
		return ObjectMeta{}, fmt.Errorf("oci: put: %w", err)
	}
	b.usageBytes.Add(size)
	return ObjectMeta{
		ID:          EncodeOCI(b.cfg.Bucket, key),
		Backend:     BackendOCI,
		Bucket:      b.cfg.Bucket,
		Key:         key,
		Size:        size,
		ContentType: opts.ContentType,
		SHA256:      sum,
		CreatedAt:   time.Now().UTC(),
	}, nil
}

func (b *OCIBackend) Get(ctx context.Context, key string) (io.ReadCloser, ObjectMeta, error) {
	resp, err := b.client.GetObject(ctx, objectstorage.GetObjectRequest{
		NamespaceName: &b.cfg.Namespace,
		BucketName:    &b.cfg.Bucket,
		ObjectName:    &key,
	})
	if err != nil {
		if svc, ok := common.IsServiceError(err); ok && svc.GetHTTPStatusCode() == http.StatusNotFound {
			return nil, ObjectMeta{}, ErrNotFound
		}
		return nil, ObjectMeta{}, err
	}
	meta := ObjectMeta{
		ID:      EncodeOCI(b.cfg.Bucket, key),
		Backend: BackendOCI,
		Bucket:  b.cfg.Bucket,
		Key:     key,
	}
	if resp.ContentLength != nil {
		meta.Size = *resp.ContentLength
	}
	if resp.ContentType != nil {
		meta.ContentType = *resp.ContentType
	}
	return resp.Content, meta, nil
}

func (b *OCIBackend) Head(ctx context.Context, key string) (ObjectMeta, error) {
	resp, err := b.client.HeadObject(ctx, objectstorage.HeadObjectRequest{
		NamespaceName: &b.cfg.Namespace,
		BucketName:    &b.cfg.Bucket,
		ObjectName:    &key,
	})
	if err != nil {
		if svc, ok := common.IsServiceError(err); ok && svc.GetHTTPStatusCode() == http.StatusNotFound {
			return ObjectMeta{}, ErrNotFound
		}
		return ObjectMeta{}, err
	}
	meta := ObjectMeta{
		ID:      EncodeOCI(b.cfg.Bucket, key),
		Backend: BackendOCI,
		Bucket:  b.cfg.Bucket,
		Key:     key,
	}
	if resp.ContentLength != nil {
		meta.Size = *resp.ContentLength
	}
	if resp.ContentType != nil {
		meta.ContentType = *resp.ContentType
	}
	return meta, nil
}

func (b *OCIBackend) Delete(ctx context.Context, key string) error {
	// Best-effort head to adjust usage cache.
	var size int64
	if m, err := b.Head(ctx, key); err == nil {
		size = m.Size
	}
	_, err := b.client.DeleteObject(ctx, objectstorage.DeleteObjectRequest{
		NamespaceName: &b.cfg.Namespace,
		BucketName:    &b.cfg.Bucket,
		ObjectName:    &key,
	})
	if err != nil {
		if svc, ok := common.IsServiceError(err); ok && svc.GetHTTPStatusCode() == http.StatusNotFound {
			return nil
		}
		return err
	}
	if size > 0 {
		b.usageBytes.Add(-size)
	}
	return nil
}

// DownloadURL mints a fresh Pre-Authenticated Request (PAR) for the
// object. The PAR is server-side at OCI; the URL doesn't need our
// signing key. Callers GET the URL directly without re-touching the
// router.
func (b *OCIBackend) DownloadURL(ctx context.Context, key string, ttl time.Duration) (string, time.Time, error) {
	if ttl <= 0 {
		ttl = 60 * time.Second
	}
	if ttl > b.cfg.PARMaxTTL {
		ttl = b.cfg.PARMaxTTL
	}
	expires := common.SDKTime{Time: time.Now().Add(ttl)}
	parName := fmt.Sprintf("dr-%s-%d", strings.ReplaceAll(key, "/", "_"), expires.Unix())
	resp, err := b.client.CreatePreauthenticatedRequest(ctx,
		objectstorage.CreatePreauthenticatedRequestRequest{
			NamespaceName: &b.cfg.Namespace,
			BucketName:    &b.cfg.Bucket,
			CreatePreauthenticatedRequestDetails: objectstorage.CreatePreauthenticatedRequestDetails{
				Name:        &parName,
				ObjectName:  &key,
				AccessType:  objectstorage.CreatePreauthenticatedRequestDetailsAccessTypeObjectread,
				TimeExpires: &expires,
			},
		})
	if err != nil {
		return "", time.Time{}, fmt.Errorf("oci: create par: %w", err)
	}
	if resp.AccessUri == nil {
		return "", time.Time{}, errors.New("oci: par response missing AccessUri")
	}
	// AccessUri is path-only ("/p/...../n/<ns>/b/<bucket>/o/<key>");
	// prepend the regional endpoint to make it usable.
	endpoint := b.client.Host
	if !strings.HasPrefix(endpoint, "http") {
		endpoint = "https://" + endpoint
	}
	return strings.TrimRight(endpoint, "/") + *resp.AccessUri, expires.Time, nil
}

// ─── helpers ───

type tempBufferedBody struct {
	f       *os.File
	size    int64
	sum     string
	cleanup func()
}

// bufferToTempWithHash drains body into a temp file, computing SHA-256
// as it goes. If declaredSize > 0 and the actual stream is shorter or
// longer, we still accept whatever streams in (server-side validation
// of size is enforced by OCI's ContentLength check on PUT, which we
// pass our actual size for).
func bufferToTempWithHash(body io.Reader, declaredSize int64) (*tempBufferedBody, error) {
	tmp, err := os.CreateTemp("", "data-router-os-*")
	if err != nil {
		return nil, fmt.Errorf("oci: temp create: %w", err)
	}
	cleanup := func() {
		_ = tmp.Close()
		_ = os.Remove(tmp.Name())
	}
	h := sha256.New()
	w := io.MultiWriter(tmp, h)
	written, err := io.Copy(w, body)
	if err != nil {
		cleanup()
		return nil, fmt.Errorf("oci: temp copy: %w", err)
	}
	if _, err := tmp.Seek(0, io.SeekStart); err != nil {
		cleanup()
		return nil, err
	}
	return &tempBufferedBody{
		f: tmp, size: written, sum: hex.EncodeToString(h.Sum(nil)), cleanup: cleanup,
	}, nil
}

// ioReadSeekCloser adapts an io.ReadSeeker into the SDK's expected
// io.ReadCloser shape. The SDK Closes the body but we do final cleanup
// via the temp-file cleanup() above either way.
type readSeekCloser struct{ io.ReadSeeker }

func (r readSeekCloser) Close() error { return nil }

func ioReadSeekCloser(rs io.ReadSeeker) io.ReadCloser {
	return readSeekCloser{rs}
}
