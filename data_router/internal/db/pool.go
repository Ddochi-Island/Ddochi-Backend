// pool.go opens the *sql.DB against ADB and runs a periodic health check.
//
// We use database/sql's pool, which is battle-tested. The settings that
// matter for ADB:
//
//   SetMaxOpenConns: must be ≤ the ADB service tier's session limit
//     (TP service: typically 30–300 depending on shape). Set lower for
//     cold/scaled-down ADBs and bump up after observing in production.
//
//   SetMaxIdleConns: keep some warm so we don't pay TLS handshake
//     latency on every burst. ~1/3 of MaxOpenConns is a good baseline.
//
//   SetConnMaxLifetime: ADB recycles connections; set ≤ 30m so we
//     refresh proactively rather than discovering a stale conn at use.
//
//   SetConnMaxIdleTime: drop conns sitting idle past this so we don't
//     hold sessions during low-traffic windows.
//
// Health check: every HealthCheckEvery, run a trivial SELECT 1 FROM DUAL.
// On failure, set 'unhealthy' which the breaker observes via Healthy().
package db

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"sync/atomic"
	"time"

	// go-ora is also imported in dsn.go where it's used directly. That
	// import runs its init() which registers the "oracle" driver with
	// database/sql, which is what we rely on below in sql.Open.

	"github.com/redesign2/services/data_router/internal/config"
	"github.com/redesign2/services/data_router/internal/logx"
)

type Pool struct {
	DB    *sql.DB
	cfg   config.Oracle
	healthy atomic.Bool
}

func Open(cfg config.Oracle) (*Pool, error) {
	tns, err := ParseTNS(cfg.WalletDir, cfg.ServiceAlias)
	if err != nil {
		return nil, fmt.Errorf("tns parse: %w", err)
	}
	if tns.Protocol != "" && tns.Protocol != "tcps" {
		return nil, fmt.Errorf("expected tcps protocol for ADB, got %q", tns.Protocol)
	}
	connStr := BuildConnString(cfg.User, cfg.Password, tns, cfg.WalletDir, cfg.WalletPassword)

	db, err := sql.Open("oracle", connStr)
	if err != nil {
		return nil, fmt.Errorf("sql.Open: %w", err)
	}
	db.SetMaxOpenConns(cfg.MaxOpenConns)
	db.SetMaxIdleConns(cfg.MaxIdleConns)
	db.SetConnMaxLifetime(cfg.ConnMaxLifetime)
	db.SetConnMaxIdleTime(cfg.ConnMaxIdleTime)

	p := &Pool{DB: db, cfg: cfg}

	// Initial probe — fail fast if creds/wallet are wrong rather than
	// waiting for the first user request to discover it.
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	if err := db.PingContext(ctx); err != nil {
		_ = db.Close()
		return nil, fmt.Errorf("initial ping: %w", err)
	}
	p.healthy.Store(true)
	logx.L().Info("oracle.connected",
		"host", tns.Host, "port", tns.Port, "service", tns.ServiceName,
		"max_open", cfg.MaxOpenConns, "max_idle", cfg.MaxIdleConns,
	)
	return p, nil
}

func (p *Pool) Close() error {
	return p.DB.Close()
}

func (p *Pool) Healthy() bool { return p.healthy.Load() }

// RunHealthCheck loops until ctx is canceled, pinging the DB every
// HealthCheckEvery. It updates Healthy() and logs transitions.
func (p *Pool) RunHealthCheck(ctx context.Context) {
	t := time.NewTicker(p.cfg.HealthCheckEvery)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			pctx, cancel := context.WithTimeout(ctx, 5*time.Second)
			err := p.pingOnce(pctx)
			cancel()
			was := p.healthy.Load()
			p.healthy.Store(err == nil)
			if was && err != nil {
				logx.L().Warn("oracle.unhealthy", "err", err)
			} else if !was && err == nil {
				logx.L().Info("oracle.recovered")
			}
		}
	}
}

func (p *Pool) pingOnce(ctx context.Context) error {
	row := p.DB.QueryRowContext(ctx, "SELECT 1 FROM DUAL")
	var n int
	if err := row.Scan(&n); err != nil {
		return err
	}
	if n != 1 {
		return errors.New("ping returned unexpected value")
	}
	return nil
}
