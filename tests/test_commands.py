"""Tests for the small commands and helpers: new, draft-abox, common, the CLI and the HTTP API."""

import json
import sys

import pytest

import main as cli
from conftest import PREFIXES, zoo
from scripts import draft_abox, generate_iteration
from scripts.common import dump_yaml, individual_id, load_yaml, resolve_iteration


def run(fn, *args):
    try:
        fn(*args)
    except SystemExit as e:
        return e.code
    return 0


# common

def test_individual_id():
    assert individual_id("  Ada Lovelace ") == "ada-lovelace"


def test_resolve_iteration(project, capsys):
    (project / "iterations" / "01-zoo").mkdir()
    assert resolve_iteration("01-zoo") == project.joinpath("iterations", "01-zoo").relative_to(project)
    assert resolve_iteration("iterations/01-zoo").name == "01-zoo"
    assert run(resolve_iteration, "02-none") == 1
    assert "iteration '02-none' not found" in capsys.readouterr().out


def test_yaml_round_trip_keeps_order_and_literal_blocks(tmp_path):
    data = {"b": 1, "a": "line one  \nline two\n", "c": "ünï"}
    dump_yaml(data, tmp_path / "x.yaml")
    text = (tmp_path / "x.yaml").read_text()
    assert text.index("b:") < text.index("a:") and "a: |" in text and "ünï" in text
    assert load_yaml(tmp_path / "x.yaml") == {**data, "a": "line one\nline two\n"}


def test_load_yaml_missing_file(tmp_path):
    assert run(load_yaml, tmp_path / "none.yaml") == 1


# new

def test_new_numbers_iterations_and_fills_the_template(project):
    generate_iteration.main("zoo")
    generate_iteration.main("keeper")
    data = load_yaml(project / "iterations" / "02-keeper" / "requirements.yaml")
    assert data["metadata"]["id"] == "02" and data["scenario"]["title"] == "Keeper"
    assert (project / "iterations" / "01-zoo" / "requirements.yaml").exists()


def test_new_needs_the_template(project, capsys):
    import shutil
    shutil.rmtree(project / "templates" / "iteration")
    assert run(generate_iteration.main, "other") == 1
    assert "does not exist" in capsys.readouterr().out


# draft-abox

def test_identifiers_and_prompt_lines():
    assert draft_abox.to_slug("research data-set") == "ResearchDataset"
    assert draft_abox.to_property_id("has URL") == "hasURL"
    assert draft_abox.describe({"term": "eats", "definition": "x", "rules": {"domain": "animal"}}) == "- eats: x (domain: animal)"
    assert draft_abox.describe({"term": "animal"}) == "- animal: "


def test_response_schema_restricts_types_and_properties():
    schema = draft_abox.response_schema(["Animal", "Thing"], ["eats"])
    item = schema["properties"]["abox"]["items"]
    assert item["properties"]["type"]["enum"] == ["Animal", "Thing"]
    assert item["properties"]["properties"]["items"]["properties"]["property"]["enum"] == ["eats"]


def test_draft_abox_cleans_the_model_reply(monkeypatch):
    seen = {}

    def fake(prompt, schema):
        seen["prompt"], seen["schema"] = prompt, schema
        return {"abox": [
            {"individual": "Rex Dog", "type": "Animal", "properties": [
                {"property": "eats", "value": "tom"}, {"property": "flies", "value": "x"}, {"property": "eats", "value": ""}]},
            {"individual": "tom", "type": "Thing", "properties": []},
            {"individual": "", "type": "Animal", "properties": []},
        ]}

    monkeypatch.setattr(draft_abox, "ask_ollama", fake)
    assert draft_abox.draft_abox(zoo()) == [
        {"individual": "rexDog", "type": "Animal", "properties": [{"property": "eats", "value": "tom"}]},
        {"individual": "tom"},
    ]
    assert "Rex eats Tom." in seen["prompt"] and "- eats: Eats another animal." in seen["prompt"]
    assert seen["schema"]["properties"]["abox"]["items"]["properties"]["type"]["enum"] == ["Animal", "Mammal", "Thing"]


def test_draft_abox_needs_classes_and_scenario(monkeypatch):
    monkeypatch.setattr(draft_abox, "ask_ollama", lambda *a: pytest.fail("model called"))
    assert draft_abox.draft_abox(zoo(glossary=[])) == []
    assert draft_abox.draft_abox(zoo(scenario={"title": "x"})) == []


