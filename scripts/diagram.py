# scripts/diagram.py

import copy
import json
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
              "object-use": "objectProperty", "data-use": "dataProperty", "assertion": "predicate"}
URL = "d4"  # GraphML key of a node's url: what the node stands for (see `key`), to keep its position across redraws
FORMATS = ("png", "svg", "pdf")  # exports written next to the GraphML file

# Graffoo (yEd) shapes and arrows in Graphviz
DOT_SHAPE = {"roundrectangle": 'box style="rounded,filled"', "parallelogram": "parallelogram style=filled",
             "ellipse": "circle style=filled", "rectangle": "box style=filled"}
DOT_ARROW = {"delta": "normal", "standard": "normal", "white_delta": "empty", "circle": "dot",
             "transparent_circle": "odot", "none": "none"}


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
        Edges have kind `"type"` or `"assertion"`, both drawn as black arrows.
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
            edges.append((s, (s, p, o), p, "assertion"))
        else:
            nodes.setdefault(o, "individual")
            edges.append((s, o, p, "assertion"))
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


def key(n):
    """Identify a node across redraws: its IRI, or the Turtle of a literal node's triple.

    Blank nodes get new ids at each parse, so their position is not kept.
    """
    return " ".join(x.n3() for x in n) if isinstance(n, tuple) else str(n)


def graphml(nodes, edges, name):
    """Render nodes and edges as Graffoo GraphML for yEd, with every node at (0, 0).

    Args:
        nodes: Node dict from `extract`.
        edges: Edge list from `extract`.
        name: Function mapping an IRI to its display label.

    Returns:
        The GraphML root element, built from the prototypes in `graffoo.graphml`.
        Each node's url (key `d4`) is its `key`.
    """
    root = ET.parse(TEMPLATE).getroot()
    graph = root.find("g:graph", NS)
    label_of = lambda el: (el.findtext(".//y:NodeLabel", "", NS) or el.findtext(".//y:EdgeLabel", "", NS)).strip()
    protos = {label_of(el): el for el in graph.iter() if el.tag in (f"{{{NS['g']}}}node", f"{{{NS['g']}}}edge")}
    for el in list(graph):
        if el.tag != f"{{{NS['g']}}}data":
            graph.remove(el)

    ids = {n: f"n{i}" for i, n in enumerate(nodes)}
    for n, kind in nodes.items():
        node = copy.deepcopy(protos[NODE_PROTO[kind]])
        node.set("id", ids[n])
        for old in node.findall(f"g:data[@key='{URL}']", NS):
            node.remove(old)
        node.insert(0, ET.Element(f"{{{NS['g']}}}data", key=URL))
        node[0].text = key(n)
        node.find(".//y:NodeLabel", NS).text = name(n)
        geo = node.find(".//y:Geometry", NS)
        if kind != "individual":
            geo.set("width", str(10 * len(name(n)) + 30))
        geo.set("x", "0"); geo.set("y", "0")
        graph.append(node)
    for i, (s, t, p, kind) in enumerate(edges):
        edge = copy.deepcopy(protos[EDGE_PROTO[kind]])
        edge.attrib.update(id=f"e{i}", source=ids[s], target=ids[t])
        if kind.endswith("-use"):
            edge.find(".//y:LineStyle", NS).set("type", "dashed")
        edge.find(".//y:EdgeLabel", NS).text = {"subclass": "rdfs:subClassOf", "type": "rdf:type"}.get(kind) or name(p)
        graph.append(edge)
    return root


def geometry(root):
    """Map the id of each node of a GraphML tree to its `y:Geometry` (top-left `x`, `y`, `width`, `height`)."""
    return {n.get("id"): n.find(".//y:Geometry", NS) for n in root.iter(f"{{{NS['g']}}}node")}


