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
    """Expand a `prefix:term` CURIE to a full IRI.

    Args:
        value: CURIE such as `fabio:hasURL`, `:Person` for a term of the
            current model, or a full IRI.
        prefixes: Mapping of prefix name to namespace IRI.

    Returns:
        The full IRI. Values that already contain `://` are returned unchanged.

    Raises:
        SystemExit: If the prefix is not in `prefixes`.
    """
    value = value.strip()
    if "://" in value:
        return value
    prefix, _, local = value.partition(":")
    if prefix == "":
        return EX + local
    if prefix not in prefixes:
        print(f"Error: unknown prefix '{prefix}' in align_to '{value}'. Add it to prefixes.yaml.")
        sys.exit(1)
    return prefixes[prefix] + local


_vocabularies = {}


def vocabulary(iri, prefixes):
    """Load the ontology that owns `iri`.

    Local (`:`) terms are owned by the current model, `project/tbox.ttl`.
    Otherwise the owning namespace is the longest one in `prefixes` that `iri`
    starts with. The graph is read from `vocabularies/<prefix>.ttl` if present,
    otherwise fetched from the namespace IRI and saved there. Results are memoized.

    Args:
        iri: Term IRI to look up.
        prefixes: Mapping of prefix name to namespace IRI.

    Returns:
        The vocabulary graph (empty if loading failed), or None if no known
        namespace matches `iri`.
    """
    if iri.startswith(EX):
        if "" not in _vocabularies:
            model = Path("project") / "tbox.ttl"
            _vocabularies[""] = Graph().parse(model, format="turtle") if model.exists() else Graph()
        return _vocabularies[""]
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
                g.parse(ns)
                path.parent.mkdir(exist_ok=True)
                g.serialize(destination=path, format="turtle")
        except Exception as e:
            print(f"Warning: cannot load vocabulary '{prefix}' ({ns}): {e}")
        _vocabularies[prefix] = g
    return _vocabularies[prefix]


def aliases(data, prefixes):
    """Map each aligned glossary term's local name to its target's local name.

    Used to match `:name` cells of `expected_result` after align or rename.

    Args:
        data: Parsed `requirements.yaml` content.
        prefixes: Mapping of prefix name to namespace IRI.

    Returns:
        Mapping of casefolded local name to casefolded target local name.
    """
    out = {}
    for t in data.get("glossary") or []:
        if t.get("term") and t.get("type") and t.get("align_to"):
            iri = expand(t["align_to"], prefixes)
            try:
                out[local_name(t).casefold()] = split_uri(iri)[1].casefold()
            except ValueError:
                pass
    return out


def load_prefixes():
    """Load the project-wide `prefixes.yaml`, or an empty mapping if absent."""
    return load_yaml(Path("prefixes.yaml")) if Path("prefixes.yaml").exists() else {}


def describe(g, term):
    """Yield all triples with `term` as subject, following blank nodes.

    Args:
        g: Graph to read from.
        term: Subject to describe.

    Yields:
        `(s, p, o)` triples about `term` and any blank nodes reachable from it.
    """
    todo, seen = [term], set()
    while todo:
        s = todo.pop()
        for p, o in g.predicate_objects(s):
            yield s, p, o
            if isinstance(o, BNode) and o not in seen:
                seen.add(o)
                todo.append(o)


def prefix_for(ns, known, taken):
    """Pick a prefix name for an unregistered namespace.

    Sources, in order: known bindings, the namespace's own RDF, prefix.cc,
    and finally the last path segment of the IRI.

    Args:
        ns: Namespace IRI.
        known: Mapping of namespace IRI to prefix name, from loaded graphs.
        taken: Prefix names already in use.

    Returns:
        A prefix name. Not guaranteed unique; the caller resolves clashes.
    """
    if ns in known:
        return known[ns]
    try:
        g = Graph().parse(ns)
        name = next((p for p, n in g.namespaces() if p and str(n) == ns and p not in taken), None)
        if name:
            return name
    except Exception:
        pass
    try:
        url = "http://prefix.cc/reverse?" + urlencode({"uri": ns, "format": "json"})
        return next(iter(json.load(urlopen(url, timeout=10))))
    except Exception:
        pass
    words = re.findall(r"[A-Za-z][\w-]*", re.sub(r"\.\w+[#/]?$", "", ns.split("://", 1)[-1]))
    return words[-1].lower() if words else "ns"


def register_prefixes(dst, prefixes):
    """Register every namespace used by `dst` and missing from prefixes.yaml.

    New prefixes are appended to prefixes.yaml and bound in `dst`.

    Args:
        dst: Graph whose IRIs are scanned.
        prefixes: Mapping of prefix name to namespace IRI. Updated in place.
    """
    known = {str(n): p for g in (*_vocabularies.values(), dst) for p, n in g.namespaces()
             if p and not re.fullmatch(r"ns\d+", p)}
    missing = set()
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
    """Rewrite local terms in a SPARQL query to their aligned IRIs.

    Args:
        query: SPARQL query using local `:name` or `<EX name>` terms.
        names: Mapping of local name to aligned IRI.

    Returns:
        The query with every aligned local term replaced by `<iri>`.
    """
    for name, iri in names.items():
        query = re.sub(re.escape(f"<{EX}{name}>"), f"<{iri}>", query, flags=re.I)
        query = re.sub(rf"(?<![\w:]):{re.escape(name)}\b", f"<{iri}>", query, flags=re.I)
    return query


def main(iteration: str):
    """Align an iteration's TBox, ABox and queries to external vocabularies.

    Writes `refactoring/<iteration>/{tbox,abox}.ttl` and adds a
    `refactored_query` to each competency question in requirements.yaml.

    Args:
        iteration: Iteration identifier, resolved by `resolve_iteration`.
    """
    it = resolve_iteration(iteration)
    data = load_yaml(it / "requirements.yaml")
    _vocabularies.pop("", None)  # the current model may have changed since the last call

    prefixes = load_prefixes()
    names = {local_name(t): expand(t["align_to"], prefixes) for t in data["glossary"] if t.get("align_to")}
    by_lower = {n.lower(): URIRef(iri) for n, iri in names.items()}

    def aligned(t):
        """Return the aligned IRI for a local term.

        Matching is case-insensitive (hasUrl == hasURL).

        Args:
            t: Any RDF term.

        Returns:
            The aligned URIRef, or None if `t` is not an aligned local term.
        """
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
            if name == "tbox" and aligned(s):
                continue
            s, p, o = (aligned(t) or t for t in (s, p, o))
            if name == "abox" and isinstance(o, Literal) and o.datatype is None and not o.language:
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
            relevant = {t for t in dst.all_nodes() if isinstance(t, URIRef)}

            def supers(c):
                """Return the named direct superclasses of `c` in its vocabulary.

                Args:
                    c: Class IRI.

                Returns:
                    List of URIRef superclasses; empty if no vocabulary is known.
                """
                vocab = vocabulary(str(c), prefixes)
                return [s for s in vocab.objects(c, RDFS.subClassOf) if isinstance(s, URIRef)] if vocab is not None else []

            def climb(c, seen):
                """Add the superclass links of `c` that lead to a relevant class.

                Args:
                    c: Class IRI to climb from.
                    seen: Classes already on the current path, to stop cycles.

                Returns:
                    True if at least one link was added.
                """
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
