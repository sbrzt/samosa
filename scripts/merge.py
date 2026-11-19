# scripts/merge.py

import re
import sys
from pathlib import Path
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, split_uri
from scripts import align
from scripts.common import EX, dump_yaml, load_yaml, resolve_iteration
from scripts.milestone import promote, rank, status
from scripts.generate_tbox import local_name
from scripts.test_iteration import run_tests

MERGED = "merged"
KINDS = {OWL.Class: "class", RDFS.Class: "class", OWL.ObjectProperty: "property",
         OWL.DatatypeProperty: "property", RDF.Property: "property", OWL.NamedIndividual: "individual"}


def kind(g, term):
    """Return the kinds (`class`, `property`, `individual`) a TBox declares for a term."""
    return {KINDS[t] for t in g.objects(term, RDF.type) if t in KINDS}


def entities(g):
    """Return the named terms a TBox declares as a class, property or individual."""
    return {s for s in g.subjects(RDF.type, None) if isinstance(s, URIRef) and kind(g, s)}


def conflicts(new, old):
    """Find terms that two TBoxes define in incompatible ways.

    A term clashes if both TBoxes declare it with disjoint kinds (e.g. a class in
    one and a property in the other), or with different non-empty `rdfs:domain`
    or `rdfs:range` sets: their union would restrict the property to the
    intersection of both.

    Args:
        new: TBox of the iteration being merged.
        old: TBox of an iteration already in the current model.

    Returns:
        List of `(term, what, new_values, old_values)` tuples.
    """
    out = []
    for t in entities(new) & entities(old):
        if kind(new, t).isdisjoint(kind(old, t)):
            out.append((t, "kind", kind(new, t), kind(old, t)))
        for p in (RDFS.domain, RDFS.range):
            a, b = set(new.objects(t, p)), set(old.objects(t, p))
            if a and b and a != b:
                out.append((t, split_uri(p)[1], a, b))
    return out


def _keys(g, t):
    """Return the normalized names of a term: local name, labels and definitions."""
    norm = lambda s: re.sub(r"\s+", " ", str(s)).strip().casefold()
    try:
        keys = {("local name", split_uri(t)[1].casefold())}
    except ValueError:
        keys = set()
    keys |= {("label", norm(o)) for o in g.objects(t, RDFS.label)}
    keys |= {("definition", norm(o)) for o in g.objects(t, RDFS.comment)}
    return {k for k in keys if k[1]}


def duplicates(new, old):
    """Find likely duplicate entities between two TBoxes (SAMOD step 2.1).

    Two different terms of the same kind are likely the same entity if they
    share a local name (ignoring case), a label or a definition. This is a
    heuristic: synonyms with different names and definitions are not found.

    Args:
        new: TBox of the iteration being merged.
        old: TBox of an iteration already in the current model.

    Returns:
        List of `(new_term, old_term, reasons)` tuples.
    """
    out = []
    shared = entities(new) & entities(old)
    for a in entities(new) - shared:
        for b in entities(old) - shared:
            same = {w for w, k in _keys(new, a) & _keys(old, b)}
            if same and not kind(new, a).isdisjoint(kind(old, b)):
                out.append((a, b, sorted(same)))
    return out


def _short(terms):
    """Render a term or a set of terms for printing."""
    if isinstance(terms, (set, frozenset)):
        return ", ".join(sorted(_short(t) for t in terms))
    return f"<{terms}>" if isinstance(terms, URIRef) else str(terms)


def header(tbox):
    """Add the ontology header and `rdfs:isDefinedBy` links to the current model.

    Reads `ontology.yaml` (all fields optional): `iri` (default the local
    namespace), `version`, `version_iri`, `title`, `description`, `creators`
    and `license`. Every local (`:`) class, property and individual gets
    `rdfs:isDefinedBy <iri>`; reused external terms keep their own.

    Args:
        tbox: Current model graph, updated in place.
    """
    path = Path("ontology.yaml")
    meta = (load_yaml(path) if path.exists() else None) or {}
    text = lambda v: str(v or "").strip()
    iri = URIRef(text(meta.get("iri")) or EX)
    tbox.add((iri, RDF.type, OWL.Ontology))
    for key, p, make in (("version", OWL.versionInfo, Literal), ("version_iri", OWL.versionIRI, URIRef),
                         ("title", DCTERMS.title, lambda v: Literal(v, lang="en")),
                         ("description", DCTERMS.description, lambda v: Literal(v, lang="en")),
                         ("license", DCTERMS.license, URIRef)):
        if text(meta.get(key)):
            tbox.add((iri, p, make(text(meta[key]))))
    for c in meta.get("creators") or []:
        c = text(c)
        if c:
            tbox.add((iri, DCTERMS.creator, URIRef(c) if "://" in c else Literal(c)))
    for t in entities(tbox):
        if t.startswith(EX):
            tbox.add((t, RDFS.isDefinedBy, iri))
    tbox.bind("dcterms", DCTERMS)


def bag(extra=None):
    """Return the iterations in the bag of test cases: the merged ones, plus `extra`."""
    dirs = sorted(d for d in Path("iterations").glob("*") if d.is_dir())
    return [d for d in dirs if (extra and d.name == extra.name) or status(d) == MERGED]


