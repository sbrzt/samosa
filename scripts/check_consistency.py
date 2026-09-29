# scripts/check_consistency.py
# OWL DL consistency check of project/{tbox,abox}.ttl with HermiT (via owlready2, needs Java).

import sys
import tempfile
from pathlib import Path
from owlready2 import OwlReadyInconsistentOntologyError, World, sync_reasoner_hermit
from rdflib import Graph


def main():
    project_dir = Path.cwd() / "project"
    graph = Graph()
    for name in ("tbox.ttl", "abox.ttl"):
        if not (project_dir / name).exists():
            print(f"Error: '{project_dir / name}' not found. Run merge first.")
            sys.exit(1)
        graph.parse(project_dir / name, format="turtle")

    # owlready2 cannot read Turtle: hand it N-Triples
    with tempfile.NamedTemporaryFile(suffix=".nt") as f:
        graph.serialize(destination=f.name, format="nt", encoding="utf-8")
        world = World()
        onto = world.get_ontology(f"file://{f.name}").load()
        try:
            sync_reasoner_hermit(world, infer_property_values=False, debug=0)
        except OwlReadyInconsistentOntologyError:
            print("Inconsistent: the ontology has no model (e.g. an individual in disjoint classes).")
            sys.exit(1)

    unsatisfiable = [c for c in world.inconsistent_classes() if c.iri != "http://www.w3.org/2002/07/owl#Nothing"]
    if unsatisfiable:
        print("Consistent, but unsatisfiable classes (equivalent to owl:Nothing):")
        for c in unsatisfiable:
            print(f"  {c.iri}")
        sys.exit(1)
    print(f"Consistent: {len(graph)} triples, no unsatisfiable classes.")


if __name__ == "__main__":
    main()
