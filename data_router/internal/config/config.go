// Package config loads env-based settings and validates them at boot.
// We loud-fail on missing critical values (DB credentials, wallet path)
// and soft-default everything else. Defaults are tuned for OCI ADB on
// the smaller TP service tiers — bump pool/queue sizes for larger shapes.
package config

import (
	"errors"
	"fmt"
	"os"
	"strconv"
	"time"
)

type Oracle struct {
	User           string
	Password       string
	WalletDir      string // path to wallet directory containing tnsnames.ora + cwallet.sso
	WalletPassword string // optional; empty when using auto-login wallet (cwallet.sso)
	ServiceAlias   string // entry name in tnsnames.ora, e.g. "univdb1_tp"

	MaxOpenConns      int
	MaxIdleConns      int
	ConnMaxLifetime   time.Duration
	ConnMaxIdleTime   time.Duration
	HealthCheckEvery  time.Duration
	StatementCacheLen int
}

type Queue struct {
	Capacity        int           // total bounded across all 3 lanes
	HighReserved    int           // tasks reserved for high-lane only
	NormalReserved  int
	PerCallerLimit  int           // max in-flight + queued per caller (fairness)
	MaxWaitMs       int           // reject if a request would wait longer than this
}

type Worker struct {
	Concurrency  int           // worker goroutines; usually = MaxOpenConns
	TickInterval time.Duration // idle wake-up cadence
}

type Cache struct {
	DefaultTTL    time.Duration // applied when caller specifies CacheTTLMs > 0 with no value? No — 0 means off
	MaxTTL        time.Duration // ceiling for caller-supplied TTLs
	MaxEntries    int
}

type Idempotency struct {
	Window     time.Duration
	MaxEntries int
}

type Breaker struct {
	WindowSize     int           // sliding sample size
	FailureRatio   float64       // 0..1, e.g. 0.5 → trip on >=50% failures
	MinSamples     int           // need this many samples before deciding
	OpenDuration   time.Duration // half-open after this much time
}

type HTTP struct {
	Addr            string
	ReadHeaderTO    time.Duration
	ReadTO          time.Duration
	WriteTO         time.Duration
	IdleTO          time.Duration
	MaxBodyBytes    int64
	ShutdownTO      time.Duration
	AuthToken       string // shared bearer for internal callers; empty in dev (logs warning)
}

type Limits struct {
	DefaultFetchLimit int
	MaxFetchLimit     int
	DefaultTimeoutMs  int
	MaxTimeoutMs      int
}

type Storage struct {
	Enabled bool

	// Block backend.
	//
	// On a stateless host (Cloud Run, App Engine, Lambda) leave this
	// disabled — the local filesystem doesn't survive instance
	// recycles, so it would silently lose attachments. On an OCI VM
	// with an attached Block Volume, enable it as the fallback when
	// the OCI Object Storage tier hits its free-tier ceiling.
	BlockEnabled      bool
	BlockRoot         string
	BlockURLBase      string
	BlockURLPrefix    string
	BlockSigningKey   string // hex-encoded; min 32 hex chars (16 bytes); only required when BlockEnabled=1

	// OCI Object Storage (primary). When OS is enabled, OS_NAMESPACE
	// and OS_BUCKET are required. Compartment is required for ensure-
	// bucket. AuthMode picks how to authenticate.
	OCIEnabled       bool
	OCINamespace     string
	OCIBucket        string
	OCICompartment   string
	OCIAuthMode      string // "instance_principal" (default on OCI VMs), "config_file", "env"
	OCIConfigFile    string
	OCIProfile       string
	OCIRegion        string

	ThresholdBytes    int64 // beyond this, new uploads go to block; default 8 GiB
	UsageRefreshEvery time.Duration
	PARMaxTTL         time.Duration

	MaxUploadBytes int64

	// Upload queue. When enabled, the HTTP handler spools uploads to
	// disk and a worker pool processes them serially per priority lane.
	// On stateless hosts (Cloud Run) the spool dir is /tmp and the
	// queue still works — just doesn't survive instance recycles. On
	// VM hosts the spool lives on the data disk.
	UploadQueueEnabled     bool
	UploadQueueSpoolDir    string
	UploadQueueCapacity    int
	UploadQueuePerCallerCap int
	UploadQueueWorkers     int
	UploadQueueRecentSize  int
	UploadQueueDefaultWaitMs int
	UploadQueueMaxWaitMs   int
}