def main(iteration: str = None, reason: bool = False):
    """Merge an iteration into the current model and re-test every test case.

    Follows SAMOD step 2. The bag of test cases is every iteration whose
    `metadata.status` is `merged`, plus `iteration`. The current model is
    rebuilt as the union of their refactored TBoxes, so renames and edits made
    by `align` replace the old definitions. Then:

    1. the refactored TBox of `iteration` is compared with those of the other
       merged iterations: conflicting definitions of the same term fail the
       merge, likely duplicate entities are printed as warnings;
    2. every test case runs `test --refactored` with the new current model as
       its TBox and its own refactored ABox.

    `iteration` must have passed `test` (status `tested` or later). Only if
    everything passes, writes the current model, with the ontology
    header from `ontology.yaml` (see `header`), to `project/tbox.ttl`,
    the union of the ABoxes to `project/abox.ttl`, and raises the status of
    `iteration` to `merged`, recording a milestone (see `milestone.promote`).

    Args:
        iteration: Iteration to merge, resolved with `resolve_iteration`. If
            omitted, rebuilds and re-tests the current model from the merged
            iterations only.
        reason: If true, run the queries on the OWL 2 RL closure of TBox+ABox.

    Raises:
        SystemExit: If the bag is empty, an iteration has no refactored TBox or
            ABox, there are conflicts, or any test fails.
    """
    new = resolve_iteration(iteration) if iteration else None
    if new and rank(status(new)) < rank("tested"):
        print(f"Error: {new.name} is '{status(new)}': its test case is not complete. Run test first.")
        sys.exit(1)
    dirs = bag(new)
    new = next((d for d in dirs if new and d.name == new.name), None)
    if not dirs:
        print("Error: no merged iterations. Run merge <iteration> first.")
        sys.exit(1)
    missing = [d.name for d in dirs
               if not all((Path("refactoring") / d.name / f).exists() for f in ("abox.ttl", "tbox.ttl"))]
    if missing:
        print(f"Error: no refactoring/ output for: {', '.join(missing)}. Run align first.")
        sys.exit(1)

    tboxes = {d: Graph().parse(Path("refactoring") / d.name / "tbox.ttl", format="turtle") for d in dirs}
    aboxes = {d: Graph().parse(Path("refactoring") / d.name / "abox.ttl", format="turtle") for d in dirs}
    tbox, abox = Graph(), Graph()
    for d in dirs:
        tbox += tboxes[d]
        abox += aboxes[d]
        for g in (tboxes[d], aboxes[d]):
            for p, ns in g.namespaces():
                tbox.bind(p, ns)
                abox.bind(p, ns)

    failures = 0
    for d in dirs if new else []:
        if d == new:
            continue
        for t, what, a, b in conflicts(tboxes[new], tboxes[d]):
            print(f"FAIL [{new.name}] conflict with {d.name}: {_short(t)} {what} is {_short(a)} here, {_short(b)} there")
            failures += 1
        for a, b, why in duplicates(tboxes[new], tboxes[d]):
            print(f"WARN [{new.name}] possible duplicate: {_short(a)} here and {_short(b)} in {d.name} "
                  f"(same {', '.join(why)}). If they are the same entity, run rename.")

    prefixes = align.load_prefixes()
    checked = 0
    for d in dirs:
        data = load_yaml(d / "requirements.yaml")
        c, f = run_tests(tbox, aboxes[d], data.get("competency_questions"), d.name,
                         "refactored_query", reason, align.aliases(data, prefixes))
        checked += c
        failures += f
    if checked == 0 or failures:
        print("Merge failed: current model not updated." if failures
              else "No queries found: current model not updated.")
        sys.exit(1)

    header(tbox)
    out = Path("project")
    out.mkdir(exist_ok=True)
    tbox.serialize(destination=out / "tbox.ttl", format="turtle")
    abox.serialize(destination=out / "abox.ttl", format="turtle")
    print(f"Current model: {len(dirs)} iteration(s) ({', '.join(d.name for d in dirs)}) in {out}/")
    if new:
        promote(new, MERGED)


def rename(old: str, new: str):
    """Rename an entity in every iteration and re-merge (SAMOD step 2.2).

    Collapses a duplicate: every glossary term that currently stands for `old`
    (its own local IRI, or its `align_to`) gets `align_to: new`. Each changed
    iteration that has a TBox and ABox is then re-aligned, which rewrites its
    refactored TBox, ABox and queries; the current model is then rebuilt and
    re-tested with `merge`. `expected_result` cells keep working through the
    `align_to` aliases.

    Args:
        old: Term to replace, as `:Local`, `prefix:term` or a full IRI.
        new: Term to use instead, in the same forms. `:Local` terms are taken
            from the current model.

    Raises:
        SystemExit: If no glossary term stands for `old`, or the re-merge fails.
    """
    prefixes = align.load_prefixes()
    old_iri, new_iri = align.expand(old, prefixes), align.expand(new, prefixes)
    changed = []
    for d in sorted(d for d in Path("iterations").glob("*") if d.is_dir()):
        data = load_yaml(d / "requirements.yaml")
        hit = False
        for t in data.get("glossary") or []:
            if not t.get("term") or not t.get("type"):
                continue
            own = EX + local_name(t)
            if (align.expand(t["align_to"], prefixes) if t.get("align_to") else own) == old_iri:
                t["align_to"] = "" if new_iri == own else new
                hit = True
        if hit:
            dump_yaml(data, d / "requirements.yaml")
            changed.append(d)
    if not changed:
        print(f"Error: no glossary term stands for <{old_iri}>.")
        sys.exit(1)
    for d in changed:
        print(f"{d.name}: align_to {new}")
        if (d / "tbox.ttl").exists() and (d / "abox.ttl").exists():
            align.main(d.name)
        else:
            print(f"{d.name}: no tbox.ttl/abox.ttl yet, run tbox, abox and align.")
    if bag():
        main()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
