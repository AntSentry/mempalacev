import sqlite3

from mempalace.migrations.runner import apply_migrations, migration_status


def _seed_base_kg(conn):
    conn.executescript(
        """
        CREATE TABLE entities (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT DEFAULT 'unknown',
            properties TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE triples (
            id TEXT PRIMARY KEY,
            subject TEXT NOT NULL,
            predicate TEXT NOT NULL,
            object TEXT NOT NULL,
            valid_from TEXT,
            valid_to TEXT,
            confidence REAL DEFAULT 1.0,
            source_closet TEXT,
            source_file TEXT,
            source_drawer_id TEXT,
            adapter_name TEXT,
            extracted_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """
    )


def test_schema_migrations_apply_and_rollback(tmp_path):
    db_path = tmp_path / "kg.sqlite3"
    with sqlite3.connect(db_path) as conn:
        _seed_base_kg(conn)

    report = apply_migrations(str(db_path), direction="up")
    assert report.current_version == "0006"
    assert report.applied == ["0001", "0002", "0003", "0004", "0005", "0006"]

    status = migration_status(str(db_path))
    assert status["pending"] == []
    with sqlite3.connect(db_path) as conn:
        version_tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('schema_versions', 'schema_migrations')"
            ).fetchall()
        }
        assert version_tables == {"schema_versions", "schema_migrations"}
        triple_columns = {row[1] for row in conn.execute("PRAGMA table_info(triples)").fetchall()}
        assert {"relation_class", "polarity", "supersedes_triple_id", "supersession_chain_id"} <= triple_columns

    rollback = apply_migrations(str(db_path), direction="down")
    assert rollback.current_version is None
    assert rollback.applied == ["0006", "0005", "0004", "0003", "0002", "0001"]


def test_schema_migration_target(tmp_path):
    db_path = tmp_path / "kg.sqlite3"
    with sqlite3.connect(db_path) as conn:
        _seed_base_kg(conn)

    report = apply_migrations(str(db_path), direction="up", target="0004")
    assert report.current_version == "0004"
    status = migration_status(str(db_path))
    assert status["pending"] == ["0005", "0006"]
