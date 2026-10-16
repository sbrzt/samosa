# scripts/verify_cqs.py

from rdflib import URIRef
from rdflib.namespace import split_uri


def _cell(term):
    if isinstance(term, URIRef):
        try:
            return str(term), split_uri(term)[1]
        except ValueError:
            return str(term), str(term)
    return ("" if term is None else str(term)), None


def _match(expected, term):
    """`:name` matches any IRI with that local name, ignoring case (abox lowercases
    individual names), so it also holds after align."""
    value, local = _cell(term)
    expected = str(expected).strip().strip("'\"")
    if expected.startswith(":") and local is not None:
        return expected[1:].casefold() == local.casefold()
    return expected == value


def _rows(expected):
    """expected_result: list of rows; a row is a list or a comma-separated string."""
    if isinstance(expected, str):
        expected = [expected]
    return [row if isinstance(row, list) else [c.strip() for c in str(row).split(",")] for row in expected]


def _diff(expected, results):
    """Return (missing expected rows, unexpected result rows), order-insensitive."""
    left = list(results)
    missing = []
    for row in expected:
        hit = next((r for r in left if len(r) == len(row) and all(_match(e, t) for e, t in zip(row, r))), None)
        if hit is None:
            missing.append(row)
        else:
            left.remove(hit)
    return missing, left


def run_queries(graph, cqs, label, key="query"):
    """Run each CQ's `key` query on graph and compare with expected_result. Return (checked, failures)."""
    checked = failures = 0
    for cq in cqs or []:
        query = cq.get(key)
        if not query:
            continue
        checked += 1
        cq_id = cq.get("id") or cq.get("question", "?")
        try:
            results = list(graph.query(query))
        except Exception as e:
            print(f"FAIL [{label}] {cq_id}: query error: {e}")
            failures += 1
            continue
        expected = cq.get("expected_result")
        if not expected:
            ok = bool(results)
            print(f"{'PASS' if ok else 'FAIL'} [{label}] {cq_id}: {len(results)} result(s), no expected_result")
            failures += not ok
            continue
        missing, extra = _diff(_rows(expected), results)
        if not missing and not extra:
            print(f"PASS [{label}] {cq_id}: {len(results)} result(s) match expected_result")
            continue
        failures += 1
        print(f"FAIL [{label}] {cq_id}: results differ from expected_result")
        for row in missing:
            print(f"    missing:    {', '.join(map(str, row))}")
        for row in extra:
            print(f"    unexpected: {', '.join(_cell(t)[0] for t in row)}")
    return checked, failures


if __name__ == "__main__":
    from rdflib import Graph, Literal
    EX = "https://www.example.org/"
    rows = [(URIRef(EX + "a"), Literal("x, y")), (URIRef("http://purl.org/spar/cito/isCitedBy"), Literal("z"))]
    assert _diff(_rows([":a, x", ":isCitedBy, z"]), rows)[0] == [[":a", "x"]]  # comma in literal needs list row
    assert _diff(_rows([[":a", "x, y"], [":isCitedBy", "z"]]), rows) == ([], [])
    assert _diff(_rows([":isCitedBy, z"]), rows)[1] == [rows[0]]
    print("ok")
