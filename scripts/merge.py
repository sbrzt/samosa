# scripts/merge.py

import sys
from pathlib import Path
from rdflib import Graph
from scripts.common import load_yaml
from scripts.verify_cqs import run_queries


def main():
    root_dir = Path.cwd()
    iter_dirs = sorted(d for d in (root_dir / "iterations").glob("*") if d.is_dir())
    if not iter_dirs:
        print("Error: no iterations found.")
        sys.exit(1)
    missing = [d.name for d in iter_dirs if not (root_dir / "refactoring" / d.name / "abox.ttl").exists()]
    if missing:
        print(f"Error: no refactoring/ output for: {', '.join(missing)}. Run align first.")
        sys.exit(1)

    abox = Graph()
    for d in iter_dirs:
        abox.parse(root_dir / "refactoring" / d.name / "abox.ttl", format="turtle")

    checked = failures = 0
    for d in iter_dirs:
        c, f = run_queries(abox, load_yaml(d / "requirements.yaml").get("competency_questions"), d.name, "refactored_query")
        checked += c
        failures += f
    if checked == 0 or failures:
        print("Queries failed on merged ABox: TBox not merged." if failures
              else "No queries found: TBox not merged.")
        sys.exit(1)

    tbox = Graph()
    for d in iter_dirs:
        tbox.parse(root_dir / "refactoring" / d.name / "tbox.ttl", format="turtle")

    out = root_dir / "project"
    out.mkdir(exist_ok=True)
    abox.serialize(destination=out / "abox.ttl", format="turtle")
    tbox.serialize(destination=out / "tbox.ttl", format="turtle")
    print(f"Merged {len(iter_dirs)} iteration(s) into {out}/")


if __name__ == "__main__":
    main()
