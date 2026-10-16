# scripts/check_consistency.py

import sys
from pathlib import Path
from owlrl import DeductiveClosure, OWLRL_Semantics
from rdflib import Graph, Namespace

# owlrl records inconsistencies as error nodes in this namespace
ERR = Namespace("http://www.daml.org/2002/03/agents/agent-ont#")


def main():
    project_dir = Path.cwd() / "project"
    graph = Graph()
    for name in ("tbox.ttl", "abox.ttl"):
        if not (project_dir / name).exists():
            print(f"Error: '{project_dir / name}' not found. Run merge first.")
            sys.exit(1)
        graph.parse(project_dir / name, format="turtle")
    asserted = len(graph)

    # OWL 2 RL closure: sound but incomplete, misses DL-only clashes (unionOf, someValuesFrom, ...)
    DeductiveClosure(OWLRL_Semantics).expand(graph)
    errors = sorted(str(m) for m in graph.objects(None, ERR.error))
    if errors:
        print("Inconsistent (OWL 2 RL):")
        for m in errors:
            print(f"  {m}")
        sys.exit(1)
    print(f"Consistent (OWL 2 RL): {asserted} triples, {len(graph) - asserted} inferred.")


if __name__ == "__main__":
    main()
