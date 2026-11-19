import json
import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS

from conftest import graph, zoo
from scripts import merge
from scripts.common import EX, dump_yaml, load_yaml

E = lambda name: URIRef(EX + name)
local = lambda term: str(term).rsplit("/", 1)[1]

OLD = graph("""
:Animal a owl:Class ; rdfs:label "animal"@en .
:eats a owl:ObjectProperty ; rdfs:range :Food .
:legs a owl:DatatypeProperty .
voc:Shared a owl:Class ; rdfs:label "shared"@en .""")


def run(fn, *args):
    try:
        fn(*args)
    except SystemExit as e:
        return e.code
    return 0


def test_conflicts_on_kind_domain_and_range():
    new = graph("""
:eats a owl:ObjectProperty ; rdfs:range :Meal .
:legs a owl:Class .
voc:Shared a owl:Class ; rdfs:label "shared"@en .""")
    assert {(local(t), what) for t, what, _, _ in merge.conflicts(new, OLD)} == {("eats", "range"), ("legs", "kind")}


def test_no_conflict_when_one_side_has_no_range():
    assert merge.conflicts(graph(":eats a owl:ObjectProperty ."), OLD) == []


def test_duplicates_by_local_name_label_or_definition():
    new = graph("""
:animal a owl:Class .
:Beast a owl:Class ; rdfs:label " Animal "@en .
:Critter a owl:Class ; rdfs:comment "x" .
:eat a owl:ObjectProperty ; rdfs:label "animal" .
voc:Shared a owl:Class ; rdfs:label "shared"@en .""")
    old = OLD + graph(':Thing2 a owl:Class ; rdfs:comment "x" .')
    found = {(local(a), local(b), tuple(why)) for a, b, why in merge.duplicates(new, old)}
    assert found == {("animal", "Animal", ("local name",)), ("Beast", "Animal", ("label",)),
                     ("Critter", "Thing2", ("definition",))}  # :eat is a property; Shared is the same IRI


def test_header_from_ontology_yaml(project):
    dump_yaml({"iri": "https://w3id.org/zoo", "version": "1.0", "version_iri": "https://w3id.org/zoo/1.0",
               "title": "Zoo", "description": "Animals.\n", "license": "https://creativecommons.org/licenses/by/4.0/",
               "creators": ["Ada", "https://orcid.org/0000-0000-0000-0001", ""]}, project / "ontology.yaml")
    tbox = graph(":Animal a owl:Class . voc:Shared a owl:Class .")
    merge.header(tbox)
    o = URIRef("https://w3id.org/zoo")
    assert (o, RDF.type, OWL.Ontology) in tbox
    assert (o, OWL.versionInfo, Literal("1.0")) in tbox
    assert (o, OWL.versionIRI, URIRef("https://w3id.org/zoo/1.0")) in tbox
    assert (o, DCTERMS.title, Literal("Zoo", lang="en")) in tbox
    assert (o, DCTERMS.description, Literal("Animals.", lang="en")) in tbox
    assert set(tbox.objects(o, DCTERMS.creator)) == {Literal("Ada"), URIRef("https://orcid.org/0000-0000-0000-0001")}
    assert (E("Animal"), RDFS.isDefinedBy, o) in tbox
    assert not list(tbox.objects(URIRef("http://example.com/voc/Shared"), RDFS.isDefinedBy))


def test_header_defaults_without_ontology_yaml(project):
    tbox = graph(":Animal a owl:Class .")
    merge.header(tbox)
    assert set(tbox.predicate_objects(URIRef(EX))) == {(RDF.type, OWL.Ontology)}
    assert (E("Animal"), RDFS.isDefinedBy, URIRef(EX)) in tbox


def ready(iteration, name, data, status="tested"):
    data["metadata"]["status"] = status
    return iteration(name, data, aligned=True)


def test_merge_builds_the_current_model_step_by_step(iteration, project, capsys):
    first = ready(iteration, "01-zoo", zoo())
    assert run(merge.main) == 1 and "no merged iterations" in capsys.readouterr().out
    assert run(merge.main, first.name) == 0
    assert load_yaml(first / "requirements.yaml")["metadata"]["status"] == "merged"
    tbox = Graph().parse(project / "project" / "tbox.ttl")
    assert (E("Mammal"), RDFS.subClassOf, E("Animal")) in tbox and (URIRef(EX), RDF.type, OWL.Ontology) in tbox

    data = zoo(glossary=[{"term": "animal", "type": "Class", "definition": "An animal."},
                         {"term": "keeper", "type": "Class", "definition": "A keeper."},
                         {"term": "feeds", "type": "ObjectProperty", "definition": "x",
                          "rules": {"domain": "keeper", "range": "animal"}}],
               abox=[{"individual": "kim", "type": "Keeper", "properties": [{"property": "feeds", "value": "tom"}]},
                     {"individual": "tom", "type": "Animal"}],
               competency_questions=[{"id": "1", "query": "SELECT ?k WHERE { ?k :feeds ?a }", "expected_result": [":kim"]}])
    second = ready(iteration, "02-keeper", data)
    assert run(merge.main, second.name) == 0
    out = capsys.readouterr().out
    assert "PASS [01-zoo] query: CQ 1" in out and "PASS [02-keeper] query: CQ 1" in out and "2 iteration(s)" in out
    assert (E("kim"), E("feeds"), E("tom")) in Graph().parse(project / "project" / "abox.ttl")
    results = json.loads((project / "project" / "results.json").read_text())
    assert results["passed"] and results["phase"] == "merge" and results["cases"] == ["01-zoo", "02-keeper"]
    assert {r["case"] for r in results["results"]} == {"current model", "01-zoo", "02-keeper"}


