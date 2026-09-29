# scripts/draft_abox.py
#
# Drafts an `abox:` block into requirements.yaml by extracting entities and
# relations from the scenario/CQ text, constrained to the classes and
# properties already formalized in the glossary (TBox). Never invents a
# class or property outside the glossary. The user reviews/edits the
# resulting `abox:` block by hand before running `main.py abox`.

import re
import sys
from pathlib import Path

import spacy
import yaml
from rapidfuzz import fuzz
from scripts.generate_tbox import camel

MATCH_THRESHOLD = 75
_nlp = None


def get_nlp():
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("en_core_web_sm")
    return _nlp


def source_text(data):
    scenario = data.get("scenario") or {}
    parts = [scenario.get("description") or ""]
    parts.extend(scenario.get("examples") or [])
    parts.extend(cq.get("question") or "" for cq in data.get("competency_questions") or [])
    return "\n".join(p for p in parts if p)


def best_class_match(chunk_text, classes):
    best_term, best_score = None, 0
    for term in classes:
        score = fuzz.token_sort_ratio(chunk_text.lower(), term.lower())
        if score > best_score:
            best_term, best_score = term, score
    if best_score >= MATCH_THRESHOLD:
        return best_term
    return None


def to_slug(term):
    return re.sub(r"[^A-Za-z0-9]", "", camel(term))


def to_individual_name(term, index):
    slug = to_slug(term)
    return f"{slug[0].lower()}{slug[1:]}{index}"


def to_property_id(term):
    slug = to_slug(term)
    return f"{slug[0].lower()}{slug[1:]}"


def extract_entities(doc, classes):
    entities = []
    seen_spans = set()
    for chunk in doc.noun_chunks:
        text = chunk.text.strip()
        if not text or text.lower() in seen_spans:
            continue
        matched_class = best_class_match(text, classes)
        if not matched_class:
            continue
        seen_spans.add(text.lower())
        entities.append({"span": chunk, "class": matched_class, "label": text})
    return entities


def extract_relations(entities, properties):
    """Per sentence, pair the first entity of a property's domain class with
    the first entity of its range class. Loose on purpose: this is a draft
    the user reviews, not a final assertion."""
    relations = []
    by_sentence = {}
    for ent in entities:
        by_sentence.setdefault(ent["span"].sent, []).append(ent)

    for sent_entities in by_sentence.values():
        used_pairs = set()
        for prop in properties:
            subj = next((e for e in sent_entities if e["class"] == prop["domain"]), None)
            obj = next((e for e in sent_entities if e["class"] == prop["range"] and e is not subj), None)
            if subj and obj and (id(subj), prop["term"]) not in used_pairs:
                relations.append((subj, obj, prop["term"]))
                used_pairs.add((id(subj), prop["term"]))
    return relations


def draft_abox(data):
    glossary = data.get("glossary") or []
    classes = [t["term"] for t in glossary if t.get("type") == "Class"]
    properties = [
        {"term": t["term"], "domain": (t.get("rules") or {}).get("domain"), "range": (t.get("rules") or {}).get("range")}
        for t in glossary
        if t.get("type") == "ObjectProperty" and (t.get("rules") or {}).get("domain") and (t.get("rules") or {}).get("range")
    ]

    text = source_text(data)
    if not text or not classes:
        return []

    doc = get_nlp()(text)
    entities = extract_entities(doc, classes)

    individual_names = {}
    for i, ent in enumerate(entities, start=1):
        individual_names[id(ent)] = to_individual_name(ent["class"], i)

    relations = extract_relations(entities, properties)

    abox = []
    added = set()
    for ent in entities:
        name = individual_names[id(ent)]
        if name in added:
            continue
        added.add(name)
        abox.append({
            "individual": name,
            "type": to_slug(ent["class"]),
            "properties": [],
            "_source_text": ent["label"],
        })

    by_name = {item["individual"]: item for item in abox}
    for subj, obj, prop_term in relations:
        subj_name = individual_names[id(subj)]
        obj_name = individual_names[id(obj)]
        by_name[subj_name]["properties"].append({"property": to_property_id(prop_term), "value": obj_name})

    for item in abox:
        item.pop("_source_text", None)
        if not item["properties"]:
            item.pop("properties")

    return abox


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

    drafted = draft_abox(data)
    if not drafted:
        print("No entities matched against the glossary; nothing drafted.")
        return

    data["abox"] = drafted
    with open(req_file, "w", encoding="utf-8") as f:
        yaml.dump(data, f, sort_keys=False, allow_unicode=True, default_flow_style=False)

    print(f"Drafted {len(drafted)} individual(s) into {req_file}. Review and edit before running 'abox'.")


if __name__ == "__main__":
    main()