type Config struct {
	NodeEnv     string
	Oracle      Oracle
	Queue       Queue
	Worker      Worker
	Cache       Cache
	Idempotency Idempotency
	Breaker     Breaker
	HTTP        HTTP
	Limits      Limits
	Storage     Storage
}

// Load reads env vars (typically pre-loaded by a process supervisor or
// an external `dotenv`-style loader; we don't pull godotenv to keep
// the dep tree small). Returns a fully-validated Config or an error.
func Load() (*Config, error) {
	c := &Config{
		NodeEnv: getenv("NODE_ENV", "development"),
		Oracle: Oracle{
			User:              must("ORACLE_USER"),
			Password:          must("ORACLE_PASSWORD"),
			WalletDir:         must("ORACLE_WALLET_DIR"),
			WalletPassword:    os.Getenv("ORACLE_WALLET_PASSWORD"),
			ServiceAlias:      getenv("ORACLE_SERVICE_ALIAS", "univdb1_tp"),
			// Defaults sized for OCI ADB Always Free tier (1 OCPU). Bump
			// these via env when running against a paid ADB shape — 1
			// Free-tier-safe defaults. Always-Free Autonomous DB caps at
			// ~20 concurrent sessions; 15 leaves a small margin for the
			// operator's own SQL/console clients without starving the
			// service. Provisioned ADB operators override up via env.
			MaxOpenConns:      getint("DB_MAX_OPEN_CONNS", 15),
			MaxIdleConns:      getint("DB_MAX_IDLE_CONNS", 5),
			ConnMaxLifetime:   getdur("DB_CONN_MAX_LIFETIME", 30*time.Minute),
			ConnMaxIdleTime:   getdur("DB_CONN_MAX_IDLE_TIME", 5*time.Minute),
			HealthCheckEvery:  getdur("DB_HEALTHCHECK_INTERVAL", 10*time.Second),
			StatementCacheLen: getint("DB_STMT_CACHE", 100),
		},
		Queue: Queue{
			Capacity:       getint("QUEUE_CAPACITY", 5000),
			HighReserved:   getint("QUEUE_HIGH_RESERVED", 500),
			NormalReserved: getint("QUEUE_NORMAL_RESERVED", 1500),
			PerCallerLimit: getint("QUEUE_PER_CALLER_LIMIT", 1000),
			MaxWaitMs:      getint("QUEUE_MAX_WAIT_MS", 8000),
		},
		Worker: Worker{
			// Match DB_MAX_OPEN_CONNS so workers don't queue on Acquire.
			Concurrency:  getint("WORKER_CONCURRENCY", 15),
			TickInterval: getdur("WORKER_TICK_INTERVAL", 10*time.Millisecond),
		},
		Cache: Cache{
			// Phase 14-B 정책: caller hot path 1s / low-churn config 5s. router MaxTTL 5s 가 절대
			// 상한 — caller 가 부주의하게 더 큰 값 보내도 5s 로 절삭하는 safety net. 변경 잦은
			// 도메인 (prospect/daily_reports/posts) 은 cache 안 걸기 (cacheTtlMs 생략).
			DefaultTTL: getdur("CACHE_DEFAULT_TTL", 1*time.Second),
			MaxTTL:     getdur("CACHE_MAX_TTL", 5*time.Second),
			MaxEntries: getint("CACHE_MAX_ENTRIES", 5000),
		},
		Idempotency: Idempotency{
			Window:     getdur("IDEMPOTENCY_WINDOW", 10*time.Minute),
			MaxEntries: getint("IDEMPOTENCY_MAX_ENTRIES", 20000),
		},
		Breaker: Breaker{
			WindowSize:   getint("BREAKER_WINDOW", 50),
			FailureRatio: getfloat("BREAKER_FAILURE_RATIO", 0.6),
			MinSamples:   getint("BREAKER_MIN_SAMPLES", 10),
			OpenDuration: getdur("BREAKER_OPEN_DURATION", 5*time.Second),
		},
		HTTP: HTTP{
			// PORT overrides HTTP_ADDR — Cloud Run / App Engine / Heroku
			// inject PORT and expect the container to bind there. We
			// bind on 0.0.0.0 so the platform's load balancer can reach
			// the listener.
			Addr: addrFromEnv("HTTP_ADDR", ":8080"),
			ReadHeaderTO: getdur("HTTP_READ_HEADER_TO", 5*time.Second),
			ReadTO:       getdur("HTTP_READ_TO", 30*time.Second),
			WriteTO:      getdur("HTTP_WRITE_TO", 30*time.Second),
			IdleTO:       getdur("HTTP_IDLE_TO", 60*time.Second),
			MaxBodyBytes: int64(getint("HTTP_MAX_BODY_BYTES", 1<<20)),
			ShutdownTO:   getdur("HTTP_SHUTDOWN_TO", 25*time.Second),
			AuthToken:    os.Getenv("INTERNAL_API_TOKEN"),
		},
		Limits: Limits{
			DefaultFetchLimit: getint("DEFAULT_FETCH_LIMIT", 1000),
			MaxFetchLimit:     getint("MAX_FETCH_LIMIT", 50000),
			DefaultTimeoutMs:  getint("DEFAULT_TIMEOUT_MS", 8000),
			MaxTimeoutMs:      getint("MAX_TIMEOUT_MS", 60000),
		},
		Storage: Storage{
			Enabled:           os.Getenv("STORAGE_ENABLED") != "0",
			BlockEnabled:      os.Getenv("STORAGE_BLOCK_ENABLED") == "1",
			BlockRoot:         getenv("BLOCK_STORAGE_ROOT", "./data/blob"),
			BlockURLBase:      os.Getenv("BLOCK_STORAGE_URL_BASE"),
			BlockURLPrefix:    getenv("BLOCK_STORAGE_URL_PREFIX", "/v1/storage/blob"),
			BlockSigningKey:   os.Getenv("BLOCK_STORAGE_SIGNING_KEY"),
			OCIEnabled:        os.Getenv("OS_ENABLED") == "1",
			OCINamespace:      os.Getenv("OS_NAMESPACE"),
			OCIBucket:         os.Getenv("OS_BUCKET"),
			OCICompartment:    os.Getenv("OS_COMPARTMENT_OCID"),
			OCIAuthMode:       getenv("OS_AUTH_MODE", "instance_principal"),
			OCIConfigFile:     os.Getenv("OCI_CONFIG_FILE"),
			OCIProfile:        os.Getenv("OCI_PROFILE"),
			OCIRegion:         os.Getenv("OCI_REGION"),
			ThresholdBytes:    int64(getint("STORAGE_THRESHOLD_BYTES", 8*1024*1024*1024)), // 8 GiB
			UsageRefreshEvery: getdur("STORAGE_USAGE_REFRESH_EVERY", 60*time.Second),
			PARMaxTTL:         getdur("STORAGE_PAR_MAX_TTL", 5*time.Minute),
			MaxUploadBytes: int64(getint("STORAGE_MAX_UPLOAD_BYTES", 10*1024*1024)), // 10 MiB

			UploadQueueEnabled:       os.Getenv("UPLOAD_QUEUE_ENABLED") != "0",
			UploadQueueSpoolDir:      getenv("UPLOAD_QUEUE_SPOOL_DIR", "/tmp/data_router-spool"),
			UploadQueueCapacity:      getint("UPLOAD_QUEUE_CAPACITY", 200),
			UploadQueuePerCallerCap:  getint("UPLOAD_QUEUE_PER_CALLER_CAP", 20),
			UploadQueueWorkers:       getint("UPLOAD_QUEUE_WORKERS", 1),
			UploadQueueRecentSize:    getint("UPLOAD_QUEUE_RECENT_SIZE", 200),
			UploadQueueDefaultWaitMs: getint("UPLOAD_QUEUE_DEFAULT_WAIT_MS", 30000),
			UploadQueueMaxWaitMs:     getint("UPLOAD_QUEUE_MAX_WAIT_MS", 60000),
		},
	}
	if err := c.validate(); err != nil {
		return nil, err
	}
	return c, nil
}

