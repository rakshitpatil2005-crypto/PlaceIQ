from collections.abc import Generator

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_access_token, get_current_admin
from app.config import settings
from app.database import Base, get_db
from app.models import User
from scripts.promote_first_admin import (
    AdminAlreadyProvisionedError,
    UnsupportedAccountRoleError,
    UserNotFoundError,
    main,
    promote_first_admin,
    require_local_sqlite,
)


@pytest.fixture
def admin_db() -> Generator[sessionmaker[Session], None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    try:
        yield factory
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def add_user(factory: sessionmaker[Session], role: str = "student") -> int:
    with factory() as db:
        user = User(
            name="Existing Student",
            email="existing@example.test",
            hashed_password="test-hash",
            role=role,
            branch="CSE",
            semester=6,
            target_role="Software Engineer",
        )
        db.add(user)
        db.commit()
        return user.id


def test_promotes_existing_student_without_changing_credentials_or_profile(
    admin_db: sessionmaker[Session],
) -> None:
    user_id = add_user(admin_db)
    with admin_db() as db:
        assert promote_first_admin(db, "existing@example.test") is True

    with admin_db() as db:
        user = db.query(User).filter_by(id=user_id).one()
        assert user.role == "admin"
        assert user.hashed_password == "test-hash"
        assert (user.name, user.email, user.branch, user.semester, user.target_role) == (
            "Existing Student",
            "existing@example.test",
            "CSE",
            6,
            "Software Engineer",
        )


def test_promoted_account_passes_existing_jwt_admin_authorization(
    admin_db: sessionmaker[Session],
) -> None:
    user_id = add_user(admin_db)
    with admin_db() as db:
        promote_first_admin(db, "existing@example.test")

    def override_get_db():
        with admin_db() as db:
            yield db

    app = FastAPI()
    app.dependency_overrides[get_db] = override_get_db

    @app.get("/admin-probe")
    def admin_probe(user: User = Depends(get_current_admin)):
        return {"id": user.id, "role": user.role}

    token = create_access_token({"sub": str(user_id)})
    response = TestClient(app).get(
        "/admin-probe",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json() == {"id": user_id, "role": "admin"}


def test_missing_user_does_not_create_or_modify_accounts(
    admin_db: sessionmaker[Session],
) -> None:
    student_id = add_user(admin_db)
    with admin_db() as db:
        with pytest.raises(UserNotFoundError):
            promote_first_admin(db, "missing@example.test")

    with admin_db() as db:
        users = db.query(User).all()
        assert [(user.id, user.role) for user in users] == [(student_id, "student")]


def test_refuses_promotion_after_an_admin_exists(
    admin_db: sessionmaker[Session],
) -> None:
    student_id = add_user(admin_db)
    with admin_db() as db:
        db.add(
            User(
                name="Existing Admin",
                email="admin@example.test",
                hashed_password="existing-hash",
                role="admin",
            )
        )
        db.commit()

    with admin_db() as db:
        with pytest.raises(AdminAlreadyProvisionedError):
            promote_first_admin(db, "existing@example.test")
        assert db.query(User).filter_by(id=student_id).one().role == "student"


def test_only_student_accounts_can_be_promoted(
    admin_db: sessionmaker[Session],
) -> None:
    add_user(admin_db, role="placement_staff")
    with admin_db() as db:
        with pytest.raises(UnsupportedAccountRoleError):
            promote_first_admin(db, "existing@example.test")


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql:///placeiq",
        "sqlite://",
        "sqlite:///:memory:",
        "sqlite:///file:shared?mode=memory&cache=shared",
    ],
)
def test_only_file_based_sqlite_is_allowed(database_url: str) -> None:
    with pytest.raises(ValueError, match="local SQLite"):
        require_local_sqlite(database_url)


def test_accepts_file_based_sqlite_without_disclosing_database_url() -> None:
    require_local_sqlite("sqlite:///./placeiq.db")


def test_cli_requires_explicit_local_development_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "DATABASE_URL", "sqlite:///./placeiq.db")
    with pytest.raises(SystemExit) as error:
        main(["--email", "existing@example.test"])
    assert error.value.code == 2


def test_cli_rejects_non_sqlite_database_before_opening_a_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql:///placeiq")
    monkeypatch.setattr(
        "scripts.promote_first_admin.SessionLocal",
        lambda: pytest.fail("The database session must not be opened."),
    )
    with pytest.raises(SystemExit) as error:
        main([
            "--email",
            "existing@example.test",
            "--confirm-local-development",
        ])
    assert error.value.code == 2
