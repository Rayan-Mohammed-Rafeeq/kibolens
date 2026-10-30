import getpass
import sys

from app.database.session import SessionLocal
from app.services.auth import BootstrapAlreadyCompletedError, bootstrap_administrator

MINIMUM_PASSWORD_LENGTH = 14


def main() -> int:
    username = input("Administrator username: ").strip()
    if (
        len(username) < 3
        or len(username) > 64
        or not all(character.isalnum() or character in "_.-" for character in username)
    ):
        print(
            "Username must be 3-64 characters using letters, digits, dots, hyphens, or "
            "underscores.",
            file=sys.stderr,
        )
        return 1
    password = getpass.getpass("Password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if len(password) < MINIMUM_PASSWORD_LENGTH:
        print(
            f"Password must contain at least {MINIMUM_PASSWORD_LENGTH} characters.", file=sys.stderr
        )
        return 1
    if password != confirmation:
        print("Passwords do not match.", file=sys.stderr)
        return 1

    database = SessionLocal()
    try:
        bootstrap_administrator(database, username, password)
    except BootstrapAlreadyCompletedError:
        print("Administrator bootstrap has already been completed.", file=sys.stderr)
        return 1
    finally:
        database.close()
    print("Administrator account created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