func (c *Config) validate() error {
	if c.Oracle.MaxOpenConns < 1 {
		return errors.New("DB_MAX_OPEN_CONNS must be >= 1")
	}
	if c.Oracle.MaxIdleConns < 0 || c.Oracle.MaxIdleConns > c.Oracle.MaxOpenConns {
		return errors.New("DB_MAX_IDLE_CONNS must be in [0, DB_MAX_OPEN_CONNS]")
	}
	if c.Worker.Concurrency < 1 {
		return errors.New("WORKER_CONCURRENCY must be >= 1")
	}
	if c.Worker.Concurrency > c.Oracle.MaxOpenConns {
		// Workers blocking on a saturated pool is fine, but emitting >pool
		// wastes goroutines. Allow but warn via the result.
		// (No logger here yet; main() will log this on startup.)
	}
	if c.Queue.Capacity < c.Queue.HighReserved+c.Queue.NormalReserved {
		return errors.New("QUEUE_CAPACITY must be >= HighReserved+NormalReserved")
	}
	if c.HTTP.AuthToken == "" && c.NodeEnv == "production" {
		return errors.New("INTERNAL_API_TOKEN is required in production")
	}
	if c.Storage.Enabled {
		if !c.Storage.BlockEnabled && !c.Storage.OCIEnabled {
			return errors.New("STORAGE_ENABLED=1 requires at least one of STORAGE_BLOCK_ENABLED=1 or OS_ENABLED=1")
		}
		if c.Storage.BlockEnabled {
			if c.Storage.BlockSigningKey == "" {
				return errors.New("BLOCK_STORAGE_SIGNING_KEY is required when STORAGE_BLOCK_ENABLED=1 (>=32 hex chars)")
			}
			if len(c.Storage.BlockSigningKey) < 32 {
				return errors.New("BLOCK_STORAGE_SIGNING_KEY must be >= 32 hex chars (16 bytes)")
			}
		}
		if c.Storage.OCIEnabled {
			if c.Storage.OCINamespace == "" || c.Storage.OCIBucket == "" {
				return errors.New("OS_NAMESPACE and OS_BUCKET are required when OS_ENABLED=1")
			}
			if c.Storage.OCICompartment == "" {
				return errors.New("OS_COMPARTMENT_OCID is required so the bucket can be created if missing")
			}
		}
	}
	return nil
}

