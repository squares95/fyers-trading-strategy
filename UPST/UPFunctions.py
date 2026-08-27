import ast
import json
import os

file_path = os.path.join(os.path.dirname(__file__), 'UPSTX_Config.properties')

def get_property(key):
    with open(file_path, 'r') as f:
        for line in f:
            if line.strip().startswith('#') or '=' not in line:
                continue
            k, v = line.strip().split('=', 1)
            if k.strip() == key:
                return v.strip()
    return None

def upsert_property(key, value):
    lines = []
    key_found = False

    with open(file_path, 'r') as f:
        for line in f:
            if line.strip().startswith(f"{key}="):
                lines.append(f"{key}={value}\n")
                key_found = True
            else:
                lines.append(line)

    if not key_found:
        lines.append(f"{key}={value}\n")

    with open(file_path, 'w') as f:
        f.writelines(lines)

def lookupKeys(filename, key1_name, key1_value, *key_names):
    """
    This function looks for a match for key1_name and key1_value,
    then returns a dictionary of key names with their corresponding values.

    :param filename: The JSON file to read
    :param key1_name: The key to search for
    :param key1_value: The value to match with key1_name
    :param key_names: The dynamic keys to fetch values for
    :return: A dictionary with key-value pairs or None if no match is found
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

    # Example usage
    # filename = 'UP_Keys.json'
    # key1_name = 'trading_symbol'
    # key1_value = 'SBIN'
    # key_names = ['instrument_key']
    # result = lookupKeys(filename, key1_name, key1_value, *key_names)
    # print(result.get('instrument_key'))  # Output will be a dictionary like {'B': 'val2', 'C': None, 'D': None}


# token = get_property('token')
# print(token)
