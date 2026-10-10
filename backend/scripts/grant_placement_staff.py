import argparse
import getpass
import ipaddress
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    ProxyHandler,
    Request,
    build_opener,
)


class ProvisioningError(Exception):
    pass


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def require_loopback_url(base_url: str) -> str:
    parsed = urlsplit(base_url)
    if (
        parsed.scheme not in ("http", "https")
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
        or not parsed.hostname
    ):
        raise ProvisioningError("Use an HTTP(S) base URL on localhost only.")
    hostname = parsed.hostname.casefold()
    is_loopback = hostname == "localhost"
    if not is_loopback:
        try:
            is_loopback = ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            is_loopback = False
    if not is_loopback:
        raise ProvisioningError("Refusing to send admin credentials to a non-local host.")
    return base_url.rstrip("/")


def _request_json(opener, url: str, payload: dict, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST" if token is None else "PUT",
    )
    try:
        with opener.open(request, timeout=10) as response:
            result = json.loads(response.read())
    except HTTPError as error:
        if token is None and error.code == 401:
            raise ProvisioningError("Admin sign-in failed; verify the admin email and password.") from None
        if token is not None and error.code == 401:
            raise ProvisioningError("Admin authorization failed; sign in again and retry.") from None
        if token is not None and error.code == 403:
            raise ProvisioningError(
                "The signed-in account is not an admin; students cannot grant placement access."
            ) from None
        if token is not None and error.code == 404:
            raise ProvisioningError("The requested user ID was not found.") from None
        if token is not None and error.code == 409:
            raise ProvisioningError("Placement access cannot be changed for this account role.") from None
        raise ProvisioningError(f"Local PlaceIQ API returned HTTP {error.code}.") from None
    except URLError:
        raise ProvisioningError("Could not reach the local PlaceIQ API.") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ProvisioningError("The local PlaceIQ API returned an invalid JSON response.") from None
    if not isinstance(result, dict):
        raise ProvisioningError("The local PlaceIQ API returned an unexpected response.")
    return result


def grant_placement_staff(opener, base_url: str, admin_email: str, password: str, user_id: int) -> dict:
    base_url = require_loopback_url(base_url)
    login = _request_json(
        opener,
        f"{base_url}/auth/login",
        {"email": admin_email, "password": password},
    )
    token = login.get("access_token")
    if not isinstance(token, str) or not token:
        raise ProvisioningError("Admin sign-in did not return an access token.")
    result = _request_json(
        opener,
        f"{base_url}/auth/admin/users/{user_id}/placement-staff",
        {"active": True},
        token=token,
    )
    if result.get("user_id") != user_id or result.get("role") != "placement_staff":
        raise ProvisioningError("The local API did not confirm the requested role change.")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Grant placement_staff through the existing local admin-only API."
    )
    parser.add_argument("--user-id", type=int, required=True, help="Existing account ID to grant access to.")
    parser.add_argument("--admin-email", required=True, help="Email of an existing admin account.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args(argv)
    if args.user_id <= 0:
        parser.error("--user-id must be a positive integer.")
    try:
        base_url = require_loopback_url(args.base_url)
    except ProvisioningError as error:
        parser.error(str(error))

    password = getpass.getpass("Existing admin password (input hidden): ")
    opener = build_opener(ProxyHandler({}), NoRedirectHandler())
    try:
        result = grant_placement_staff(
            opener,
            base_url,
            args.admin_email,
            password,
            args.user_id,
        )
    except ProvisioningError as error:
        print(str(error), file=sys.stderr)
        return 1
    finally:
        password = ""

    print(f"Granted placement_staff to user ID {result['user_id']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
