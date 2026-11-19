import shutil

import pytest

from conftest import graph, zoo
from scripts.common import EX, load_yaml
from scripts.model_test import hermit, not_dl, run_model_test, undocumented, unsupported_datatypes
from scripts.test_iteration import main

java = pytest.mark.skipif(shutil.which("java") is None, reason="HermiT needs Java")
local = lambda term: str(term).rsplit("/", 1)[1]


def test_undocumented_needs_label_and_non_empty_comment():
    tbox = graph(""":A a owl:Class ; rdfs:label "a" ; rdfs:comment "An A." .
    :b a owl:ObjectProperty ; rdfs:comment " " . :c a owl:NamedIndividual ; rdfs:label "c" .""")
    assert {(local(t), p) for t, p in undocumented(tbox)} == {
        ("b", "has no rdfs:label"), ("b", "has no rdfs:comment"), ("c", "has no rdfs:comment")}


def test_not_dl_finds_punning_rdfs_typing_and_wrong_ranges():
    tbox = graph(""":p a owl:ObjectProperty , owl:DatatypeProperty . :D a owl:Class , rdfs:Datatype .
    :R a rdfs:Class . :Q a rdfs:Class , owl:Class . :q a rdf:Property .
    :o a owl:ObjectProperty ; rdfs:range xsd:string . :d a owl:DatatypeProperty ; rdfs:range :Q .
    :ok a owl:DatatypeProperty ; rdfs:range :D , xsd:date , [ owl:unionOf ( xsd:string xsd:integer ) ] .""")
    assert {(local(t), p) for t, p in not_dl(tbox)} == {
        ("p", "is declared as more than one kind of property"),
        ("D", "is declared as both a class and a datatype"),
        ("R", "is typed only with rdfs:Class or rdf:Property, not as an OWL entity"),
        ("q", "is typed only with rdfs:Class or rdf:Property, not as an OWL entity"),
        ("o", "is an object property with a datatype range <http://www.w3.org/2001/XMLSchema#string>"),
        ("d", f"is a datatype property with a non-datatype range <{EX}Q>")}


def test_unsupported_datatypes():
    tbox = graph(":a a owl:DatatypeProperty ; rdfs:range xsd:date . :b a owl:DatatypeProperty ; rdfs:range xsd:dateTime .")
    assert [(local(p), str(r)) for p, r in unsupported_datatypes(tbox)] == [("a", "http://www.w3.org/2001/XMLSchema#date")]


@java
def test_hermit_finds_unsatisfiable_inconsistent_and_rejected_models():
    tbox = graph(":A a owl:Class . :B a owl:Class ; owl:disjointWith :A . :C a owl:Class ; rdfs:subClassOf :A , :B .")
    assert hermit(tbox) == [f"<{EX}C> is unsatisfiable (OWL 2 DL, HermiT)"]
    assert hermit(tbox + graph(":c a :C .")) == ["inconsistent (OWL 2 DL, HermiT)"]
    rejected = hermit(graph(":p a owl:ObjectProperty , owl:TransitiveProperty , owl:FunctionalProperty ."))
    assert rejected[0].startswith(f"rejected by HermiT: Non-simple property '<{EX}p>'")
    assert hermit(graph(":p a owl:DatatypeProperty ; rdfs:range xsd:date .")) == []


def test_hermit_without_java(monkeypatch):
    monkeypatch.setattr("owlready2.JAVA_EXE", "no-such-java")
    assert hermit(graph(":A a owl:Class .")) is None


@java
def test_run_model_test_fails_on_local_terms_and_warns_on_reused_ones(capsys):
    tbox = graph(""":A a owl:Class ; rdfs:label "a" . voc:B a rdfs:Class .
    :p a owl:DatatypeProperty ; rdfs:label "p" ; rdfs:comment "P." ; rdfs:range xsd:date .""")
    assert run_model_test(tbox, "it") == 1
    out = capsys.readouterr().out
    assert f"FAIL [it] model: <{EX}A> has no rdfs:comment" in out
    assert "WARN [it] model: <http://example.com/voc/B> is typed only with rdfs:Class" in out
    assert "WARN [it] model: <http://example.com/voc/B> has no rdfs:label" in out
    assert "outside the OWL 2 datatype map" in out
    assert run_model_test(graph(':A a owl:Class ; rdfs:label "a" ; rdfs:comment "An A." .'), "it") == 0
    assert "PASS [it] model: all checks pass" in capsys.readouterr().out


@java
def test_main_fails_on_an_undocumented_term(iteration, capsys):
    data = zoo()
    data["glossary"][0]["definition"] = ""
    it = iteration(data=data, build=True)
    with pytest.raises(SystemExit) as e:
        main(it.name)
    assert e.value.code == 1
    assert f"FAIL [01-zoo] model: <{EX}Animal> has no rdfs:comment" in capsys.readouterr().out
    assert load_yaml(it / "requirements.yaml")["metadata"]["status"] == "draft"
