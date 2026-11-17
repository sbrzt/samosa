# SAMOSA (Semi-Automated Modelling of Ontologies with SAMOD)

SMOSA is a tool to semi-automate [SAMOD](https://essepuntato.it/samod/) (Simplified Agile Methodology for Ontology Development).

It consists in a CLI interface that allows one to generate small, iterated model development iterations, driven by a series of documentation artifacts, such as a motivating scenario, a glossary, a series of competency questions (CQs), and so on.

## Iteration workflow

Each iteration lives under `iterations/<NN>-<name>/requirements.yaml` and declares:

- `scenario`: title, description, examples.
- `glossary`: terms with `type` (`Class`, `ObjectProperty`, `DataTypeProperty`, `NamedIndividual`), `definition`, and optional `rules`: `domain`/`range`/`subproperty_of` for properties, `subclass_of` for classes, `member_of` for individuals. Used to generate the TBox. A bare datatype-property `range` is an XSD datatype (`date` -> `xsd:date`), and ABox values of that property are typed with it.
- `abox`: example individuals instantiating the scenario as modelled according to the TBox, used to test CQs.
- `competency_questions`: `question`, `expected_result` (filled by hand), `query` (SPARQL on the first-version ABox) and `refactored_query` (filled by `align`, run on the refactored ABox) to verify the ontology answers it.
- glossary terms may carry `align_to: <prefix:term or full IRI>` (prefixes defined project-wide in `prefixes.yaml`): the existing vocabulary term that replaces the local one. Terms without it become terms of the new vocabulary.

## CLI

| Command                         | Description                         |
| ------------------------------- | ----------------------------------- |
| `samosa new <name>`             | scaffold a new iteration            |
| `samosa tbox <iter>`            | glossary -> tbox.ttl                |
| `samosa draft-abox <iter>`      | (optional) draft the abox: block    |
| `samosa diagram <iter>`         | tbox.graphml (yEd, Graffoo style) + tbox.png |
| `samosa abox <iter>`            | abox: block -> abox.ttl             |
| `samosa test <iter> [--reason]` | data and query tests on tbox.ttl + abox.ttl, see below |
| `samosa align <iter>`           | refactoring/\<iter\>/{tbox,abox}.ttl, refactored_query in requirements.yaml |
| `samosa diagram <iter> --refactored` |  same, into refactoring/\<iter\>/ |
| `samosa test <iter> --refactored` | run refactored queries on refactored TBox+ABox |
| `samosa merge [--reason]`       | all iterations, see below           |
| `samosa check`                  | OWL 2 RL consistency check (owlrl, pure Python) on project/ |

`align` also fills the refactored TBox: for each aligned term it fetches the term's vocabulary (content negotiation on the prefix namespace, cached as `vocabularies/<prefix>.ttl`) and copies every triple describing the term (blank nodes followed). Every namespace used by the refactored TBox/ABox but missing from `prefixes.yaml` is appended to it. The prefix name comes from, in order: bindings in the loaded vocabularies/rdflib, the namespace's own RDF (fetched), prefix.cc, or the namespace IRI itself. If a namespace does not serve RDF, drop the vocabulary's Turtle file into `vocabularies/<prefix>.ttl` by hand.

## API

The same commands are also exposed over HTTP (same functions, see `COMMANDS` in `main.py`):

```
uv sync --extra api
uv run fastapi dev api.py   # from the repository root
```

Open http://127.0.0.1:8000/ for the web interface (`ui/index.html`): pick or create an iteration, fill in its `requirements.yaml` through a form, run the steps in order and see the output and diagrams. http://127.0.0.1:8000/docs lists the raw API. Each command is `POST /<command>` with the CLI arguments as query parameters (e.g. `POST /test?iteration=01-rights&refactored=true`) and returns `{"ok": bool, "output": str}`. `GET /iterations/<iter>/requirements` returns `requirements.yaml` as JSON, `PUT` on the same path overwrites it with a JSON body, and all iteration files are served under `/iterations/`, `/refactoring/` and `/project/`.

Per iteration: 
1. `new`
2. fill in `requirements.yaml`
3. `tbox`
4. `diagram`
5. `draft-abox`, then `abox`
6. `test`
7. add `align_to` to glossary terms
8. `align`
9. `diagram --refactored`
10. `test --refactored`
11. once refactoring is complete, `merge` merges all refactored TBoxes and ABoxes, runs every refactored query of every iteration on their union, and only if all pass writes `project/tbox.ttl` and `project/abox.ttl`
12. `check`

### Tests

`test` fails if:

- the ABox uses a property or class, or the TBox refers to a local (`:`) term, that the TBox does not describe (usually a typo);
- an object property has a literal value (usually a misspelled individual name) or a datatype property has an IRI value;
- TBox+ABox is inconsistent under OWL 2 RL (owlrl), e.g. `"four"^^xsd:integer`;
- a CQ query fails (see below).

It also warns, without failing, about glossary terms that no CQ query or no ABox triple uses. Queries run on the asserted triples; with `--reason` they run on the OWL 2 RL closure, so CQs that rely on inference (e.g. `?x a :Animal` for an individual typed `:Mammal`) pass.

### Expected results

`test` (and `merge`) compare each query's results with the competency question's `expected_result`:

```yaml
expected_result:
- :qualifiedRelation1, :dataset1
- [:x, "value, with comma"]
```

- `:name` matches any IRI whose local name is `name`, ignoring case, so it still matches after `align` (e.g. `:isCitedBy` matches `cito:isCitedBy`).
- Anything else (literals, full IRIs) must match exactly.
- Row order is ignored; missing and unexpected rows both fail, and are printed.
- Without `expected_result`, a query passes if it returns at least one row.

### Drafting the ABox

`draft-abox` asks a local LLM (via [Ollama](https://ollama.com)) to read the scenario description, examples and glossary and propose individuals and relations. The response is constrained by a JSON schema to the classes and properties already in the glossary, so nothing outside it is invented. The result is written into the iteration's `requirements.yaml` for the user to edit, correct, or extend before running `abox`.

The model defaults to `qwen3:4b`; override with `DRAFT_MODEL`, and the server
with `OLLAMA_URL` (default `http://localhost:11434`).

## Setup

```
uv sync
uv tool install -e .   # puts `samosa` on PATH (run it from the project folder)
# optional, for draft-abox: install Ollama (https://ollama.com), then
ollama pull qwen3:4b
```
