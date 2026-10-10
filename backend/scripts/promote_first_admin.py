import argparse
import sys

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import User


class UserNotFoundError(Exception):
    pass


class AdminAlreadyProvisionedError(Exception):
    pass


class UnsupportedAccountRoleError(Exception):
    pass


def require_local_sqlite(database_url: str) -> None:
    url = make_url(database_url)
    if (
        url.get_backend_name() != "sqlite"
        or not url.database
        or url.database == ":memory:"
        or url.database.startswith("file:")
        or url.database.startswith(("//", "\\\\"))
    ):
        raise ValueError("First-admin promotion is restricted to a local SQLite database.")


def promote_first_admin(db: Session, email: str) -> bool:
    db.execute(text("BEGIN IMMEDIATE"))
    user = db.query(User).filter(User.email == email.strip()).first()
    if user is None:
        raise UserNotFoundError("No account exists for the supplied email.")
    if user.role == "admin":
        return False
    if user.role != "student":
        raise UnsupportedAccountRoleError(
            "Only an existing student account can be promoted by this command."
        )
    if db.query(User).filter(User.role == "admin").first() is not None:
        raise AdminAlreadyProvisionedError(
            "An admin account already exists; first-admin promotion is one-time."
        )

    user.role = "admin"
    db.commit()
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Promote one existing student account to the first local admin."
    )
    parser.add_argument("--email", required=True, help="Email of the already-registered account.")
    parser.add_argument(
        "--confirm-local-development",
        action="store_true",
        required=True,
        help="Confirm this is an intentional local-development operation.",
    )
    args = parser.parse_args(argv)

    try:
        require_local_sqlite(settings.DATABASE_URL)
    except ValueError as error:
        parser.error(str(error))

    try:
        with SessionLocal() as db:
            promoted = promote_first_admin(db, args.email)
    except (UserNotFoundError, AdminAlreadyProvisionedError, UnsupportedAccountRoleError) as error:
        print(str(error), file=sys.stderr)
        return 1

    if promoted:
        print(f"Promoted the existing account {args.email.strip()} to admin.")
    else:
        print("The specified account is already an admin; no changes were made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
