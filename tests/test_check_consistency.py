import pytest
from rdflib import URIRef
from rdflib.namespace import RDF

from conftest import graph
from scripts.check_consistency import inconsistencies, main, reason
from scripts.common import EX

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


def write_project(project, abox):
    (project / "project").mkdir()
    (project / "project" / "tbox.ttl").write_text(graph(TBOX).serialize(format="turtle"))
    (project / "project" / "abox.ttl").write_text(graph(abox).serialize(format="turtle"))


def test_main_reports_a_consistent_project(project, capsys):
    write_project(project, ":rex a :Mammal .")
    main()
    assert "Consistent (OWL 2 RL)" in capsys.readouterr().out


def test_main_fails_on_inconsistency(project, capsys):
    write_project(project, ":rex a :Cat , :Dog .")
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 1 and "Inconsistent" in capsys.readouterr().out


def test_main_needs_a_merged_project(project, capsys):
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 1 and "Run merge first" in capsys.readouterr().out
