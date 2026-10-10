import sqlite3
from pathlib import Path

import pytest

from scripts.recover_placement_staff import (
    RecoveryError,
    apply_recovery,
    configured_database_path,
    create_verified_backup,
    inspect_target,
    main,
    validate_database_target,
    validate_user_confirmation,
)


@pytest.fixture
def project_database(tmp_path: Path) -> Path:
    database = tmp_path / "placeiq.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                email TEXT NOT NULL,
                hashed_password TEXT NOT NULL,
                role TEXT NOT NULL,
                profile TEXT
            );
            CREATE TABLE learning_records (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE payment_records (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                payload TEXT NOT NULL
            );
            INSERT INTO users VALUES
                (1, 'admin@example.test', 'admin-hash', 'admin', 'admin-profile'),
                (14, 'student@example.test', 'student-hash', 'student', 'student-profile'),
                (15, 'staff@example.test', 'staff-hash', 'placement_staff', 'staff-profile');
            INSERT INTO learning_records VALUES (1, 14, 'learning-data');
            INSERT INTO payment_records VALUES (1, 14, 'payment-data');
            """
        )
    return database.resolve()


def dump_database(database: Path) -> dict[str, list[tuple]]:
    with sqlite3.connect(database) as connection:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        return {
            table: connection.execute(f'SELECT * FROM "{table}" ORDER BY 1').fetchall()
            for table in tables
        }


def test_dry_run_inspects_role_without_modifying_any_database_records(
    project_database: Path,
) -> None:
    before = dump_database(project_database)
    snapshot = inspect_target(project_database, 14)
    after = dump_database(project_database)

    assert snapshot.user_role == "student"
    assert snapshot.admin_ids == (1,)
    assert before == after


def test_backup_is_new_verified_and_contains_all_existing_tables_and_rows(
    project_database: Path,
    tmp_path: Path,
) -> None:
    backup_path = tmp_path / "verified-backup.db"
    before = dump_database(project_database)

    result = create_verified_backup(project_database, str(backup_path))

    assert result == backup_path
    assert dump_database(result) == before
    with sqlite3.connect(result) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)


def test_backup_validation_refuses_to_overwrite_existing_file(
    project_database: Path,
    tmp_path: Path,
) -> None:
    backup = tmp_path / "existing-backup.db"
    backup.write_bytes(b"preserve this file")

    with pytest.raises(RecoveryError, match="refusing to overwrite"):
        create_verified_backup(project_database, str(backup))
    assert backup.read_bytes() == b"preserve this file"


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql:///placeiq",
        "sqlite://",
        "sqlite:///:memory:",
        "sqlite:///file:shared?mode=memory&cache=shared",
        "sqlite:////server/share/placeiq.db",
    ],
)
def test_rejects_unsafe_or_ambiguous_configured_database_urls(
    database_url: str,
    tmp_path: Path,
) -> None:
    with pytest.raises(RecoveryError):
        configured_database_path(database_url, tmp_path)


def test_refuses_database_outside_configured_target(
    project_database: Path,
    tmp_path: Path,
) -> None:
    unexpected = tmp_path / "other.db"
    with sqlite3.connect(unexpected) as connection:
        connection.execute("CREATE TABLE users (id INTEGER, role TEXT)")
    with pytest.raises(RecoveryError, match="not the configured"):
        validate_database_target(
            str(unexpected),
            str(unexpected),
            project_database,
        )


def test_refuses_wrong_path_confirmation_or_noncanonical_alias(
    project_database: Path,
) -> None:
    with pytest.raises(RecoveryError, match="confirmation"):
        validate_database_target(
            str(project_database),
            str(project_database) + ".wrong",
            project_database,
        )
    alias = project_database.parent / "." / project_database.name
    with pytest.raises(RecoveryError, match="dot-segment"):
        validate_database_target(
            str(project_database.parent) + "\\.\\placeiq.db",
            str(project_database),
            project_database,
        )


def test_refuses_missing_database_and_user_confirmation_mismatch(
    project_database: Path,
    tmp_path: Path,
) -> None:
    with pytest.raises(RecoveryError, match="existing local file"):
        validate_database_target(
            str(tmp_path / "missing.db"),
            str(tmp_path / "missing.db"),
            project_database,
        )
    with pytest.raises(RecoveryError, match="User confirmation"):
        validate_user_confirmation(14, 15)


def test_refuses_missing_user_or_non_student_role_without_writes(
    project_database: Path,
) -> None:
    before = dump_database(project_database)
    with pytest.raises(RecoveryError, match="does not exist"):
        inspect_target(project_database, 999)
    with pytest.raises(RecoveryError, match="currently a student"):
        apply_recovery(
            project_database,
            15,
            str(project_database.parent / "staff-backup.db"),
            lambda _path: pytest.fail("A non-student target must not reach backup confirmation."),
        )
    assert dump_database(project_database) == before


def test_cli_defaults_to_dry_run_and_does_not_create_backup_or_change_data(
    project_database: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    before = dump_database(project_database)
    monkeypatch.setattr("scripts.recover_placement_staff.BACKEND_ROOT", project_database.parent)
    monkeypatch.setattr(
        "scripts.recover_placement_staff.settings.DATABASE_URL",
        f"sqlite:///{str(project_database).replace(chr(92), '/')}",
    )
    monkeypatch.chdir(project_database.parent)
    backup_path = project_database.parent / "dry-run-backup.db"

    result = main([
        "--database",
        str(project_database),
        "--confirm-database",
        str(project_database),
        "--user-id",
        "14",
        "--confirm-user-id",
        "14",
        "--backup",
        str(backup_path),
    ])

    assert result == 0
    assert "DRY RUN" in capsys.readouterr().out
    assert not backup_path.exists()
    assert dump_database(project_database) == before


def test_successful_recovery_changes_only_target_role_and_preserves_backup(
    project_database: Path,
    tmp_path: Path,
) -> None:
    before = dump_database(project_database)
    backup_path = tmp_path / "before-role-recovery.db"
    confirmed_paths = []

    result = apply_recovery(
        project_database,
        14,
        str(backup_path),
        lambda path: confirmed_paths.append(path) or path,
    )

    after = dump_database(project_database)
    assert result == backup_path
    assert confirmed_paths == [str(backup_path)]
    assert dump_database(backup_path) == before
    assert after["users"] == [
        (1, "admin@example.test", "admin-hash", "admin", "admin-profile"),
        (14, "student@example.test", "student-hash", "placement_staff", "student-profile"),
        (15, "staff@example.test", "staff-hash", "placement_staff", "staff-profile"),
    ]
    assert after["learning_records"] == before["learning_records"]
    assert after["payment_records"] == before["payment_records"]


def test_wrong_backup_confirmation_retains_backup_and_does_not_write(
    project_database: Path,
    tmp_path: Path,
) -> None:
    before = dump_database(project_database)
    backup_path = tmp_path / "confirmed-backup.db"

    with pytest.raises(RecoveryError, match="confirmation did not match"):
        apply_recovery(project_database, 14, str(backup_path), lambda _path: "no")

    assert backup_path.exists()
    assert dump_database(project_database) == before
