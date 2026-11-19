from rdflib import Literal, URIRef

from conftest import graph
from scripts.verify_cqs import _cell, _diff, _match, _rows, run_queries

EX = "https://www.example.org/"


def test_cell_splits_iris_and_keeps_other_terms():
    assert _cell(URIRef(EX + "rex")) == (EX + "rex", "rex")
    assert _cell(URIRef("http://example.org/")) == ("http://example.org/", "http://example.org/")
    assert _cell(Literal("x")) == ("x", None)
    assert _cell(None) == ("", None)


def test_match_local_name_ignores_case_and_namespace():
    assert _match(":Rex", URIRef(EX + "rex"))
    assert _match(":isCitedBy", URIRef("http://purl.org/spar/cito/isCitedBy"))
    assert not _match(":rex", URIRef(EX + "tom"))


def test_match_aliases_follow_alignment():
    rights = URIRef("http://purl.org/dc/terms/rights")
    assert not _match(":hasRights", rights)
    assert _match(":hasRights", rights, {"hasrights": "rights"})


def test_match_literals_exactly_after_stripping_quotes():
    assert _match('"CC-BY"', Literal("CC-BY"))
    assert _match(" CC-BY ", Literal("CC-BY"))
    assert not _match("cc-by", Literal("CC-BY"))
    assert _match(":x", Literal(":x"))  # a literal is never matched by local name


def test_rows_normalizes_strings_and_lists():
    assert _rows("a, b") == [["a", "b"]]
    assert _rows(["a, b", "c"]) == [["a", "b"], ["c"]]
    assert _rows([["a, with comma", "b"]]) == [["a, with comma", "b"]]


def test_diff_reports_missing_and_unexpected_rows_ignoring_order():
    rows = [(URIRef(EX + "a"), Literal("1")), (URIRef(EX + "b"), Literal("2"))]
    assert _diff(_rows([":b, 2", ":a, 1"]), rows) == ([], [])
    missing, extra = _diff(_rows([":a, 1", ":c, 3"]), rows)
    assert missing == [[":c", "3"]] and extra == [rows[1]]
    assert _diff(_rows([":a, 1, x"]), rows)[0] == [[":a", "1", "x"]]  # wrong width never matches


def test_diff_matches_each_result_row_once():
    row = (URIRef(EX + "a"),)
    assert _diff(_rows([":a", ":a"]), [row]) == ([[":a"]], [])
    assert _diff(_rows([":a"]), [row, row]) == ([], [row])


G = graph(":rex :eats :tom . :tom :eats :jerry .")


def test_run_queries_counts_passes_and_failures(capsys):
    cqs = [
        {"id": "ok", "query": "SELECT ?a ?b WHERE { ?a :eats ?b }", "expected_result": [":rex, :tom", ":tom, :jerry"]},
        {"id": "wrong", "query": "SELECT ?a WHERE { ?a :eats :tom }", "expected_result": [":tom"]},
        {"id": "any", "query": "SELECT ?a WHERE { ?a :eats ?b }"},
        {"id": "empty", "query": "SELECT ?a WHERE { ?a :flies ?b }"},
        {"id": "broken", "query": "SELECT WHERE {"},
        {"id": "skipped", "question": "no query yet"},
    ]
    assert run_queries(G, cqs, "it") == (5, 3)
    out = capsys.readouterr().out
    assert "PASS [it] ok" in out and "PASS [it] any" in out
    assert "FAIL [it] wrong" in out and "missing:    :tom" in out and "unexpected: " + EX + "rex" in out
    assert "FAIL [it] empty" in out and "FAIL [it] broken: query error" in out
    assert "skipped" not in out


def test_run_queries_uses_the_given_key_and_aliases(capsys):
    cqs = [{"id": "1", "query": "SELECT ?x WHERE { ?x ?p ?o }",
            "refactored_query": "SELECT ?p WHERE { :rex ?p ?o }", "expected_result": [":devours"]}]
    assert run_queries(G, cqs, "it", "refactored_query", {"devours": "eats"}) == (1, 0)
    assert run_queries(G, None, "it") == (0, 0)
