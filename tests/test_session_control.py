"""The GeWu-facing engine additions: revisions, atomic writes, previews and cancellation."""

import ast
import os
import stat
import threading
import time
from pathlib import Path

import pytest

from fignimble.core import Cancelled, CancelToken, Session

STYLE = '''from fignimble import *
STYLE = Style(font="Arial", size=7, linewidth=0.6, palette="okabe-ito")
'''

FIGURE = '''from fignimble import *
from style import STYLE

fig = Figure(width=60, height=40, style=STYLE)
fig.text("hello", x=4, y=4, size=8)
'''

LOOPING = '''def draw(fig):
    while True:
        pass
'''


def project(tmp_path: Path) -> Path:
    (tmp_path / "style.py").write_text(STYLE)
    (tmp_path / "fig1.py").write_text(FIGURE)
    (tmp_path / "panels").mkdir()
    (tmp_path / "panels" / "loop.py").write_text(LOOPING)
    return tmp_path


def test_instruction_files_are_optional(tmp_path):
    root = project(tmp_path)
    quiet = Session(str(root), manage_agent_files=False)
    try:
        assert not (root / "CLAUDE.md").exists()
        assert not (root / "AGENTS.md").exists()
    finally:
        quiet.close()
    chatty = Session(str(root))
    try:
        assert (root / "AGENTS.md").is_file()
    finally:
        chatty.close()
    assert not (root / "AGENTS.md").exists()


def test_write_source_checks_revision_and_creates_files(tmp_path):
    root = project(tmp_path)
    session = Session(str(root), manage_agent_files=False)
    try:
        figure = root / "fig1.py"
        assert session.write_source({"file": str(figure), "text": FIGURE})["ok"] is True
        stale = session.write_source({"file": str(figure), "text": FIGURE, "expectedRevision": "0" * 64})
        assert stale["ok"] is False and "STALE_REVISION" in stale["error"]
        assert figure.read_text() == FIGURE
        fresh = session.write_source({"file": str(figure), "text": FIGURE + "\n# note\n",
                                      "expectedRevision": __import__("hashlib").sha256(
                                          figure.read_bytes()).hexdigest()})
        assert fresh["ok"] is True and figure.read_text().endswith("# note\n")
        created = root / "panels" / "new.py"
        assert session.write_source({"file": str(created), "text": "def draw(fig):\n    pass\n",
                                     "expectedRevision": None})["ok"] is True
        assert created.is_file()
        refused = session.write_source({"file": str(created), "text": "x = 1\n", "expectedRevision": None})
        assert refused["ok"] is False and "STALE_REVISION" in refused["error"]
        assert "def draw" in created.read_text()
    finally:
        session.close()


def test_source_write_is_atomic_and_keeps_mode(tmp_path):
    root = project(tmp_path)
    session = Session(str(root), manage_agent_files=False)
    try:
        figure = root / "fig1.py"
        figure.chmod(0o640)
        assert session.write_source({"file": str(figure), "text": FIGURE + "\n# x\n"})["ok"]
        assert stat.S_IMODE(figure.stat().st_mode) == 0o640
        assert not list(root.glob("fig1.py.*.tmp"))
        ast.parse(figure.read_text())
    finally:
        session.close()


def test_undo_conflict_keeps_the_history(tmp_path):
    root = project(tmp_path)
    session = Session(str(root), manage_agent_files=False)
    try:
        data = session.api_figure({"name": "fig1"})
        moved = session.edit({"figure": "fig1", "op": "move", "oids": [data["elements"][0]["oid"]],
                              "dx": 2, "dy": 0})
        assert moved["ok"], moved
        assert len(session.history) == 1
        figure = root / "fig1.py"
        figure.write_text(figure.read_text().replace("hello", "bye"))
        assert len(session.history) == 1
        failed = session.undo({})
        assert failed["ok"] is False and "Can't undo" in failed["error"]
        assert len(session.history) == 1 and session.redo == []
        figure.write_text(FIGURE)
        assert session.undo({})["ok"] is True
        assert session.history == []
    finally:
        session.close()


def test_preview_png_is_the_whole_figure(tmp_path):
    root = project(tmp_path)
    session = Session(str(root), manage_agent_files=False)
    try:
        plain = session.api_figure({"name": "fig1"})
        assert "preview" not in plain
        shot = session.api_figure({"name": "fig1", "preview": True})
        path = Path(shot["preview"])
        assert path.is_file() and path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        assert (path.parent / path.name).stat().st_size > 500
    finally:
        session.close()


def test_cancel_stops_a_looping_panel(tmp_path):
    root = project(tmp_path)
    (root / "fig2.py").write_text('''from fignimble import *
from style import STYLE

fig = Figure(width=40, height=30, style=STYLE)
fig.panel("panels/loop.py", x=2, y=2, w=20, h=20)
''')
    session = Session(str(root), manage_agent_files=False)
    errors = []

    def render():
        session.bind(token)
        try:
            session.api_figure({"name": "fig2"})
        except BaseException as exc:                       # noqa: BLE001
            errors.append(exc)

    token = CancelToken()
    thread = threading.Thread(target=render)
    started = time.monotonic()
    thread.start()
    time.sleep(0.8)
    token.cancel()
    thread.join(timeout=15)
    session.bind(None)
    try:
        assert not thread.is_alive(), "the cancelled render did not stop"
        assert time.monotonic() - started < 12
        assert len(errors) == 1 and isinstance(errors[0], Cancelled)
        assert session.worker.proc is None                   # the worker that looped is gone
        assert session.api_figure({"name": "fig1"})["size"] == [60, 40]
    finally:
        session.close()
