# scripts/diagram.py

import copy
import shutil
import subprocess
import sys
from pathlib import Path
import xml.etree.ElementTree as ET
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD
from scripts.common import resolve_iteration

TEMPLATE = Path(__file__).with_name("graffoo.graphml")
NS = {"g": "http://graphml.graphdrawing.org/xmlns", "y": "http://www.yworks.com/xml/graphml"}
for prefix, uri in (("", NS["g"]), ("y", NS["y"]), ("yed", "http://www.yworks.com/xml/yed/3"),
                    ("xsi", "http://www.w3.org/2001/XMLSchema-instance")):
    ET.register_namespace(prefix, uri)

NODE_PROTO = {"class": "Class", "datatype": "Datatype", "individual": "instance", "literal": '"value"^^datatype'}
EDGE_PROTO = {"object": "objectProperty", "data": "dataProperty", "subclass": "predicate", "type": "predicate",
              "object-use": "objectProperty", "data-use": "dataProperty"}

DOT_NODE = {"class": 'shape=box style="rounded,filled" fillcolor="#FFFF00"',
            "datatype": 'shape=parallelogram style=filled fillcolor="#CCFFCC"',
            "individual": 'shape=circle style=filled fillcolor="#FF99CC" penwidth=3 width=0.25 fixedsize=true xlabel={label} label=""',
            "literal": "shape=plaintext"}
DOT_EDGE = {"object": 'color="#000080" fontcolor="#000080" dir=both arrowtail=dot arrowhead=normal',
            "data": 'color="#008000" fontcolor="#008000" dir=both arrowtail=odot arrowhead=empty',
            "subclass": "", "type": ""}
DOT_EDGE["object-use"] = DOT_EDGE["object"] + " style=dashed"

# Mermaid shapes and Graffoo colours. Mermaid cannot draw Graffoo's dot at the
# start of property edges, so properties are told apart by colour only.
MERMAID_NODE = {"class": '("{}"):::owlClass', "datatype": '[/"{}"/]:::datatype',
                "individual": '(("{}")):::individual', "literal": '["{}"]:::literal'}
MERMAID_STYLE = {"owlClass": "fill:#FFFF00,stroke:#000", "datatype": "fill:#CCFFCC,stroke:#000",
                 "individual": "fill:#FF99CC,stroke:#000", "literal": "fill:none,stroke:none"}
MERMAID_EDGE = {"object": "#000080", "data": "#008000"}
DOT_EDGE["data-use"] = DOT_EDGE["data"] + " style=dashed"


def extract(g):
    """Collect TBox nodes and edges to draw.

    Args:
        g: Graph holding the TBox.

    Returns:
        A `(nodes, edges)` pair. `nodes` maps each IRI to its kind (`"class"`,
        `"datatype"` or `"individual"`). `edges` lists `(source, target, property, kind)`
        tuples, with kind `"subclass"`, `"type"`, `"object"` or `"data"`. Missing
        domains and ranges default to `owl:Thing` or `rdfs:Literal`.
    """
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


def extract_abox(abox):
    """Collect ABox nodes and edges to draw: individuals, their classes and assertions.

    Args:
        abox: Graph holding the ABox.

    Returns:
        A `(nodes, edges)` pair, as for `extract`. Individuals are named or
        blank nodes, kind `"individual"`; their `rdf:type` objects are kind
        `"class"` (`owl:NamedIndividual` is left out). Each literal value is its
        own node of kind `"literal"`, keyed by the `(subject, property, value)`
        triple, so equal values of different assertions are drawn apart.
        Edges have kind `"type"`, `"object"` or `"data"`.
    """
    nodes, edges = {}, []
    for s, p, o in sorted(abox):
        if not isinstance(s, (URIRef, BNode)) or o == OWL.NamedIndividual:
            continue
        nodes.setdefault(s, "individual")
        if p == RDF.type:
            nodes[o] = "class"
            edges.append((s, o, "rdf:type", "type"))
        elif isinstance(o, Literal):
            nodes[(s, p, o)] = "literal"
            edges.append((s, (s, p, o), p, "data"))
        else:
            nodes.setdefault(o, "individual")
            edges.append((s, o, p, "object"))
    return nodes, edges


