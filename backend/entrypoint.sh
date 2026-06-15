#!/usr/bin/env bash
set -euo pipefail

# Database bootstrap strategy (idempotent, self-healing):
#
# The production path manages schema with Alembic. A hazard exists when a DB
# volume predates Alembic (tables created by an early SENTINEL_DB_CREATE_ALL
# build) — `alembic upgrade head` would then try to CREATE existing tables and
# crash, taking the container down (502). To make redeploys robust regardless of
# how the volume was first created, we reconcile Alembic's version state before
# upgrading:
#
#   1. If alembic_version is already present -> normal `upgrade head`.
#   2. Else if core tables already exist (legacy create_all volume) -> stamp the
#      baseline revision, then `upgrade head` to apply only newer migrations.
#   3. Else (empty DB) -> `upgrade head` builds everything from scratch.
#
# This is wrapped so a transient failure logs clearly rather than silently
# crash-looping.

if [ "${SENTINEL_DB_CREATE_ALL:-true}" = "false" ]; then
  echo "[entrypoint] Reconciling database schema with Alembic..."
  python - <<'PY' || { echo "[entrypoint] Schema reconcile step reported an issue; continuing to upgrade."; true; }
import asyncio
from sqlalchemy import text
from app.db.session import get_engine

BASELINE = "cace9457d0b0"  # initial schema revision

async def main():
    engine = get_engine()
    async with engine.connect() as conn:
        has_version = False
        has_tenants = False
        # Does alembic_version exist (and hold a row)?
        try:
            res = await conn.execute(text("SELECT version_num FROM alembic_version"))
            has_version = res.first() is not None
        except Exception:
            has_version = False
        # Does a known core table already exist (legacy create_all volume)?
        try:
            await conn.execute(text("SELECT 1 FROM tenants LIMIT 1"))
            has_tenants = True
        except Exception:
            has_tenants = False

        if not has_version and has_tenants:
            print("[entrypoint] Legacy schema detected without Alembic stamp; stamping baseline.")
            # Create alembic_version and stamp the baseline so upgrade applies only newer revs.
            await conn.execute(text(
                "CREATE TABLE IF NOT EXISTS alembic_version "
                "(version_num VARCHAR(32) NOT NULL)"
            ))
            await conn.execute(text("DELETE FROM alembic_version"))
            await conn.execute(text(
                "INSERT INTO alembic_version (version_num) VALUES (:v)"
            ), {"v": BASELINE})
            await conn.commit()
        else:
            print(f"[entrypoint] has_version={has_version} has_tenants={has_tenants}; no stamp needed.")
    await engine.dispose()

asyncio.run(main())
PY
  echo "[entrypoint] Running alembic upgrade head..."
  alembic upgrade head || {
    echo "[entrypoint] ERROR: alembic upgrade failed. Backend will still start so /health is reachable; investigate migrations."
  }
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "${WEB_CONCURRENCY:-4}"
