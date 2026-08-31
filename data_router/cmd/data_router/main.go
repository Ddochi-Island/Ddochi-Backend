// data_router — single gateway between caller services and the OCI
// Autonomous Database. See services/data_router/README.md for the full
// design. main() is intentionally tiny: load config, build the parts,
// wire them, run, drain on signal.
package main

import (
	"context"
	"encoding/hex"
	"errors"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"

	"github.com/redesign2/services/data_router/internal/breaker"
	"github.com/redesign2/services/data_router/internal/cache"
	"github.com/redesign2/services/data_router/internal/config"
	"github.com/redesign2/services/data_router/internal/db"
	"github.com/redesign2/services/data_router/internal/idem"
	"github.com/redesign2/services/data_router/internal/logx"
	"github.com/redesign2/services/data_router/internal/metrics"
	"github.com/redesign2/services/data_router/internal/queue"
	"github.com/redesign2/services/data_router/internal/server"
	"github.com/redesign2/services/data_router/internal/storage"
	"github.com/redesign2/services/data_router/internal/uploadq"
	"github.com/redesign2/services/data_router/internal/worker"
)

func main() {
	cfg, err := config.Load()
	if err != nil {
		logx.L().Error("config.load", "err", err)
		os.Exit(2)
	}

	if cfg.HTTP.AuthToken == "" && cfg.NodeEnv != "production" {
		logx.L().Warn("auth.disabled", "msg", "INTERNAL_API_TOKEN is empty; all requests accepted")
	}
	if cfg.Worker.Concurrency > cfg.Oracle.MaxOpenConns {
		logx.L().Warn("worker.over_pool",
			"workers", cfg.Worker.Concurrency,
			"max_open_conns", cfg.Oracle.MaxOpenConns,
			"msg", "workers exceed DB pool — extras will block on Acquire",
		)
	}

	rootCtx, rootCancel := context.WithCancel(context.Background())
	defer rootCancel()

	pool, err := db.Open(cfg.Oracle)
	if err != nil {
		logx.L().Error("db.open", "err", err)
		os.Exit(3)
	}

	q := queue.New(cfg.Queue.Capacity, cfg.Queue.HighReserved, cfg.Queue.NormalReserved, cfg.Queue.PerCallerLimit)
	c := cache.New(cfg.Cache.MaxEntries)
	idemStore := idem.New(cfg.Idempotency.Window, cfg.Idempotency.MaxEntries)
	br := breaker.New(cfg.Breaker.WindowSize, cfg.Breaker.FailureRatio, cfg.Breaker.MinSamples, cfg.Breaker.OpenDuration)
	mreg := metrics.New()
	exec := db.NewExecutor(pool, cfg.Limits.DefaultFetchLimit, cfg.Limits.MaxFetchLimit)

	wp := worker.NewPool(q, exec, c, idemStore, br, mreg, cfg.Worker.Concurrency)
	wp.Start(rootCtx)

	// Background sweepers — cheap, run forever.
	var bgWG sync.WaitGroup
	bgWG.Add(3)
	go func() { defer bgWG.Done(); pool.RunHealthCheck(rootCtx) }()
	go func() { defer bgWG.Done(); sweepLoop(rootCtx, 1*time.Second, c.Sweep) }()
	go func() { defer bgWG.Done(); sweepLoop(rootCtx, 30*time.Second, idemStore.Sweep) }()

	// Storage backends (optional — only set up when STORAGE_ENABLED).
	var (
		storageRouter *storage.Router
		blockBackend  storage.Backend
		signSecret    []byte
	)
	if cfg.Storage.Enabled {
		if cfg.Storage.BlockEnabled {
			var err error
			signSecret, err = hex.DecodeString(cfg.Storage.BlockSigningKey)
			if err != nil {
				logx.L().Error("storage.signing_key", "err", err)
				os.Exit(4)
			}
			blockOpts := storage.BlockOpts{
				Root:             cfg.Storage.BlockRoot,
				URLBase:          cfg.Storage.BlockURLBase,
				URLPathPrefix:    cfg.Storage.BlockURLPrefix,
				URLSigningSecret: signSecret,
			}
			bb, err := storage.NewBlockBackend(blockOpts)
			if err != nil {
				logx.L().Error("storage.block_open", "err", err)
				os.Exit(4)
			}
			blockBackend = bb
		}

		var primary storage.Backend
		if cfg.Storage.OCIEnabled {
			ociCtx, ociCancel := context.WithTimeout(rootCtx, 30*time.Second)
			ob, err := storage.NewOCIBackend(ociCtx, storage.OCIOpts{
				Namespace:         cfg.Storage.OCINamespace,
				Bucket:            cfg.Storage.OCIBucket,
				Compartment:       cfg.Storage.OCICompartment,
				AuthMode:          cfg.Storage.OCIAuthMode,
				ConfigFile:        cfg.Storage.OCIConfigFile,
				Profile:           cfg.Storage.OCIProfile,
				Region:            cfg.Storage.OCIRegion,
				UsageRefreshEvery: cfg.Storage.UsageRefreshEvery,
				PARMaxTTL:         cfg.Storage.PARMaxTTL,
			})
			ociCancel()
			if err != nil {
				logx.L().Error("storage.oci_open", "err", err)
				os.Exit(4)
			}
			primary = ob
		}
		storageRouter = storage.NewRouter(primary, blockBackend, cfg.Storage.ThresholdBytes)
		logx.L().Info("storage.ready",
			"primary", primary != nil,
			"block", blockBackend != nil,
			"threshold_bytes", cfg.Storage.ThresholdBytes,
		)
	}

	// Upload queue + worker (only when storage is on AND queue is on).
	var (
		uq        *uploadq.Queue
		uqWorker  *uploadq.Worker
	)
	if storageRouter != nil && cfg.Storage.UploadQueueEnabled {
		uq = uploadq.New(
			cfg.Storage.UploadQueueCapacity,
			cfg.Storage.UploadQueuePerCallerCap,
			cfg.Storage.UploadQueueRecentSize,
		)
		uqWorker = uploadq.NewWorker(uq, storageRouter, cfg.Storage.UploadQueueWorkers)
		uqWorker.Start(rootCtx)
		logx.L().Info("uploadq.ready",
			"capacity", cfg.Storage.UploadQueueCapacity,
			"workers", cfg.Storage.UploadQueueWorkers,
			"spool_dir", cfg.Storage.UploadQueueSpoolDir,
		)
	}

	srv := server.New(cfg, q, pool, c, idemStore, br, mreg, server.Optional{
		Storage:      storageRouter,
		BlockBackend: blockBackend,
		SignSecret:   signSecret,
		UploadQueue:  uq,
	})
	logx.L().Info("server.listen", "addr", cfg.HTTP.Addr)
	srvErr := make(chan error, 1)
	go func() {
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			srvErr <- err
		}
	}()

	// Wait for signal or fatal server error.
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	select {
	case sig := <-sigCh:
		logx.L().Info("shutdown.signal", "sig", sig.String())
	case err := <-srvErr:
		logx.L().Error("http.fatal", "err", err)
	}

	// ───── graceful shutdown ─────
	// 1. Stop accepting new HTTP requests.
	shutCtx, shutCancel := context.WithTimeout(context.Background(), cfg.HTTP.ShutdownTO)
	defer shutCancel()
	if err := srv.Shutdown(shutCtx); err != nil {
		logx.L().Warn("http.shutdown", "err", err)
	}
	// 2. Close DB queue — pending tasks get ErrShuttingDown.
	q.Close()
	// 3. Close upload queue — pending jobs marked StatusShutdown so any
	//    HTTP handler still sync-waiting unblocks.
	if uq != nil {
		uq.Close()
	}
	// 4. Cancel the root context — workers and background loops exit.
	rootCancel()
	// 5. Wait for worker goroutines so we don't yank the DB pool / spool
	//    files out from under in-flight work.
	wp.Wait()
	if uqWorker != nil {
		uqWorker.Wait()
	}
	bgWG.Wait()
	// 5. Close DB.
	if err := pool.Close(); err != nil {
		logx.L().Warn("db.close", "err", err)
	}
	logx.L().Info("shutdown.complete")
}

func sweepLoop(ctx context.Context, every time.Duration, fn func() int) {
	t := time.NewTicker(every)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			fn()
		}
	}
}
