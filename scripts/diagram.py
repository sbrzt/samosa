# scripts/diagram.py

import copy
import shutil
import subprocess
import sys
from pathlib import Path
import xml.etree.ElementTree as ET
from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD
from scripts.common import resolve_iteration

TEMPLATE = Path(__file__).with_name("graffoo.graphml")  # Graffoo palette, drawn in yEd
NS = {"g": "http://graphml.graphdrawing.org/xmlns", "y": "http://www.yworks.com/xml/graphml"}
for prefix, uri in (("", NS["g"]), ("y", NS["y"]), ("yed", "http://www.yworks.com/xml/yed/3"),
                    ("xsi", "http://www.w3.org/2001/XMLSchema-instance")):
    ET.register_namespace(prefix, uri)

# template label of the prototype element per node / edge kind
NODE_PROTO = {"class": "Class", "datatype": "Datatype", "individual": "instance"}
EDGE_PROTO = {"object": "objectProperty", "data": "dataProperty", "subclass": "predicate", "type": "predicate",
              "object-use": "objectProperty", "data-use": "dataProperty"}

# Graphviz approximation of the same palette, for the PNG
DOT_NODE = {"class": 'shape=box style="rounded,filled" fillcolor="#FFFF00"',
            "datatype": 'shape=parallelogram style=filled fillcolor="#CCFFCC"',
            "individual": 'shape=circle style=filled fillcolor="#FF99CC" penwidth=3 width=0.25 fixedsize=true xlabel={label} label=""'}
DOT_EDGE = {"object": 'color="#000080" fontcolor="#000080" dir=both arrowtail=dot arrowhead=normal',
            "data": 'color="#008000" fontcolor="#008000" dir=both arrowtail=odot arrowhead=empty',
            "subclass": "", "type": ""}
DOT_EDGE["object-use"] = DOT_EDGE["object"] + " style=dashed"
DOT_EDGE["data-use"] = DOT_EDGE["data"] + " style=dashed"


def extract(g):
    nodes, edges = {}, []
    for c in g.subjects(RDF.type, OWL.Class):
        if isinstance(c, URIRef):
            nodes[c] = "class"
    for c, sup in g.subject_objects(RDFS.subClassOf):
        if isinstance(c, URIRef) and isinstance(sup, URIRef):
            nodes.setdefault(c, "class"); nodes.setdefault(sup, "class")
            edges.append((c, sup, "", "subclass"))
    for kind, prop_type in (("object", OWL.ObjectProperty), ("data", OWL.DatatypeProperty)):
        for p in g.subjects(RDF.type, prop_type):
            if not isinstance(p, URIRef):
                continue
            d = g.value(p, RDFS.domain)
            r = g.value(p, RDFS.range)
            d = d if isinstance(d, URIRef) else OWL.Thing
            r = r if isinstance(r, URIRef) else (OWL.Thing if kind == "object" else RDFS.Literal)
            nodes.setdefault(d, "class")
            nodes.setdefault(r, "datatype" if kind == "data" or str(r).startswith(str(XSD)) else "class")
            edges.append((d, r, p, kind))
    for i in g.subjects(RDF.type, OWL.NamedIndividual):
        nodes[i] = "individual"
        for t in g.objects(i, RDF.type):
            if isinstance(t, URIRef) and t != OWL.NamedIndividual:
                nodes.setdefault(t, "class")
                edges.append((i, t, "rdf:type", "type"))
    return nodes, edges


def usage(g, abox, nodes, edges):
    kinds = {p: k for k, t in (("object", OWL.ObjectProperty), ("data", OWL.DatatypeProperty)) for p in g.subjects(RDF.type, t)}
    classes = lambda i: [t for t in abox.objects(i, RDF.type) if isinstance(t, URIRef) and t != OWL.NamedIndividual]
    seen = {(s, t, p) for s, t, p, _ in edges}
    for s, p, o in abox:
        if p not in kinds:
            continue
        targets = classes(o) if kinds[p] == "object" else [getattr(o, "datatype", None) or RDFS.Literal]
        for d in classes(s):
            for r in targets:
                if (d, r, p) not in seen:
                    seen.add((d, r, p))
                    nodes.setdefault(d, "class")
                    nodes.setdefault(r, "class" if kinds[p] == "object" else "datatype")
                    edges.append((d, r, p, kinds[p] + "-use"))


