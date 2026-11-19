"""Shared fixtures: an isolated project directory, iteration builders, no network."""

import shutil
import socket
from pathlib import Path

import pytest
from rdflib import Graph

from scripts import align, generate_abox, generate_tbox
from scripts.common import RESULTS, dump_yaml

REPO = Path(__file__).resolve().parent.parent

PREFIXES = """\
@prefix : <https://www.example.org/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix voc: <http://example.com/voc/> .
"""

VOCABULARY = PREFIXES + """
voc:Agent a owl:Class ; rdfs:label "agent"@en ; rdfs:subClassOf voc:Being .
voc:Pet a owl:Class ; rdfs:subClassOf voc:Domestic .
voc:Domestic a owl:Class ; rdfs:subClassOf voc:Creature .
voc:Creature a owl:Class ; rdfs:label "creature"@en ; rdfs:subClassOf voc:Agent , voc:Unrelated .
voc:Unrelated a owl:Class .
voc:feedsOn a owl:ObjectProperty ; rdfs:label "feeds on"@en ; rdfs:domain voc:Creature ;
    rdfs:comment [ rdfs:label "a blank node" ] .
voc:legCount a owl:DatatypeProperty ; rdfs:range xsd:integer .
"""


def zoo(**overrides):
    """Requirements of a small, valid iteration; keyword arguments replace sections."""
    data = {
        "metadata": {"id": "01", "status": "draft"},
        "scenario": {"title": "Zoo", "description": "Animals eat animals.", "examples": ["Rex eats Tom."]},
        "glossary": [
            {"term": "animal", "type": "Class", "definition": "An animal."},
            {"term": "mammal", "type": "Class", "definition": "A mammal.", "rules": {"subclass_of": "animal"}},
            {"term": "eats", "type": "ObjectProperty", "definition": "Eats another animal.",
             "rules": {"domain": "animal", "range": "animal"}},
            {"term": "has legs", "type": "DatatypeProperty", "definition": "Number of legs.",
             "rules": {"domain": "animal", "range": "integer"}},
        ],
        "abox": [
            {"individual": "rex", "type": "Mammal",
             "properties": [{"property": "eats", "value": "tom"}, {"property": "hasLegs", "value": "4"}]},
            {"individual": "tom", "type": "Animal"},
        ],
        "competency_questions": [
            {"id": "1", "question": "Who eats whom?", "expected_result": [":rex, :tom"],
             "query": "SELECT ?a ?b WHERE { ?a :eats ?b }"},
        ],
    }
    data.update(overrides)
    return data


def graph(text):
    """Parse Turtle, with the common prefixes declared."""
    return Graph().parse(data=PREFIXES + text, format="turtle")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Fail any test that tries to open a network connection."""
    def blocked(*args, **kwargs):
        raise OSError("network disabled in tests")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)


@pytest.fixture(autouse=True)
def fresh_results():
    """Clear the test results recorded by `common.report` before each test."""
    RESULTS.clear()


@pytest.fixture(autouse=True)
def fresh_vocabularies():
    """Clear align's module-level vocabulary cache around each test."""
    align._vocabularies.clear()
    yield
    align._vocabularies.clear()


@pytest.fixture
def project(tmp_path, monkeypatch):
    """An empty SAMOSA project as the current directory, with templates and prefixes."""
    shutil.copytree(REPO / "templates", tmp_path / "templates")
    (tmp_path / "prefixes.yaml").write_text("voc: http://example.com/voc/\n")
    (tmp_path / "iterations").mkdir()
    (tmp_path / "vocabularies").mkdir()
    (tmp_path / "vocabularies" / "voc.ttl").write_text(VOCABULARY)
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def iteration(project):
    """Factory: write `iterations/<name>/requirements.yaml` and return the directory.

    With `build=True`, also generate tbox.ttl and abox.ttl; with `aligned=True`,
    also run align.
    """
    def make(name="01-zoo", data=None, build=False, aligned=False):
        it = project / "iterations" / name
        it.mkdir(parents=True, exist_ok=True)
        dump_yaml(data if data is not None else zoo(), it / "requirements.yaml")
        if build or aligned:
            generate_tbox.main(name)
            generate_abox.main(name)
        if aligned:
            align.main(name)
        return it
    return make
