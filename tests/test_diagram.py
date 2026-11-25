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
    assert (E("tom"), E("jerry"), E("eats"), "assertion") in edges and (E("tom"), blank, E("eats"), "assertion") in edges
    assert (E("jerry"), (E("jerry"), E("legs"), four), E("legs"), "assertion") in edges


def test_labeler_shortens_iris_and_shows_literals_as_turtle():
    name = diagram.labeler(TBOX)
    assert name(E("tom")) == ":tom" and name(XSD.string) == "xsd:string"
    assert name((E("tom"), E("legs"), Literal("4", datatype=XSD.integer))) == '"4"^^xsd:integer'
    assert name(BNode("b1")) == "_:b1" and name("rdf:type") == "rdf:type"


G = "{http://graphml.graphdrawing.org/xmlns}"
Y = "{http://www.yworks.com/xml/graphml}"


def test_dot_and_graphml_render_every_node_and_edge():
    nodes, edges = diagram.extract(TBOX)
    root = diagram.graphml(nodes, edges, name)
    assert len(root.findall(f".//{G}graph/{G}node")) == len(nodes)
    assert len(root.findall(f".//{G}graph/{G}edge")) == len(edges)
    dot = diagram.dot(root)
    assert dot.startswith("digraph G") and dot.count("->") == len(edges) and "pos=" not in dot


def test_graphml_nodes_carry_their_iri_and_dot_draws_graffoo():
    nodes = {E("A"): "class", XSD.string: "datatype", E("i"): "individual", (E("i"), E("d"), Literal('say "hi"')): "literal"}
    edges = [(E("A"), XSD.string, E("d"), "data-use"), (E("i"), E("A"), "rdf:type", "type"), (E("A"), E("A"), E("p"), "object")]
    root = diagram.graphml(nodes, edges, diagram.labeler(TBOX))
    urls = [n.findtext(f"{G}data[@key='d4']") for n in root.iter(f"{G}node")]
    assert urls == [EX + "A", str(XSD.string), EX + "i", f'<{EX}i> <{EX}d> "say \\"hi\\""']
    dot = diagram.dot(root, {"n0"}).splitlines()
    assert dot[1].startswith('n0 [width=') and 'shape=box style="rounded,filled" fillcolor="#FFFF00"' in dot[1] and dot[1].endswith('pos="25.0,-22.0!"];')
    assert "shape=parallelogram" in dot[2] and 'xlabel=":i" label=""' in dot[3] and "pos=" not in dot[3]
    assert 'shape=plaintext label="\\"say \\\\\\"hi\\\\\\"\\""' in dot[4]
    assert 'n0 -> n1 [label=":d" color="#008000"' in dot[5] and "arrowtail=odot arrowhead=empty style=dashed" in dot[5]
    assert "arrowtail=none arrowhead=normal" in dot[6] and 'color="#000080"' in dot[7] and "arrowtail=dot" in dot[7]


def write_tbox(project):
    it = project / "iterations" / "01-zoo"
    it.mkdir(parents=True)
    (it / "tbox.ttl").write_text(TBOX.serialize(format="turtle"))
    (it / "abox.ttl").write_text(ABOX.serialize(format="turtle"))
    return it


def positions(path):
    return {u.rsplit("/", 1)[-1]: xy for u, xy in diagram.saved(path).items()}


needs_graphviz = pytest.mark.skipif(diagram.shutil.which("dot") is None, reason="needs Graphviz")


@needs_graphviz
def test_main_writes_graphml_and_exports(project, capsys):
    it = write_tbox(project)
    diagram.main(it.name)
    for stem in ("tbox", "abox"):
        assert {p.suffix for p in it.glob(f"{stem}.*")} == {".ttl", ".graphml", ".png", ".svg", ".pdf"}
    labels = [l.text for l in ET.parse(it / "abox.graphml").iter(f"{Y}NodeLabel")]
    assert '"Tom"' in labels and ":tom" in labels
    tbox = positions(it / "tbox.graphml")
    assert len(set(tbox.values())) == len(tbox)  # laid out, not stacked
    assert "Wrote iterations/01-zoo/tbox.graphml, iterations/01-zoo/tbox.png" in capsys.readouterr().out


