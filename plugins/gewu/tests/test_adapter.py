"""The GeWu adapter against the real Fignimble engine."""

import hashlib
import json
from pathlib import Path
import shutil
import sys
import threading
import time

import pytest

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
REPO = PLUGIN.parents[1]
sys.path.insert(0, str(PLUGIN))
sys.path.insert(0, str(REPO / "engine"))

from adapter import Adapter                                   # noqa: E402
from gewu_plugin import ProtocolError                         # noqa: E402


class Control:
    def __init__(self):
        self.cancelled = threading.Event()

    def progress(self, message):
        pass


@pytest.fixture()
def workspace(tmp_path):
    project = tmp_path / "figures" / "paper1"
    shutil.copytree(PLUGIN / "fixtures" / "project", project)
    (tmp_path / "assets").mkdir()
    shutil.copy2(project / "images" / "test.svg", tmp_path / "assets" / "extra.svg")
    return tmp_path


@pytest.fixture()
def adapter(workspace):
    adapters = []

    def start(settings=None):
        instance = Adapter()
        instance.activate({
            "apiVersion": "gewu.plugin/v1", "instanceId": "test", "generation": 1,
            "workspaceId": "test", "workspaceRoot": str(workspace),
            "bindingResource": {"uri": "workspace:///figures/paper1", "type": "fignimble.project"},
            "settings": settings or {"python": sys.executable, "engineRoot": str(REPO / "engine")},
        })
        adapters.append(instance)
        return instance

    yield start
    for instance in adapters:
        instance.deactivate({})


def call(adapter, tool, **args):
    return adapter.call(tool, args, {"callId": f"call-{tool}-{time.time()}"}, Control())


def test_state_and_figure(adapter):
    instance = adapter()
    state = call(instance, "state")
    assert state["ok"], state
    assert state["data"]["revision"]
    names = [figure["name"] for figure in state["data"]["figures"]]
    assert names == ["fig1"]

    figure = call(instance, "figure", figure="fig1")
    assert figure["ok"], figure
    data = figure["data"]
    assert data["size"] == [120, 60]
    assert len(data["elements"]) >= 4
    assert data["labels"]
    assert data["preview"]["type"] == "fignimble.preview"
    assert data["scene"]["type"] == "fignimble.scene"
    assert any(element.get("sprite") for element in data["elements"])
    assert instance.resolve(data["preview"])["kind"] == "file"

    scene = json.loads((instance.cache / "snapshots" / data["snapshotId"] / "scene.json").read_text())
    assert scene["schemaVersion"] == "fignimble.scene/v1"
    assert scene["file"] == "fig1.py"
    assert len(scene["elements"]) == len(data["elements"]) or data["page"]["total"] == len(scene["elements"])


def test_move_writes_source_and_checks_revisions(adapter, workspace):
    instance = adapter()
    figure = call(instance, "figure", figure="fig1")["data"]
    target = next(element for element in figure["elements"] if element["kind"] == "text")
    result = call(instance, "edit", figure="fig1", expectedRevision=figure["revision"],
                  snapshotId=figure["snapshotId"], op="move", oids=[target["oid"]], dx=6, dy=0)
    assert result["ok"], result
    changes = result["changes"]
    assert [change["uri"] for change in changes] == ["workspace:///figures/paper1/fig1.py"]
    assert result["data"]["revision"] != figure["revision"]
    assert "x=40" in (workspace / "figures/paper1/fig1.py").read_text()

    stale = call(instance, "edit", figure="fig1", expectedRevision=figure["revision"],
                 snapshotId=figure["snapshotId"], op="move", oids=[target["oid"]], dx=1, dy=1)
    assert stale["ok"] is False and stale["error"]["code"] == "STALE_REVISION"

    old_snapshot = call(instance, "edit", figure="fig1", expectedRevision=result["data"]["revision"],
                        snapshotId=figure["snapshotId"], op="move", oids=[target["oid"]], dx=1, dy=1)
    assert old_snapshot["ok"] is False and old_snapshot["error"]["code"] == "STALE_SNAPSHOT"

    undo = call(instance, "undo", expectedRevision=result["data"]["revision"], figure="fig1")
    assert undo["ok"], undo
    assert "x=34" in (workspace / "figures/paper1/fig1.py").read_text()
    redo = call(instance, "redo", expectedRevision=undo["data"]["revision"], figure="fig1")
    assert redo["ok"], redo


