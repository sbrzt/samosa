# scripts/generate_abox.py

import json
import sys
from scripts.common import individual_id, load_yaml, resolve_iteration
from scripts.generate_tbox import local_name, owl_type
from jinja2 import Environment, FileSystemLoader


def generate_abox(data, output_dir):
    """Render the ABox as Turtle and write it to `abox.ttl`.

    Property values that name an ABox individual or a glossary term (by label or
    local name) become IRIs. Other values become literals, typed with the
    property's XSD `range` from the glossary (except `xsd:string`).

    Args:
        data: Parsed `requirements.yaml` content, with `abox` and `glossary`.
        output_dir: Directory where `abox.ttl` is written.
    """
    env = Environment(loader=FileSystemLoader("templates"))
    template = env.get_template("abox.ttl.jinja")

    individuals = {individual_id(item["individual"]) for item in data.get("abox") or [] if item.get("individual")}
    terms, datatypes = {}, {}
    for term in data.get("glossary") or []:
        if term.get("term") and term.get("type"):
            terms[term["term"].strip()] = terms[local_name(term)] = local_name(term)
            if owl_type(term) == "DatatypeProperty":
                rng = str((term.get("rules") or {}).get("range") or "").strip()
                rng = rng if ":" in rng else f"xsd:{rng}"  # bare names are XSD datatypes, as in tbox
                if rng.startswith("xsd:") and rng not in ("xsd:", "xsd:string"):
                    datatypes[local_name(term)] = rng

    def resolve(name):
        """Return the local name that `name` refers to, or None if it is a literal."""
        if individual_id(name) in individuals:
            return individual_id(name)
        return terms.get(name.strip())

    abox_data = []
    for item in data.get("abox") or []:
        if not item.get("individual"):
            continue
        properties = []
        for prop in item.get("properties") or []:
            if not prop.get("property") or not prop.get("value"):
                continue
            value = str(prop["value"])
            if resolve(value):
                rendered_value = f":{resolve(value)}"
            else:
                rendered_value = json.dumps(value)
                if prop["property"] in datatypes:
                    rendered_value += "^^" + datatypes[prop["property"]]
            properties.append({"property": prop["property"], "value": rendered_value})
        abox_data.append({
            "individual": terms.get(item["individual"].strip()) or individual_id(item["individual"]),
            "type": item.get("type"),
            "properties": properties,
        })

    abox_content = template.render(abox=abox_data)
    output_path = output_dir / "abox.ttl"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(abox_content)


def main(iteration: str):
    """Generate `abox.ttl` from the `requirements.yaml` of an iteration.

    Args:
        iteration: Iteration path or name, resolved with `resolve_iteration`.
    """
    it = resolve_iteration(iteration)
    generate_abox(load_yaml(it / "requirements.yaml"), it)


if __name__ == "__main__":
    main(sys.argv[1])
