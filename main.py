import argparse
import sys

from scripts import (
    check_consistency,
    draft_abox,
    align,
    diagram,
    generate_abox,
    generate_iteration,
    generate_tbox,
    merge,
    test_iteration,
)


def main():
    parser = argparse.ArgumentParser(prog="samosa", description="SAMOSA: Semi-Automated Modelling of Ontologies with SAMOD.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    new_parser = subparsers.add_parser("new", help="Create a new iteration from the template.")
    new_parser.add_argument("name")

    tbox_parser = subparsers.add_parser("tbox", help="Generate tbox.ttl for an iteration.")
    tbox_parser.add_argument("iteration")

    abox_parser = subparsers.add_parser("abox", help="Generate abox.ttl for an iteration.")
    abox_parser.add_argument("iteration")

    draft_parser = subparsers.add_parser("draft-abox", help="Draft an abox: block from scenario/CQ text.")
    draft_parser.add_argument("iteration")

    test_parser = subparsers.add_parser("test", help="Run an iteration's SPARQL queries on its TBox+ABox.")
    test_parser.add_argument("iteration")
    test_parser.add_argument("--refactored", action="store_true", help="Test the refactored files.")

    diagram_parser = subparsers.add_parser("diagram", help="Draw tbox.graphml + tbox.png of an iteration's TBox.")
    diagram_parser.add_argument("iteration")
    diagram_parser.add_argument("--refactored", action="store_true", help="Draw the refactored TBox.")

    align_parser = subparsers.add_parser("align", help="Refactor TBox, ABox and queries using align_to IRIs.")
    align_parser.add_argument("iteration")

    subparsers.add_parser("merge", help="Merge refactored ABoxes, run all queries, then merge TBoxes.")
    subparsers.add_parser("check", help="Check project/ consistency.")

    args = parser.parse_args()

    if args.command == "new":
        sys.argv = ["generate_iteration.py", args.name]
        generate_iteration.main()
    elif args.command == "tbox":
        sys.argv = ["generate_tbox.py", args.iteration]
        generate_tbox.main()
    elif args.command == "abox":
        sys.argv = ["generate_abox.py", args.iteration]
        generate_abox.main()
    elif args.command == "draft-abox":
        sys.argv = ["draft_abox.py", args.iteration]
        draft_abox.main()
    elif args.command == "test":
        sys.argv = ["test_iteration.py", args.iteration] + (["--refactored"] if args.refactored else [])
        test_iteration.main()
    elif args.command == "align":
        sys.argv = ["align.py", args.iteration]
        align.main()
    elif args.command == "diagram":
        sys.argv = ["diagram.py", args.iteration] + (["--refactored"] if args.refactored else [])
        diagram.main()
    elif args.command == "merge":
        merge.main()
    elif args.command == "check":
        check_consistency.main()


if __name__ == "__main__":
    main()
