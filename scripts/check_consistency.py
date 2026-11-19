# scripts/check_consistency.py

import io
import logging
import sys
from pathlib import Path
from owlready2 import OwlReadyInconsistentOntologyError, OwlReadyJavaError, World, sync_reasoner_hermit
from owlrl import DeductiveClosure, OWLRL_Semantics
from rdflib import Graph, Literal, Namespace
from rdflib.namespace import OWL

ERR = Namespace("http://www.daml.org/2002/03/agents/agent-ont#")

# rdflib logs a traceback for each ill-typed literal (e.g. "four"^^xsd:integer)
# while parsing; `ill_typed` reports the same problem as one line.
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


def hermit(graph, unsatisfiable=True):
    """Check a graph with HermiT (OWL 2 DL), through owlready2.

    Needs Java. Datatypes outside the OWL 2 datatype map (e.g. `xsd:date`) are
    ignored. Ill-typed literals must be removed first, see `ill_typed`.

    Args:
        graph: TBox, or TBox+ABox.
        unsatisfiable: If true, also list the unsatisfiable classes.

    Returns:
        List of problems: the graph is inconsistent, HermiT rejects it (e.g. a
        transitive property in a cardinality restriction, a malformed literal),
        or classes are unsatisfiable. Empty if none, None if Java is not installed.
    """
    world = World()
    data = graph.serialize(format="nt", encoding="utf-8")
    world.get_ontology("http://samosa.local/test#").load(fileobj=io.BytesIO(data), format="ntriples")
    try:
        sync_reasoner_hermit(world, infer_property_values=False, ignore_unsupported_datatypes=True, debug=0)
        return [f"<{c.iri}> is unsatisfiable (OWL 2 DL, HermiT)"
                for c in world.inconsistent_classes() if unsatisfiable and c.iri != str(OWL.Nothing)]
    except FileNotFoundError:
        return None
    except OwlReadyInconsistentOntologyError:
        return ["inconsistent (OWL 2 DL, HermiT)"]
    except OwlReadyJavaError as e:
        line = next((l for l in str(e).splitlines() if "Exception" in l), str(e).strip())
        return [f"rejected by HermiT: {line.split(': ', 1)[-1]}"]
    finally:
        world.close()


def ill_typed(graph):
    """Find literals whose value does not fit their datatype, e.g. `"four"^^xsd:integer`.

    Args:
        graph: Graph to check.

    Returns:
        Sorted list of the triples with an ill-typed literal.
    """
    return sorted(t for t in graph if isinstance(t[2], Literal) and t[2].ill_typed)


def problems(graph):
    """Run the SAMOD data test: check TBox+ABox for consistency.

    Ill-typed literals fail, then HermiT (OWL 2 DL, see `hermit`) checks the
    rest. Without Java, falls back to owlrl (OWL 2 RL), which is sound but
    misses DL-only clashes.

    Args:
        graph: TBox+ABox graph. Left unchanged.

    Returns:
        List of `(level, message)` pairs, `level` being `"FAIL"` or `"WARN"`.
        Empty if the graph is consistent.
    """
    bad = ill_typed(graph)
    out = [("FAIL", f"{s.n3()} {p.n3()} {o.n3()}: the value does not fit its datatype") for s, p, o in bad]
    clean = Graph()
    clean += graph
    for t in bad:
        clean.remove(t)
    found = hermit(clean, unsatisfiable=False)
    if found is None:
        out.append(("WARN", "Java not found, OWL 2 RL (owlrl) used instead of HermiT (OWL 2 DL)"))
        found = [f"inconsistent (OWL 2 RL): {m}" for m in inconsistencies(reason(clean))]
    return out + [("FAIL", m) for m in found]


def main():
    """Check the merged ontology for consistency (SAMOD data test).

    Loads `project/tbox.ttl` and `project/abox.ttl` and runs `problems` on them.

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

    found = problems(graph)
    for level, m in found:
        print(f"{level} {m}")
    if any(level == "FAIL" for level, _ in found):
        print("Inconsistent.")
        sys.exit(1)
    print(f"Consistent: {len(graph)} triples.")


if __name__ == "__main__":
    main()