// helpers ────────────────────────────────────────────────────────────

func getenv(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

// addrFromEnv prefers PORT (Cloud Run / App Engine / Heroku convention)
// over the named env, falling back to def. PORT is treated as bare
// digits ("8080") and we prepend ":" so the listener binds on all
// interfaces, which is what those platforms require.
func addrFromEnv(key, def string) string {
	if p := os.Getenv("PORT"); p != "" {
		return ":" + p
	}
	return getenv(key, def)
}

func must(key string) string {
	v := os.Getenv(key)
	if v == "" {
		fmt.Fprintf(os.Stderr, "FATAL: missing required env %s\n", key)
		os.Exit(2)
	}
	return v
}

func getint(key string, def int) int {
	v := os.Getenv(key)
	if v == "" {
		return def
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		fmt.Fprintf(os.Stderr, "FATAL: invalid int for %s=%q\n", key, v)
		os.Exit(2)
	}
	return n
}

func getfloat(key string, def float64) float64 {
	v := os.Getenv(key)
	if v == "" {
		return def
	}
	n, err := strconv.ParseFloat(v, 64)
	if err != nil {
		fmt.Fprintf(os.Stderr, "FATAL: invalid float for %s=%q\n", key, v)
		os.Exit(2)
	}
	return n
}

func getdur(key string, def time.Duration) time.Duration {
	v := os.Getenv(key)
	if v == "" {
		return def
	}
	d, err := time.ParseDuration(v)
	if err != nil {
		fmt.Fprintf(os.Stderr, "FATAL: invalid duration for %s=%q\n", key, v)
		os.Exit(2)
	}
	return d
}
