# scripts/check_consistency.py

import io
import logging
import sys
from pathlib import Path
from owlready2 import OwlReadyInconsistentOntologyError, OwlReadyJavaError, World, sync_reasoner_hermit
from owlrl import DeductiveClosure, OWLRL_Semantics
from rdflib import Graph, Literal, Namespace
from rdflib.namespace import OWL, RDF, RDFS, XSD

ERR = Namespace("http://www.daml.org/2002/03/agents/agent-ont#")
BUILTIN = tuple(str(ns) for ns in (RDF, RDFS, OWL, XSD))

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


def individuals(graph):
    """List the individuals of a graph.

    Args:
        graph: TBox+ABox graph.

    Returns:
        Sorted list of the subjects typed `owl:NamedIndividual` or with a class
        outside the RDF, RDFS, OWL and XSD namespaces.
    """
    return sorted({s for s, t in graph.subject_objects(RDF.type)
                   if t == OWL.NamedIndividual or not str(t).startswith(BUILTIN)})


def culprits(graph, inds):
    """Find the individuals whose own assertions make a graph inconsistent (HermiT).

    Each individual is checked alone: its assertions, plus the graph without
    any individual's assertions. Clashes that need several individuals (e.g. a
    functional property with two different values) are not found.

    Args:
        graph: Inconsistent TBox+ABox graph.
        inds: Individuals of `graph`, see `individuals`.

    Returns:
        Sorted list of the individuals inconsistent on their own.
    """
    # ponytail: one HermiT run (~0.5 s) per individual, only on failure; bisect if ABoxes grow large
    base = Graph()
    base += graph
    for i in inds:
        base.remove((i, None, None))
    out = []
    for i in inds:
        g = Graph()
        g += base
        g += graph.triples((i, None, None))
        if hermit(g, unsatisfiable=False):
            out.append(i)
    return out


def problems(graph):
    """Run the SAMOD consistency test on TBox+ABox.

    Ill-typed literals fail, then HermiT (OWL 2 DL, see `hermit`) checks the
    rest. Without Java, falls back to owlrl (OWL 2 RL), which is sound but
    misses DL-only clashes. If HermiT finds the graph inconsistent, the
    explanation comes from owlrl or, for DL-only clashes, from `culprits`.

    Args:
        graph: TBox+ABox graph. Left unchanged.

    Returns:
        List of `(level, message, details)` triples, `level` being `"PASS"`,
        `"FAIL"` or `"WARN"` and `details` a dict of extra JSON fields:
        `reasoner`, `triples` and `individuals` (counts) on the `PASS`,
        `explanation` (list of strings) on an inconsistency, and `term`,
        `subject`, `value`, `datatype` on an ill-typed literal. A consistent
        graph gives exactly one `PASS`.
    """
    bad = ill_typed(graph)
    out = [("FAIL", f"{s.n3()} {p.n3()} {o.n3()}: the value does not fit its datatype",
            {"term": str(p), "subject": str(s), "value": str(o), "datatype": str(o.datatype)}) for s, p, o in bad]
    clean = Graph()
    clean += graph
    for t in bad:
        clean.remove(t)
    inds = individuals(clean)
    found = hermit(clean, unsatisfiable=False)
    if found is None:
        reasoner = "owlrl (OWL 2 RL)"
        out.append(("WARN", "Java not found, OWL 2 RL (owlrl) used instead of HermiT (OWL 2 DL)", {"reasoner": reasoner}))
        out += [("FAIL", f"inconsistent (OWL 2 RL): {m}", {"reasoner": reasoner, "explanation": [m]})
                for m in inconsistencies(reason(clean))]
    else:
        reasoner = "HermiT (OWL 2 DL)"
        for m in found:
            details = {"reasoner": reasoner}
            if m.startswith("inconsistent"):
                details["explanation"] = (inconsistencies(reason(clean))
                                          or [f"the assertions on <{i}> clash with the TBox" for i in culprits(clean, inds)]
                                          or ["no single individual causes it: look at assertions linking several "
                                              "individuals, or at the TBox"])
            out.append(("FAIL", m, details))
    if not any(level == "FAIL" for level, _, _ in out):
        out.append(("PASS", f"consistent according to {reasoner}: {len(graph)} triples, {len(inds)} individuals",
                    {"reasoner": reasoner, "triples": len(graph), "individuals": len(inds)}))
    return out


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
    for level, m, details in found:
        print(f"{level} {m}")
        for line in details.get("explanation", []):
            print(f"  {line}")
    if any(level == "FAIL" for level, _, _ in found):
        print("Inconsistent.")
        sys.exit(1)


if __name__ == "__main__":
    main()
