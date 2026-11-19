# scripts/model_test.py

from rdflib import URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD
from scripts.check_consistency import hermit
from scripts.common import EX, entities, report

PROPERTIES = {OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty}
OWL_TYPES = PROPERTIES | {OWL.Class, RDFS.Datatype, OWL.NamedIndividual}

# The OWL 2 datatype map (OWL 2 Structural Specification, section 4).
DATATYPES = {OWL.real, OWL.rational, RDF.PlainLiteral, RDF.XMLLiteral, RDFS.Literal} | {URIRef(XSD + n) for n in (
    "decimal integer nonNegativeInteger nonPositiveInteger positiveInteger negativeInteger long int short byte "
    "unsignedLong unsignedInt unsignedShort unsignedByte double float string normalizedString token language "
    "Name NCName NMTOKEN boolean hexBinary base64Binary anyURI dateTime dateTimeStamp").split()}


def undocumented(tbox):
    """Find TBox entities without a label or a description (rhetorical model test).

    Args:
        tbox: TBox graph.

    Returns:
        Sorted list of `(term, problem)` pairs, for each class, property or
        individual with no `rdfs:label` or no non-empty `rdfs:comment`.
    """
    return [(t, f"has no {name}") for t in sorted(entities(tbox))
            for p, name in ((RDFS.label, "rdfs:label"), (RDFS.comment, "rdfs:comment"))
            if not any(str(o).strip() for o in tbox.objects(t, p))]


def _is_datatype(tbox, term):
    """Check if a range is a datatype: in the XSD namespace, the datatype map, or declared `rdfs:Datatype`."""
    return term in DATATYPES or term.startswith(str(XSD)) or (term, RDF.type, RDFS.Datatype) in tbox


def not_dl(tbox):
    """Find declarations that OWL 2 DL forbids (formal model test).

    Checks what HermiT does not reject but silently repairs: an IRI declared as
    two kinds of property, or as both a class and a datatype; a term typed only
    with `rdfs:Class` or `rdf:Property`, without an OWL entity type; an object
    property ranging over a datatype, or a datatype property over a class.

    Args:
        tbox: TBox graph.

    Returns:
        Sorted list of `(term, problem)` pairs.
    """
    out = []
    for t in {s for s in tbox.subjects(RDF.type, None) if isinstance(s, URIRef)}:
        types = set(tbox.objects(t, RDF.type))
        if len(types & PROPERTIES) > 1:
            out.append((t, "is declared as more than one kind of property"))
        if {OWL.Class, RDFS.Datatype} <= types:
            out.append((t, "is declared as both a class and a datatype"))
        if types & {RDFS.Class, RDF.Property} and not types & OWL_TYPES:
            out.append((t, "is typed only with rdfs:Class or rdf:Property, not as an OWL entity"))
    for p, r in tbox.subject_objects(RDFS.range):
        if not isinstance(r, URIRef):
            continue
        if (p, RDF.type, OWL.ObjectProperty) in tbox and _is_datatype(tbox, r):
            out.append((p, f"is an object property with a datatype range <{r}>"))
        if (p, RDF.type, OWL.DatatypeProperty) in tbox and not _is_datatype(tbox, r):
            out.append((p, f"is a datatype property with a non-datatype range <{r}>"))
    return sorted(out)


def unsupported_datatypes(tbox):
    """Find datatype ranges outside the OWL 2 datatype map, e.g. `xsd:date`.

    These are not OWL 2 DL, but common and harmless: HermiT ignores them.

    Args:
        tbox: TBox graph.

    Returns:
        Sorted list of `(property, datatype)` pairs.
    """
    return sorted((p, r) for p, r in tbox.subject_objects(RDFS.range)
                  if isinstance(r, URIRef) and r.startswith(str(XSD)) and r not in DATATYPES)


def run_model_test(tbox, label):
    """Run the SAMOD model test on a TBox and print the results.

    Formal requirements: OWL 2 DL declarations (`not_dl`) and HermiT
    classification (`hermit`). Rhetorical requirements: every entity has a
    label and a description (`undocumented`). Problems with local (`:`) terms
    fail; problems with reused terms only warn, since their vocabulary cannot
    be edited here. Datatypes outside the OWL 2 datatype map always only warn.

    Args:
        tbox: TBox graph, the iteration's own or the current model.
        label: Name shown in each printed line, e.g. the iteration name.

    Returns:
        The number of failed checks.
    """
    failures = 0
    for term, problem in not_dl(tbox) + undocumented(tbox):
        local = term.startswith(EX)
        report("FAIL" if local else "WARN", label, "model", f"<{term}> {problem}", term=str(term))
        failures += local
    for p, r in unsupported_datatypes(tbox):
        report("WARN", label, "model", f"<{p}> ranges over <{r}>, outside the OWL 2 datatype map (not OWL 2 DL)",
               term=str(p))
    problems = hermit(tbox)
    if problems is None:
        report("WARN", label, "model", "Java not found, HermiT (OWL 2 DL) reasoning skipped")
    for m in problems or []:
        report("FAIL", label, "model", m)
    failures += len(problems or [])
    if not failures:
        report("PASS", label, "model", "all checks pass")
    return failures
