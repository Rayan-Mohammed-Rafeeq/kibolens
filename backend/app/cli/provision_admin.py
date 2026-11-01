"""
Secure multi-administrator provisioning CLI.

Security:
- Validates email against allowlist
- Uses getpass for password input (never echoed)
- Requires password confirmation
- Enforces 14-character minimum
- Stores only Argon2 hashes
- Never logs or prints passwords
"""
import getpass
import sys

from app.core.config import get_settings
from app.database.session import SessionLocal
from app.services.auth import (
    DuplicateEmailError,
    DuplicateUsernameError,
    EmailNotAllowedError,
    provision_administrator,
)

MINIMUM_PASSWORD_LENGTH = 14


def main() -> int:
    """Provision an administrator account."""
    settings = get_settings()
    
    print("=== KiboLens Administrator Provisioning ===")
    print("")
    print("Allowed administrator emails:")
    for email in sorted(settings.get_allowed_emails()):
        print(f"  - {email}")
    print("")
    
    # Get email
    email = input("Administrator email: ").strip()
    if not email:
        print("Error: Email is required.", file=sys.stderr)
        return 1
    
    # Validate email format (basic check)
    if "@" not in email or "." not in email.split("@")[1]:
        print("Error: Invalid email format.", file=sys.stderr)
        return 1
    
    # Get username
    username = input("Username: ").strip()
    if not username:
        print("Error: Username is required.", file=sys.stderr)
        return 1
    
    if (
        len(username) < 3
        or len(username) > 64
        or not all(character.isalnum() or character in "_.-" for character in username)
    ):
        print(
            "Error: Username must be 3-64 characters using letters, digits, dots, hyphens, or "
            "underscores.",
            file=sys.stderr,
        )
        return 1
    
    # Get password
    password = getpass.getpass("Password (min 14 characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    
    if len(password) < MINIMUM_PASSWORD_LENGTH:
        print(
            f"Error: Password must contain at least {MINIMUM_PASSWORD_LENGTH} characters.",
            file=sys.stderr
        )
        return 1
    
    if password != confirmation:
        print("Error: Passwords do not match.", file=sys.stderr)
        return 1
    
    # Provision administrator
    database = SessionLocal()
    try:
        user = provision_administrator(database, username, email, password, settings)
        print("")
        print(f"✓ Administrator account created successfully")
        print(f"  Email: {user.email}")
        print(f"  Username: {user.username}")
        print(f"  Role: {user.role}")
        print("")
        return 0
        
    except EmailNotAllowedError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("")
        print("The email address must be in the KIBOLENS_ALLOWED_EMAILS configuration.", file=sys.stderr)
        return 1
        
    except DuplicateEmailError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
        
    except DuplicateUsernameError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
        
    except Exception as e:
        print(f"Error: Failed to create administrator account: {e}", file=sys.stderr)
        return 1
        
    finally:
        database.close()


if __name__ == "__main__":
    raise SystemExit(main())
