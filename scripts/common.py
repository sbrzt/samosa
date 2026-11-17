# scripts/common.py

import sys
import yaml
from pathlib import Path

EX = "https://www.example.org/"


def individual_id(name):
    """Build the local identifier of a named individual.

    Args:
        name: Human-readable name, e.g. `"Ada Lovelace"`.

    Returns:
        The name trimmed, lower-cased, with spaces as dashes (`"ada-lovelace"`).
    """
    return name.strip().lower().replace(" ", "-")


def resolve_iteration(name):
    """Find an iteration directory.

    Args:
        name: Path to the iteration, or its name under `iterations/`.

    Returns:
        The first existing path among `name` and `iterations/<name>`.

    Raises:
        SystemExit: If neither path exists.
    """
    for path in (Path(name), Path("iterations") / name):
        if path.exists():
            return path
    print(f"Error: iteration '{name}' not found.")
    sys.exit(1)


def load_yaml(path):
    """Load a YAML file with `yaml.safe_load`.

    Args:
        path: Path of the YAML file.

    Returns:
        The parsed YAML content.

    Raises:
        SystemExit: If the file does not exist.
    """
    if not path.exists():
        print(f"Error: File {path} not found.")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _str(dumper, s):
    """Represent strings, multi-line ones as literal blocks (`|`).

    Literal blocks keep queries readable and editable. PyYAML refuses literal
    style when lines have trailing spaces, so those are stripped.

    Args:
        dumper: The YAML dumper.
        s: String to represent.

    Returns:
        The YAML scalar node.
    """
    if "\n" in s:
        s = "\n".join(line.rstrip() for line in s.split("\n"))
        return dumper.represent_scalar("tag:yaml.org,2002:str", s, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", s)


class _Dumper(yaml.SafeDumper):
    """SafeDumper with literal-block multi-line strings (see `_str`)."""


_Dumper.add_representer(str, _str)


def dump_yaml(data, path):
    """Write data to a YAML file, keeping key order and multi-line strings readable.

    Args:
        data: Object to serialize.
        path: Destination file path. Overwritten if it exists.
    """
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=1000)
