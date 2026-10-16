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


def _str(dumper, s):
    # Multi-line strings as literal blocks (|) so queries stay readable and editable.
    # Trailing spaces block literal style in PyYAML, so they are stripped.
    if "\n" in s:
        s = "\n".join(line.rstrip() for line in s.split("\n"))
        return dumper.represent_scalar("tag:yaml.org,2002:str", s, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", s)


class _Dumper(yaml.SafeDumper):
    pass


_Dumper.add_representer(str, _str)


def dump_yaml(data, path):
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=1000)
