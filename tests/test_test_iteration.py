import json

import pytest
from rdflib import URIRef

from conftest import graph, zoo
from scripts.common import EX, load_yaml
from scripts.test_iteration import main, misused, run_tests, uncovered, undeclared

TBOX = graph("""
:Animal a owl:Class . :Mammal a owl:Class ; rdfs:subClassOf :Animal .
:eats a owl:ObjectProperty ; rdfs:range :Food .
:hasLegs a owl:DatatypeProperty ; rdfs:range xsd:integer ; rdfs:isDefinedBy : .""")
ABOX = graph(""":rex a :Mammal , owl:Thing ; :eats "fod" ; :hasLeg "4" ; :hasLegs :four .""")
local = lambda term: str(term).rsplit("/", 1)[1]


def run(fn, *args):
    """Call a command and return its exit code (0 if it returns normally)."""
    try:
        fn(*args)
    except SystemExit as e:
        return e.code
    return 0


def test_undeclared_finds_unknown_abox_and_tbox_terms():
    found = {(local(t), where) for t, where in undeclared(TBOX, ABOX)}
    assert found == {("Food", "tbox"), ("hasLeg", "abox")}  # owl:Thing and the isDefinedBy target are skipped


def test_misused_finds_values_of_the_wrong_kind():
    assert {(local(p), str(o)) for _, p, o in misused(TBOX, ABOX)} == {("eats", "fod"), ("hasLegs", EX + "four")}


def test_uncovered_lists_terms_missing_from_queries_and_abox():
    data = {"glossary": [{"term": "animal", "type": "Class"}, {"term": "eats", "type": "ObjectProperty"},
                         {"term": "", "type": ""}],
            "competency_questions": [{"query": "PREFIX ex: <https://www.example.org/> SELECT ?a WHERE { ?a a ex:animal }"},
                                     {"query": None}]}
    assert set(uncovered(data, ABOX)) == {("Animal", "abox"), ("eats", "queries")}


def test_run_tests_counts_every_failure(capsys):
    cqs = [{"id": "1", "query": "SELECT ?x WHERE { ?x a :Animal }", "expected_result": [":rex"]}]
    checked, failures = run_tests(TBOX, ABOX, cqs, "it")
    assert checked == 1
    assert failures == 2 + 2 + 1  # undeclared, misused, query (no reasoning: rex is only a Mammal)
    assert "is not described in the TBox" in capsys.readouterr().out


def test_run_tests_reasoning_and_inconsistency():
    tbox = graph(":Animal a owl:Class . :Mammal a owl:Class ; rdfs:subClassOf :Animal . :legs a owl:DatatypeProperty .")
    cqs = [{"id": "1", "query": "SELECT ?x WHERE { ?x a :Animal }", "expected_result": [":rex"]}]
    assert run_tests(tbox, graph(":rex a :Mammal ."), cqs, "it", reason=True) == (1, 0)
    assert run_tests(tbox, graph(':rex a :Animal ; :legs "x"^^xsd:integer .'), cqs, "it") == (1, 1)


def test_main_passes_and_promotes(iteration, capsys):
    it = iteration(build=True)
    assert run(main, it.name) == 0
    out = capsys.readouterr().out
    assert "PASS [01-zoo] query: CQ 1" in out and "Status of 01-zoo: tested" in out
    assert load_yaml(it / "requirements.yaml")["metadata"]["status"] == "tested"
    results = json.loads((it / "results.json").read_text())
    assert results["passed"] and results["phase"] == "first-version" and results["iteration"] == "01-zoo"
    assert {(r["test"], r["status"]) for r in results["results"]} >= {("model", "PASS"), ("data", "PASS"), ("query", "PASS")}
    cq = next(r for r in results["results"] if r["test"] == "query")
    assert cq["cq"] == "1" and cq["results"] == 1 and cq["missing"] == cq["unexpected"] == []


def test_main_warns_about_uncovered_terms(iteration, capsys):
    data = zoo()
    data["glossary"].append({"term": "plant", "type": "Class", "definition": "x"})
    it = iteration(data=data, build=True)
    assert run(main, it.name) == 0
    out = capsys.readouterr().out
    assert "WARN [01-zoo] coverage: glossary term 'Plant' is not used by the queries" in out
    assert "WARN [01-zoo] coverage: glossary term 'Plant' is not used by the abox" in out


def test_main_fails_without_promoting(iteration):
    it = iteration(data=zoo(abox=[{"individual": "rex", "type": "Animal"}]), build=True)
    assert run(main, it.name) == 1
    assert load_yaml(it / "requirements.yaml")["metadata"]["status"] == "draft"
    results = json.loads((it / "results.json").read_text())
    cq = next(r for r in results["results"] if r["test"] == "query")
    assert not results["passed"] and cq["status"] == "FAIL" and cq["missing"] == [[":rex", ":tom"]]


def test_main_reason_flag(iteration):
    query = {"id": "1", "query": "SELECT ?x WHERE { ?x a :Animal }", "expected_result": [":rex", ":tom"]}
    it = iteration(data=zoo(competency_questions=[query]), build=True)
    assert run(main, it.name) == 1
    assert run(main, it.name, False, True) == 0


def test_main_needs_files_and_queries(iteration, capsys):
    it = iteration()
    assert run(main, it.name) == 1
    assert "tbox.ttl not found" in capsys.readouterr().out
    it = iteration("02-empty", zoo(competency_questions=[]), build=True)
    assert run(main, it.name) == 1
    assert "No competency questions" in capsys.readouterr().out


def test_main_refactored_uses_refactored_queries_and_aliases(iteration, project, capsys):
    data = zoo()
    data["glossary"][0]["align_to"] = "voc:Creature"
    data["competency_questions"][0]["expected_result"] = [":rex, :tom"]
    data["competency_questions"].append({"id": "2", "query": "SELECT ?c WHERE { :tom a ?c }", "expected_result": [":animal"]})
    it = iteration(data=data, aligned=True)
    assert run(main, it.name, True) == 0
    assert "Status of 01-zoo: aligned" in capsys.readouterr().out
    assert URIRef("http://example.com/voc/Creature") in {
        o for o in graph((project / "refactoring" / it.name / "abox.ttl").read_text()).objects()}
