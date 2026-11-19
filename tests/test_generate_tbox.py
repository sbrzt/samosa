import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

from conftest import zoo
from scripts.common import EX
from scripts.generate_tbox import BASE_PREFIXES, camel, generate_tbox, local_name, main, owl_type, ref

E = lambda name: URIRef(EX + name)


def test_camel_keeps_inner_case():
    assert camel("has URL") == "HasURL"
    assert camel("qualified  relation") == "QualifiedRelation"


@pytest.mark.parametrize("value, expected", [
    ("Class", "Class"), ("Object Property", "ObjectProperty"),
    ("datatype_property", "DatatypeProperty"), ("named individual", "NamedIndividual"),
])
def test_owl_type_normalizes_spelling(value, expected):
    assert owl_type({"type": value}) == expected


def test_owl_type_rejects_unknown_types():
    with pytest.raises(KeyError):
        owl_type({"type": "Relation"})


def test_local_name_per_kind():
    assert local_name({"term": "rights statement", "type": "Class"}) == "RightsStatement"
    assert local_name({"term": "has URL", "type": "DatatypeProperty"}) == "hasURL"
    assert local_name({"term": "Ada Lovelace", "type": "NamedIndividual"}) == "ada-lovelace"


@pytest.mark.parametrize("value, kind, expected", [
    ("rights statement", "Class", ":RightsStatement"),
    ("has URL", "ObjectProperty", ":hasURL"),
    ("date", "Datatype", "xsd:date"),
    ("xsd:integer", "Datatype", "xsd:integer"),
    ("http://x.org/A", "Class", "<http://x.org/A>"),
    ("  owl:Thing ", "Class", "owl:Thing"),
    ("", "Class", None),
    (None, "Class", None),
])
def test_ref_renders_turtle_references(value, kind, expected):
    assert ref(value, BASE_PREFIXES, kind) == expected


def test_ref_rejects_unknown_prefixes(capsys):
    with pytest.raises(SystemExit):
        ref("foaf:Person", BASE_PREFIXES)
    assert "unknown prefix" in capsys.readouterr().out


def tbox_of(project, data):
    generate_tbox(data, project)
    text = (project / "tbox.ttl").read_text()
    return text, Graph().parse(data=text, format="turtle")


def test_generate_tbox_renders_rules(project):
    data = zoo()
    data["glossary"] += [
        {"term": "has name", "type": "DatatypeProperty", "definition": 'Say "hi"\nthere',
         "rules": {"subproperty_of": "rdfs:label", "range": "string"}},
        {"term": "Rex", "type": "NamedIndividual", "definition": "A dog.", "rules": {"member_of": "mammal"}},
        {"term": "", "type": "", "definition": ""},  # empty template entry is skipped
    ]
    _, g = tbox_of(project, data)
    assert (E("Mammal"), RDFS.subClassOf, E("Animal")) in g
    assert (E("eats"), RDFS.domain, E("Animal")) in g and (E("eats"), RDFS.range, E("Animal")) in g
    assert (E("hasLegs"), RDFS.range, XSD.integer) in g
    assert (E("hasName"), RDFS.subPropertyOf, RDFS.label) in g
    assert (E("hasName"), RDFS.comment, Literal('Say "hi"\nthere', lang="en")) in g
    assert (E("hasName"), RDFS.label, Literal("has name", lang="en")) in g
    assert {E("rex")} == set(g.subjects(RDF.type, OWL.NamedIndividual))
    assert (E("rex"), RDF.type, E("Mammal")) in g


def test_generate_tbox_ignores_rules_that_do_not_apply(project):
    data = zoo(glossary=[{"term": "animal", "type": "Class", "definition": "x",
                          "rules": {"domain": "plant", "range": "plant", "subproperty_of": "eats"}}])
    _, g = tbox_of(project, data)
    assert set(g.predicate_objects(E("Animal"))) == {
        (RDF.type, OWL.Class), (RDFS.label, Literal("animal", lang="en")), (RDFS.comment, Literal("x", lang="en"))}


def test_generate_tbox_declares_only_used_project_prefixes(project):
    text, _ = tbox_of(project, zoo())
    assert "@prefix voc:" not in text
    data = zoo(glossary=[{"term": "pet", "type": "Class", "definition": "x", "rules": {"subclass_of": "voc:Creature"}}])
    text, g = tbox_of(project, data)
    assert "@prefix voc: <http://example.com/voc/>" in text
    assert (E("Pet"), RDFS.subClassOf, URIRef("http://example.com/voc/Creature")) in g


def test_main_writes_the_iteration_tbox(iteration):
    it = iteration()
    main(it.name)
    assert (E("Animal"), RDF.type, OWL.Class) in Graph().parse(it / "tbox.ttl")
