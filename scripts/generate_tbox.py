# scripts/generate_tbox.py

import sys
from pathlib import Path
from scripts.common import EX, individual_id, load_yaml, resolve_iteration
from jinja2 import Environment, FileSystemLoader

BASE_PREFIXES = {
    "": EX,
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
}


OWL_TYPES = {
    "class": "Class",
    "objectproperty": "ObjectProperty",
    "datatypeproperty": "DatatypeProperty",
    "namedindividual": "NamedIndividual",
}


def camel(text):
    """Join words, upper-casing only each word's first letter.

    Args:
        text: Words separated by whitespace, e.g. `"has URL"`.

    Returns:
        The words joined in UpperCamelCase, with the rest of each word kept
        as is (`"HasURL"`).
    """
    return "".join(w[:1].upper() + w[1:] for w in text.split())


def owl_type(term):
    """Normalize the `type` of a glossary term to an OWL entity type.

    Args:
        term: Glossary entry with a `type`, e.g. `"Object Property"` or `"datatype_property"`.

    Returns:
        One of `"Class"`, `"ObjectProperty"`, `"DatatypeProperty"` or `"NamedIndividual"`.

    Raises:
        KeyError: If the type is not one of these.
    """
    return OWL_TYPES[term["type"].lower().replace(" ", "").replace("_", "")]


def local_name(term):
    """Build the local IRI name of a glossary term, as used in `tbox.ttl`.

    Args:
        term: Glossary entry with `term` and `type`.

    Returns:
        UpperCamelCase for classes, lowerCamelCase for properties, and the
        `individual_id` form for named individuals.
    """
    term_id = camel(term["term"])
    kind = owl_type(term)
    if kind in ("ObjectProperty", "DatatypeProperty"):
        return term_id[0].lower() + term_id[1:]
    if kind == "NamedIndividual":
        return individual_id(term["term"])
    return term_id


def ref(value, prefixes, kind="Class"):
    """Render a term named in a glossary rule as a Turtle reference.

    Args:
        value: Full IRI, CURIE (`xsd:date`, `foaf:Person`) or glossary term name.
        prefixes: Mapping of prefix name to namespace IRI declared in `tbox.ttl`.
        kind: OWL type of the referred term. A bare name is a local class
            (`:UpperCamel`), a local property (`:lowerCamel`) or, for
            `"Datatype"`, an XSD datatype (`string` -> `xsd:string`).

    Returns:
        The Turtle reference, or None if `value` is empty.

    Raises:
        SystemExit: If a CURIE uses a prefix missing from `prefixes`.
    """
    value = (value or "").strip()
    if not value:
        return None
    if "://" in value:
        return f"<{value}>"
    if ":" in value:
        if value.partition(":")[0] not in prefixes:
            print(f"Error: unknown prefix in '{value}'. Add it to prefixes.yaml.")
            sys.exit(1)
        return value
    if kind == "Datatype":
        return f"xsd:{value}"
    return ":" + local_name({"term": value, "type": kind})


def generate_tbox(data, output_dir):
    """Render the glossary as Turtle and write it to `tbox.ttl`.

    Args:
        data: Parsed `requirements.yaml` content, with a `glossary` list. Each
            entry needs `term`, `type` and `definition`, and may have `rules`
            with `domain`, `range`, `subclass_of`, `subproperty_of` and `member_of`.
        output_dir: Directory where `tbox.ttl` is written.
    """
    env = Environment(loader=FileSystemLoader("templates"))
    template = env.get_template("tbox.ttl.jinja")
    project = Path("prefixes.yaml")
    prefixes = {**(load_yaml(project) if project.exists() else {}), **BASE_PREFIXES}
    glossary_data = []
    for term in data["glossary"]:
        if not term.get("term") or not term.get("type"):
            continue
        kind = owl_type(term)
        is_property = kind in ("ObjectProperty", "DatatypeProperty")
        rules = term.get("rules") or {}
        range_kind = "Datatype" if kind == "DatatypeProperty" else "Class"
        glossary_data.append({
            "term": local_name(term),
            "label": term["term"].lower() if is_property else term["term"],
            "definition": str(term.get("definition") or "").strip(),
            "type": kind,
            "domain": ref(rules.get("domain"), prefixes) if is_property else None,
            "range": ref(rules.get("range"), prefixes, range_kind) if is_property else None,
            "subclass_of": ref(rules.get("subclass_of"), prefixes) if kind == "Class" else None,
            "subproperty_of": ref(rules.get("subproperty_of"), prefixes, kind) if is_property else None,
            "member_of": ref(rules.get("member_of"), prefixes) if kind == "NamedIndividual" else None,
        })
    rule_keys = ("domain", "range", "subclass_of", "subproperty_of", "member_of")
    used = {item[k].partition(":")[0] for item in glossary_data for k in rule_keys if item[k] and item[k][0] != "<"}
    declared = {p: prefixes[p] for p in {**BASE_PREFIXES, **prefixes} if p in BASE_PREFIXES or p in used}
    tbox_content = template.render(glossary=glossary_data, prefixes=declared)
    output_path = output_dir / "tbox.ttl"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(tbox_content)


def main(iteration: str):
    """Generate `tbox.ttl` from the `requirements.yaml` of an iteration.

    Args:
        iteration: Iteration path or name, resolved with `resolve_iteration`.
    """
    it = resolve_iteration(iteration)
    generate_tbox(load_yaml(it / "requirements.yaml"), it)


if __name__ == "__main__":
    main(sys.argv[1])