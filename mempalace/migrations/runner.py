"""Minimal ordered SQLite migration runner for topology-layer schema.

This runner is intentionally independent from ``mempalace migrate``, which is
reserved for ChromaDB palace upgrades. The CLI exposes these migrations via
``mempalace schema migrate`` to avoid changing existing upgrade behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import sqlite3
from typing import List, Optional, Sequence


MIGRATIONS_DIR = Path(__file__).resolve().parent
MIGRATIONS_TABLE = "schema_versions"
LEGACY_MIGRATIONS_TABLE = "schema_migrations"


@dataclass(frozen=True)
class Migration:
    """One reversible SQL migration."""

    version: str
    name: str
    up_path: Path
    down_path: Path


@dataclass
class MigrationReport:
    """Result from applying or rolling back migrations."""

    direction: str
    applied: List[str] = field(default_factory=list)
    current_version: Optional[str] = None
    latest_version: Optional[str] = None

    @property
    def changed(self) -> bool:
        return bool(self.applied)


def discover_migrations(migrations_dir: Path = MIGRATIONS_DIR) -> List[Migration]:
    """Return ordered migrations discovered from ``*_*.sql`` up/down pairs."""
    migrations = []
    for up_path in sorted(migrations_dir.glob("[0-9][0-9][0-9][0-9]_*.sql")):
        if up_path.name.endswith("_down.sql"):
            continue
        version, stem_name = up_path.stem.split("_", 1)
        down_path = migrations_dir / f"{version}_{stem_name}_down.sql"
        if not down_path.exists():
            raise FileNotFoundError(f"Missing down migration for {up_path.name}")
        migrations.append(
            Migration(version=version, name=stem_name, up_path=up_path, down_path=down_path)
        )
    return migrations


def _ensure_migration_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {MIGRATIONS_TABLE} (
            version TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {LEGACY_MIGRATIONS_TABLE} (
            version TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        f"""
        INSERT OR IGNORE INTO {MIGRATIONS_TABLE} (version, name, applied_at)
        SELECT version, name, applied_at FROM {LEGACY_MIGRATIONS_TABLE}
        """
    )
    conn.execute(
        f"""
        INSERT OR IGNORE INTO {LEGACY_MIGRATIONS_TABLE} (version, name, applied_at)
        SELECT version, name, applied_at FROM {MIGRATIONS_TABLE}
        """
    )


def applied_versions(conn: sqlite3.Connection) -> List[str]:
    """Return migration versions already recorded in the target database."""
    _ensure_migration_table(conn)
    rows = conn.execute(f"SELECT version FROM {MIGRATIONS_TABLE} ORDER BY version").fetchall()
    return [row[0] for row in rows]


def migration_status(db_path: str, migrations_dir: Path = MIGRATIONS_DIR) -> dict:
    """Return current/latest migration status for ``db_path``."""
    migrations = discover_migrations(migrations_dir)
    with sqlite3.connect(db_path) as conn:
        versions = applied_versions(conn)
    latest = migrations[-1].version if migrations else None
    current = versions[-1] if versions else None
    return {
        "current_version": current,
        "latest_version": latest,
        "applied": versions,
        "pending": [m.version for m in migrations if m.version not in versions],
    }


def apply_migrations(
    db_path: str,
    direction: str = "up",
    target: Optional[str] = None,
    migrations_dir: Path = MIGRATIONS_DIR,
) -> MigrationReport:
    """Apply ordered up migrations or roll back down migrations.

    ``direction`` must be ``"up"`` or ``"down"``. For ``up``, all migrations up
    to ``target`` are applied. For ``down``, applied migrations are rolled back in
    reverse order until ``target`` remains applied; omit ``target`` to roll back
    all topology migrations.
    """
    if direction not in {"up", "down"}:
        raise ValueError("direction must be 'up' or 'down'")

    migrations = discover_migrations(migrations_dir)
    by_version = {m.version: m for m in migrations}
    if target is not None and target not in by_version:
        raise ValueError(f"unknown migration target: {target}")

    report = MigrationReport(
        direction=direction,
        latest_version=migrations[-1].version if migrations else None,
    )

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        _ensure_migration_table(conn)
        current = set(applied_versions(conn))
        if direction == "up":
            for migration in migrations:
                if target is not None and migration.version > target:
                    break
                if migration.version in current:
                    continue
                _execute_sql(conn, migration.up_path)
                conn.execute(
                    f"INSERT INTO {MIGRATIONS_TABLE} (version, name) VALUES (?, ?)",
                    (migration.version, migration.name),
                )
                conn.execute(
                    f"INSERT OR IGNORE INTO {LEGACY_MIGRATIONS_TABLE} (version, name) VALUES (?, ?)",
                    (migration.version, migration.name),
                )
                report.applied.append(migration.version)
        else:
            for migration in reversed(migrations):
                if migration.version not in current:
                    continue
                if target is not None and migration.version <= target:
                    break
                _execute_sql(conn, migration.down_path)
                conn.execute(f"DELETE FROM {MIGRATIONS_TABLE} WHERE version=?", (migration.version,))
                conn.execute(
                    f"DELETE FROM {LEGACY_MIGRATIONS_TABLE} WHERE version=?", (migration.version,)
                )
                report.applied.append(migration.version)
        remaining = applied_versions(conn)
        report.current_version = remaining[-1] if remaining else None
    return report


def _execute_sql(conn: sqlite3.Connection, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    conn.executescript(sql)
