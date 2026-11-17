# scripts/check_consistency.py

import logging
import sys
from pathlib import Path
from owlrl import DeductiveClosure, OWLRL_Semantics
from rdflib import Graph, Namespace

ERR = Namespace("http://www.daml.org/2002/03/agents/agent-ont#")

# rdflib logs a traceback for each ill-typed literal (e.g. "four"^^xsd:integer)
# while parsing; `inconsistencies` reports the same problem as one line.
logging.getLogger("rdflib.term").setLevel(logging.ERROR)


def reason(graph):
    """Compute the OWL 2 RL deductive closure of a graph.

    Args:
        graph: Graph to expand. Left unchanged.

    Returns:
        A new graph with the asserted and the inferred triples. Inconsistencies
        found by owlrl are recorded in it, see `inconsistencies`.
    """
    closure = Graph()
    for prefix, ns in graph.namespaces():
        closure.bind(prefix, ns)
    closure += graph
    DeductiveClosure(OWLRL_Semantics).expand(closure)
    return closure


def inconsistencies(closure):
    """List the inconsistencies owlrl recorded in a closure from `reason`.

    The check is sound but incomplete: DL-only clashes are not detected.

    Args:
        closure: Graph returned by `reason`.

    Returns:
        Sorted list of error messages, empty if the graph is consistent.
    """
    return sorted(str(m) for m in closure.objects(None, ERR.error))


def main():
    """Check the merged ontology for consistency under OWL 2 RL.

    Loads `project/tbox.ttl` and `project/abox.ttl`, computes the OWL 2 RL
    deductive closure, and reports any inconsistencies owlrl records.

    Raises:
        SystemExit: If an input file is missing or the graph is inconsistent.
    """
    project_dir = Path.cwd() / "project"
    graph = Graph()
    for name in ("tbox.ttl", "abox.ttl"):
        if not (project_dir / name).exists():
            print(f"Error: '{project_dir / name}' not found. Run merge first.")
            sys.exit(1)
        graph.parse(project_dir / name, format="turtle")

    closure = reason(graph)
    errors = inconsistencies(closure)
    if errors:
        print("Inconsistent (OWL 2 RL):")
        for m in errors:
            print(f"  {m}")
        sys.exit(1)
    print(f"Consistent (OWL 2 RL): {len(graph)} triples, {len(closure) - len(graph)} inferred.")


if __name__ == "__main__":
    main()
