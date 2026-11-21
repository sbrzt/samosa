import contextlib
import functools
import io
import threading
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from main import COMMANDS, summary
from scripts import diagram
from scripts.common import dump_yaml, load_yaml

app = FastAPI(title="SAMOSA")
_lock = threading.Lock()

def endpoint(fn):
    @functools.wraps(fn)
    def run(*args, **kwargs):
        out = io.StringIO()
        with _lock, contextlib.redirect_stdout(out):
            try:
                fn(*args, **kwargs)
                ok = True
            except SystemExit as e:
                ok = e.code in (None, 0)
                if isinstance(e.code, str):
                    print(e.code)
            except Exception as e:
                ok = False
                print(f"Error: {e}")
        return {"ok": ok, "output": out.getvalue()}
    return run


for name, fn in COMMANDS.items():
    app.post(f"/{name}", summary=summary(fn))(endpoint(fn))


def requirements(name):
    path = Path("iterations") / name / "requirements.yaml"
    if not path.exists():
        raise HTTPException(404, f"iteration '{name}' not found")
    return path


@app.get("/iterations")
def list_iterations():
    return sorted(p.name for p in Path("iterations").iterdir() if p.is_dir())


@app.get("/iterations/{name}/requirements")
def get_requirements(name: str):
    return load_yaml(requirements(name))


@app.put("/iterations/{name}/requirements")
def put_requirements(name: str, data: dict):
    dump_yaml(data, requirements(name))
    return {"ok": True}


@app.put("/iterations/{name}/diagram/{stem}")
def put_layout(name: str, stem: Literal["tbox", "abox"], positions: dict[str, dict[str, float]], refactored: bool = False):
    """Save the node positions of a diagram (node id -> top-left x, y) and write its exports again."""
    if name not in list_iterations():
        raise HTTPException(404, f"iteration '{name}' not found")
    return endpoint(diagram.save_layout)(name, stem, positions, refactored)


for d in ("iterations", "refactoring", "project"):  # generated files (tbox.ttl, tbox.png, ...)
    app.mount(f"/{d}", StaticFiles(directory=d, check_dir=False))
# the web interface, shipped with the code (project files above are relative to the working directory); must be mounted last
app.mount("/", StaticFiles(directory=Path(__file__).with_name("ui"), html=True))