@needs_graphviz
def test_redraw_keeps_saved_positions_and_places_new_nodes(project):
    it = write_tbox(project)
    diagram.main(it.name)
    root = ET.parse(it / "tbox.graphml").getroot()
    animal = next(n.get("id") for n in root.iter(f"{G}node") if n.findtext(f"{G}data[@key='d4']") == EX + "Animal")
    diagram.save_layout(it.name, "tbox", {animal: {"x": 1000, "y": 2000}})
    before = positions(it / "tbox.graphml")
    assert before["Animal"] == (1000.0, 2000.0)
    diagram.main(it.name)
    assert positions(it / "tbox.graphml") == before  # nothing new: nothing moves
    (it / "tbox.ttl").write_text((TBOX + graph(":Plant a owl:Class .")).serialize(format="turtle"))
    diagram.main(it.name)
    after = positions(it / "tbox.graphml")
    dx, dy = after["Animal"][0] - before["Animal"][0], after["Animal"][1] - before["Animal"][1]
    assert all(after[k] == pytest.approx((x + dx, y + dy), abs=0.01) for k, (x, y) in before.items())  # kept, at most shifted together
    assert "Plant" in after


def test_save_layout_moves_only_positions(project, monkeypatch, capsys):
    it = write_tbox(project)
    monkeypatch.setattr(diagram.shutil, "which", lambda cmd: None)
    diagram.main(it.name)
    old = (it / "tbox.graphml").read_text()
    diagram.save_layout(it.name, "tbox", {"n1": {"x": 12.5, "y": -3}, "nope": {"x": 0, "y": 0}})
    new = (it / "tbox.graphml").read_text()
    geo = ET.parse(it / "tbox.graphml").getroot().find(f".//{G}node[@id='n1']//{Y}Geometry")
    assert (geo.get("x"), geo.get("y")) == ("12.5", "-3.0")
    strip = lambda t: [l for l in ET.fromstring(t).iter() if l.tag != f"{Y}Geometry"]
    assert [(e.tag, e.text) for e in strip(old)] == [(e.tag, e.text) for e in strip(new)]
    assert "Wrote iterations/01-zoo/tbox.graphml" in capsys.readouterr().out


def test_save_layout_needs_a_diagram(project, capsys):
    it = write_tbox(project)
    with pytest.raises(SystemExit):
        diagram.save_layout(it.name, "tbox", {})
    assert "tbox.graphml not found" in capsys.readouterr().out


def test_main_without_abox_draws_only_the_tbox(project, monkeypatch):
    it = write_tbox(project)
    (it / "abox.ttl").unlink()
    monkeypatch.setattr(diagram.shutil, "which", lambda cmd: None)
    diagram.main(it.name)
    assert (it / "tbox.graphml").exists() and not (it / "abox.graphml").exists()


def test_main_without_graphviz_uses_a_grid(project, monkeypatch, capsys):
    it = write_tbox(project)
    monkeypatch.setattr(diagram.shutil, "which", lambda cmd: None)
    diagram.main(it.name)
    assert {p.suffix for p in it.glob("tbox.*")} == {".ttl", ".graphml"}
    assert sorted(positions(it / "tbox.graphml").values())[:2] == [(0.0, 0.0), (0.0, 150.0)]
    assert "exports skipped" in capsys.readouterr().out


def test_main_needs_a_tbox(project, capsys):
    (project / "iterations" / "01-zoo").mkdir()
    with pytest.raises(SystemExit):
        diagram.main("01-zoo", refactored=True)
    assert "refactoring/01-zoo/tbox.ttl not found" in capsys.readouterr().out
