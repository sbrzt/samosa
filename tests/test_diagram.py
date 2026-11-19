import xml.etree.ElementTree as ET

import pytest
from rdflib import BNode, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

from conftest import graph
from scripts import diagram
from scripts.common import EX

E = lambda name: URIRef(EX + name)
TBOX = graph("""
:Animal a owl:Class . :Mammal a owl:Class ; rdfs:subClassOf :Animal .
:eats a owl:ObjectProperty ; rdfs:domain :Animal .
:name a owl:DatatypeProperty ; rdfs:range xsd:string .
:rex a owl:NamedIndividual , :Mammal .""")
ABOX = graph(""":tom a :Animal . :jerry a :Mammal . :tom :eats :jerry . :tom :name "Tom" .""")
name = lambda iri: TBOX.namespace_manager.normalizeUri(iri).strip("<>")


def test_extract_nodes_and_edges_with_defaults():
    nodes, edges = diagram.extract(TBOX)
    assert nodes[E("Animal")] == "class" and nodes[XSD.string] == "datatype" and nodes[E("rex")] == "individual"
    assert nodes[OWL.Thing] == "class"  # missing range of :eats, missing domain of :name
    assert set(edges) == {
        (E("Mammal"), E("Animal"), "", "subclass"),
        (E("Animal"), OWL.Thing, E("eats"), "object"),
        (OWL.Thing, XSD.string, E("name"), "data"),
        (E("rex"), E("Mammal"), "rdf:type", "type"),
    }


def test_usage_adds_abox_edges_once():
    nodes, edges = diagram.extract(TBOX)
    diagram.usage(TBOX, ABOX + graph(":tom :eats :jerry ."), nodes, edges)
    uses = [e for e in edges if e[3].endswith("-use")]
    assert sorted(uses) == sorted([(E("Animal"), E("Mammal"), E("eats"), "object-use"),
                                   (E("Animal"), RDFS.Literal, E("name"), "data-use")])


def test_extract_abox_draws_individuals_classes_and_assertions():
    abox = graph(""":tom a :Animal , owl:NamedIndividual ; :eats :jerry , [ a :Mouse ] ;
                    :legs "4"^^xsd:integer ; :nick "4"^^xsd:integer . :jerry :legs "4"^^xsd:integer .""")
    nodes, edges = diagram.extract_abox(abox)
    blank = next(n for n in nodes if isinstance(n, BNode))
    four = Literal("4", datatype=XSD.integer)
    assert {n: k for n, k in nodes.items() if not isinstance(n, (tuple, BNode))} == {
        E("tom"): "individual", E("jerry"): "individual", E("Animal"): "class", E("Mouse"): "class"}
    assert nodes[blank] == "individual"
    assert [k for k in nodes.values()].count("literal") == 3  # equal values of different assertions stay apart
    assert (E("tom"), E("Animal"), "rdf:type", "type") in edges and OWL.NamedIndividual not in nodes
    assert (E("tom"), E("jerry"), E("eats"), "object") in edges and (E("tom"), blank, E("eats"), "object") in edges
    assert (E("jerry"), (E("jerry"), E("legs"), four), E("legs"), "data") in edges


def test_labeler_shortens_iris_and_shows_literals_as_turtle():
    name = diagram.labeler(TBOX)
    assert name(E("tom")) == ":tom" and name(XSD.string) == "xsd:string"
    assert name((E("tom"), E("legs"), Literal("4", datatype=XSD.integer))) == '"4"^^xsd:integer'
    assert name(BNode("b1")) == "_:b1" and name("rdf:type") == "rdf:type"


def test_mermaid_draws_literals_as_plain_text():
    key = (E("tom"), E("legs"), Literal("4"))
    text = diagram.mermaid({E("tom"): "individual", key: "literal"}, [(E("tom"), key, E("legs"), "data")],
                           diagram.labeler(TBOX))
    assert '  n1["#quot;4#quot;"]:::literal' in text.splitlines()
    assert "  classDef literal fill:none,stroke:none,color:#000" in text.splitlines()
    assert "  linkStyle 0 stroke:#008000,color:#008000" in text.splitlines()


