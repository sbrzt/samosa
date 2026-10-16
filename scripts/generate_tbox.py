# scripts/generate_tbox.py

import sys
import yaml
from scripts.common import individual_id
from pathlib import Path
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


def local_name(term):
    """Local IRI name of a glossary term, as used in tbox.ttl."""
    term_id = camel(term["term"])
    owl_type = OWL_TYPES[term["type"].lower().replace(" ", "").replace("_", "")]
    if owl_type in ("ObjectProperty", "DatatypeProperty"):
        return term_id[0].lower() + term_id[1:]
    if owl_type == "NamedIndividual":
        return individual_id(term["term"])
    return term_id


def generate_tbox(data, output_dir):
    env = Environment(loader=FileSystemLoader("templates"))
    template = env.get_template("tbox.ttl.jinja")
    glossary_data = []
    for term in data["glossary"]:
        owl_type = OWL_TYPES[term["type"].lower().replace(" ", "").replace("_", "")]
        is_property = owl_type in ("ObjectProperty", "DatatypeProperty")
        rules = term.get("rules") or {}
        domain = rules.get("domain")
        range_ = rules.get("range")
        member_of = rules.get("member_of") if owl_type == "NamedIndividual" else None
        glossary_data.append({
            "term": local_name(term),
            "label": term["term"].lower() if is_property else term["term"],
            "definition": term["definition"],
            "type": owl_type,
            "domain": camel(domain) if domain else None,
            "range": camel(range_) if range_ else None,
            "member_of": camel(member_of) if member_of else None,
        })
    template_data = {}
    template_data["glossary"] = glossary_data
    tbox_content = template.render(template_data)
    output_path = output_dir / "tbox.ttl"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(tbox_content)


def main():
    iter_path = sys.argv[1]
    if Path(iter_path).exists():
        iter_path = Path(iter_path)
    elif (Path("iterations") / iter_path).exists():
        iter_path = Path("iterations") / iter_path
    else:
        sys.exit(1)
    req_file = iter_path / "requirements.yaml"
    if not req_file.exists():
        print(f"Error: File {req_file} not found.")
        sys.exit(1)
    with open(req_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    generate_tbox(data, iter_path)


if __name__ == "__main__":
    main()