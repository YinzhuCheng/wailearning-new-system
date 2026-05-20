from __future__ import annotations

import sqlite3

from apps.backend.courseeval_backend.db.database import configure_sqlite_connection


def test_sqlite_connection_pragmas_enable_busy_timeout_and_foreign_keys():
    conn = sqlite3.connect(":memory:")
    try:
        configure_sqlite_connection(conn)
        busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        foreign_keys = conn.execute("PRAGMA foreign_keys").fetchone()[0]

        assert busy_timeout >= 30000
        assert foreign_keys == 1
    finally:
        conn.close()
