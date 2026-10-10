import argparse
import os
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from sqlalchemy.engine import make_url

from app.config import settings


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_TABLES = {"users"}
SQLITE_HEADER = b"SQLite format 3\x00"


class RecoveryError(Exception):
    pass


@dataclass(frozen=True)
class DatabaseSnapshot:
    user_role: str
    admin_ids: tuple[int, ...]
    tables: tuple[str, ...]


def _canonical_existing_file(raw_path: str, label: str) -> Path:
    if any(part in (".", "..") for part in re.split(r"[\\/]+", raw_path)):
        raise RecoveryError(f"{label} must not contain dot-segment aliases.")
    path = Path(raw_path)
    if not path.is_absolute():
        raise RecoveryError(f"{label} must be an absolute path.")
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError):
        raise RecoveryError(f"{label} does not resolve to an existing local file.") from None
    if str(path) != str(resolved):
        raise RecoveryError(f"{label} must use its canonical path; aliases are not accepted.")
    if not resolved.is_file():
        raise RecoveryError(f"{label} must be a regular file.")
    current = Path(resolved.anchor)
    for component in resolved.parts[1:]:
        current /= component
        if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
            raise RecoveryError(f"{label} cannot contain symlink or junction aliases.")
    try:
        if resolved.stat().st_nlink > 1:
            raise RecoveryError(f"{label} cannot be a hard-linked file.")
    except OSError:
        raise RecoveryError(f"{label} cannot be inspected safely.") from None
    return resolved


def configured_database_path(database_url: str, backend_root: Path = BACKEND_ROOT) -> Path:
    try:
        url = make_url(database_url)
    except (TypeError, ValueError):
        raise RecoveryError("The configured database target is invalid.") from None
    if (
        url.get_backend_name() != "sqlite"
        or url.host is not None
        or url.username is not None
        or url.password is not None
        or url.query
        or not url.database
        or url.database == ":memory:"
        or url.database.startswith("file:")
        or url.database.startswith(("//", "\\\\"))
    ):
        raise RecoveryError("Recovery is restricted to a configured local SQLite file.")
    configured = Path(url.database)
    if not configured.is_absolute():
        configured = backend_root / configured
    try:
        return _canonical_existing_file(str(configured), "Configured database")
    except RecoveryError:
        raise RecoveryError("The configured database is missing or has an unsafe path.") from None


def validate_database_target(
    database_path: str,
    confirmed_database: str,
    expected_database: Path,
) -> Path:
    target = _canonical_existing_file(database_path, "Database path")
    expected = _canonical_existing_file(str(expected_database), "Configured database")
    if str(target) != str(expected):
        raise RecoveryError("The requested database is not the configured local project database.")
    if confirmed_database != str(target):
        raise RecoveryError("Database confirmation must exactly match the canonical database path.")
    try:
        with target.open("rb") as database_file:
            if database_file.read(len(SQLITE_HEADER)) != SQLITE_HEADER:
                raise RecoveryError("The target file is not a SQLite database.")
    except OSError:
        raise RecoveryError("The database file cannot be read safely.") from None
    return target


def validate_backup_target(backup_path: str, database_path: Path) -> Path:
    if any(part in (".", "..") for part in re.split(r"[\\/]+", backup_path)):
        raise RecoveryError("Backup path must not contain dot-segment aliases.")
    backup = Path(backup_path)
    if not backup.is_absolute():
        raise RecoveryError("Backup path must be absolute.")
    if str(backup) != os.path.abspath(str(backup)):
        raise RecoveryError("Backup path must use a normalized canonical path.")
    parent = backup.parent
    if not parent.exists() or not parent.is_dir():
        raise RecoveryError("Backup directory must already exist.")
    if parent.is_symlink() or (
        hasattr(parent, "is_junction") and parent.is_junction()
    ):
        raise RecoveryError("Backup directory cannot be a symlink or junction.")
    if backup.exists() or backup.is_symlink():
        raise RecoveryError("Backup already exists; refusing to overwrite it.")
    if os.path.normcase(os.path.abspath(str(backup))) == os.path.normcase(str(database_path)):
        raise RecoveryError("Backup path must not be the database path.")
    if os.path.normcase(str(parent.resolve())) != os.path.normcase(str(parent)):
        raise RecoveryError("Backup directory must use its canonical path.")
    return backup


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _tables(connection: sqlite3.Connection) -> tuple[str, ...]:
    return tuple(
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    )


