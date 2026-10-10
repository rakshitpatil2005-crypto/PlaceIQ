import sqlite3
from pathlib import Path


def test_payment_migration_is_additive_idempotent_and_enforces_payment_uniqueness() -> None:
    migration_path = (
        Path(__file__).parents[2]
        / "migrations"
        / "002_add_premium_payment_tables.sql"
    )
    migration = migration_path.read_text(encoding="utf-8")

    with sqlite3.connect(":memory:") as connection:
        connection.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE resumes (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, raw_text TEXT)"
        )
        connection.execute("INSERT INTO users (id, name) VALUES (1, 'Existing')")
        connection.execute(
            "INSERT INTO resumes (id, user_id, raw_text) VALUES (1, 1, 'preserved')"
        )

        connection.executescript(migration)
        connection.executescript(migration)

        assert connection.execute(
            "SELECT name FROM users WHERE id = 1"
        ).fetchone() == ("Existing",)
        assert connection.execute(
            "SELECT raw_text FROM resumes WHERE id = 1"
        ).fetchone() == ("preserved",)
        connection.execute(
            """INSERT INTO premium_payment_orders
               (user_id, idempotency_key, receipt, amount, currency, status)
               VALUES (1, 'key-1', 'receipt-1', 100, 'INR', 'created')"""
        )
        try:
            connection.execute(
                """INSERT INTO premium_payment_orders
                   (user_id, idempotency_key, receipt, amount, currency, status)
                   VALUES (1, 'key-2', 'receipt-2', 100, 'INR', 'created')"""
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("A user must not have multiple open payment orders")
