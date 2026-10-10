import sqlite3
from pathlib import Path


def test_premium_migration_is_additive_and_preserves_existing_records() -> None:
    migration_path = (
        Path(__file__).parents[2] / "migrations" / "001_add_premium_tables.sql"
    )
    migration = migration_path.read_text(encoding="utf-8")

    with sqlite3.connect(":memory:") as connection:
        connection.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE resumes (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, raw_text TEXT)"
        )
        connection.execute("INSERT INTO users (id, name) VALUES (1, 'Existing user')")
        connection.execute(
            "INSERT INTO resumes (id, user_id, raw_text) VALUES (1, 1, 'saved record')"
        )

        connection.executescript(migration)
        connection.executescript(migration)

        assert connection.execute(
            "SELECT id, name FROM users"
        ).fetchall() == [(1, "Existing user")]
        assert connection.execute(
            "SELECT id, user_id, raw_text FROM resumes"
        ).fetchall() == [(1, 1, "saved record")]
        assert connection.execute(
            "SELECT user_id, plan, status FROM premium_subscriptions"
        ).fetchall() == []
        assert connection.execute(
            "SELECT user_id, status FROM premium_access_requests"
        ).fetchall() == []

        connection.execute(
            "INSERT INTO premium_subscriptions (user_id) VALUES (1)"
        )
        connection.execute(
            "INSERT INTO premium_access_requests (user_id) VALUES (1)"
        )
        assert connection.execute(
            "SELECT plan, status FROM premium_subscriptions"
        ).fetchone() == ("free", "inactive")
        assert connection.execute(
            "SELECT status FROM premium_access_requests"
        ).fetchone() == ("pending",)
