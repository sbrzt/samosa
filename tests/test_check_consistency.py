import shutil

import pytest
from rdflib import URIRef
from rdflib.namespace import RDF

from conftest import graph
from scripts.check_consistency import ill_typed, inconsistencies, main, problems, reason
from scripts.common import EX

java = pytest.mark.skipif(shutil.which("java") is None, reason="HermiT needs Java")

TBOX = ":Mammal rdfs:subClassOf :Animal . :Cat owl:disjointWith :Dog . :legs rdfs:range xsd:integer ."


def test_reason_returns_a_new_graph_with_inferences():
    g = graph(TBOX + ":rex a :Mammal .")
    size = len(g)
    closure = reason(g)
    assert len(g) == size
    assert (URIRef(EX + "rex"), RDF.type, URIRef(EX + "Animal")) in closure
    assert inconsistencies(closure) == []


@pytest.mark.parametrize("abox", [':rex a :Cat , :Dog .', ':rex :legs "four"^^xsd:integer .'])
def test_inconsistencies_are_reported(abox):
    assert inconsistencies(reason(graph(TBOX + abox)))


def test_ill_typed():
    assert [str(t[2]) for t in ill_typed(graph(':rex :legs "four"^^xsd:integer , "4"^^xsd:integer , "four" .'))] == ["four"]


# A :C must have a :p value and cannot have one: OWL 2 RL misses the clash.
DL_ONLY = """:p a owl:ObjectProperty . :C a owl:Class ;
    rdfs:subClassOf [ a owl:Restriction ; owl:onProperty :p ; owl:minCardinality 1 ] ,
                    [ a owl:Restriction ; owl:onProperty :p ; owl:maxCardinality 0 ] . :x a :C ."""


@java
def test_problems_finds_dl_only_clashes_and_ill_typed_literals():
    assert inconsistencies(reason(graph(DL_ONLY))) == []
    assert problems(graph(DL_ONLY)) == [("FAIL", "inconsistent (OWL 2 DL, HermiT)")]
    found = problems(graph(TBOX + ':rex :legs "four"^^xsd:integer .'))
    assert found == [("FAIL", f'<{EX}rex> <{EX}legs> "four"^^<http://www.w3.org/2001/XMLSchema#integer>: '
                              "the value does not fit its datatype")]
    assert problems(graph(TBOX + ":rex a :Mammal .")) == []


def test_problems_falls_back_to_owl_2_rl_without_java(monkeypatch):
    monkeypatch.setattr("owlready2.JAVA_EXE", "no-such-java")
    found = problems(graph(TBOX + ":rex a :Cat , :Dog ."))
    assert found[0] == ("WARN", "Java not found, OWL 2 RL (owlrl) used instead of HermiT (OWL 2 DL)")
    assert found[1][0] == "FAIL" and found[1][1].startswith("inconsistent (OWL 2 RL)")


def write_project(project, abox):
    (project / "project").mkdir()
    (project / "project" / "tbox.ttl").write_text(graph(TBOX).serialize(format="turtle"))
    (project / "project" / "abox.ttl").write_text(graph(abox).serialize(format="turtle"))


def test_main_reports_a_consistent_project(project, capsys):
    write_project(project, ":rex a :Mammal .")
    main()
    assert "Consistent: " in capsys.readouterr().out


def test_main_fails_on_inconsistency(project, capsys):
    write_project(project, ":rex a :Cat , :Dog .")
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 1 and "Inconsistent" in capsys.readouterr().out


def test_main_needs_a_merged_project(project, capsys):
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 1 and "Run merge first" in capsys.readouterr().out
