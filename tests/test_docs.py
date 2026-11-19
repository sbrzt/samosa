import io
import sys
import zipfile
from urllib.error import HTTPError, URLError

import pytest

from scripts import docs

TBOX = """@prefix : <https://www.example.org/> . @prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
: a owl:Ontology . :Animal a owl:Class ; rdfs:label "animal"@en ; rdfs:isDefinedBy : .
"""


def run(fn, *args):
    try:
        fn(*args)
    except SystemExit as e:
        return e.code
    return 0


@pytest.fixture
def model(project):
    (project / "project").mkdir()
    (project / "project" / "tbox.ttl").write_text(TBOX)
    stale = project / "project" / "docs" / "stale.html"
    stale.parent.mkdir()
    stale.write_text("old")
    return project


def site(*names):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for name in names:
            z.writestr(name, "<html></html>")
    return buffer.getvalue()


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_main_needs_a_merged_model(project, capsys):
    assert run(docs.main) == 1
    assert "Run merge first" in capsys.readouterr().out


def test_online_uploads_the_model_and_flattens_the_site(model, monkeypatch, capsys):
    sent = {}

    def fake_urlopen(request, timeout):
        sent["url"], sent["body"], sent["type"] = request.full_url, request.data, request.headers["Content-type"]
        return Response(site("tbox/index.html", "tbox/static/style.css"))

    monkeypatch.setattr(docs, "urlopen", fake_urlopen)
    assert run(docs.main, True) == 0
    out_dir = model / "project" / "docs"
    assert (out_dir / "index.html").exists() and (out_dir / "static" / "style.css").exists()
    assert not (out_dir / "tbox").exists() and not (out_dir / "stale.html").exists()
    assert sent["url"] == docs.LODE_API and sent["type"].startswith("multipart/form-data; boundary=")
    assert b'name="read_as"\r\n\r\nowl' in sent["body"] and b'filename="tbox.ttl"' in sent["body"]
    assert TBOX.encode() in sent["body"]
    assert "Documentation: project/docs/index.html" in capsys.readouterr().out


def test_online_keeps_a_site_without_a_wrapping_folder(model, monkeypatch):
    monkeypatch.setattr(docs, "urlopen", lambda request, timeout: Response(site("index.html", "static/a.css")))
    assert run(docs.main, True) == 0
    assert (model / "project" / "docs" / "index.html").exists()


@pytest.mark.parametrize("error, message", [
    (HTTPError(docs.LODE_API, 422, "bad", {}, io.BytesIO(b"read_as not enabled")), "HTTP 422: read_as not enabled"),
    (URLError("offline"), "cannot reach"),
])
def test_online_reports_request_errors(model, monkeypatch, capsys, error, message):
    def fail(request, timeout):
        raise error
    monkeypatch.setattr(docs, "urlopen", fail)
    assert run(docs.main, True) == 1
    assert message in capsys.readouterr().out


def test_online_rejects_a_non_zip_reply(model, monkeypatch, capsys):
    monkeypatch.setattr(docs, "urlopen", lambda request, timeout: Response(b"<html>error</html>"))
    assert run(docs.main, True) == 1
    assert "did not return a ZIP" in capsys.readouterr().out


def test_local_without_oc_lode(model, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "lode", None)
    assert run(docs.main) == 1
    assert "uv sync --extra docs" in capsys.readouterr().out


def test_local_runs_lode_build(model, monkeypatch, capsys):
    pytest.importorskip("lode")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        (model / "project" / "docs").mkdir(parents=True, exist_ok=True)
        (model / "project" / "docs" / "index.html").write_text("x")
        return type("Result", (), {"returncode": 0, "stdout": "Done", "stderr": ""})()

    monkeypatch.setattr(docs.subprocess, "run", fake_run)
    assert run(docs.main) == 0
    cmd = calls[0]
    assert cmd[0] == sys.executable and cmd[3] == "build"
    assert cmd[cmd.index("--file") + 1] == "project/tbox.ttl" and cmd[cmd.index("--read-as") + 1] == "owl"
    assert not (model / "project" / "docs" / "stale.html").exists()


def test_local_build_failure(model, monkeypatch):
    pytest.importorskip("lode")
    monkeypatch.setattr(docs.subprocess, "run",
                        lambda cmd, **kw: type("Result", (), {"returncode": 2, "stdout": "", "stderr": "boom"})())
    assert run(docs.main) == 1


def test_local_real_build(model):
    """End-to-end with the installed oc-lode (no network needed for a local file)."""
    pytest.importorskip("lode")
    assert run(docs.main) == 0
    assert "animal" in (model / "project" / "docs" / "index.html").read_text()
