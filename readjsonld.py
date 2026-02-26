import json
import os

def read_jsonld_file(file_path):
    """
    Reads a JSON-LD file and returns its content as a Python dictionary.
    Includes validation and error handling.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)  # Parse JSON-LD as normal JSON
        return data
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON-LD format: {e}")