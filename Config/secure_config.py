"""
Secure Configuration Module.

Replaces plain-text config.properties with secure credential storage using:
- Windows Credential Manager (via keyring) for production
- Environment variables as fallback
- .env file as last resort (gitignored)

Credentials that should be secured:
- appId (Fyers API app ID)
- secretID (Fyers API secret)
- auth_code (JWT auth token - short-lived)
- access_token (JWT access token - expires daily)

Setup:
    First time:
        1. Run: py -c "from Config.secure_config import setup_credentials; setup_credentials()"
        2. Enter your credentials when prompted
        3. Credentials are stored in Windows Credential Manager

    Migrating from old config.properties:
        1. Run: py -c "from Config.secure_config import migrate_from_properties; migrate_from_properties()"
        2. This will read old config.properties and store in keyring
        3. Delete old config.properties file

Usage:
    from Config.secure_config import get_credentials

    creds = get_credentials()
    app_id = creds['appId']
    secret = creds['secretID']
    access_token = creds['access_token']
"""

import os
import sys
from pathlib import Path

# Try to import keyring (secure credential storage)
try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False
    print("WARNING: 'keyring' not installed. Run: pip install keyring")

# Try to import python-dotenv for .env file support
try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False


# Service name for keyring (Windows Credential Manager)
SERVICE_NAME = "FyersTrading"
ROOT = Path(__file__).resolve().parent.parent
OLD_CONFIG_PATH = ROOT / "Config" / "LoginConfig" / "config.properties"
ENV_FILE_PATH = ROOT / ".env"
ENV_EXAMPLE_PATH = ROOT / ".env.example"


def get_from_keyring(key: str) -> str | None:
    """Get credential from Windows Credential Manager."""
    if not KEYRING_AVAILABLE:
        return None
    try:
        return keyring.get_password(SERVICE_NAME, key)
    except Exception as e:
        print(f"Warning: Failed to read from keyring: {e}")
        return None


def set_in_keyring(key: str, value: str) -> bool:
    """Store credential in Windows Credential Manager."""
    if not KEYRING_AVAILABLE:
        return False
    try:
        keyring.set_password(SERVICE_NAME, key, value)
        return True
    except Exception as e:
        print(f"Error: Failed to store in keyring: {e}")
        return False


def delete_from_keyring(key: str) -> bool:
    """Delete credential from Windows Credential Manager."""
    if not KEYRING_AVAILABLE:
        return False
    try:
        keyring.delete_password(SERVICE_NAME, key)
        return True
    except Exception as e:
        print(f"Warning: Failed to delete from keyring: {e}")
        return False


def get_from_env(key: str) -> str | None:
    """Get credential from environment variable or .env file."""
    if DOTENV_AVAILABLE and ENV_FILE_PATH.exists():
        load_dotenv(ENV_FILE_PATH)
    return os.environ.get(key)


def get_from_file(key: str, file_path: Path = OLD_CONFIG_PATH) -> str | None:
    """Fallback: read from old config.properties file."""
    if not file_path.exists():
        return None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip().startswith('#') or '=' not in line:
                    continue
                k, v = line.strip().split('=', 1)
                if k.strip() == key:
                    return v.strip()
    except Exception as e:
        print(f"Warning: Failed to read from {file_path}: {e}")
    return None


def get_credential(key: str) -> str | None:
    """
    Get credential with priority: keyring > env var > file.

    Returns None if not found anywhere.
    """
    # Try keyring first (most secure)
    value = get_from_keyring(key)
    if value:
        return value

    # Try environment variable
    value = get_from_env(key)
    if value:
        return value

    # Fallback to file (least secure)
    value = get_from_file(key)
    if value:
        print(f"Warning: '{key}' loaded from unencrypted file. Consider migrating to keyring.")
        return value

    return None


