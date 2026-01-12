import sys
import yaml
from pathlib import Path
from jinja2 import Environment, FileSystemLoader


def generate_tbox(data, output_dir):
    env = Environment(loader=FileSystemLoader("templates"))
    template = env.get_template("tbox.ttl.jinja")
    tbox_content = template.render(data)
    output_path = output_dir / "tbox.ttl"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(tbox_content)


def main():
    iter_path = sys.argv[1]
    if Path(iter_path).exists():
        iter_path = Path(iter_path)
    elif (Path("iterations") / iter_path).exists():
        iter_path = Path("iterations") / iter_path
    else:
        sys.exit(1)
    req_file = iter_path / "requirements.yaml"
    if not req_file.exists():
        print(f"Error: File {req_file} not found.")
        sys.exit(1)
    with open(req_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    generate_tbox(data, iter_path)


if __name__ == "__main__":
    main()