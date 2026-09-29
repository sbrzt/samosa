# scripts/common.py

import sys
import yaml
from pathlib import Path

EX = "https://www.example.org/"


def individual_id(name):
    """Named individuals: lower case, spaces as dashes."""
    return name.strip().lower().replace(" ", "-")


def resolve_iteration(name):
    for path in (Path(name), Path("iterations") / name):
        if path.exists():
            return path
    print(f"Error: iteration '{name}' not found.")
    sys.exit(1)


def load_yaml(path):
    if not path.exists():
        print(f"Error: File {path} not found.")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