def graphml(nodes, edges, name):
    tree = ET.parse(TEMPLATE)
    graph = tree.getroot().find("g:graph", NS)
    label_of = lambda el: (el.findtext(".//y:NodeLabel", "", NS) or el.findtext(".//y:EdgeLabel", "", NS)).strip()
    protos = {label_of(el): el for el in graph.iter() if el.tag in (f"{{{NS['g']}}}node", f"{{{NS['g']}}}edge")}
    for el in list(graph):
        if el.tag != f"{{{NS['g']}}}data":
            graph.remove(el)

    ids = {n: f"n{i}" for i, n in enumerate(nodes)}
    # ponytail: grid positions only; in yEd run Layout > Hierarchical once
    for i, (n, kind) in enumerate(nodes.items()):
        node = copy.deepcopy(protos[NODE_PROTO[kind]])
        node.set("id", ids[n])
        node.find(".//y:NodeLabel", NS).text = name(n)
        geo = node.find(".//y:Geometry", NS)
        if kind != "individual":  # individuals keep the small circle, label sits outside
            geo.set("width", str(10 * len(name(n)) + 30))  # ponytail: ~10px per char at Dialog 16
        geo.set("x", str((i % 5) * 300)); geo.set("y", str((i // 5) * 150))
        graph.append(node)
    for i, (s, t, p, kind) in enumerate(edges):
        edge = copy.deepcopy(protos[EDGE_PROTO[kind]])
        edge.attrib.update(id=f"e{i}", source=ids[s], target=ids[t])
        if kind.endswith("-use"):
            edge.find(".//y:LineStyle", NS).set("type", "dashed")
        edge.find(".//y:EdgeLabel", NS).text = {"subclass": "rdfs:subClassOf", "type": "rdf:type"}.get(kind) or name(p)
        graph.append(edge)
    return ET.tostring(tree.getroot(), encoding="unicode", xml_declaration=True)


def dot(nodes, edges, name):
    q = lambda s: '"' + s.replace('"', '\\"') + '"'
    out = ['digraph G { rankdir=LR; node [fontname="Helvetica"]; edge [fontname="Helvetica"];']
    for n, kind in nodes.items():
        out.append(f'{q(str(n))} [label={q(name(n))} {DOT_NODE[kind].format(label=q(name(n)))}];')
    for s, t, p, kind in edges:
        label = {"subclass": "rdfs:subClassOf", "type": "rdf:type"}.get(kind) or name(p)
        out.append(f"{q(str(s))} -> {q(str(t))} [label={q(label)} {DOT_EDGE[kind]}];")
    out.append("}")
    return "\n".join(out)


def main():
    it = resolve_iteration(sys.argv[1])
    base = Path("refactoring") / it.name if "--refactored" in sys.argv[2:] else it
    tbox = base / "tbox.ttl"
    if not tbox.exists():
        print(f"Error: {tbox} not found. Run the previous step first.")
        sys.exit(1)
    g = Graph().parse(tbox, format="turtle")
    name = lambda iri: g.namespace_manager.normalizeUri(iri).strip("<>")
    nodes, edges = extract(g)
    if (base / "abox.ttl").exists():
        usage(g, Graph().parse(base / "abox.ttl", format="turtle"), nodes, edges)

    (base / "tbox.graphml").write_text(graphml(nodes, edges, name), encoding="utf-8")
    if shutil.which("dot") is None:
        print(f"Wrote {base / 'tbox.graphml'}. PNG skipped: install Graphviz (`sudo apt install graphviz`).")
        return
    subprocess.run(["dot", "-Tpng", "-o", str(base / "tbox.png")], input=dot(nodes, edges, name), text=True, check=True)
    print(f"Wrote {base / 'tbox.graphml'} and {base / 'tbox.png'}")


if __name__ == "__main__":
    main()
