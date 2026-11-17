# scripts/generate_iteration.py

import sys
import shutil
from pathlib import Path
from scripts.common import dump_yaml, load_yaml


def fill_requirements(file_path, iteration_id, iteration_name):
    """Fill the iteration ID and title into a copied `requirements.yaml`, in place.

    Does nothing if the file does not exist.

    Args:
        file_path: Path of the `requirements.yaml` to update.
        iteration_id: Zero-padded iteration number, e.g. `"03"`, stored as `metadata.id`.
        iteration_name: Iteration name, stored in title case as `scenario.title`.
    """
    if not file_path.exists():
        return
    data = load_yaml(file_path)
    data["metadata"]["id"] = iteration_id
    data["scenario"]["title"] = iteration_name.title()
    dump_yaml(data, file_path)


def main(iteration_name: str):
    """Create a new iteration directory from `templates/iteration/`.

    The directory is `iterations/<NN>-<iteration_name>`, where `NN` is the highest
    existing iteration number plus one.

    Args:
        iteration_name: Name of the new iteration.

    Raises:
        SystemExit: If the template directory is missing, the target directory
            already exists, or the copy or update fails.
    """
    root_dir = Path.cwd()
    template_dir = root_dir / "templates" / "iteration"
    iterations_dir = root_dir / "iterations"
    if not template_dir.exists():
        print(f"Error: template directory '{template_dir}' does not exist.")
        sys.exit(1)
    iterations_dir.mkdir(exist_ok=True)
    existing_ids = [int(d.name.split("-")[0]) for d in iterations_dir.iterdir()
                    if d.is_dir() and d.name.split("-")[0].isdigit()]
    next_id = max(existing_ids, default=0) + 1
    next_id_str = f"{next_id:02d}"
    new_folder_name = f"{next_id_str}-{iteration_name}"
    target_path = iterations_dir / new_folder_name
    try:
        shutil.copytree(template_dir, target_path)
        requirements = target_path / "requirements.yaml"
        fill_requirements(requirements, next_id_str, iteration_name)
    except FileExistsError:
        print(f"Error: directory '{target_path}' already exists.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1])