# scripts/generate_tbox.py

import sys
from scripts.common import individual_id, load_yaml, resolve_iteration
from jinja2 import Environment, FileSystemLoader


OWL_TYPES = {
    "class": "Class",
    "objectproperty": "ObjectProperty",
    "datatypeproperty": "DatatypeProperty",
    "namedindividual": "NamedIndividual",
}


def camel(text):
    """Join words, upper-casing only each word's first letter: "has URL" -> "HasURL"."""
    return "".join(w[:1].upper() + w[1:] for w in text.split())


def owl_type(term):
    return OWL_TYPES[term["type"].lower().replace(" ", "").replace("_", "")]


def local_name(term):
    """Local IRI name of a glossary term, as used in tbox.ttl."""
    term_id = camel(term["term"])
    kind = owl_type(term)
    if kind in ("ObjectProperty", "DatatypeProperty"):
        return term_id[0].lower() + term_id[1:]
    if kind == "NamedIndividual":
        return individual_id(term["term"])
    return term_id


def generate_tbox(data, output_dir):
    env = Environment(loader=FileSystemLoader("templates"))
    template = env.get_template("tbox.ttl.jinja")
    glossary_data = []
    for term in data["glossary"]:
        kind = owl_type(term)
        is_property = kind in ("ObjectProperty", "DatatypeProperty")
        rules = term.get("rules") or {}
        domain = rules.get("domain")
        range_ = rules.get("range")
        member_of = rules.get("member_of") if kind == "NamedIndividual" else None
        glossary_data.append({
            "term": local_name(term),
            "label": term["term"].lower() if is_property else term["term"],
            "definition": term["definition"],
            "type": kind,
            "domain": camel(domain) if domain else None,
            "range": camel(range_) if range_ else None,
            "member_of": camel(member_of) if member_of else None,
        })
    tbox_content = template.render(glossary=glossary_data)
    output_path = output_dir / "tbox.ttl"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(tbox_content)


def main(iteration):
    it = resolve_iteration(iteration)
    generate_tbox(load_yaml(it / "requirements.yaml"), it)


if __name__ == "__main__":
    main(sys.argv[1])