import io
import json
from urllib.error import HTTPError

import pytest

from scripts.grant_placement_staff import (
    ProvisioningError,
    grant_placement_staff,
    main,
    require_loopback_url,
)


class FakeResponse:
    def __init__(self, body: dict):
        self.body = json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


class FakeOpener:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return FakeResponse(response)


def test_cli_logs_in_as_existing_admin_then_calls_admin_only_role_endpoint() -> None:
    opener = FakeOpener([
        {"access_token": "test-token"},
        {"user_id": 14, "role": "placement_staff", "updated_by_admin_id": 1},
    ])

    result = grant_placement_staff(
        opener,
        "http://127.0.0.1:8000",
        "admin@example.test",
        "not-printed-password",
        14,
    )

    assert result["role"] == "placement_staff"
    login_request, login_timeout = opener.requests[0]
    role_request, role_timeout = opener.requests[1]
    assert login_request.full_url == "http://127.0.0.1:8000/auth/login"
    assert json.loads(login_request.data) == {
        "email": "admin@example.test",
        "password": "not-printed-password",
    }
    assert login_timeout == role_timeout == 10
    assert role_request.full_url.endswith("/auth/admin/users/14/placement-staff")
    assert json.loads(role_request.data) == {"active": True}
    assert role_request.get_header("Authorization") == "Bearer test-token"


def test_student_token_cannot_grant_placement_staff_and_cli_does_not_claim_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    opener = FakeOpener([
        {"access_token": "student-token"},
        HTTPError("http://127.0.0.1:8000/auth/admin/users/14/placement-staff", 403, "Forbidden", {}, io.BytesIO()),
    ])

    monkeypatch.setattr("scripts.grant_placement_staff.getpass.getpass", lambda _prompt: "hidden")
    monkeypatch.setattr("scripts.grant_placement_staff.build_opener", lambda *_args: opener)
    result = main([
        "--user-id", "14",
        "--admin-email", "student@example.test",
    ])

    captured = capsys.readouterr()
    assert result == 1
    assert "not an admin" in captured.err
    assert "Granted" not in captured.out
    assert "hidden" not in captured.out + captured.err
    assert len(opener.requests) == 2


@pytest.mark.parametrize(
    "base_url",
    [
        "http://example.com",
        "https://192.168.1.5",
        "http://user:pass@localhost:8000",
        "http://localhost:8000/path",
    ],
)
def test_refuses_non_loopback_or_credential_bearing_base_urls(base_url: str) -> None:
    with pytest.raises(ProvisioningError):
        require_loopback_url(base_url)


def test_accepts_loopback_localhost_urls() -> None:
    assert require_loopback_url("http://127.0.0.1:8000/") == "http://127.0.0.1:8000"
    assert require_loopback_url("http://[::1]:8000") == "http://[::1]:8000"
    assert require_loopback_url("http://localhost:8000") == "http://localhost:8000"
