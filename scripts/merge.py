# scripts/merge.py

import sys
from pathlib import Path
from rdflib import Graph
from scripts import check_consistency
from scripts.common import load_yaml
from scripts.verify_cqs import run_queries


def main(reason: bool = False):
    """Merge the refactored TBoxes and ABoxes of all iterations into `project/`.

    Parses every `refactoring/<iteration>/tbox.ttl` and `abox.ttl` into two
    graphs and runs each iteration's `refactored_query` competency questions on
    their union. Only if all queries pass, writes both graphs to
    `project/tbox.ttl` and `project/abox.ttl`.

    Args:
        reason: If true, run the queries on the OWL 2 RL closure of the merged
            TBox+ABox (see `test --reason`).

    Raises:
        SystemExit: If there are no iterations, an iteration has no refactored
            ABox or TBox, no queries are found, or any query fails.
    """
    root_dir = Path.cwd()
    iter_dirs = sorted(d for d in (root_dir / "iterations").glob("*") if d.is_dir())
    if not iter_dirs:
        print("Error: no iterations found.")
        sys.exit(1)
    missing = [d.name for d in iter_dirs
               if not all((root_dir / "refactoring" / d.name / f).exists() for f in ("abox.ttl", "tbox.ttl"))]
    if missing:
        print(f"Error: no refactoring/ output for: {', '.join(missing)}. Run align first.")
        sys.exit(1)

    tbox, abox = Graph(), Graph()
    for d in iter_dirs:
        tbox.parse(root_dir / "refactoring" / d.name / "tbox.ttl", format="turtle")
        abox.parse(root_dir / "refactoring" / d.name / "abox.ttl", format="turtle")
    graph = check_consistency.reason(tbox + abox) if reason else tbox + abox

    checked = failures = 0
    for d in iter_dirs:
        c, f = run_queries(graph, load_yaml(d / "requirements.yaml").get("competency_questions"), d.name, "refactored_query")
        checked += c
        failures += f
    if checked == 0 or failures:
        print("Queries failed on merged TBox+ABox: nothing written." if failures
              else "No queries found: nothing written.")
        sys.exit(1)

    out = root_dir / "project"
    out.mkdir(exist_ok=True)
    abox.serialize(destination=out / "abox.ttl", format="turtle")
    tbox.serialize(destination=out / "tbox.ttl", format="turtle")
    print(f"Merged {len(iter_dirs)} iteration(s) into {out}/")


if __name__ == "__main__":
    main()
