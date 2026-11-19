# SAMOSA (Semi-Automated Modelling of Ontologies with SAMOD)

SMOSA is a tool to semi-automate [SAMOD](https://essepuntato.it/samod/) (Simplified Agile Methodology for Ontology Development).

It consists in a CLI interface that allows one to generate small, iterated model development iterations, driven by a series of documentation artifacts, such as a motivating scenario, a glossary, a series of competency questions (CQs), and so on.

## Iteration workflow

Each iteration lives under `iterations/<NN>-<name>/requirements.yaml` and declares:

- `scenario`: title, description, examples.
- `glossary`: terms with `type` (`Class`, `ObjectProperty`, `DataTypeProperty`, `NamedIndividual`), `definition`, and optional `rules`: `domain`/`range`/`subproperty_of` for properties, `subclass_of` for classes, `member_of` for individuals. Used to generate the TBox. A bare datatype-property `range` is an XSD datatype (`date` -> `xsd:date`), and ABox values of that property are typed with it.
- `abox`: example individuals instantiating the scenario as modelled according to the TBox, used to test CQs.
- `competency_questions`: `question`, `expected_result` (filled by hand), `query` (SPARQL on the first-version ABox) and `refactored_query` (filled by `align`, run on the refactored ABox) to verify the ontology answers it.
- glossary terms may carry `align_to: <prefix:term or full IRI>` (prefixes defined project-wide in `prefixes.yaml`): the existing vocabulary term that replaces the local one. `align_to: :Term` reuses a term of the current model (`project/tbox.ttl`), e.g. one defined by an earlier iteration. Terms without it become terms of the new vocabulary.

## CLI

| Command                         | Description                         |
| ------------------------------- | ----------------------------------- |
| `samosa new <name>`             | scaffold a new iteration            |
| `samosa tbox <iter>`            | glossary -> tbox.ttl                |
| `samosa draft-abox <iter>`      | (optional) draft the abox: block    |
| `samosa diagram <iter> [--graffoo]` | tbox.mmd and, once abox.ttl exists, abox.mmd (Mermaid, Graffoo colours); with `--graffoo` also tbox/abox.graphml (yEd) and tbox/abox.png (needs Graphviz) |
| `samosa abox <iter>`            | abox: block -> abox.ttl             |
| `samosa test <iter> [--reason]` | data and query tests on tbox.ttl + abox.ttl, see below |
| `samosa align <iter>`           | refactoring/\<iter\>/{tbox,abox}.ttl, refactored_query in requirements.yaml |
| `samosa diagram <iter> --refactored` | same, into refactoring/\<iter\>/ |
| `samosa test <iter> --refactored` | run refactored queries on refactored TBox+ABox |
| `samosa merge [<iter>] [--reason]` | merge an iteration into the current model `project/`, re-test all merged iterations, see below |
| `samosa rename <old> <new>`     | replace a term in every iteration (collapse duplicates), re-align, re-merge |
| `samosa check`                  | OWL 2 RL consistency check (owlrl, pure Python) on project/ |
| `samosa restore [<milestone>]`  | list the milestones, or restore the project to one |
| `samosa docs [--online]`        | HTML documentation of project/tbox.ttl with LODE 2.0, into project/docs/ |

`align` also fills the refactored TBox: for each aligned term it fetches the term's vocabulary (content negotiation on the prefix namespace, cached as `vocabularies/<prefix>.ttl`) and copies every triple describing the term (blank nodes followed). Every namespace used by the refactored TBox/ABox but missing from `prefixes.yaml` is appended to it. The prefix name comes from, in order: bindings in the loaded vocabularies/rdflib, the namespace's own RDF (fetched), prefix.cc, or the namespace IRI itself. If a namespace does not serve RDF, drop the vocabulary's Turtle file into `vocabularies/<prefix>.ttl` by hand.

## API

The same commands are also exposed over HTTP (same functions, see `COMMANDS` in `main.py`):

```
uv sync --extra api
uv run fastapi dev api.py   # from the repository root
```

Open http://127.0.0.1:8000/ for the web interface (`ui/index.html`): pick or create an iteration, fill in its `requirements.yaml` through a form, run the steps in order and see the output and diagrams (Mermaid, drawn in the browser with mermaid.js from a CDN; tick the Graffoo box to also write yEd files). http://127.0.0.1:8000/docs lists the raw API. Each command is `POST /<command>` with the CLI arguments as query parameters (e.g. `POST /test?iteration=01-rights&refactored=true`) and returns `{"ok": bool, "output": str}`. `GET /iterations/<iter>/requirements` returns `requirements.yaml` as JSON, `PUT` on the same path overwrites it with a JSON body, and all iteration files are served under `/iterations/`, `/refactoring/` and `/project/`.

Per iteration: 
1. `new`
2. fill in `requirements.yaml`
3. `tbox`
4. `diagram`
5. `draft-abox`, then `abox`, then `diagram` again to draw the ABox too
6. `test`
7. add `align_to` to glossary terms
8. `align`
9. `diagram --refactored`
10. `test --refactored`
11. `merge <iter>`: add the iteration to the current model (see below)
12. `check`
13. `docs`: once the ontology metadata in `ontology.yaml` is filled in

### Merging (SAMOD step 2)

The bag of test cases is every iteration whose `metadata.status` is `merged`. `merge <iter>`:

1. rebuilds the current model as the union of the refactored TBoxes of the bag plus `<iter>` (rebuilt, not accumulated, so edits and renames replace old definitions);
2. compares `<iter>`'s refactored TBox with each merged iteration's: the same term declared with clashing kinds (class vs property) or different `rdfs:domain`/`rdfs:range` fails the merge; different terms of the same kind sharing a local name, label or definition are printed as possible duplicates;
3. runs `test --refactored` on every test case, with the current model as TBox and the iteration's own refactored ABox.

Only if everything passes does it write `project/tbox.ttl` (current model) and `project/abox.ttl` (all ABoxes), and set `<iter>`'s status to `merged`. `merge` without an iteration rebuilds and re-tests the bag as is.

To collapse a duplicate, run `rename <old> <new>` (e.g. `rename :HumanBeing :Person`, or `rename :RightsStatement dcterms:RightsStatement`). It sets `align_to: <new>` on every glossary term that stands for `<old>`, re-runs `align` on those iterations (rewriting their refactored TBox, ABox and queries), then re-runs `merge`. `expected_result` cells such as `:humanBeing` keep matching the renamed term. To fix a conflict, edit the glossary of one iteration, or rename one of the terms.

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

### Status and milestones

`metadata.status` records how far an iteration got, and only goes up:

| Status | Set when |
| ------ | -------- |
| `draft` | `new` |
| `tested` | `test` passes: the test case is complete (SAMOD step 1) |
| `aligned` | `test --refactored` passes |
| `merged` | `merge <iter>` passes: the iteration is in the current model (SAMOD step 2) |

`merge <iter>` refuses an iteration that is still `draft`. Each time a status goes up, the project state (`iterations/`, `refactoring/`, `project/` without `docs/`, `prefixes.yaml`, `ontology.yaml`) is copied to `milestones/<timestamp>-<iter>-<status>/`.

After a serious failure, go back to a milestone: `restore` lists them, `restore <name>` (or a unique part of it, e.g. `restore 03-holder-tested`) replaces the current state with it. The current state is first saved as a `before-restore` milestone, so a restore can be undone. Run `docs` again afterwards. `milestones/` is in `.gitignore`; delete old milestones by hand.

### Documentation (SAMOD step 3)

`merge` writes the metadata in `ontology.yaml` (`iri`, `version`, `version_iri`, `title`, `description`, `creators`, `license`; empty fields are left out) as the `owl:Ontology` header of `project/tbox.ttl`. It also adds `rdfs:isDefinedBy <iri>` to every local term. Labels and comments come from the glossary.

`docs` turns `project/tbox.ttl` into a static HTML site in `project/docs/` (open `project/docs/index.html`) with [LODE 2.0](https://lode.opencitations.net/), replacing the folder's previous content:

- by default with the local [`oc-lode`](https://pypi.org/project/oc-lode/) package: `uv sync --extra docs`;
- with `--online`, by uploading `project/tbox.ttl` to the LODE 2.0 web service (`POST https://lode.opencitations.net/build`). Nothing needs to be installed, but the ontology leaves your machine.

## Tests

```
uv run pytest
```

The suite in `tests/` runs every command in a temporary project, with the network blocked (LODE, Ollama, prefix.cc and vocabulary downloads are faked). The test that builds real documentation runs only if `oc-lode` is installed (`uv sync --extra docs`), and the API tests only if FastAPI is (`uv sync --extra api`).

## Setup

```
uv sync
uv tool install -e .   # puts `samosa` on PATH (run it from the project folder)
uv sync --extra docs   # optional, for `docs` without --online (oc-lode)
# optional, for draft-abox: install Ollama (https://ollama.com), then
ollama pull qwen3:4b
```