def test_mermaid_uses_graffoo_shapes_and_colours():
    nodes = {E("A"): "class", XSD.string: "datatype", E("i"): "individual"}
    edges = [(E("A"), E("A"), "", "subclass"), (E("A"), E("A"), E("p"), "object"),
             (E("A"), XSD.string, E("d"), "data-use"), (E("i"), E("A"), "rdf:type", "type")]
    text = diagram.mermaid(nodes, edges, lambda iri: 'say "hi"' if iri == E("A") else name(iri))
    lines = text.splitlines()
    assert lines[0] == "flowchart LR"
    assert '  n0("say #quot;hi#quot;"):::owlClass' in lines
    assert '  n1[/"xsd:string"/]:::datatype' in lines and '  n2((":i")):::individual' in lines
    assert '  n0 -->|"rdfs:subClassOf"| n0' in lines and '  n2 -->|"rdf:type"| n0' in lines
    assert '  n0 -.->|":d"| n1' in lines
    assert "  linkStyle 1 stroke:#000080,color:#000080" in lines
    assert "  linkStyle 2 stroke:#008000,color:#008000" in lines


def test_dot_and_graphml_render_every_node_and_edge():
    nodes, edges = diagram.extract(TBOX)
    dot = diagram.dot(nodes, edges, name)
    assert dot.startswith("digraph G") and dot.count("->") == len(edges)
    root = ET.fromstring(diagram.graphml(nodes, edges, name))
    ns = {"g": "http://graphml.graphdrawing.org/xmlns"}
    assert len(root.findall(".//g:graph/g:node", ns)) == len(nodes)
    assert len(root.findall(".//g:graph/g:edge", ns)) == len(edges)


def write_tbox(project):
    it = project / "iterations" / "01-zoo"
    it.mkdir(parents=True)
    (it / "tbox.ttl").write_text(TBOX.serialize(format="turtle"))
    (it / "abox.ttl").write_text(ABOX.serialize(format="turtle"))
    return it


def test_main_writes_mermaid_only_by_default(project, capsys):
    it = write_tbox(project)
    diagram.main(it.name)
    assert (it / "tbox.mmd").read_text().startswith("flowchart LR")
    abox = (it / "abox.mmd").read_text()
    assert '((":tom")):::individual' in abox and '["#quot;Tom#quot;"]:::literal' in abox
    assert not list(it.glob("*.graphml"))
    assert "Wrote iterations/01-zoo/tbox.mmd, iterations/01-zoo/abox.mmd" in capsys.readouterr().out


def test_main_without_abox_draws_only_the_tbox(project):
    it = write_tbox(project)
    (it / "abox.ttl").unlink()
    diagram.main(it.name)
    assert (it / "tbox.mmd").exists() and not (it / "abox.mmd").exists()


def test_abox_graphml_renders_literals(project):
    nodes, edges = diagram.extract_abox(ABOX)
    root = ET.fromstring(diagram.graphml(nodes, edges, diagram.labeler(ABOX)))
    labels = [l.text for l in root.iter("{http://www.yworks.com/xml/graphml}NodeLabel")]
    assert '"Tom"' in labels and ":tom" in labels


def test_main_graffoo_without_graphviz(project, monkeypatch, capsys):
    it = write_tbox(project)
    monkeypatch.setattr(diagram.shutil, "which", lambda cmd: None)
    diagram.main(it.name, graffoo=True)
    assert (it / "tbox.graphml").exists() and (it / "abox.graphml").exists()
    assert not list(it.glob("*.png"))
    assert "PNG skipped" in capsys.readouterr().out


def test_main_graffoo_png(project, monkeypatch):
    it = write_tbox(project)
    calls = []
    monkeypatch.setattr(diagram.shutil, "which", lambda cmd: "/usr/bin/dot")
    monkeypatch.setattr(diagram.subprocess, "run", lambda cmd, **kw: calls.append((cmd, kw["input"])))
    diagram.main(it.name, graffoo=True)
    assert [c[0][:4] for c in calls] == [["dot", "-Tpng", "-o", f"iterations/{it.name}/tbox.png"],
                                         ["dot", "-Tpng", "-o", f"iterations/{it.name}/abox.png"]]
    assert all(c[1].startswith("digraph G") for c in calls)


def test_main_needs_a_tbox(project, capsys):
    (project / "iterations" / "01-zoo").mkdir()
    with pytest.raises(SystemExit):
        diagram.main("01-zoo", refactored=True)
    assert "refactoring/01-zoo/tbox.ttl not found" in capsys.readouterr().out
