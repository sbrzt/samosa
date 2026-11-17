# scripts/verify_cqs.py

from rdflib import URIRef
from rdflib.namespace import split_uri


def _cell(term):
    """Split a query result term into its printable value and local name.

    Args:
        term: An rdflib term from a result row, or None for an unbound variable.

    Returns:
        A `(value, local)` pair. For an IRI, `local` is its local name, or the full
        IRI if it cannot be split. For anything else, `local` is None, and `value`
        is `""` for None.
    """
    if isinstance(term, URIRef):
        try:
            return str(term), split_uri(term)[1]
        except ValueError:
            return str(term), str(term)
    return ("" if term is None else str(term)), None


def _match(expected, term):
    """Check if one expected cell matches one result term.

    `:name` matches any IRI with that local name, ignoring case (abox lowercases
    individual names), so it also holds after align. Any other expected value must
    equal the term's string value. Surrounding whitespace and quotes are ignored.

    Args:
        expected: Expected cell from `expected_result`.
        term: An rdflib term from a result row.

    Returns:
        True if the term matches.
    """
    value, local = _cell(term)
    expected = str(expected).strip().strip("'\"")
    if expected.startswith(":") and local is not None:
        return expected[1:].casefold() == local.casefold()
    return expected == value


def _rows(expected):
    """Normalize `expected_result` to a list of rows of cells.

    Args:
        expected: A list of rows, or one row. A row is a list of cells or a
            comma-separated string. Use a list row when a cell contains a comma.

    Returns:
        A list of rows, each a list of cells.
    """
    if isinstance(expected, str):
        expected = [expected]
    return [row if isinstance(row, list) else [c.strip() for c in str(row).split(",")] for row in expected]


def _diff(expected, results):
    """Compare expected rows with result rows, ignoring order.

    Each result row can match only one expected row.

    Args:
        expected: Expected rows from `_rows`.
        results: Result rows from the query.

    Returns:
        A `(missing, unexpected)` pair: expected rows with no matching result row,
        and result rows left unmatched.
    """
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
    """Run the competency question queries on a graph and print PASS or FAIL for each.

    A query with an `expected_result` passes if its results match it exactly,
    ignoring order. A query without one passes if it returns any result.
    Competency questions without a `key` query are skipped.

    Args:
        graph: Graph to query.
        cqs: List of competency questions from `requirements.yaml`, or None.
        label: Name shown in each printed line, e.g. the iteration name.
        key: Field holding the SPARQL query, `"query"` or `"refactored_query"`.

    Returns:
        A `(checked, failures)` pair: the number of queries run and the number
        that failed or raised an error.
    """
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
    assert _diff(_rows([":a, x", ":isCitedBy, z"]), rows)[0] == [[":a", "x"]]
    assert _diff(_rows([[":a", "x, y"], [":isCitedBy", "z"]]), rows) == ([], [])
    assert _diff(_rows([":isCitedBy, z"]), rows)[1] == [rows[0]]
    print("ok")
