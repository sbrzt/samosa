# scripts/draft_abox.py

import json
import os
import re
import sys
import urllib.error
import urllib.request

from scripts.common import dump_yaml, load_yaml, resolve_iteration
from scripts.generate_tbox import camel

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DRAFT_MODEL = os.environ.get("DRAFT_MODEL", "qwen3:4b")

PROMPT = """You draft the ABox (individuals) of an OWL ontology from a scenario.

Use only the classes and properties listed below. Create one individual for
each concrete entity mentioned in the scenario examples, give it a class, and
link individuals with properties. Entities that fit none of the classes
(e.g. things only used as subject or object of a relation) still become
individuals, with type Thing. A property value is either the name of
another individual you created or a plain literal string.
Individual names are lowerCamelCase and descriptive, e.g. dataset1, article1.

Classes:
{classes}

Properties:
{properties}

Scenario:
{scenario}

Examples:
{examples}
"""


def to_slug(term):
    """Turn a glossary term into a class identifier.

    Args:
        term: Term label, e.g. `"research dataset"`.

    Returns:
        The term in UpperCamelCase with non-alphanumeric characters removed
        (`"ResearchDataset"`).
    """
    return re.sub(r"[^A-Za-z0-9]", "", camel(term))


def to_property_id(term):
    """Turn a glossary term into a property or individual identifier.

    Args:
        term: Term label, e.g. `"has author"`.

    Returns:
        The term in lowerCamelCase with non-alphanumeric characters removed
        (`"hasAuthor"`).
    """
    slug = to_slug(term)
    return slug[:1].lower() + slug[1:]


def describe(term):
    """Format a glossary entry as one prompt line.

    Args:
        term: Glossary entry with `term`, an optional `definition`, and optional
            `rules` holding `domain` and `range`.

    Returns:
        A line like `"- has author: Links a work to its author (domain: Work, range: Person)"`.
    """
    rules = term.get("rules") or {}
    extra = ", ".join(f"{k}: {rules[k]}" for k in ("domain", "range") if rules.get(k))
    return f"- {term['term']}: {term.get('definition') or ''}" + (f" ({extra})" if extra else "")


def response_schema(class_ids, property_ids):
    """Build the JSON schema that constrains the model output.

    Args:
        class_ids: Allowed values for each individual's `type`.
        property_ids: Allowed values for each property assertion's `property`.

    Returns:
        A JSON schema for an object with an `abox` list of individuals.
    """
    return {
        "type": "object",
        "properties": {
            "abox": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "individual": {"type": "string"},
                        "type": {"type": "string", "enum": class_ids},
                        "properties": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "property": {"type": "string", "enum": property_ids},
                                    "value": {"type": "string"},
                                },
                                "required": ["property", "value"],
                            },
                        },
                    },
                    "required": ["individual", "type", "properties"],
                },
            }
        },
        "required": ["abox"],
    }


def ask_ollama(prompt, schema):
    """Send a prompt to the Ollama chat API and parse the structured reply.

    Uses `DRAFT_MODEL` at `OLLAMA_URL`, with temperature 0 and thinking off.

    Args:
        prompt: User message to send.
        schema: JSON schema passed as the `format` of the response.

    Returns:
        The model reply parsed from JSON.

    Raises:
        SystemExit: If Ollama cannot be reached.
    """
    body = json.dumps({
        "model": DRAFT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "format": schema,
        "stream": False,
        "think": False,
        "options": {"temperature": 0},
    }).encode()
    req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=1800) as resp:
            return json.loads(json.loads(resp.read())["message"]["content"])
    except urllib.error.URLError as e:
        sys.exit(f"Error: cannot reach Ollama at {OLLAMA_URL} ({e}). Is it running, and is '{DRAFT_MODEL}' pulled?")


def draft_abox(data):
    """Draft ABox individuals from the glossary and scenario with a local LLM.

    Args:
        data: Parsed `requirements.yaml` content, with `glossary` and `scenario`.

    Returns:
        A list of `{"individual", "type", "properties"}` dicts, ready to store
        under `abox`. `type` is left out for `Thing`, and `properties` is left out
        when empty. Returns an empty list if there are no classes or no scenario text.
    """
    glossary = data.get("glossary") or []
    classes = [t for t in glossary if t.get("type") == "Class"]
    properties = [t for t in glossary if t.get("type") in ("ObjectProperty", "DatatypeProperty")]
    scenario = data.get("scenario") or {}
    if not classes or not (scenario.get("description") or scenario.get("examples")):
        return []

    prompt = PROMPT.format(
        classes="\n".join(describe(t) for t in classes),
        properties="\n".join(describe(t) for t in properties) or "(none)",
        scenario=scenario.get("description") or "",
        examples="\n".join(f"- {e}" for e in scenario.get("examples") or []),
    )
    class_ids = [to_slug(t["term"]) for t in classes] + ["Thing"]
    property_ids = [to_property_id(t["term"]) for t in properties] or [""]
    result = ask_ollama(prompt, response_schema(class_ids, property_ids))

    abox = []
    for item in result.get("abox") or []:
        name = to_property_id(item.get("individual") or "")
        if not name:
            continue
        entry = {"individual": name}
        if item.get("type") != "Thing":
            entry["type"] = item.get("type")
        props = [p for p in item.get("properties") or [] if p.get("property") in property_ids and p.get("value")]
        if props:
            entry["properties"] = props
        abox.append(entry)
    return abox


def main(iteration: str):
    """Draft the ABox of an iteration and write it into its `requirements.yaml`.

    Replaces any existing `abox` section.

    Args:
        iteration: Iteration path or name, resolved with `resolve_iteration`.
    """
    req_file = resolve_iteration(iteration) / "requirements.yaml"
    data = load_yaml(req_file)

    drafted = draft_abox(data)
    if not drafted:
        print("Nothing drafted (no classes, no scenario text, or empty model output).")
        return

    data["abox"] = drafted
    dump_yaml(data, req_file)

    print(f"Drafted {len(drafted)} individual(s) into {req_file}. Review and edit before running 'abox'.")


if __name__ == "__main__":
    main(sys.argv[1])