def labeler(g):
    """Return a function giving the display label of a node or property.

    IRIs are shortened with the prefixes bound in `g`, literal nodes (see
    `extract_abox`) are shown as Turtle (`"4"^^xsd:integer`), blank nodes as
    `_:id`.

    Args:
        g: Graph whose prefix bindings are used.
    """
    def name(n):
        if isinstance(n, tuple):
            return n[2].n3(g.namespace_manager)
        if isinstance(n, URIRef):
            return g.namespace_manager.normalizeUri(n).strip("<>")
        return n.n3() if isinstance(n, BNode) else str(n)
    return name


def write(base, stem, nodes, edges, name, graffoo):
    """Write `<stem>.mmd` and, with `graffoo`, `<stem>.graphml` and `<stem>.png`.

    Args:
        base: Output directory.
        stem: File name stem, `"tbox"` or `"abox"`.
        nodes: Node dict from `extract` or `extract_abox`.
        edges: Edge list from `extract` or `extract_abox`.
        name: Function mapping a node or property to its display label.
        graffoo: If true, also write the Graffoo files. The PNG needs Graphviz.

    Returns:
        The list of written paths.
    """
    (base / f"{stem}.mmd").write_text(mermaid(nodes, edges, name), encoding="utf-8")
    written = [base / f"{stem}.mmd"]
    if graffoo:
        (base / f"{stem}.graphml").write_text(graphml(nodes, edges, name), encoding="utf-8")
        written.append(base / f"{stem}.graphml")
        if shutil.which("dot"):
            subprocess.run(["dot", "-Tpng", "-o", str(base / f"{stem}.png")],
                           input=dot(nodes, edges, name), text=True, check=True)
            written.append(base / f"{stem}.png")
    return written


def usage(g, abox, nodes, edges):
    """Add property usages found in the ABox, in place.

    Args:
        g: Graph holding the TBox, used to find object and datatype properties.
        abox: Graph holding the ABox.
        nodes: Node dict from `extract`, updated with new classes and datatypes.
        edges: Edge list from `extract`, extended with `"object-use"` and
            `"data-use"` edges between the types of subjects and objects.
    """
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
    """Render nodes and edges as Graffoo GraphML for yEd.

    Args:
        nodes: Node dict from `extract`.
        edges: Edge list from `extract`.
        name: Function mapping an IRI to its display label.

    Returns:
        The GraphML document as a string, built from the prototypes in `graffoo.graphml`.
    """
    tree = ET.parse(TEMPLATE)
    graph = tree.getroot().find("g:graph", NS)
    label_of = lambda el: (el.findtext(".//y:NodeLabel", "", NS) or el.findtext(".//y:EdgeLabel", "", NS)).strip()
    protos = {label_of(el): el for el in graph.iter() if el.tag in (f"{{{NS['g']}}}node", f"{{{NS['g']}}}edge")}
    for el in list(graph):
        if el.tag != f"{{{NS['g']}}}data":
            graph.remove(el)

    ids = {n: f"n{i}" for i, n in enumerate(nodes)}
    for i, (n, kind) in enumerate(nodes.items()):
        node = copy.deepcopy(protos[NODE_PROTO[kind]])
        node.set("id", ids[n])
        node.find(".//y:NodeLabel", NS).text = name(n)
        geo = node.find(".//y:Geometry", NS)
        if kind != "individual":  
            geo.set("width", str(10 * len(name(n)) + 30))
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


