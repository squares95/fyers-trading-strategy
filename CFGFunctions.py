import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOGIN_CONFIG_PATH = ROOT / "Config" / "LoginConfig" / "config.properties"


def get_property(key, file_path: str | Path = LOGIN_CONFIG_PATH):
    path = Path(file_path)
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip().startswith("#") or "=" not in line:
                continue
            k, v = line.strip().split("=", 1)
            if k.strip() == key:
                return v.strip()
    return None


def upsert_property(file_path, key, value=None):
    if value is None:
        value = key
        key = file_path
        file_path = LOGIN_CONFIG_PATH

    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("", encoding="utf-8")

    lines = []
    key_found = False

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip().startswith(f"{key}="):
                lines.append(f"{key}={value}\n")
                key_found = True
            else:
                lines.append(line)

    if not key_found:
        lines.append(f"{key}={value}\n")

    with path.open("w", encoding="utf-8") as f:
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
    with open(filename) as file:
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

    # Example usage
    # filename = 'UP_Keys.json'
    # :param key1_name: 'trading_symbol'
    # :param key1_value: 'SBIN'
    # :param key_names: ['instrument_key']
    # result = lookupKeys(filename, key1_name, key1_value, *key_names)
    # print(result.get('instrument_key'))  # Output will be a dictionary like {'B': 'val2', 'C': None, 'D': None}


if __name__ == "__main__":
    print(get_property("appId"))


GetProperty = get_property
UpsertProperty = upsert_property
FetchSymbols = fetchSymbols
LookupKeys = lookupKeys
