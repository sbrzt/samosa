# scripts/common.py

import json
import sys
import yaml
from datetime import datetime
from pathlib import Path
from rdflib import URIRef
from rdflib.namespace import OWL, RDF, RDFS

EX = "https://www.example.org/"
KINDS = {OWL.Class: "class", RDFS.Class: "class", OWL.ObjectProperty: "property",
         OWL.DatatypeProperty: "property", RDF.Property: "property", OWL.NamedIndividual: "individual"}


def kind(g, term):
    """Return the kinds (`class`, `property`, `individual`) a TBox declares for a term."""
    return {KINDS[t] for t in g.objects(term, RDF.type) if t in KINDS}


def entities(g):
    """Return the named terms a TBox declares as a class, property or individual."""
    return {s for s in g.subjects(RDF.type, None) if isinstance(s, URIRef) and kind(g, s)}


RESULTS = []  # test results recorded by `report`, written by `write_results`


def report(status, case, test, message, **details):
    """Print a test result and record it for `write_results`.

    Args:
        status: `"PASS"`, `"FAIL"` or `"WARN"`.
        case: Test case, e.g. the iteration name, or `"current model"`.
        test: Kind of test: `"model"`, `"data"`, `"consistency"`, `"query"`, `"coverage"` or `"merge"`.
        message: Human-readable result.
        **details: Extra JSON-serializable fields, e.g. `term` or `cq`.
    """
    print(f"{status} [{case}] {test}: {message}")
    RESULTS.append({"status": status, "case": case, "test": test, "message": message, **details})


def write_results(path, passed, **meta):
    """Write the results recorded by `report` to a JSON file, then clear them.

    Args:
        path: JSON file to write, e.g. `iterations/<iter>/results.json`.
        passed: Whether the whole command passed.
        **meta: Extra top-level fields, e.g. `phase` and `iteration`.
    """
    data = {**meta, "timestamp": datetime.now().isoformat(timespec="seconds"), "passed": passed,
            "results": list(RESULTS)}
    RESULTS.clear()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


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
