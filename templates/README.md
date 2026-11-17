# templates

Templates used by the SAMOSA CLI. The scripts load them with paths relative to the current directory, so run `samosa` from the repository root.

| File | Used by | Output |
| ---- | ------- | ------ |
| `iteration/` | `samosa new <name>` | `iterations/<NN>-<name>/` |
| `tbox.ttl.jinja` | `samosa tbox <iter>` | `iterations/<iter>/tbox.ttl` |
| `abox.ttl.jinja` | `samosa abox <iter>` | `iterations/<iter>/abox.ttl` |

## `iteration/`

`samosa new` copies this whole directory into `iterations/<NN>-<name>/`. It then sets `metadata.id` to `NN` and `scenario.title` to the name in title case. Any file added here appears in every new iteration.

`requirements.yaml` is the skeleton that you fill in for each iteration:

- `metadata`: `id` (set by `new`) and `status`.
- `scenario`: `title`, `description` and `examples`.
- `glossary`: one entry per term, with:
  - `term`: label of the term.
  - `definition`: becomes the `rdfs:comment`.
  - `type`: `Class`, `Object Property`, `Datatype Property` or `Named Individual`. Case, spaces and underscores are ignored.
  - `align_to`: optional existing vocabulary term (`prefix:term` or full IRI) that `align` uses to replace the local term.
  - `rules`: optional `domain`, `range` and `subproperty_of` for properties, `subclass_of` for classes, and `member_of` for named individuals (the class they belong to). Each value is a glossary term name, a CURIE with a prefix from `prefixes.yaml` (e.g. `foaf:Person`) or a full IRI. A bare `range` of a datatype property is an XSD datatype (`date` becomes `xsd:date`).
- `abox`: example individuals, each with `individual`, `type` (left empty for `owl:Thing`) and `properties` (`property` and `value` pairs). A value that names another individual or a glossary term becomes an IRI. Any other value becomes a literal, typed with the property's XSD `range` if it has one. `draft-abox` can fill this block for you.
- `competency_questions`: one entry per CQ, with:
  - `id` and `question`.
  - `expected_result`: rows that the query must return. A row is a list of cells or a comma-separated string. Write `:name` to match any IRI with that local name.
  - `query`: SPARQL query run by `test` on the first-version TBox and ABox.
  - `refactored_query`: filled by `align`, run by `test --refactored`.

## `tbox.ttl.jinja`

Turtle template for the TBox. It receives `glossary`, a list of items with:

- `term`: local name (UpperCamelCase for classes, lowerCamelCase for properties).
- `type`: OWL type (`Class`, `ObjectProperty`, `DatatypeProperty` or `NamedIndividual`).
- `label`: `rdfs:label` (lower case for properties).
- `definition`: `rdfs:comment`.
- `domain`, `range`, `subclass_of`, `subproperty_of`: optional `rdfs:domain`, `rdfs:range`, `rdfs:subClassOf` and `rdfs:subPropertyOf`, already rendered as Turtle (`:Name`, `prefix:name` or `<iri>`).
- `member_of`: optional extra class of a named individual, rendered the same way.

It also receives `prefixes`, the `@prefix` declarations to write: `:`, `rdf`, `rdfs`, `owl`, `xsd`, and any prefix from `prefixes.yaml` that a rule uses.

## `abox.ttl.jinja`

Turtle template for the ABox. It receives `abox`, a list of items with:

- `individual`: local name of the individual.
- `type`: local name of its class, or empty for `owl:Thing`.
- `properties`: list of `property` and `value` pairs. `value` is already rendered as Turtle, either `:name` or a quoted literal.

Both templates use `https://www.example.org/` as the default (`:`) namespace.
