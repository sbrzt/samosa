# SAMOSA (Semi-Automated Modelling of Ontologies with SAMOD)

SMOSA is a tool to semi-automate [SAMOD](https://essepuntato.it/samod/) (Simplified Agile Methodology for Ontology Development).

It consists in a CLI interface that allows one to generate small, testable iterations that each add a fragment of an ontology (_modelet_), driven by a motivating scenario, a glossary, and a series of competency questions (CQs).

## Iteration workflow

Each iteration lives under `iterations/<NN>-<name>/requirements.yaml` and declares:

- `scenario`: title, description, examples — the motivating scenario.
- `glossary`: terms with `type` (`Class`, `ObjectProperty`, `DataTypeProperty`, `NamedIndividual`), `definition`, and for properties a `rules.domain`/`rules.range`.
- `abox`: example individuals instantiating the glossary, used to test CQs concretely.
- `competency_questions`: `question`, `expected_result` (filled by hand), `query` (SPARQL on the first-version ABox) and `refactored_query` (filled by `align`, run on the refactored ABox) to verify the ontology answers it.

- glossary terms may carry `align_to: <prefix:term or full IRI>` (prefixes defined project-wide in `prefixes.yaml`): the existing vocabulary term that replaces the local one. Terms without it become terms of the new vocabulary.

## CLI

```
uv run main.py new <name>                 # scaffold a new iteration
uv run main.py tbox <iter>                # glossary -> tbox.ttl
uv run main.py draft-abox <iter>          # (optional) draft the abox: block
uv run main.py diagram <iter>             # tbox.graphml (yEd, Graffoo style) + tbox.png
uv run main.py abox <iter>                # abox: block -> abox.ttl
uv run main.py test <iter>                # run the CQ queries on tbox.ttl + abox.ttl
uv run main.py align <iter>               # -> refactoring/<iter>/{tbox,abox}.ttl, refactored_query in requirements.yaml
uv run main.py diagram <iter> --refactored # same, into refactoring/<iter>/
uv run main.py test <iter> --refactored   # run refactored queries on refactored TBox+ABox
uv run main.py merge                      # all iterations, see below
uv run main.py check                      # OWL 2 RL consistency check (owlrl, pure Python) on project/
```

`align` also fills the refactored TBox: for each aligned term it fetches the term's vocabulary (content negotiation on the prefix namespace, cached as `vocabularies/<prefix>.ttl`) and copies every triple describing the term (blank nodes followed). Every namespace used by the refactored TBox/ABox but missing from `prefixes.yaml` is appended to it. The prefix name comes from, in order: bindings in the loaded vocabularies/rdflib, the namespace's own RDF (fetched), prefix.cc, or the namespace IRI itself. If a namespace does not serve RDF, drop the vocabulary's Turtle file into `vocabularies/<prefix>.ttl` by hand.

Per iteration: `new` → fill in `requirements.yaml` → `tbox` → `diagram` → `abox` → `test` → add `align_to` to glossary terms → `align` → `diagram --refactored` → `test --refactored`.

Once every iteration is refactored, `merge` merges all refactored ABoxes, runs every refactored query of every iteration on the result, and only if all pass merges the refactored TBoxes. Output: `project/abox.ttl`, `project/tbox.ttl`. Then `check`.

### Drafting the ABox

`draft-abox` asks a local LLM (via [Ollama](https://ollama.com)) to read the scenario description, examples and glossary and propose individuals and relations. The response is constrained by a JSON schema to the classes and properties already in the glossary, so nothing outside it is invented. The result is written into the iteration's `requirements.yaml` for the user to edit, correct, or extend before running `abox`.

The model defaults to `qwen3:4b`; override with `DRAFT_MODEL`, and the server
with `OLLAMA_URL` (default `http://localhost:11434`).

## Setup

```
uv sync
# optional, for draft-abox: install Ollama (https://ollama.com), then
ollama pull qwen3:4b
```
