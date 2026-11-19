# scripts/test_iteration.py

import re
import sys
from pathlib import Path
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS
from scripts import check_consistency
from scripts.align import aliases, load_prefixes
from scripts.common import EX, RESULTS, load_yaml, report, resolve_iteration, write_results
from scripts.milestone import promote
from scripts.model_test import run_model_test
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
    used |= {(o, "tbox") for _, p, o in tbox
             if p != RDFS.isDefinedBy and isinstance(o, URIRef) and o.startswith(EX)}
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


def run_tests(tbox, abox, cqs, label, key="query", reason=False, aliases=None):
    """Run the formal data and query tests of one test case and print the results.

    Fails on terms the TBox does not describe (`undeclared`), ABox values of
    the wrong kind (`misused`), inconsistencies of TBox+ABox (OWL 2 DL with
    HermiT, see `check_consistency.problems`), and
    failing competency question queries.

    Args:
        tbox: TBox graph, the iteration's own or the current model.
        abox: ABox graph of the test case.
        cqs: Competency questions from `requirements.yaml`, or None.
        label: Name shown in each printed line, e.g. the iteration name.
        key: Field holding the SPARQL query, `"query"` or `"refactored_query"`.
        reason: If true, run the queries on the OWL 2 RL closure of TBox+ABox.
        aliases: See `verify_cqs._match`.

    Returns:
        A `(checked, failures)` pair: the number of queries run and the number
        of failed tests.
    """
    failures = 0
    for term, where in undeclared(tbox, abox):
        report("FAIL", label, "data", f"<{term}> is not described in the TBox (used in the {where})", term=str(term))
        failures += 1
    for s, p, o in misused(tbox, abox):
        report("FAIL", label, "data", f"<{s}> <{p}> has the wrong kind of value: {o.n3()}", term=str(p))
        failures += 1
    graph = tbox + abox
    for level, message in check_consistency.problems(graph):
        report(level, label, "data", message)
        failures += level == "FAIL"
    if not failures:
        report("PASS", label, "data", "all checks pass")
    checked, failed = run_queries(check_consistency.reason(graph) if reason else graph, cqs, label, key, aliases)
    return checked, failures + failed


def main(iteration: str, refactored: bool = False, reason: bool = False):
    """Run the model, data and query tests of an iteration on its TBox and ABox.

    Runs the model test on the TBox (`model_test.run_model_test`), then
    `run_tests` and, on the first version only, warns (without failing)
    about glossary terms unused by the queries or the ABox. If everything
    passes, raises the iteration's status to `tested` (first version) or
    `aligned` (refactored), see `milestone.promote`. Writes every result,
    passing or not, to `results.json` next to the tested TBox (see
    `common.write_results`).

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
    RESULTS.clear()

    graphs = {}
    for name in ("tbox", "abox"):
        if not (base / f"{name}.ttl").exists():
            print(f"Error: {base / name}.ttl not found. Run the previous step first.")
            sys.exit(1)
        graphs[name] = Graph().parse(base / f"{name}.ttl", format="turtle")
    data = load_yaml(it / "requirements.yaml")

    if not refactored:
        for name, where in uncovered(data, graphs["abox"]):
            report("WARN", it.name, "coverage", f"glossary term '{name}' is not used by the {where}", term=name,
                   missing_from=where)
    key = "refactored_query" if refactored else "query"
    names = aliases(data, load_prefixes()) if refactored else None
    model_failures = run_model_test(graphs["tbox"], it.name)
    checked, failures = run_tests(graphs["tbox"], graphs["abox"], data.get("competency_questions"),
                                  it.name, key, reason, names)
    failures += model_failures
    write_results(base / "results.json", checked > 0 and not failures, iteration=it.name,
                  phase="refactored" if refactored else "first-version", reason=reason)
    if checked == 0:
        print("No competency questions with a query found.")
        sys.exit(1)
    if failures:
        sys.exit(1)
    promote(it, "aligned" if refactored else "tested")
    sys.exit(0)


if __name__ == "__main__":
    main(sys.argv[1], "--refactored" in sys.argv[2:], "--reason" in sys.argv[2:])
