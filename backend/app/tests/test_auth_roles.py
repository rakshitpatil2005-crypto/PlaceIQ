from collections.abc import Generator

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import (
    PLACEMENT_STAFF_ROLE,
    create_access_token,
    get_current_placement_staff,
)
from app.database import Base, get_db
from app.models import User
from app.routers.auth_router import router as auth_router


@pytest.fixture
def role_app(monkeypatch) -> Generator[dict, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    with session_factory() as db:
        student = User(
            name="Role Student",
            email="role-student@example.test",
            hashed_password="hash",
            role="student",
        )
        staff = User(
            name="Placement Staff",
            email="placement-staff@example.test",
            hashed_password="hash",
            role=PLACEMENT_STAFF_ROLE,
        )
        admin = User(
            name="Role Admin",
            email="role-admin@example.test",
            hashed_password="hash",
            role="admin",
        )
        db.add_all([student, staff, admin])
        db.commit()
        ids = {"student": student.id, "staff": staff.id, "admin": admin.id}

    monkeypatch.setattr(
        "app.routers.auth_router.get_password_hash",
        lambda password: "hashed-test-password",
    )

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(auth_router)

    @app.get("/placement/probe")
    def placement_probe(user: User = Depends(get_current_placement_staff)):
        return {"user_id": user.id, "role": user.role}

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    headers = {
        key: {
            "Authorization": f"Bearer {create_access_token({'sub': str(user_id)})}"
        }
        for key, user_id in ids.items()
    }
    yield {
        "client": client,
        "factory": session_factory,
        "headers": headers,
        "ids": ids,
    }
    client.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_placement_staff_dependency_requires_authentication_and_denies_students(
    role_app: dict,
) -> None:
    client = role_app["client"]
    assert client.get("/placement/probe").status_code == 401
    denied = client.get(
        "/placement/probe",
        headers=role_app["headers"]["student"],
    )
    assert denied.status_code == 403


@pytest.mark.parametrize("role", ["staff", "admin"])
def test_placement_staff_dependency_allows_staff_and_admin(role_app: dict, role: str) -> None:
    response = role_app["client"].get(
        "/placement/probe",
        headers=role_app["headers"][role],
    )
    assert response.status_code == 200
    assert response.json()["role"] == (
        PLACEMENT_STAFF_ROLE if role == "staff" else "admin"
    )


def test_only_admin_can_grant_and_revoke_placement_staff_access(role_app: dict) -> None:
    client = role_app["client"]
    student_id = role_app["ids"]["student"]
    path = f"/auth/admin/users/{student_id}/placement-staff"

    assert client.put(path, json={"active": True}).status_code == 401
    denied = client.put(
        path,
        json={"active": True},
        headers=role_app["headers"]["student"],
    )
    assert denied.status_code == 403

    granted = client.put(
        path,
        json={"active": True},
        headers=role_app["headers"]["admin"],
    )
    assert granted.status_code == 200
    assert granted.json()["role"] == PLACEMENT_STAFF_ROLE
    assert client.get(
        "/placement/probe",
        headers=role_app["headers"]["student"],
    ).json()["role"] == PLACEMENT_STAFF_ROLE

    revoked = client.put(
        path,
        json={"active": False},
        headers=role_app["headers"]["admin"],
    )
    assert revoked.status_code == 200
    assert revoked.json()["role"] == "student"
    assert client.get(
        "/placement/probe",
        headers=role_app["headers"]["student"],
    ).status_code == 403


def test_placement_staff_cannot_use_admin_provisioning_endpoint(role_app: dict) -> None:
    response = role_app["client"].put(
        f"/auth/admin/users/{role_app['ids']['student']}/placement-staff",
        json={"active": True},
        headers=role_app["headers"]["staff"],
    )
    assert response.status_code == 403
    with role_app["factory"]() as db:
        assert (
            db.query(User)
            .filter_by(id=role_app["ids"]["student"])
            .one()
            .role
            == "student"
        )


@pytest.mark.parametrize("active", [True, False])
def test_provisioning_nonexistent_user_returns_404_without_changing_roles(
    role_app: dict,
    active: bool,
) -> None:
    with role_app["factory"]() as db:
        roles_before = [(user.id, user.role) for user in db.query(User).order_by(User.id)]

    response = role_app["client"].put(
        "/auth/admin/users/999999/placement-staff",
        json={"active": active},
        headers=role_app["headers"]["admin"],
    )

    assert response.status_code == 404
    with role_app["factory"]() as db:
        roles_after = [(user.id, user.role) for user in db.query(User).order_by(User.id)]
        assert roles_after == roles_before


def test_repeated_staff_grant_and_revoke_are_idempotent(role_app: dict) -> None:
    client = role_app["client"]
    path = f"/auth/admin/users/{role_app['ids']['student']}/placement-staff"
    headers = role_app["headers"]["admin"]

    grant_once = client.put(path, json={"active": True}, headers=headers)
    grant_twice = client.put(path, json={"active": True}, headers=headers)
    assert grant_once.status_code == grant_twice.status_code == 200
    assert grant_once.json() == grant_twice.json()
    with role_app["factory"]() as db:
        assert (
            db.query(User)
            .filter_by(id=role_app["ids"]["student"])
            .one()
            .role
            == PLACEMENT_STAFF_ROLE
        )

    revoke_once = client.put(path, json={"active": False}, headers=headers)
    revoke_twice = client.put(path, json={"active": False}, headers=headers)
    assert revoke_once.status_code == revoke_twice.status_code == 200
    assert revoke_once.json() == revoke_twice.json()
    with role_app["factory"]() as db:
        assert (
            db.query(User)
            .filter_by(id=role_app["ids"]["student"])
            .one()
            .role
            == "student"
        )


def test_role_provisioning_does_not_modify_admin_accounts(role_app: dict) -> None:
    response = role_app["client"].put(
        f"/auth/admin/users/{role_app['ids']['admin']}/placement-staff",
        json={"active": False},
        headers=role_app["headers"]["admin"],
    )
    assert response.status_code == 409
    with role_app["factory"]() as db:
        assert db.query(User).filter_by(id=role_app["ids"]["admin"]).one().role == "admin"


@pytest.mark.parametrize("requested_role", ["admin", PLACEMENT_STAFF_ROLE])
def test_registration_cannot_self_assign_privileged_roles(
    role_app: dict,
    requested_role: str,
) -> None:
    client = role_app["client"]
    registration = client.post(
        "/auth/register",
        json={
            "name": "Attempted Privileged User",
            "email": f"attempted-{requested_role.replace('_', '-')}@example.com",
            "password": "test-password",
            "role": requested_role,
        },
    )
    assert registration.status_code == 201
    with role_app["factory"]() as db:
        registered = (
            db.query(User)
            .filter_by(email=f"attempted-{requested_role.replace('_', '-')}@example.com")
            .one()
        )
        assert registered.role == "student"


@pytest.mark.parametrize("requested_role", ["admin", PLACEMENT_STAFF_ROLE])
def test_profile_update_cannot_self_assign_privileged_roles(
    role_app: dict,
    requested_role: str,
) -> None:
    client = role_app["client"]
    profile = client.put(
        "/auth/me/profile",
        json={
            "branch": "CSE",
            "semester": 5,
            "target_role": "Engineer",
            "role": requested_role,
        },
        headers=role_app["headers"]["student"],
    )
    assert profile.status_code == 200
    with role_app["factory"]() as db:
        assert (
            db.query(User)
            .filter_by(id=role_app["ids"]["student"])
            .one()
            .role
            == "student"
        )
