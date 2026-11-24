"""Packaging: one staged package, no source paths in code, a working probe."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
REPO = PLUGIN.parents[1]
GEWU = Path(os.environ.get("GEWU_ROOT", "/data3/litian/projects/GeWu"))
PYTHON = Path(sys.executable)


@pytest.fixture(scope="module")
def staged(tmp_path_factory):
    out = tmp_path_factory.mktemp("stage") / "package"
    subprocess.run([str(PYTHON), str(PLUGIN / "package.py"), "--sdk-root", str(GEWU / "sdk/python"),
                    "--python", str(PYTHON), "--out", str(out)], check=True, capture_output=True)
    return out


def test_package_layout(staged):
    for name in ("plugin.json", "adapter.py", "engine_client.py", "tools.schema.json",
                 "README.md", "INSTALL.md", "VERSION", "compatibility.json"):
        assert (staged / name).is_file(), name
    for name in ("bin/fignimble-gewu", "web/index.html", "web/editor.mjs",
                 "skills/fignimble/SKILL.md", "lib/gewu_plugin.py",
                 "engine/fignimble/rpc.py", "engine/requirements.txt"):
        assert (staged / name).is_file(), name
    assert not list(staged.rglob("__pycache__"))
    assert not list(staged.rglob("*.pyc"))


def test_launcher_binds_the_interpreter_and_never_the_source_tree(staged):
    launcher = (staged / "bin/fignimble-gewu").read_text()
    assert str(PYTHON) in launcher
    assert "__pycache__" not in launcher
    adapter = (staged / "adapter.py").read_text()
    assert str(REPO) not in adapter
    assert str(REPO / "engine") not in adapter


def test_manifest_is_the_protocol_schema(staged):
    import jsonschema
    schema = json.loads((GEWU / "gewu-protocol/schema/plugin.v1.schema.json").read_text())
    manifest = json.loads((staged / "plugin.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(manifest)
    tools = json.loads((staged / "tools.schema.json").read_text())
    assert len([tool for tool in tools if tool["exposeToAgent"]]) == 12
    assert all(tool["target"] == "backend" for tool in tools)


def test_tool_schemas_accept_real_payloads(staged):
    import jsonschema
    tools = {tool["name"]: tool for tool in json.loads((staged / "tools.schema.json").read_text())}
    edit = jsonschema.Draft202012Validator(tools["edit"]["inputSchema"])
    edit.validate({"figure": "fig1", "expectedRevision": "r", "snapshotId": "s", "op": "move",
                   "oids": ["1"], "dx": 2, "dy": -1})
    edit.validate({"figure": "fig1", "expectedRevision": "r", "snapshotId": "s", "op": "insert",
                   "kind": "text", "props": {"text": "hi", "x": 1, "y": 2}})
    with pytest.raises(jsonschema.ValidationError):
        edit.validate({"figure": "fig1", "expectedRevision": "r", "snapshotId": "s", "op": "run_python"})
    figure = jsonschema.Draft202012Validator(tools["figure"]["outputSchema"])
    figure.validate({"figure": "f", "revision": "r", "snapshotId": "s", "elements": [],
                     "scene": {"uri": "u", "type": "fignimble.scene", "revision": "r"},
                     "preview": None, "thumb": None})


def test_probe_renders_with_the_packaged_engine(staged):
    done = subprocess.run([str(PYTHON), str(staged / "probe.py")], capture_output=True, text=True,
                          timeout=300, cwd=str(staged))
    assert done.returncode == 0, done.stderr[-2000:]
    result = json.loads(done.stdout.strip().splitlines()[-1])
    assert result["ok"] is True
    assert result["files"]["png"] > 500 and result["files"]["pdf"] > 500


def test_release_descriptor_names_real_files():
    descriptor = json.loads((PLUGIN / "release.json").read_text())
    for name in descriptor["packageFiles"]:
        assert (PLUGIN / name).is_file(), name
    for name in descriptor["packageDirs"]:
        assert (PLUGIN / name).is_dir(), name
    assert json.loads((PLUGIN / "runtime-plan.json").read_text())["schemaVersion"] == "gewu.runtime-plan/v1"