def test_draft_abox_main_writes_requirements(iteration, monkeypatch, capsys):
    it = iteration()
    monkeypatch.setattr(draft_abox, "ask_ollama", lambda *a: {"abox": [{"individual": "kim", "type": "Animal"}]})
    draft_abox.main(it.name)
    assert load_yaml(it / "requirements.yaml")["abox"] == [{"individual": "kim", "type": "Animal"}]
    monkeypatch.setattr(draft_abox, "ask_ollama", lambda *a: {"abox": []})
    draft_abox.main(it.name)
    assert "Nothing drafted" in capsys.readouterr().out


def test_ask_ollama_reports_an_unreachable_server():
    with pytest.raises(SystemExit) as e:
        draft_abox.ask_ollama("hi", {})
    assert "cannot reach Ollama" in str(e.value.code)


def test_ask_ollama_parses_the_structured_reply(monkeypatch):
    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps({"message": {"content": '{"abox": []}'}}).encode()

    monkeypatch.setattr(draft_abox.urllib.request, "urlopen", lambda req, timeout: Reply())
    assert draft_abox.ask_ollama("hi", {}) == {"abox": []}


# CLI

def test_cli_builds_arguments_from_signatures(monkeypatch):
    calls = []

    def needs(iteration: str, refactored: bool = False):
        """Needs an iteration."""
        calls.append((iteration, refactored))

    def optional(iteration: str = None, reason: bool = False):
        """Optional iteration."""
        calls.append((iteration, reason))

    monkeypatch.setattr(cli, "COMMANDS", {"needs": needs, "optional": optional})
    for argv in (["needs", "01", "--refactored"], ["optional"], ["optional", "02", "--reason"]):
        monkeypatch.setattr(sys, "argv", ["samosa", *argv])
        cli.main()
    assert calls == [("01", True), (None, False), ("02", True)]
    monkeypatch.setattr(sys, "argv", ["samosa", "needs"])
    with pytest.raises(SystemExit):
        cli.main()


def test_every_command_has_a_summary():
    for fn in cli.COMMANDS.values():
        assert cli.summary(fn)


# HTTP API

@pytest.fixture
def client(project):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    import api
    return TestClient(api.app)


def test_api_serves_the_ui_from_any_directory(client):
    assert "<title>SAMOSA</title>" in client.get("/").text


def test_api_runs_commands_and_reports_output(client, project):
    assert client.post("/new", params={"iteration_name": "zoo"}).json() == {"ok": True, "output": ""}
    assert client.get("/iterations").json() == ["01-zoo"]
    reply = client.post("/test", params={"iteration": "01-zoo"}).json()
    assert reply["ok"] is False and "tbox.ttl not found" in reply["output"]
    assert client.post("/restore").json() == {"ok": True, "output": "No milestones yet.\n"}


def test_api_reads_and_writes_requirements(client, project):
    client.post("/new", params={"iteration_name": "zoo"})
    data = client.get("/iterations/01-zoo/requirements").json()
    data["scenario"]["description"] = "Changed."
    assert client.put("/iterations/01-zoo/requirements", json=data).json() == {"ok": True}
    assert load_yaml(project / "iterations" / "01-zoo" / "requirements.yaml")["scenario"]["description"] == "Changed."
    assert client.get("/iterations/99-none/requirements").status_code == 404


def test_api_saves_diagram_layouts(client, project):
    client.post("/new", params={"iteration_name": "zoo"})
    it = project / "iterations" / "01-zoo"
    (it / "tbox.ttl").write_text(PREFIXES + ":Animal a owl:Class .")
    client.post("/diagram", params={"iteration": "01-zoo"})
    reply = client.put("/iterations/01-zoo/diagram/tbox", json={"n0": {"x": 7, "y": 8}}).json()
    assert reply["ok"] and 'x="7.0" y="8.0"' in (it / "tbox.graphml").read_text()
    assert client.put("/iterations/01-zoo/diagram/abox", json={}).json()["ok"] is False  # not drawn
    assert client.put("/iterations/01-zoo/diagram/oops", json={}).status_code == 422
    assert client.put("/iterations/99-none/diagram/tbox", json={}).status_code == 404


def test_api_turns_exceptions_into_failed_replies(client, monkeypatch):
    import api

    def boom():
        raise RuntimeError("kaput")
    reply = api.endpoint(boom)()
    assert reply == {"ok": False, "output": "Error: kaput\n"}