def _schema(connection: sqlite3.Connection) -> tuple[tuple[str, str], ...]:
    return tuple(
        connection.execute(
            "SELECT type, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' AND sql IS NOT NULL "
            "ORDER BY type, name"
        )
    )


def _row_counts(connection: sqlite3.Connection, tables: tuple[str, ...]) -> tuple[tuple[str, int], ...]:
    return tuple(
        (
            table,
            connection.execute(
                f"SELECT COUNT(*) FROM {_quote_identifier(table)}"
            ).fetchone()[0],
        )
        for table in tables
    )


def _validate_database(connection: sqlite3.Connection) -> tuple[str, ...]:
    integrity = connection.execute("PRAGMA integrity_check").fetchone()
    if integrity != ("ok",):
        raise RecoveryError("Database integrity check failed.")
    tables = _tables(connection)
    if not REQUIRED_TABLES.issubset(tables):
        raise RecoveryError("Database is missing required application tables.")
    user_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(users)")
    }
    if not {"id", "role"}.issubset(user_columns):
        raise RecoveryError("The users table does not have the expected role schema.")
    if connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'trigger' AND tbl_name = 'users' LIMIT 1"
    ).fetchone():
        raise RecoveryError("Recovery refuses databases with users-table triggers.")
    return tables


def _snapshot(connection: sqlite3.Connection, user_id: int) -> DatabaseSnapshot:
    tables = _validate_database(connection)
    user = connection.execute(
        "SELECT role FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if user is None:
        raise RecoveryError("The specified user ID does not exist.")
    admin_ids = tuple(
        row[0]
        for row in connection.execute(
            "SELECT id FROM users WHERE role = 'admin' ORDER BY id"
        )
    )
    if not admin_ids:
        raise RecoveryError("No existing admin was found; recovery will not proceed.")
    return DatabaseSnapshot(user_role=user[0], admin_ids=admin_ids, tables=tables)


def inspect_target(database_path: Path, user_id: int) -> DatabaseSnapshot:
    try:
        connection = sqlite3.connect(
            database_path.as_uri() + "?mode=ro",
            uri=True,
            timeout=5,
        )
        try:
            connection.execute("PRAGMA query_only = ON")
            return _snapshot(connection, user_id)
        finally:
            connection.close()
    except sqlite3.Error:
        raise RecoveryError("The database could not be inspected safely.") from None


def validate_user_confirmation(user_id: int, confirmed_user_id: int) -> None:
    if user_id <= 0 or confirmed_user_id != user_id:
        raise RecoveryError("User confirmation must exactly match a positive target user ID.")


def create_verified_backup(database_path: Path, backup_path: str) -> Path:
    backup = validate_backup_target(backup_path, database_path)
    created = False
    try:
        descriptor = os.open(
            backup,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
        os.close(descriptor)
        created = True
        source = sqlite3.connect(
            database_path.as_uri() + "?mode=ro",
            uri=True,
            timeout=5,
        )
        destination = sqlite3.connect(backup, timeout=5)
        try:
            source.execute("PRAGMA query_only = ON")
            source_tables = _validate_database(source)
            source_schema = _schema(source)
            source_counts = _row_counts(source, source_tables)
            source.backup(destination)
        finally:
            destination.close()
            source.close()

        verification = sqlite3.connect(
            backup.as_uri() + "?mode=ro",
            uri=True,
            timeout=5,
        )
        try:
            verification.execute("PRAGMA query_only = ON")
            backup_tables = _validate_database(verification)
            if (
                backup_tables != source_tables
                or _schema(verification) != source_schema
                or _row_counts(verification, backup_tables) != source_counts
            ):
                raise RecoveryError("Backup verification did not match the source database.")
        finally:
            verification.close()
        return backup
    except FileExistsError:
        raise RecoveryError("Backup already exists; refusing to overwrite it.") from None
    except RecoveryError:
        raise
    except (OSError, sqlite3.Error):
        raise RecoveryError("Backup creation or verification failed; no role update was made.") from None
    finally:
        if created and backup.exists():
            try:
                with backup.open("rb") as backup_file:
                    valid_header = backup_file.read(len(SQLITE_HEADER)) == SQLITE_HEADER
                if not valid_header:
                    backup.unlink()
            except OSError:
                pass


def apply_recovery(
    database_path: Path,
    user_id: int,
    backup_path: str,
    confirm_backup: Callable[[str], str],
) -> Path:
    initial = inspect_target(database_path, user_id)
    if initial.user_role != "student":
        raise RecoveryError("The target user is not currently a student; no change is possible.")
    backup = create_verified_backup(database_path, backup_path)
    if confirm_backup(str(backup)) != str(backup):
        raise RecoveryError(
            f"Backup confirmation did not match; verified backup retained at {backup}."
        )

    try:
        connection = sqlite3.connect(database_path, timeout=5)
        try:
            connection.execute("BEGIN IMMEDIATE")
            before = _snapshot(connection, user_id)
            if before.user_role != "student":
                raise RecoveryError("The target user is not currently a student; no update was made.")
            cursor = connection.execute(
                "UPDATE users SET role = ? WHERE id = ? AND role = ?",
                ("placement_staff", user_id, "student"),
            )
            if cursor.rowcount != 1:
                raise RecoveryError("Exactly one student role update was not confirmed.")
            after = _snapshot(connection, user_id)
            if after.user_role != "placement_staff":
                raise RecoveryError("Post-update role verification failed.")
            if after.admin_ids != before.admin_ids:
                raise RecoveryError("Existing admin access changed; update was rolled back.")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        verification = sqlite3.connect(
            database_path.as_uri() + "?mode=ro",
            uri=True,
            timeout=5,
        )
        try:
            verification.execute("PRAGMA query_only = ON")
            final = _snapshot(verification, user_id)
            if final.user_role != "placement_staff" or final.admin_ids != before.admin_ids:
                raise RecoveryError("Committed role or admin-preservation verification failed.")
        finally:
            verification.close()
        return backup
    except RecoveryError:
        raise
    except (OSError, sqlite3.Error):
        raise RecoveryError("Recovery failed safely; inspect the verified backup before retrying.") from None


def main(
    argv: list[str] | None = None,
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> int:
    parser = argparse.ArgumentParser(
        description="Local-only recovery to grant placement_staff to one existing student."
    )
    parser.add_argument("--database", required=True, help="Canonical absolute configured SQLite path.")
    parser.add_argument("--confirm-database", required=True, help="Repeat the exact canonical database path.")
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument("--confirm-user-id", type=int, required=True)
    parser.add_argument("--apply", action="store_true", help="Apply the role change; otherwise dry-run.")
    parser.add_argument("--confirm-backend-stopped", action="store_true")
    parser.add_argument("--backup", help="New absolute backup path; required with --apply.")
    args = parser.parse_args(argv)

    try:
        if Path.cwd().resolve() != BACKEND_ROOT.resolve():
            raise RecoveryError("Run this command from the backend project directory.")
        expected_database = configured_database_path(settings.DATABASE_URL)
        target = validate_database_target(
            args.database,
            args.confirm_database,
            expected_database,
        )
        validate_user_confirmation(args.user_id, args.confirm_user_id)
        if args.apply and not args.confirm_backend_stopped:
            raise RecoveryError("Stop the backend and pass --confirm-backend-stopped before applying.")
        if args.apply and not args.backup:
            raise RecoveryError("--backup is required with --apply.")
        snapshot = inspect_target(target, args.user_id)
        if snapshot.user_role != "student":
            raise RecoveryError("The target user is not currently a student; no change is possible.")

        output_fn(
            f"{'APPLY' if args.apply else 'DRY RUN'}: database={target}; "
            f"user_id={args.user_id}; current_role=student; new_role=placement_staff; "
            f"existing_admin_ids={','.join(map(str, snapshot.admin_ids))}"
        )
        if not args.apply:
            if args.backup:
                validate_backup_target(args.backup, target)
                output_fn(f"Would create and verify backup at {Path(args.backup)} before applying.")
            output_fn("No database changes made.")
            return 0

        backup = apply_recovery(
            target,
            args.user_id,
            args.backup,
            lambda path: input_fn(
                f"Verified backup created at {path}. Type this exact full path to continue: "
            ),
        )
        output_fn(
            f"Recovery verified: user_id={args.user_id} role=placement_staff; "
            f"existing admin access preserved; backup={backup}"
        )
        return 0
    except RecoveryError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (OSError, sqlite3.Error):
        print("Recovery stopped because the local database operation failed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
