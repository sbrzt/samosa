# scripts/test_iteration.py
# Test one iteration: its TBox+ABox against its SPARQL queries.
# Default: original files + requirements.yaml queries. --refactored: refactoring/<iter>/ files.

import sys
from pathlib import Path
from rdflib import Graph
from scripts.common import load_yaml, resolve_iteration
from scripts.verify_cqs import run_queries


def main():
    it = resolve_iteration(sys.argv[1])
    refactored = "--refactored" in sys.argv[2:]
    base = Path("refactoring") / it.name if refactored else it

    graph = Graph()
    for name in ("tbox.ttl", "abox.ttl"):
        if not (base / name).exists():
            print(f"Error: {base / name} not found. Run the previous step first.")
            sys.exit(1)
        graph.parse(base / name, format="turtle")

    cqs = load_yaml(it / "requirements.yaml").get("competency_questions")
    key = "refactored_query" if refactored else "query"
    checked, failures = run_queries(graph, cqs, it.name, key)
    if checked == 0:
        print("No competency questions with a query found.")
        sys.exit(1)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
