import contextlib
import functools
import io
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from main import COMMANDS, summary
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


for d in ("iterations", "refactoring", "project"):  # generated files (tbox.ttl, tbox.png, ...)
    app.mount(f"/{d}", StaticFiles(directory=d, check_dir=False))
app.mount("/", StaticFiles(directory="ui", html=True))  # the web interface, must be mounted last