def dot(root, placed=()):
    """Render a Graffoo GraphML tree as a Graphviz DOT graph in Graffoo style.

    Args:
        root: GraphML root element, as from `graphml`.
        placed: Ids of the nodes to give their GraphML position (`pos`, pinned
            for `neato`). Graphviz's y axis points up, so y is negated.

    Returns:
        The DOT source as a string. Node names are the GraphML ids.
    """
    q = lambda s: '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    out = ['digraph G { rankdir=LR; nodesep=0.8; ranksep=1.2; node [fontname="Helvetica" fontsize=16 fixedsize=true]; edge [fontname="Helvetica" fontsize=16];']
    for n in root.iter(f"{{{NS['g']}}}node"):
        geo, fill, border, label, shape = (n.find(f".//y:{t}", NS) for t in ("Geometry", "Fill", "BorderStyle", "NodeLabel", "Shape"))
        w, h = float(geo.get("width")), float(geo.get("height"))
        attrs = [f"width={w / 72} height={h / 72}"]
        attrs.append(f'shape={DOT_SHAPE[shape.get("type")]} fillcolor="{fill.get("color")}" penwidth={border.get("width")}'
                     if fill.get("color") else "shape=plaintext")
        text = q(label.text or "")
        attrs.append(f'xlabel={text} label=""' if label.get("modelName") == "eight_pos" else f"label={text}")
        if n.get("id") in placed:
            attrs.append(f'pos="{float(geo.get("x")) + w / 2},{-float(geo.get("y")) - h / 2}!"')
        out.append(f'{n.get("id")} [{" ".join(attrs)}];')
    for e in root.iter(f"{{{NS['g']}}}edge"):
        line, arrows = e.find(".//y:LineStyle", NS), e.find(".//y:Arrows", NS)
        c = line.get("color")
        dashed = " style=dashed" if line.get("type") == "dashed" else ""
        out.append(f'{e.get("source")} -> {e.get("target")} [label={q(e.findtext(".//y:EdgeLabel", "", NS).strip())} '
                   f'color="{c}" fontcolor="{c}" dir=both arrowtail={DOT_ARROW[arrows.get("source")]} '
                   f'arrowhead={DOT_ARROW[arrows.get("target")]}{dashed}];')
    out.append("}")
    return "\n".join(out)


def saved(path):
    """Read the node positions of a GraphML file written by `draw`.

    Returns:
        A dict mapping each node's url (see `key`) to its top-left `(x, y)`.
        Empty if the file does not exist.
    """
    if not path.exists():
        return {}
    root = ET.parse(path).getroot()
    return {n.findtext(f"g:data[@key='{URL}']", "", NS): (float(g.get("x")), float(g.get("y")))
            for n in root.iter(f"{{{NS['g']}}}node") if (g := n.find(".//y:Geometry", NS)) is not None}


def place(root, positions):
    """Position the nodes of a GraphML tree, in place.

    Nodes whose url is in `positions` keep that position. If none is, Graphviz
    `dot` lays out the whole graph. Otherwise `neato` places the new nodes
    around the kept ones, which it does not move relative to each other.
    Without Graphviz, new nodes go on a grid.

    Args:
        root: GraphML root element, as from `graphml`.
        positions: Dict from `saved`.
    """
    geos = geometry(root)
    urls = {n.get("id"): n.findtext(f"g:data[@key='{URL}']", "", NS) for n in root.iter(f"{{{NS['g']}}}node")}
    placed = {i for i, u in urls.items() if u in positions}
    for i in placed:
        geos[i].set("x", str(positions[urls[i]][0])); geos[i].set("y", str(positions[urls[i]][1]))
    if len(placed) == len(geos):
        return
    if shutil.which("dot") is None:
        for k, i in enumerate(i for i in geos if i not in placed):
            geos[i].set("x", str((k % 5) * 300)); geos[i].set("y", str((k // 5) * 150))
        return
    cmd = ["neato", "-s"] if placed else ["dot"]  # -s: pos in points
    layout = json.loads(subprocess.run([*cmd, "-Tjson"], input=dot(root, placed), text=True,
                                       capture_output=True, check=True).stdout)
    for obj in layout.get("objects", []):
        x, y = map(float, obj["pos"].split(","))
        geo = geos[obj["name"]]
        geo.set("x", str(round(x - float(geo.get("width")) / 2, 2)))
        geo.set("y", str(round(-y - float(geo.get("height")) / 2, 2)))


def export(path, root):
    """Write a GraphML tree to `path` and, with Graphviz, its PNG, SVG and PDF exports.

    The exports are drawn by `neato -n2` with every node at its GraphML position.

    Returns:
        The list of written paths.
    """
    path.write_text(ET.tostring(root, encoding="unicode", xml_declaration=True), encoding="utf-8")
    written = [path]
    if shutil.which("dot"):
        src = dot(root, geometry(root))
        for fmt in FORMATS:
            subprocess.run(["neato", "-n2", f"-T{fmt}", "-o", str(path.with_suffix(f".{fmt}"))],
                           input=src, text=True, check=True)
            written.append(path.with_suffix(f".{fmt}"))
    return written


def draw(path, nodes, edges, name):
    """Write a Graffoo diagram and its exports, keeping the saved position of every node still in it.

    Args:
        path: The `.graphml` file.
        nodes: Node dict from `extract` or `extract_abox`.
        edges: Edge list from `extract` or `extract_abox`.
        name: Function mapping a node or property to its display label.

    Returns:
        The list of written paths.
    """
    root = graphml(nodes, edges, name)
    place(root, saved(path))
    return export(path, root)


def folder(iteration, refactored):
    """Directory of an iteration's files: `iterations/<it>/`, or `refactoring/<it>/` if `refactored`."""
    it = resolve_iteration(iteration)
    return Path("refactoring") / it.name if refactored else it


def main(iteration: str, refactored: bool = False):
    """Draw Graffoo diagrams of an iteration's TBox (`tbox.graphml`) and ABox (`abox.graphml`), with PNG, SVG and PDF exports.

    Nodes already in a previous diagram keep their saved position; new ones
    are laid out by Graphviz. In the TBox diagram, property usages found in the
    ABox, if any, are drawn as dashed edges. The ABox diagram is written only
    if `abox.ttl` exists.

    Args:
        iteration: Iteration path or name, resolved with `resolve_iteration`.
        refactored: If true, read from `refactoring/<iteration>/` instead.

    Raises:
        SystemExit: If `tbox.ttl` does not exist.
    """
    base = folder(iteration, refactored)
    tbox = base / "tbox.ttl"
    if not tbox.exists():
        print(f"Error: {tbox} not found. Run the previous step first.")
        sys.exit(1)
    g = Graph().parse(tbox, format="turtle")
    abox = Graph().parse(base / "abox.ttl", format="turtle") if (base / "abox.ttl").exists() else None
    nodes, edges = extract(g)
    if abox is not None:
        usage(g, abox, nodes, edges)
    written = draw(base / "tbox.graphml", nodes, edges, labeler(g))
    if abox is not None:
        written += draw(base / "abox.graphml", *extract_abox(abox), labeler(abox))
    print(f"Wrote {', '.join(map(str, written))}")
    if shutil.which("dot") is None:
        print("Nodes placed on a grid and exports skipped: install Graphviz (`sudo apt install graphviz`).")


def save_layout(iteration: str, stem: str, positions: dict, refactored: bool = False):
    """Move the nodes of a saved diagram and write its exports again.

    Only positions change: labels, nodes and edges stay as drawn.

    Args:
        iteration: Iteration path or name, resolved with `resolve_iteration`.
        stem: `"tbox"` or `"abox"`.
        positions: Maps node ids to `{"x": ..., "y": ...}`, top-left corners in
            pixels. Unknown ids are ignored.
        refactored: If true, the diagram under `refactoring/<iteration>/`.

    Raises:
        SystemExit: If the diagram does not exist.
    """
    path = folder(iteration, refactored) / f"{stem}.graphml"
    if stem not in ("tbox", "abox") or not path.exists():
        print(f"Error: {path} not found. Draw the diagrams first.")
        sys.exit(1)
    root = ET.parse(path).getroot()
    geos = geometry(root)
    for i, p in positions.items():
        if i in geos:
            geos[i].set("x", str(float(p["x"]))); geos[i].set("y", str(float(p["y"])))
    print(f"Wrote {', '.join(map(str, export(path, root)))}")


if __name__ == "__main__":
    main(sys.argv[1], "--refactored" in sys.argv[2:])