def test_merge_refuses_untested_iterations(iteration, capsys):
    it = ready(iteration, "01-zoo", zoo(), status="draft")
    assert run(merge.main, it.name) == 1
    assert "Run test first" in capsys.readouterr().out


def test_merge_needs_refactoring_output(iteration, capsys):
    data = zoo()
    data["metadata"]["status"] = "tested"
    it = iteration(data=data, build=True)
    assert run(merge.main, it.name) == 1
    assert "Run align first" in capsys.readouterr().out


def test_merge_fails_on_conflicts_and_keeps_the_current_model(iteration, project, capsys):
    run(merge.main, ready(iteration, "01-zoo", zoo()).name)
    before = (project / "project" / "tbox.ttl").read_text()
    data = zoo()
    data["glossary"][2]["rules"] = {"domain": "mammal", "range": "animal"}
    second = ready(iteration, "02-clash", data)
    assert run(merge.main, second.name) == 1
    out = capsys.readouterr().out
    assert "FAIL [02-clash] merge: conflict with 01-zoo: <https://www.example.org/eats> domain" in out
    assert "current model not updated" in out
    assert (project / "project" / "tbox.ttl").read_text() == before
    assert load_yaml(second / "requirements.yaml")["metadata"]["status"] == "tested"


def test_merge_warns_about_duplicates(iteration, capsys):
    run(merge.main, ready(iteration, "01-zoo", zoo()).name)
    data = zoo(glossary=[{"term": "beast", "type": "Class", "definition": "An animal."}],
               abox=[{"individual": "tom", "type": "Beast"}],
               competency_questions=[{"id": "1", "query": "SELECT ?b WHERE { ?b a :Beast }", "expected_result": [":tom"]}])
    assert run(merge.main, ready(iteration, "02-beast", data).name) == 0
    assert "possible duplicate: <https://www.example.org/Beast> here and <https://www.example.org/Animal>" in capsys.readouterr().out


def test_rename_collapses_a_duplicate_and_re_merges(iteration, project, capsys):
    run(merge.main, ready(iteration, "01-zoo", zoo()).name)
    data = zoo(glossary=[{"term": "beast", "type": "Class", "definition": "An animal."}],
               abox=[{"individual": "tom", "type": "Beast"}],
               competency_questions=[{"id": "1", "query": "SELECT ?c WHERE { :tom a ?c }",
                                      "expected_result": [":beast"]}])
    second = ready(iteration, "02-beast", data)
    assert run(merge.main, second.name) == 0
    capsys.readouterr()
    assert run(merge.rename, ":Beast", ":Animal") == 0
    assert load_yaml(second / "requirements.yaml")["glossary"][0]["align_to"] == ":Animal"
    assert (E("tom"), RDF.type, E("Animal")) in Graph().parse(project / "refactoring" / second.name / "abox.ttl")
    tbox = Graph().parse(project / "project" / "tbox.ttl")
    assert E("Beast") not in set(tbox.subjects())
    out = capsys.readouterr().out
    assert "02-beast: align_to :Animal" in out
    assert "PASS [02-beast] query: CQ 1" in out and "2 iteration(s)" in out  # :beast still matches through the alias


def test_rename_back_to_the_own_term_clears_align_to(iteration):
    data = zoo()
    data["glossary"][0]["align_to"] = "voc:Creature"
    it = iteration(data=data, aligned=True)
    assert run(merge.rename, "voc:Creature", ":Animal") == 0
    assert load_yaml(it / "requirements.yaml")["glossary"][0]["align_to"] == ""


def test_rename_unknown_term(iteration, capsys):
    iteration()
    assert run(merge.rename, ":Nope", ":Animal") == 1
    assert "no glossary term stands for" in capsys.readouterr().out


def test_rename_without_built_files_only_updates_the_glossary(iteration, capsys):
    it = iteration()
    assert run(merge.rename, ":Animal", "voc:Creature") == 0
    assert load_yaml(it / "requirements.yaml")["glossary"][0]["align_to"] == "voc:Creature"
    assert "run tbox, abox and align" in capsys.readouterr().out
