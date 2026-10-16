# scripts/generate_abox.py

import sys
import yaml
from scripts.common import individual_id
from scripts.generate_tbox import local_name
from pathlib import Path
from jinja2 import Environment, FileSystemLoader


def generate_abox(data, output_dir):
    env = Environment(loader=FileSystemLoader("templates"))
    template = env.get_template("abox.ttl.jinja")

    individuals = {individual_id(item["individual"]) for item in data.get("abox") or [] if item.get("individual")}
    # Glossary terms are resolvable too (by label or local name), so an individual
    # can be, or point to, a TBox entity via punning.
    terms = {}
    for term in data.get("glossary") or []:
        if term.get("term") and term.get("type"):
            terms[term["term"].strip()] = terms[local_name(term)] = local_name(term)

    def resolve(name):
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
            rendered_value = f":{resolve(value)}" if resolve(value) else f'"{value}"'
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
    generate_abox(data, iter_path)


if __name__ == "__main__":
    main()
