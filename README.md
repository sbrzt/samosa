# SAMOSA (Semi-Automated Modelling of Ontologies with SAMOD)

SMOSA is a tool to semi-automate [SAMOD](https://essepuntato.it/samod/) (Simplified Agile Methodology for Ontology Development).

It consists in a CLI interface that allows one to generate small, iterated model development iterations, driven by a series of documentation artifacts, such as a motivating scenario, a glossary, a series of competency questions (CQs), and so on.

## Iteration workflow

Each iteration lives under `iterations/<NN>-<name>/requirements.yaml` and declares:

- `scenario`: title, description, examples.
- `glossary`: terms with `type` (`Class`, `ObjectProperty`, `DataTypeProperty`, `NamedIndividual`), `definition`, and for properties a `rules.domain`/`rules.range`, used to generate the TBox.
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
| `samosa test <iter>`            | run the CQ queries on tbox.ttl + abox.ttl |
| `samosa align <iter>`           | refactoring/\<iter\>/{tbox,abox}.ttl, refactored_query in requirements.yaml |
| `samosa diagram <iter> --refactored` |  same, into refactoring/\<iter\>/ |
| `samosa test <iter> --refactored` | run refactored queries on refactored TBox+ABox |
| `samosa merge`                  | all iterations, see below           |
| `samosa check`                  | OWL 2 RL consistency check (owlrl, pure Python) on project/ |

`align` also fills the refactored TBox: for each aligned term it fetches the term's vocabulary (content negotiation on the prefix namespace, cached as `vocabularies/<prefix>.ttl`) and copies every triple describing the term (blank nodes followed). Every namespace used by the refactored TBox/ABox but missing from `prefixes.yaml` is appended to it. The prefix name comes from, in order: bindings in the loaded vocabularies/rdflib, the namespace's own RDF (fetched), prefix.cc, or the namespace IRI itself. If a namespace does not serve RDF, drop the vocabulary's Turtle file into `vocabularies/<prefix>.ttl` by hand.

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
11. once refactorinf is complete, `merge` merges all refactored ABoxes, runs every refactored query of every iteration on the result, and only if all pass merges the refactored TBoxes, generating `project/abox.ttl` and `project/tbox.ttl`
12. `check`

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
