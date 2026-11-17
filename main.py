import argparse
import inspect

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

COMMANDS = {
    "new": generate_iteration.main,
    "tbox": generate_tbox.main,
    "abox": generate_abox.main,
    "draft-abox": draft_abox.main,
    "test": test_iteration.main,
    "diagram": diagram.main,
    "align": align.main,
    "merge": merge.main,
    "check": check_consistency.main,
}


def summary(fn):
    return inspect.getdoc(fn).splitlines()[0]


def main():
    parser = argparse.ArgumentParser(prog="samosa", description="SAMOSA: Semi-Automated Modelling of Ontologies with SAMOD.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, fn in COMMANDS.items():
        sub = subparsers.add_parser(name, help=summary(fn))
        for p in inspect.signature(fn).parameters.values():
            if p.default is inspect.Parameter.empty:
                sub.add_argument(p.name)
            else:
                sub.add_argument(f"--{p.name}", action="store_true")
    args = vars(parser.parse_args())
    COMMANDS[args.pop("command")](**args)


if __name__ == "__main__":
    main()
