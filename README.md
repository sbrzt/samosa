# samsad

Tooling to semi-automate [SAMOD](https://essepuntato.it/samod/) (Simplified
Agile Methodology for Ontology Development): small, testable iterations that
each add a fragment of ontology, driven by a motivating scenario and its
competency questions (CQs).

## Iteration workflow

Each iteration lives under `iterations/<NN>-<name>/requirements.yaml` and
declares:

- `scenario`: title, description, examples — the motivating scenario.
- `glossary`: terms with `type` (`Class`, `ObjectProperty`,
  `DataTypeProperty`, `NamedIndividual`), `definition`, and for properties a
  `rules.domain`/`rules.range`.
- `abox`: example individuals instantiating the glossary, used to test CQs
  concretely.
- `competency_questions`: `question`, `expected_result` (filled by hand), `query` (SPARQL on the
  first-version ABox) and `refactored_query` (filled by `align`, run on the
  refactored ABox) to
  verify the ontology answers it.

- glossary terms may carry `align_to: <prefix:term or full IRI>` (prefixes
  defined project-wide in `prefixes.yaml`): the existing vocabulary term
  that replaces the local one. Terms without it become terms of the new
  vocabulary.

## CLI

```
uv run main.py new <name>                 # scaffold a new iteration
uv run main.py tbox <iter>                # glossary -> tbox.ttl
uv run main.py draft-abox <iter>          # (optional) draft the abox: block
uv run main.py abox <iter>                # abox: block -> abox.ttl
uv run main.py test <iter>                # run the CQ queries on tbox.ttl + abox.ttl
uv run main.py align <iter>               # -> refactoring/<iter>/{tbox,abox}.ttl, refactored_query in requirements.yaml
uv run main.py test <iter> --refactored   # run refactored queries on refactored TBox+ABox
uv run main.py merge                      # all iterations, see below
uv run main.py check                      # OWL DL consistency check (HermiT, needs Java) on project/
```

`align` also fills the refactored TBox: for each aligned term it fetches the
term's vocabulary (content negotiation on the prefix namespace, cached as
`vocabularies/<prefix>.ttl`) and copies every triple describing the term
(blank nodes followed). Every namespace used by the refactored TBox/ABox but
missing from `prefixes.yaml` is appended to it. The prefix name comes from, in
order: bindings in the loaded vocabularies/rdflib, the namespace's own RDF
(fetched), prefix.cc, or the namespace IRI itself. If a namespace does not serve RDF, drop the
vocabulary's Turtle file into `vocabularies/<prefix>.ttl` by hand.

Per iteration: `new` → fill in `requirements.yaml` → `tbox` → `abox` →
`test` → add `align_to` to glossary terms → `align` → `test --refactored`.

Once every iteration is refactored, `merge` merges all refactored ABoxes,
runs every refactored query of every iteration on the result, and only if
all pass merges the refactored TBoxes. Output: `project/abox.ttl`,
`project/tbox.ttl`. Then `check`.

### Drafting the ABox

`draft-abox` extracts candidate individuals and relations straight from the
scenario description and CQ text: noun chunks are fuzzy-matched (rapidfuzz)
against glossary class labels, and pairs of matched entities in the same
sentence are linked by whichever `ObjectProperty` has a matching
`domain`/`range` in the glossary. It only ever proposes classes and
properties already formalized in the glossary — nothing is invented. The
result is written into the iteration's `requirements.yaml` for the user to
edit, correct, or extend before running `abox`.

## Setup

```
uv sync
uv run python -m spacy download en_core_web_sm
```
