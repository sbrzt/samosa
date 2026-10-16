# scripts/align.py

import json
import re
import sys
import yaml
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import RDFS, XSD
from rdflib.namespace import split_uri
from scripts.common import EX, dump_yaml, load_yaml, resolve_iteration
from scripts.generate_tbox import local_name


def expand(value, prefixes):
    """`prefix:term` -> full IRI. Full IRIs pass through."""
    if "://" in value:
        return value
    prefix, _, local = value.partition(":")
    if prefix not in prefixes:
        print(f"Error: unknown prefix '{prefix}' in align_to '{value}'. Add it to prefixes.yaml.")
        sys.exit(1)
    return prefixes[prefix] + local


_vocabularies = {}


def vocabulary(iri, prefixes):
    """Graph of the ontology owning `iri`, fetched once from its namespace and cached in vocabularies/."""
    prefix, ns = max(((p, n) for p, n in prefixes.items() if iri.startswith(n)),
                     key=lambda x: len(x[1]), default=(None, None))
    if prefix is None:
        return None
    if prefix not in _vocabularies:
        path = Path("vocabularies") / f"{prefix}.ttl"
        g = Graph()
        try:
            if path.exists():
                g.parse(path, format="turtle")
            else:
                g.parse(ns)  # content negotiation on the namespace IRI
                path.parent.mkdir(exist_ok=True)
                g.serialize(destination=path, format="turtle")
        except Exception as e:
            print(f"Warning: cannot load vocabulary '{prefix}' ({ns}): {e}")
        _vocabularies[prefix] = g
    return _vocabularies[prefix]


def describe(g, term):
    """All triples with `term` as subject, following blank nodes."""
    todo, seen = [term], set()
    while todo:
        s = todo.pop()
        for p, o in g.predicate_objects(s):
            yield s, p, o
            if isinstance(o, BNode) and o not in seen:
                seen.add(o)
                todo.append(o)


def prefix_for(ns, known, taken):
    """Prefix name for an unregistered namespace: known bindings, the namespace's own RDF, prefix.cc, the IRI."""
    if ns in known:
        return known[ns]
    try:
        g = Graph().parse(ns)  # content negotiation on the namespace IRI
        # skip names already taken: badly parsed RDF/XML can bind e.g. `owl` to the wrong namespace
        name = next((p for p, n in g.namespaces() if p and str(n) == ns and p not in taken), None)
        if name:
            return name
    except Exception:
        pass
    try:
        # plain http: prefix.cc's https certificate has expired
        url = "http://prefix.cc/reverse?" + urlencode({"uri": ns, "format": "json"})
        return next(iter(json.load(urlopen(url, timeout=10))))
    except Exception:
        pass
    # last path segment, file extension dropped: .../region.owl# -> region
    words = re.findall(r"[A-Za-z][\w-]*", re.sub(r"\.\w+[#/]?$", "", ns.split("://", 1)[-1]))
    return words[-1].lower() if words else "ns"


def register_prefixes(dst, prefixes):
    """Register in prefixes.yaml every namespace used by dst and missing from it."""
    known = {str(n): p for g in (*_vocabularies.values(), dst) for p, n in g.namespaces()
             if p and not re.fullmatch(r"ns\d+", p)}
    missing = set()
    # ponytail: every IRI counts, doc links included; filter by triple position if junk prefixes show up
    for t in {t for triple in dst for t in triple if isinstance(t, URIRef)}:
        if any(t.startswith(n) for n in prefixes.values()):
            continue
        try:
            missing.add(split_uri(t)[0])
        except ValueError:
            pass
    missing.discard(EX)

    new = {}
    for ns in sorted(missing):
        name = base = prefix_for(ns, known, set(prefixes) | set(new))
        i = 2
        while name in prefixes or name in new:
            name, i = f"{base}{i}", i + 1
        new[name] = ns
    if new:
        with open("prefixes.yaml", "a", encoding="utf-8") as f:
            f.writelines(f"{p}: {ns}\n" for p, ns in new.items())
        for p, ns in new.items():
            dst.bind(p, ns, override=True, replace=True)
        prefixes.update(new)
        print(f"Added to prefixes.yaml: {', '.join(new)}")


