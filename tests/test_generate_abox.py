from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, XSD

from conftest import zoo
from scripts.common import EX
from scripts.generate_abox import generate_abox, main

E = lambda name: URIRef(EX + name)


def abox_of(project, data):
    generate_abox(data, project)
    return Graph().parse(project / "abox.ttl", format="turtle")


def test_values_naming_individuals_or_terms_become_iris(project):
    data = zoo()
    data["glossary"].append({"term": "spot", "type": "NamedIndividual", "definition": "x"})
    data["abox"].append({"individual": "Jerry Mouse", "type": "Animal",
                         "properties": [{"property": "eats", "value": "spot"},
                                        {"property": "eats", "value": "Rex"}]})
    g = abox_of(project, data)
    assert (E("rex"), E("eats"), E("tom")) in g
    assert (E("jerry-mouse"), E("eats"), E("spot")) in g
    assert (E("jerry-mouse"), E("eats"), E("rex")) in g


def test_literals_are_typed_with_the_xsd_range(project):
    data = zoo()
    data["glossary"] += [
        {"term": "born", "type": "DatatypeProperty", "definition": "x", "rules": {"range": "xsd:date"}},
        {"term": "nickname", "type": "DatatypeProperty", "definition": "x", "rules": {"range": "string"}},
        {"term": "page", "type": "DatatypeProperty", "definition": "x", "rules": {"range": "voc:Page"}},
        {"term": "note", "type": "DatatypeProperty", "definition": "x"},
    ]
    data["abox"][1]["properties"] = [
        {"property": "born", "value": "2020-01-01"}, {"property": "nickname", "value": "Tommy"},
        {"property": "page", "value": "p1"}, {"property": "note", "value": 'He said "hi"'},
    ]
    g = abox_of(project, data)
    assert (E("rex"), E("hasLegs"), Literal("4", datatype=XSD.integer)) in g
    assert (E("tom"), E("born"), Literal("2020-01-01", datatype=XSD.date)) in g
    assert (E("tom"), E("nickname"), Literal("Tommy")) in g
    assert (E("tom"), E("page"), Literal("p1")) in g
    assert (E("tom"), E("note"), Literal('He said "hi"')) in g


def test_untyped_individuals_and_empty_entries(project):
    data = zoo(abox=[
        {"individual": "rex", "properties": [{"property": "eats", "value": ""}, {"property": "", "value": "x"}]},
        {"individual": "", "type": "Animal"},
    ])
    g = abox_of(project, data)
    assert set(g) == {(E("rex"), RDF.type, OWL.Thing)}


def test_main_writes_the_iteration_abox(iteration):
    it = iteration()
    main(it.name)
    assert (E("tom"), RDF.type, E("Animal")) in Graph().parse(it / "abox.ttl")