def get_credentials() -> dict:
    """
    Get all Fyers credentials.

    Returns:
        Dictionary with keys: appId, secretID, REDIRECT, auth_code, access_token

    Example:
        >>> creds = get_credentials()
        >>> app_id = creds['appId']
        >>> access_token = creds['access_token']
    """
    return {
        'appId': get_credential('appId'),
        'secretID': get_credential('secretID'),
        'REDIRECT': get_credential('REDIRECT') or 'http://127.0.0.1:5000',
        'auth_code': get_credential('auth_code'),
        'access_token': get_credential('access_token'),
    }


def set_credential(key: str, value: str, use_keyring: bool = True) -> bool:
    """
    Store a credential securely.

    Args:
        key: Credential name (e.g., 'appId', 'secretID')
        value: Credential value
        use_keyring: If True, store in Windows Credential Manager (recommended)

    Returns:
        True if stored successfully
    """
    if use_keyring and KEYRING_AVAILABLE:
        return set_in_keyring(key, value)
    else:
        # Fallback to .env file
        return set_in_env_file(key, value)


def set_in_env_file(key: str, value: str) -> bool:
    """Store credential in .env file."""
    try:
        # Read existing .env
        env_content = ""
        if ENV_FILE_PATH.exists():
            with open(ENV_FILE_PATH, 'r', encoding='utf-8') as f:
                env_content = f.read()

        # Update or add the key
        lines = env_content.splitlines()
        key_found = False
        for i, line in enumerate(lines):
            if line.strip().startswith(f"{key}="):
                lines[i] = f"{key}={value}"
                key_found = True
                break

        if not key_found:
            lines.append(f"{key}={value}")

        # Write back
        ENV_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(ENV_FILE_PATH, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        # Set restrictive permissions on Windows
        try:
            import stat
            os.chmod(ENV_FILE_PATH, stat.S_IRUSR | stat.S_IWUSR)
        except Exception:
            pass

        return True
    except Exception as e:
        print(f"Error: Failed to write .env file: {e}")
        return False


def setup_credentials():
    """
    Interactive setup: prompt user for credentials and store securely.

    Run this once to set up your Fyers API credentials.
    """
    print("=" * 80)
    print("FYERS CREDENTIALS SETUP")
    print("=" * 80)
    print()
    print("This will store your Fyers API credentials securely in Windows Credential Manager.")
    print("You only need to run this once.")
    print()

    if not KEYRING_AVAILABLE:
        print("ERROR: 'keyring' library not installed.")
        print("Install it with: pip install keyring")
        return False

    credentials = {
        'appId': 'Fyers App ID (from https://myapi.fyers.in/)',
        'secretID': 'Fyers Secret ID',
        'REDIRECT': 'Redirect URL (default: http://127.0.0.1:5000)',
    }

    print("Please enter your Fyers API credentials:")
    print()
    for key, prompt in credentials.items():
        # Check if already exists
        existing = get_from_keyring(key)
        if existing:
            print(f"[{key}] Already configured. Press Enter to keep, or type new value to update.")
            value = input(f"{prompt}: ").strip()
            if not value:
                print(f"  Keeping existing {key}")
                continue
        else:
            value = input(f"{prompt}: ").strip()
            if not value:
                print(f"  Skipping {key}")
                continue

        if set_in_keyring(key, value):
            print(f"  ✓ Stored {key} securely in Windows Credential Manager")
        else:
            print(f"  ✗ Failed to store {key}")
            return False
        print()

    print("=" * 80)
    print("SETUP COMPLETE!")
    print("=" * 80)
    print()
    print("Your credentials are now stored securely.")
    print("You can now use the trading system without plain-text passwords.")
    print()
    print("To update credentials later, run this script again.")
    print()
    return True


def migrate_from_properties(auto_confirm: bool = False):
    """
    Migrate credentials from old plain-text config.properties to secure storage.

    Args:
        auto_confirm: If True, don't prompt for confirmation (for automated use)
    """
    print("=" * 80)
    print("MIGRATE CREDENTIALS FROM config.properties")
    print("=" * 80)
    print()

    if not OLD_CONFIG_PATH.exists():
        print(f"ERROR: {OLD_CONFIG_PATH} not found.")
        return False

    if not KEYRING_AVAILABLE:
        print("ERROR: 'keyring' library not installed.")
        print("Install it with: pip install keyring")
        return False

    # Read old config
    creds = {}
    with open(OLD_CONFIG_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            creds[key.strip()] = value.strip()

    if not creds:
        print("No credentials found in config.properties")
        return False

    print(f"Found {len(creds)} credentials in {OLD_CONFIG_PATH}:")
    for key in creds:
        print(f"  - {key}")
    print()

    # Confirm migration
    if not auto_confirm:
        try:
            response = input("Migrate to Windows Credential Manager? (yes/no): ").strip().lower()
            if response not in ['yes', 'y']:
                print("Migration cancelled.")
                return False
        except EOFError:
            print("No input available, use auto_confirm=True for non-interactive mode.")
            return False

    # Store in keyring
    success = 0
    for key, value in creds.items():
        if set_in_keyring(key, value):
            print(f"  ✓ Migrated {key}")
            success += 1
        else:
            print(f"  ✗ Failed to migrate {key}")

    print()
    print(f"Migrated {success}/{len(creds)} credentials to Windows Credential Manager.")
    print()

    # Ask to delete old file
    delete_file = auto_confirm
    if not auto_confirm:
        try:
            response = input(f"Delete old {OLD_CONFIG_PATH}? (yes/no): ").strip().lower()
            delete_file = response in ['yes', 'y']
        except EOFError:
            pass

    if delete_file:
        try:
            OLD_CONFIG_PATH.unlink()
            print(f"  ✓ Deleted {OLD_CONFIG_PATH}")
        except Exception as e:
            print(f"  ✗ Failed to delete: {e}")
    else:
        print(f"  Keeping {OLD_CONFIG_PATH}")
        print("  WARNING: File still contains plain-text credentials!")

    print()
    print("=" * 80)
    print("MIGRATION COMPLETE!")
    print("=" * 80)
    return True


def list_stored_credentials():
    """List all stored credentials (values are masked)."""
    print("=" * 80)
    print("STORED CREDENTIALS")
    print("=" * 80)
    print()

    keys = ['appId', 'secretID', 'REDIRECT', 'auth_code', 'access_token']
    for key in keys:
        value = get_credential(key)
        if value:
            masked = value[:4] + '*' * (len(value) - 8) + value[-4:] if len(value) > 8 else '****'
            source = 'keyring' if get_from_keyring(key) else 'env' if get_from_env(key) else 'file'
            print(f"  {key:15s}: {masked:30s} [{source}]")
        else:
            print(f"  {key:15s}: <not set>")
    print()


def create_env_example():
    """Create .env.example file with placeholders."""
    content = """# Fyers API Credentials
# DO NOT COMMIT THIS FILE WITH REAL VALUES
# Copy this to .env and fill in your actual credentials
# Or use: py -c "from Config.secure_config import setup_credentials; setup_credentials()"

appId=YOUR_APP_ID_HERE
secretID=YOUR_SECRET_ID_HERE
REDIRECT=http://127.0.0.1:5000
auth_code=YOUR_AUTH_CODE_HERE
access_token=YOUR_ACCESS_TOKEN_HERE
"""
    try:
        with open(ENV_EXAMPLE_PATH, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Created {ENV_EXAMPLE_PATH}")
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "setup":
            setup_credentials()
        elif command == "migrate":
            migrate_from_properties()
        elif command == "list":
            list_stored_credentials()
        elif command == "example":
            create_env_example()
        else:
            print(f"Unknown command: {command}")
            print("Available: setup, migrate, list, example")
    else:
        print("Fyers Secure Configuration Manager")
        print()
        print("Usage:")
        print("  py -m Config.secure_config setup    - Set up credentials interactively")
        print("  py -m Config.secure_config migrate  - Migrate from config.properties")
        print("  py -m Config.secure_config list     - List stored credentials")
        print("  py -m Config.secure_config example  - Create .env.example file")
        print()
        print("Or in Python:")
        print("  from Config.secure_config import setup_credentials, migrate_from_properties")
        print("  setup_credentials()")
        print("  migrate_from_properties()")
