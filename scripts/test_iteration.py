# scripts/test_iteration.py

import re
import sys
from pathlib import Path
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF
from scripts import check_consistency
from scripts.common import EX, load_yaml, resolve_iteration
from scripts.generate_tbox import BASE_PREFIXES, local_name
from scripts.verify_cqs import run_queries

BUILTIN = tuple(ns for p, ns in BASE_PREFIXES.items() if p)


def undeclared(tbox, abox):
    """Find terms that the ABox or the TBox uses but the TBox does not describe.

    Checks the ABox predicates and classes (`rdf:type` objects), and the
    local (`:`) terms that the TBox refers to (e.g. domains, ranges,
    superclasses). Terms in the RDF, RDFS, OWL and XSD namespaces are skipped.

    Args:
        tbox: TBox graph.
        abox: ABox graph.

    Returns:
        Sorted list of `(term, where)` pairs, `where` being `"abox"` or `"tbox"`.
    """
    declared = set(tbox.subjects())
    used = {(p, "abox") for p in abox.predicates() if p != RDF.type}
    used |= {(c, "abox") for c in abox.objects(None, RDF.type)}
    used |= {(o, "tbox") for o in tbox.objects() if isinstance(o, URIRef) and o.startswith(EX)}
    return sorted((t, w) for t, w in used if not str(t).startswith(BUILTIN) and t not in declared)


def misused(tbox, abox):
    """Find ABox values of the wrong kind for their property.

    An object property needs an IRI (a literal there is usually a misspelled
    individual name), a datatype property needs a literal.

    Args:
        tbox: TBox graph.
        abox: ABox graph.

    Returns:
        List of `(subject, property, value)` triples with the wrong kind of value.
    """
    return [(s, p, o) for s, p, o in abox
            if ((p, RDF.type, OWL.ObjectProperty) in tbox and isinstance(o, Literal))
            or ((p, RDF.type, OWL.DatatypeProperty) in tbox and not isinstance(o, Literal))]


def uncovered(data, abox):
    """Find glossary terms that no CQ query or no ABox triple uses.

    These are rhetorical warnings, not failures: an unused term may be
    irrelevant to the scenario, or the CQs and examples may be incomplete.

    Args:
        data: Parsed `requirements.yaml` content.
        abox: First-version ABox graph.

    Returns:
        List of `(term, missing_from)` pairs, `missing_from` being
        `"queries"` or `"abox"`.
    """
    queries = "\n".join(cq.get("query") or "" for cq in data.get("competency_questions") or [])
    nodes = set(abox.all_nodes()) | set(abox.predicates())
    missing = []
    for term in data.get("glossary") or []:
        if not term.get("term") or not term.get("type"):
            continue
        name = local_name(term)
        if not re.search(rf"[:/#]{re.escape(name)}\b", queries, flags=re.I):
            missing.append((name, "queries"))
        if URIRef(EX + name) not in nodes:
            missing.append((name, "abox"))
    return missing


def main(iteration: str, refactored: bool = False, reason: bool = False):
    """Run the data and query tests of an iteration on its TBox and ABox.

    Fails if the ABox or TBox uses terms the TBox does not describe, if an
    ABox value has the wrong kind for its property, if TBox+ABox is
    inconsistent under OWL 2 RL, or if a competency question query fails.
    Warns (without failing) about glossary terms unused by the queries or
    the ABox.

    Args:
        iteration: Iteration path or name, resolved with `resolve_iteration`.
        refactored: If true, read the graphs from `refactoring/<iteration>/` and
            run each `refactored_query` instead of `query`.
        reason: If true, run the queries on the OWL 2 RL closure of
            TBox+ABox, so CQs that rely on inference (subclasses, inverses,
            domains) can pass.

    Raises:
        SystemExit: Always. Exit code 0 if all tests pass, 1 if a graph file is
            missing, no query is found, or any test fails.
    """
    it = resolve_iteration(iteration)
    base = Path("refactoring") / it.name if refactored else it

    graphs = {}
    for name in ("tbox", "abox"):
        if not (base / f"{name}.ttl").exists():
            print(f"Error: {base / name}.ttl not found. Run the previous step first.")
            sys.exit(1)
        graphs[name] = Graph().parse(base / f"{name}.ttl", format="turtle")
    tbox, abox = graphs["tbox"], graphs["abox"]
    graph = tbox + abox
    data = load_yaml(it / "requirements.yaml")

    failures = 0
    for term, where in undeclared(tbox, abox):
        print(f"FAIL [{it.name}] {where}: <{term}> is not described in the TBox")
        failures += 1
    for s, p, o in misused(tbox, abox):
        print(f"FAIL [{it.name}] abox: <{s}> <{p}> has the wrong kind of value: {o.n3()}")
        failures += 1
    closure = check_consistency.reason(graph)
    for message in check_consistency.inconsistencies(closure):
        print(f"FAIL [{it.name}] inconsistent (OWL 2 RL): {message}")
        failures += 1
    if not refactored:
        for name, where in uncovered(data, abox):
            print(f"WARN [{it.name}] glossary term '{name}' is not used by the {where}")

    key = "refactored_query" if refactored else "query"
    checked, failed = run_queries(closure if reason else graph, data.get("competency_questions"), it.name, key)
    if checked == 0:
        print("No competency questions with a query found.")
        sys.exit(1)
    sys.exit(1 if failures or failed else 0)


if __name__ == "__main__":
    main(sys.argv[1], "--refactored" in sys.argv[2:], "--reason" in sys.argv[2:])
