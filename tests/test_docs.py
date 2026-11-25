import io
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


def test_uploads_the_model_and_flattens_the_site(model, monkeypatch, capsys):
    sent = {}

    def fake_urlopen(request, timeout):
        sent["url"], sent["body"], sent["type"] = request.full_url, request.data, request.headers["Content-type"]
        return Response(site("tbox/index.html", "tbox/static/style.css"))

    monkeypatch.setattr(docs, "urlopen", fake_urlopen)
    assert run(docs.main) == 0
    out_dir = model / "project" / "docs"
    assert (out_dir / "index.html").exists() and (out_dir / "static" / "style.css").exists()
    assert not (out_dir / "tbox").exists() and not (out_dir / "stale.html").exists()
    assert sent["url"] == docs.LODE_API and sent["type"].startswith("multipart/form-data; boundary=")
    assert b'name="read_as"\r\n\r\nowl' in sent["body"] and b'filename="tbox.ttl"' in sent["body"]
    assert TBOX.encode() in sent["body"]
    assert "Documentation: project/docs/index.html" in capsys.readouterr().out


def test_keeps_a_site_without_a_wrapping_folder(model, monkeypatch):
    monkeypatch.setattr(docs, "urlopen", lambda request, timeout: Response(site("index.html", "static/a.css")))
    assert run(docs.main) == 0
    assert (model / "project" / "docs" / "index.html").exists()


@pytest.mark.parametrize("error, message", [
    (HTTPError(docs.LODE_API, 422, "bad", {}, io.BytesIO(b"read_as not enabled")), "HTTP 422: read_as not enabled"),
    (URLError("offline"), "cannot reach"),
])
def test_reports_request_errors(model, monkeypatch, capsys, error, message):
    def fail(request, timeout):
        raise error
    monkeypatch.setattr(docs, "urlopen", fail)
    assert run(docs.main) == 1
    assert message in capsys.readouterr().out


def test_rejects_a_non_zip_reply(model, monkeypatch, capsys):
    monkeypatch.setattr(docs, "urlopen", lambda request, timeout: Response(b"<html>error</html>"))
    assert run(docs.main) == 1
    assert "did not return a ZIP" in capsys.readouterr().out
