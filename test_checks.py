# Self-check for the TBox rule rendering and the data/coverage tests.
# Run with: uv run python test_checks.py

from rdflib import Graph
from scripts.check_consistency import inconsistencies, reason
from scripts.generate_tbox import BASE_PREFIXES, ref
from scripts.test_iteration import misused, uncovered, undeclared

TBOX = """@prefix : <https://www.example.org/> . @prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
:Animal a owl:Class . :Mammal a owl:Class ; rdfs:subClassOf :Animal .
:eats a owl:ObjectProperty ; rdfs:range :Food .
:hasLegs a owl:DatatypeProperty ; rdfs:range xsd:integer ."""
ABOX = """@prefix : <https://www.example.org/> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
:rex a :Mammal ; :eats "fod" ; :hasLeg "4" ; :hasLegs "four"^^xsd:integer ."""

if __name__ == "__main__":
    assert ref("date", BASE_PREFIXES, "Datatype") == "xsd:date"
    assert ref("xsd:integer", BASE_PREFIXES, "Datatype") == "xsd:integer"
    assert ref("rights statement", BASE_PREFIXES) == ":RightsStatement"
    assert ref("has URL", BASE_PREFIXES, "DatatypeProperty") == ":hasURL"
    assert ref("http://x.org/A", BASE_PREFIXES) == "<http://x.org/A>"
    assert ref("", BASE_PREFIXES) is None

    tbox, abox = Graph().parse(data=TBOX, format="turtle"), Graph().parse(data=ABOX, format="turtle")
    names = {(str(t).rsplit("/", 1)[1], w) for t, w in undeclared(tbox, abox)}
    assert names == {("Food", "tbox"), ("hasLeg", "abox")}, names
    assert [str(o) for _, _, o in misused(tbox, abox)] == ["fod"]
    assert inconsistencies(reason(tbox + abox))

    data = {"glossary": [{"term": "animal", "type": "Class"}, {"term": "eats", "type": "ObjectProperty"}],
            "competency_questions": [{"query": "SELECT ?a WHERE { ?a a :Animal }"}]}
    assert set(uncovered(data, abox)) == {("Animal", "abox"), ("eats", "queries")}
    print("ok")