def test_source_edit_and_panel_import(adapter, workspace):
    instance = adapter()
    source = call(instance, "source", file="fig1.py", maxLines=5)
    assert source["ok"] and source["data"]["totalLines"] > 3
    created = call(instance, "edit_source", file="panels/extra.py", text="def draw(fig):\n    pass\n",
                   expectedRevision=None)
    assert created["ok"], created
    assert created["changes"][0]["beforeRevision"] is None
    assert (workspace / "figures/paper1/panels/extra.py").is_file()
    again = call(instance, "edit_source", file="panels/extra.py", text="x = 1\n", expectedRevision=None)
    assert again["ok"] is False and again["error"]["code"] == "STALE_REVISION"

    figure = call(instance, "figure", figure="fig1")["data"]
    imported = call(instance, "import_asset", figure="fig1", path="assets/extra.svg", x=80, y=6, w=20,
                    expectedRevision=figure["revision"], snapshotId=figure["snapshotId"])
    assert imported["ok"], imported
    assert (workspace / "figures/paper1/images/extra.svg").is_file()
    assert "images/extra.svg" in (workspace / "figures/paper1/fig1.py").read_text()


def test_export_is_a_real_file_with_provenance(adapter, workspace):
    instance = adapter()
    revision = call(instance, "state")["data"]["revision"]
    result = call(instance, "export", figure="fig1", format="pdf", dpi=600, expectedRevision=revision)
    assert result["ok"], result
    data = result["data"]
    path = instance.resolve(data["export"])["path"]
    assert Path(path).read_bytes()[:5] == b"%PDF-"
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == data["sha256"]
    provenance = json.loads(Path(instance.resolve(data["provenance"])["path"]).read_text())
    assert provenance["documentRevision"] == revision
    assert provenance["output"] == data["filename"]
    assert provenance["sha256"] == data["sha256"]


def test_preflight_lists_checks(adapter):
    instance = adapter()
    result = call(instance, "preflight", figure="fig1")
    assert result["ok"], result
    assert set(result["data"]["counts"]) == {"error", "warning", "info"}
    assert "page" in result["data"]


def test_new_figure_refuses_a_taken_name(adapter, workspace):
    instance = adapter()
    revision = call(instance, "state")["data"]["revision"]
    taken = call(instance, "new_figure", name="fig1", width=100, height=80, expectedRevision=revision)
    assert taken["ok"] is False and taken["error"]["code"] == "ALREADY_EXISTS"
    created = call(instance, "new_figure", name="fig2", width=100, height=80, expectedRevision=revision)
    assert created["ok"], created
    assert (workspace / "figures/paper1/fig2.py").is_file()


def test_paths_outside_the_workspace_are_refused(adapter):
    instance = adapter()
    bad = call(instance, "import_asset", figure="fig1", path="/etc/passwd",
               expectedRevision=call(instance, "state")["data"]["revision"], snapshotId="x")
    assert bad["ok"] is False
    assert bad["error"]["code"] in ("INVALID_PATH", "FILE_UNAVAILABLE")


def test_second_instance_is_refused(adapter):
    adapter()
    with pytest.raises(ProtocolError) as error:
        adapter()
    assert error.value.payload["code"] == "PROJECT_IN_USE"


def test_cancel_stops_a_looping_panel(adapter, workspace):
    instance = adapter()
    project = workspace / "figures" / "paper1"
    (project / "panels" / "loop.py").write_text("def draw(fig):\n    while True:\n        pass\n")
    (project / "fig2.py").write_text(
        'from fignimble import *\nfrom style import STYLE\n\n'
        'fig = Figure(width=40, height=30, style=STYLE)\n'
        'fig.panel("panels/loop.py", x=2, y=2, w=20, h=20)\n')
    control = Control()
    answer = {}

    def run():
        answer["result"] = instance.call("figure", {"figure": "fig2"},
                                         {"callId": "cancel-me"}, control)

    thread = threading.Thread(target=run)
    started = time.monotonic()
    thread.start()
    time.sleep(1.0)
    control.cancelled.set()
    thread.join(timeout=15)
    assert not thread.is_alive(), "a cancelled figure call did not settle"
    assert time.monotonic() - started < 12
    assert answer["result"]["ok"] is False
    assert answer["result"]["error"]["code"] == "CANCELLED"
    assert call(instance, "figure", figure="fig1")["ok"]
