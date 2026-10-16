# scripts/generate_iteration.py

import os
import sys
import shutil
from pathlib import Path
from scripts.common import dump_yaml, load_yaml


def compile(file_path, iteration_id, iteration_name):
    if not file_path.exists():
        return
    data = load_yaml(file_path)
    data["metadata"]["id"] = iteration_id
    data["scenario"]["title"] = iteration_name.title()
    dump_yaml(data, file_path)


def main(iteration_name):
    root_dir = Path.cwd()
    template_dir = root_dir / "templates" / "iteration"
    iterations_dir = root_dir / "iterations"
    if not template_dir.exists():
        print(f"Error: template directory '{template_dir}' does not exist.")
        sys.exit(1)
    iterations_dir.mkdir(exist_ok=True)
    existing_dirs = [d for d in iterations_dir.iterdir() if d.is_dir()]
    next_id = len(existing_dirs) + 1
    next_id_str = f"{next_id:02d}"
    new_folder_name = f"{next_id_str}-{iteration_name}"
    target_path = iterations_dir / new_folder_name
    try:
        shutil.copytree(template_dir, target_path)
        requirements = target_path / "requirements.yaml"
        compile(requirements, next_id_str, iteration_name)
    except FileExistsError:
        print(f"Error: directory '{target_path}' already exists.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1])