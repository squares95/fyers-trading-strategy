import ast
import json
from pathlib import Path

# Import secure config for credential management
try:
    from Config.secure_config import get_credential, set_credential
    SECURE_CONFIG_AVAILABLE = True
except ImportError:
    try:
        from secure_config import get_credential, set_credential
        SECURE_CONFIG_AVAILABLE = True
    except ImportError:
        SECURE_CONFIG_AVAILABLE = False

ROOT = Path(__file__).resolve().parent
LOGIN_CONFIG_PATH = ROOT / "Config" / "LoginConfig" / "config.properties"


def get_property(key, file_path: str | Path = LOGIN_CONFIG_PATH):
    """
    Get property value with secure credential lookup.

    Priority:
    1. Windows Credential Manager (keyring) - MOST SECURE
    2. Environment variable / .env file
    3. Plain-text file (LEGACY - not recommended)

    For sensitive credentials (appId, secretID, auth_code, access_token),
    use the secure storage. For other config, file-based works fine.
    """
    # Try secure config first for sensitive keys
    sensitive_keys = {'appId', 'secretID', 'auth_code', 'access_token', 'REDIRECT'}
    if SECURE_CONFIG_AVAILABLE and key in sensitive_keys:
        value = get_credential(key)
        if value:
            return value

    # Fallback to file
    path = Path(file_path)
    if not path.exists():
        return None
    with path.open('r', encoding='utf-8') as f:
        for line in f:
            if line.strip().startswith('#') or '=' not in line:
                continue
            k, v = line.strip().split('=', 1)
            if k.strip() == key:
                return v.strip()
    return None


def upsert_property(file_path, key, value=None):
    """
    Update or insert a property.

    For sensitive credentials, stores in Windows Credential Manager.
    For other config, stores in file.
    """
    if value is None:
        value = key
        key = file_path
        file_path = LOGIN_CONFIG_PATH

    # Store sensitive keys securely
    sensitive_keys = {'appId', 'secretID', 'auth_code', 'access_token', 'REDIRECT'}
    if SECURE_CONFIG_AVAILABLE and key in sensitive_keys:
        if set_credential(key, value):
            return
        # Fallback to file if keyring fails

    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("", encoding="utf-8")

    lines = []
    key_found = False

    with path.open('r', encoding='utf-8') as f:
        for line in f:
            if line.strip().startswith(f"{key}="):
                lines.append(f"{key}={value}\n")
                key_found = True
            else:
                lines.append(line)

    if not key_found:
        lines.append(f"{key}={value}\n")

    with path.open('w', encoding='utf-8') as f:
        f.writelines(lines)


def fetchSymbols(key=None):
    value = get_property(key) if key else None
    return ast.literal_eval(value) if value else []


def lookupKeys(filename, key1_name, key1_value, *key_names):
    """
    This function looks for a match for key1_name and key1_value,
    then returns a dictionary of key names with their corresponding values.

    :param filename: The JSON file to read
    :param key1_name: The key to search for
    :param key1_value: The value to match with key1_name
    :param key_names: The dynamic keys to fetch values for
    :return: A dictionary of key-value pairs or None if no match is found
    """
    # Read the JSON data from the file
    with open(filename, 'r') as file:
        data = json.load(file)

    # Iterate over each dictionary in the list
    for item in data:
        # Check if key1_name matches key1_value
        if item.get(key1_name) == key1_value:
            result = {}
            for key in key_names:
                result[key] = item.get(key, None)  # Get the value of each dynamic key

            return result  # Return the dictionary with the requested key-value pairs

    return None  # Return None if no match is found


if __name__ == "__main__":
    print(get_property('appId'))


GetProperty = get_property
UpsertProperty = upsert_property
FetchSymbols = fetchSymbols
LookupKeys = lookupKeys