def mermaid(nodes, edges, name):
    """Render nodes and edges as a Mermaid flowchart in Graffoo colours.

    Args:
        nodes: Node dict from `extract`.
        edges: Edge list from `extract`.
        name: Function mapping an IRI to its display label.

    Returns:
        The Mermaid source as a string.
    """
    q = lambda s: s.replace('"', "#quot;")
    ids = {n: f"n{i}" for i, n in enumerate(nodes)}
    out = ["flowchart LR"]
    out += [f"  {ids[n]}{MERMAID_NODE[kind].format(q(name(n)))}" for n, kind in nodes.items()]
    colored = {}
    for i, (s, t, p, kind) in enumerate(edges):
        label = {"subclass": "rdfs:subClassOf", "type": "rdf:type"}.get(kind) or name(p)
        arrow = "-.->" if kind.endswith("-use") else "-->"
        out.append(f'  {ids[s]} {arrow}|"{q(label)}"| {ids[t]}')
        if kind.removesuffix("-use") in MERMAID_EDGE:
            colored.setdefault(MERMAID_EDGE[kind.removesuffix("-use")], []).append(str(i))
    out += [f"  classDef {c} {style},color:#000" for c, style in MERMAID_STYLE.items()]
    out += [f"  linkStyle {','.join(ix)} stroke:{color},color:{color}" for color, ix in colored.items()]
    return "\n".join(out) + "\n"


def dot(nodes, edges, name):
    """Render nodes and edges as a Graphviz DOT graph in Graffoo style.

    Args:
        nodes: Node dict from `extract`.
        edges: Edge list from `extract`.
        name: Function mapping an IRI to its display label.

    Returns:
        The DOT source as a string.
    """
    q = lambda s: '"' + s.replace('"', '\\"') + '"'
    out = ['digraph G { rankdir=LR; node [fontname="Helvetica"]; edge [fontname="Helvetica"];']
    for n, kind in nodes.items():
        out.append(f'{q(str(n))} [label={q(name(n))} {DOT_NODE[kind].format(label=q(name(n)))}];')
    for s, t, p, kind in edges:
        label = {"subclass": "rdfs:subClassOf", "type": "rdf:type"}.get(kind) or name(p)
        out.append(f"{q(str(s))} -> {q(str(t))} [label={q(label)} {DOT_EDGE[kind]}];")
    out.append("}")
    return "\n".join(out)


def main(iteration: str, refactored: bool = False, graffoo: bool = False):
    """Write Mermaid diagrams of an iteration's TBox (`tbox.mmd`) and ABox (`abox.mmd`).

    In the TBox diagram, property usages found in the ABox, if any, are drawn
    as dashed edges. The ABox diagram is written only if `abox.ttl` exists.

    Args:
        iteration: Iteration path or name, resolved with `resolve_iteration`.
        refactored: If true, read from `refactoring/<iteration>/` instead.
        graffoo: If true, also write Graffoo diagrams for yEd (`tbox.graphml`,
            `abox.graphml`) and, if Graphviz is installed, Graffoo-style PNGs.

    Raises:
        SystemExit: If `tbox.ttl` does not exist.
    """
    it = resolve_iteration(iteration)
    base = Path("refactoring") / it.name if refactored else it
    tbox = base / "tbox.ttl"
    if not tbox.exists():
        print(f"Error: {tbox} not found. Run the previous step first.")
        sys.exit(1)
    g = Graph().parse(tbox, format="turtle")
    abox = Graph().parse(base / "abox.ttl", format="turtle") if (base / "abox.ttl").exists() else None
    nodes, edges = extract(g)
    if abox is not None:
        usage(g, abox, nodes, edges)
    written = write(base, "tbox", nodes, edges, labeler(g), graffoo)
    if abox is not None:
        written += write(base, "abox", *extract_abox(abox), labeler(abox), graffoo)
    print(f"Wrote {', '.join(map(str, written))}")
    if graffoo and shutil.which("dot") is None:
        print("PNG skipped: install Graphviz (`sudo apt install graphviz`).")

if __name__ == "__main__":
    main(sys.argv[1], "--refactored" in sys.argv[2:], "--graffoo" in sys.argv[2:])
