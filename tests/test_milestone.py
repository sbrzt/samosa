import pytest

from conftest import zoo
from scripts import milestone
from scripts.common import load_yaml


def run(fn, *args):
    try:
        fn(*args)
    except SystemExit as e:
        return e.code
    return 0


def test_rank_orders_statuses_and_defaults_to_draft():
    assert [milestone.rank(s) for s in milestone.STATUSES] == [0, 1, 2, 3]
    assert milestone.rank("wip") == milestone.rank(None) == 0


def test_status_defaults_to_draft(iteration):
    assert milestone.status(iteration(data=zoo(metadata={"id": "01"}))) == "draft"


def test_snapshot_copies_tracked_files_without_docs(project, iteration):
    iteration()
    (project / "project" / "docs").mkdir(parents=True)
    (project / "project" / "tbox.ttl").write_text("x")
    (project / "project" / "docs" / "index.html").write_text("x")
    (project / "ontology.yaml").write_text("iri: x\n")
    dest = milestone.snapshot("label")
    assert dest.parent.name == "milestones" and dest.name.endswith("-label")
    assert (dest / "iterations" / "01-zoo" / "requirements.yaml").exists()
    assert (dest / "project" / "tbox.ttl").exists() and not (dest / "project" / "docs").exists()
    assert (dest / "prefixes.yaml").exists() and (dest / "ontology.yaml").exists()
    assert not (dest / "refactoring").exists()  # missing sources are skipped


def test_promote_only_goes_up_and_snapshots_on_change(iteration, project, capsys):
    it = iteration()
    milestone.promote(it, "aligned")
    assert milestone.status(it) == "aligned"
    assert "Status of 01-zoo: aligned" in capsys.readouterr().out
    milestone.promote(it, "tested")
    milestone.promote(it, "aligned")
    assert milestone.status(it) == "aligned"
    assert [d.name.split("-", 3)[3] for d in (project / "milestones").iterdir()] == ["01-zoo-aligned"]


def test_promote_replaces_unknown_statuses(iteration):
    it = iteration(data=zoo(metadata={"id": "01", "status": "wip"}))
    milestone.promote(it, "tested")
    assert milestone.status(it) == "tested"


def test_main_lists_milestones(project, capsys):
    milestone.main()
    assert "No milestones yet." in capsys.readouterr().out
    first, second = milestone.snapshot("a"), milestone.snapshot("b")
    milestone.main()
    assert capsys.readouterr().out.split() == [first.name, second.name]


def test_restore_replaces_state_and_can_be_undone(iteration, project, capsys):
    it = iteration()
    (project / "project" / "docs").mkdir(parents=True)
    (project / "project" / "tbox.ttl").write_text("old model")
    milestone.promote(it, "tested")
    (project / "project" / "tbox.ttl").write_text("new model")
    (project / "project" / "abox.ttl").write_text("new data")
    (project / "project" / "docs" / "index.html").write_text("docs")
    iteration("02-later")
    milestone.promote(it, "merged")
    capsys.readouterr()

    assert run(milestone.main, "01-zoo-tested") == 0
    assert milestone.status(it) == "tested"
    assert (project / "project" / "tbox.ttl").read_text() == "old model"
    assert not (project / "project" / "abox.ttl").exists()
    assert not (project / "iterations" / "02-later").exists()
    assert (project / "project" / "docs" / "index.html").read_text() == "docs"  # docs are kept
    assert "Previous state saved as" in capsys.readouterr().out

    assert run(milestone.main, "before-restore") == 0
    assert milestone.status(it) == "merged" and (project / "iterations" / "02-later").exists()
    assert (project / "project" / "tbox.ttl").read_text() == "new model"


def test_restore_needs_exactly_one_match(iteration, project, capsys):
    milestone.snapshot("01-zoo-tested")
    milestone.snapshot("01-zoo-merged")
    assert run(milestone.main, "01-zoo") == 1
    assert "2 milestones match '01-zoo'" in capsys.readouterr().out
    assert run(milestone.main, "nothing") == 1
    assert "no milestones match" in capsys.readouterr().out