def refactor_query(query, names):
    for name, iri in names.items():
        # case-insensitive: glossary "has url" -> hasUrl, but hand-written ABox/queries may say hasURL
        query = re.sub(re.escape(f"<{EX}{name}>"), f"<{iri}>", query, flags=re.I)
        query = re.sub(rf"(?<![\w:]):{re.escape(name)}\b", f"<{iri}>", query, flags=re.I)
    return query


def main(iteration):
    it = resolve_iteration(iteration)
    data = load_yaml(it / "requirements.yaml")

    prefixes = load_yaml(Path("prefixes.yaml")) if Path("prefixes.yaml").exists() else {}
    names = {local_name(t): expand(t["align_to"], prefixes) for t in data["glossary"] if t.get("align_to")}
    by_lower = {n.lower(): URIRef(iri) for n, iri in names.items()}

    def aligned(t):
        """Aligned IRI for a local term, matched case-insensitively (hasUrl == hasURL)."""
        if isinstance(t, URIRef) and t.startswith(EX):
            return by_lower.get(t[len(EX):].lower())
        return None

    out = Path("refactoring") / it.name
    out.mkdir(parents=True, exist_ok=True)

    for name in ("tbox", "abox"):
        src = Graph().parse(it / f"{name}.ttl", format="turtle")
        dst = Graph()
        for prefix, ns in src.namespaces():
            dst.bind(prefix, ns)
        for prefix, ns in prefixes.items():
            dst.bind(prefix, ns)
        for s, p, o in src:
            # aligned terms are defined by their external vocabulary: drop local declaration
            if name == "tbox" and aligned(s):
                continue
            s, p, o = (aligned(t) or t for t in (s, p, o))
            if name == "abox" and isinstance(o, Literal) and o.datatype is None and not o.language:
                # type plain literals with the aligned property's XSD range (e.g. fabio:hasURL -> xsd:anyURI)
                rng = tbox.value(p, RDFS.range)
                if rng is not None and str(rng).startswith(str(XSD)) and rng != XSD.string:
                    o = Literal(str(o), datatype=rng)
            dst.add((s, p, o))
        if name == "tbox":
            for iri in by_lower.values():
                vocab = vocabulary(str(iri), prefixes)
                triples = list(describe(vocab, iri)) if vocab is not None else []
                if not triples:
                    print(f"Warning: no triples for <{iri}> in its vocabulary.")
                for t in triples:
                    dst.add(t)
            # named superclass chains (e.g. datacite:Identifier -> literal:Literal), kept only up to the last class
            # the TBox already mentions (as class, domain, range...), without the ancestors' full definitions
            relevant = {t for t in dst.all_nodes() if isinstance(t, URIRef)}

            def supers(c):
                vocab = vocabulary(str(c), prefixes)
                return [s for s in vocab.objects(c, RDFS.subClassOf) if isinstance(s, URIRef)] if vocab is not None else []

            def climb(c, seen):
                """Add c's superclass links that lead to a relevant class; True if any did."""
                found = False
                for sup in supers(c):
                    if sup not in seen and (climb(sup, seen | {sup}) or sup in relevant):
                        dst.add((c, RDFS.subClassOf, sup))
                        found = True
                return found

            for iri in by_lower.values():
                climb(iri, {iri})
        register_prefixes(dst, prefixes)
        if name == "tbox":
            tbox = dst
        dst.serialize(destination=out / f"{name}.ttl", format="turtle")

    for cq in data.get("competency_questions") or []:
        if cq.get("query"):
            cq["refactored_query"] = refactor_query(cq["query"], names)
    dump_yaml(data, it / "requirements.yaml")
    print(f"Aligned {len(names)} term(s); wrote {out}")


if __name__ == "__main__":
    main(sys.argv[1])
