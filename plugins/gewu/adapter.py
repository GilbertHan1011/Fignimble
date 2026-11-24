"""GeWu adapter for Fignimble: figure project, tools, resources and previews.

The Fignimble engine owns the Python project, the source edits and the undo
history; this adapter only translates GeWu's protocol into its JSON lines. All
geometry stays in millimetres with the origin at the figure's top-left.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
from urllib.parse import quote, unquote

from gewu_plugin import ProtocolError, serve

from engine_client import Engine

MIME = {
    "fignimble.source": "text/x-python",
    "fignimble.scene": "application/json",
    "fignimble.preview": "image/png",
    "fignimble.thumb": "image/png",
    "fignimble.sprite": "image/png",
    "fignimble.export": None,          # by suffix
    "fignimble.provenance": "application/json",
}
EXPORT_MIME = {
    ".pdf": "application/pdf", ".svg": "image/svg+xml", ".png": "image/png",
    ".tif": "image/tiff", ".tiff": "image/tiff", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
}
EXPORTS = {"pdf", "svg", "png", "tiff", "jpg"}
SKIP_DIRS = {".fignimble", "__pycache__", ".git", "node_modules", ".venv", ".gewu"}
HASHED_TEXT = {".py", ".txt", ".csv", ".tsv", ".json", ".md"}
SCENE_LIMIT = 16 * 1024 * 1024
MAX_ELEMENTS = 2000

# One row per native edit operation the adapter accepts.
EDIT_OPS = {
    "set", "move", "resize", "endpoints", "insert", "delete", "duplicate", "order",
    "align", "distribute", "match", "group", "ungroup",
    "figure", "style", "labels",
    "guide_add", "guide_move", "guide_delete", "guide_clear",
    "panel_text", "panel_text_style", "panel_text_reset", "panel_color",
    "make_layout", "release_layout", "divider", "crop", "rotate", "flip",
}
ELEMENT_LISTS = ("oids",)
PAGE_DEFAULTS = {"cursor": 0, "limit": 50, "max": 200}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def inside(root: Path, value: str | Path) -> Path:
    path = (root / value).resolve()
    if path != root and not path.is_relative_to(root):
        raise ProtocolError("INVALID_PATH", "Path is outside the bound project")
    return path


def from_uri(root: Path, uri: str) -> Path:
    if not isinstance(uri, str) or not uri.startswith("workspace:///"):
        raise ProtocolError("INVALID_RESOURCE", "Expected a workspace:/// URI")
    value = unquote(uri.removeprefix("workspace:///"))
    if not value or value.startswith("/") or "\x00" in value or any(p == ".." for p in value.split("/")):
        raise ProtocolError("INVALID_RESOURCE", "Invalid workspace URI")
    return inside(root, value)


def ref_only(ref: dict) -> dict:
    """A ResourceRef has exactly uri/type/mimeType/revision; sprite boxes stay in scene data."""
    return {key: ref[key] for key in ("uri", "type", "mimeType", "revision") if key in ref}


def page_args(args: dict) -> tuple[int, int]:
    try:
        cursor, limit = int(args.get("cursor", 0)), int(args.get("limit", PAGE_DEFAULTS["limit"]))
    except (TypeError, ValueError):
        raise ProtocolError("INVALID_ARGUMENT", "cursor and limit must be integers") from None
    if cursor < 0 or limit < 1 or limit > PAGE_DEFAULTS["max"]:
        raise ProtocolError("INVALID_ARGUMENT", f"cursor >= 0 and 1 <= limit <= {PAGE_DEFAULTS['max']} are required")
    return cursor, limit


class Adapter:
    def __init__(self):
        self.engine: Engine | None = None
        self.lock = None
        self.snapshots: dict[str, dict] = {}
        self.version = 0
        self.dirty = False
        self.foreground_lock = threading.Lock()

    # --- lifecycle ---

    def activate(self, params: dict):
        self.workspace = Path(params["workspaceRoot"]).resolve(strict=True)
        binding = params.get("bindingResource") or {}
        if binding.get("type") != "fignimble.project":
            raise ProtocolError("PROJECT_REQUIRED", "Select a workspace folder as a Fignimble figure project")
        self.project = from_uri(self.workspace, binding["uri"])
        if not self.project.is_dir():
            raise ProtocolError("PROJECT_NOT_FOUND", "The figure project folder does not exist")
        settings = params.get("settings") or {}
        plugin_root = Path(os.environ.get("GEWU_PLUGIN_ROOT") or Path(__file__).resolve().parent).resolve()
        runtime_root = os.environ.get("GEWU_RUNTIME_ROOT")
        python = None
        if runtime_root:
            for candidate in ("bin/python", "bin/python3"):
                path = Path(runtime_root) / candidate
                if path.is_file():
                    python = path
                    break
        python = python or (Path(settings["python"]).absolute() if settings.get("python")
                            else Path(os.environ.get("FIGNIMBLE_GEWU_PYTHON", "python3")).absolute())
        packaged = plugin_root / "engine" / "fignimble" / "rpc.py"
        engine_root = Path(settings["engineRoot"]).resolve() if settings.get("engineRoot") else plugin_root / "engine"
        self.plugin_root, self.engine_root = plugin_root, engine_root
        if not (engine_root / "fignimble" / "rpc.py").is_file():
            raise ProtocolError("ENGINE_UNAVAILABLE", "The Fignimble engine is missing; install the plugin or set engineRoot")
        if not python.is_file() or not os.access(python, os.X_OK):
            raise ProtocolError("PYTHON_UNAVAILABLE", "Configure an executable Python with Fignimble's dependencies")
        probe = subprocess.run(
            [str(python), "-c", "import matplotlib, fitz, PIL, numpy"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
        if probe.returncode:
            raise ProtocolError("DEPENDENCIES_MISSING",
                                "The Fignimble Python cannot import matplotlib, PyMuPDF, Pillow and NumPy")
        key = hashlib.sha256(os.fsencode(self.project)).hexdigest()[:16]
        base = self.workspace / ".gewu" / "fignimble" / key
        self.cache = base
        (base / "snapshots").mkdir(parents=True, exist_ok=True)
        self.lock = (base / "engine.lock").open("a")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close()
            self.lock = None
            raise ProtocolError("PROJECT_IN_USE", "This project is already open in another Fignimble instance") from None
        self.engine = Engine(python, engine_root, self.project, base, on_event=self.on_event)
        try:
            self.engine.request("open", project=str(self.project), manageAgentFiles=False, timeout=60)
            self.engine.request("state", timeout=60)
        except BaseException:
            self.deactivate({})
            raise
        tools = json.loads((plugin_root / "tools.schema.json").read_text())
        return {"tools": tools, "serviceEndpoints": []}

    def on_event(self, message: dict):
        if message.get("event") in ("changed", "rendered"):
            self.version += 1

    def deactivate(self, _params):
        stopped = True
        if self.engine:
            try:
                stopped = self.engine.close()
            finally:
                self.engine = None
        if self.lock:
            self.lock.close()
            self.lock = None
        if not stopped:
            raise ProtocolError("CLEANUP_INCOMPLETE", "The Fignimble engine did not stop", retryable=False)

    # --- project revisions ---

    def _files(self):
        for dirpath, dirs, files in os.walk(self.project):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
            for name in sorted(files):
                if name.startswith(".") or name.endswith((".tmp", ".pyc")):
                    continue
                yield Path(dirpath) / name

    def document_revision(self) -> str:
        parts = []
        for path in self._files():
            rel = path.relative_to(self.project).as_posix()
            try:
                if path.suffix.lower() in HASHED_TEXT:
                    parts.append(f"{rel}:{sha256(path)}")
                else:
                    st = path.stat()
                    parts.append(f"{rel}:{st.st_mtime_ns}:{st.st_size}")
            except OSError:
                continue
        return hashlib.sha256("\n".join(parts).encode()).hexdigest()

    def source_revisions(self) -> dict[str, str]:
        """Revision of every project file; large binaries use mtime+size instead of a content hash."""
        out = {}
        for path in self._files():
            try:
                if path.suffix.lower() in HASHED_TEXT:
                    out[path.relative_to(self.project).as_posix()] = sha256(path)
                else:
                    st = path.stat()
                    out[path.relative_to(self.project).as_posix()] = f"{st.st_mtime_ns}:{st.st_size}"
            except OSError:
                continue
        return out

    def changes(self, before: dict[str, str]) -> tuple[list[dict], list[dict]]:
        after = self.source_revisions()
        changes, resources = [], []
        for rel, now in after.items():
            was = before.get(rel)
            if was == now:
                continue
            ref = self.reference(self.project / rel, "fignimble.source")
            changes.append({"uri": ref["uri"], "beforeRevision": was, "afterRevision": now})
            resources.append(ref)
        for rel, was in before.items():
            if rel not in after:
                changes.append({"uri": "workspace:///" + quote(rel), "beforeRevision": was,
                                "afterRevision": "deleted"})
        return changes, resources

    def check_revision(self, expected):
        current = self.document_revision()
        if expected != current:
            raise ProtocolError("STALE_REVISION",
                                "The project changed since it was read; call state/figure and retry")
        return current

    # --- resources ---

    def reference(self, path: Path, kind: str) -> dict:
        path = path.resolve()
        if not path.is_file() or not path.is_relative_to(self.workspace):
            raise ProtocolError("FILE_UNAVAILABLE", "The %s file is missing" % kind)
        if kind == "fignimble.export":
            mime = EXPORT_MIME.get(path.suffix.lower(), "application/octet-stream")
        else:
            mime = MIME[kind]
        return {"uri": "workspace:///" + quote(path.relative_to(self.workspace).as_posix()),
                "type": kind, "mimeType": mime, "revision": sha256(path)}

    def resolve(self, ref: dict):
        path = from_uri(self.workspace, ref["uri"])
        kind = ref.get("type")
        if kind == "fignimble.source":
            allowed = path.is_relative_to(self.project) and path.suffix == ".py"
        elif kind in ("fignimble.preview", "fignimble.thumb", "fignimble.scene"):
            allowed = path.is_relative_to(self.cache / "snapshots") or (
                kind == "fignimble.thumb" and path.is_relative_to(self.project / ".fignimble"))
        elif kind == "fignimble.sprite":
            allowed = path.is_relative_to(self.project / ".fignimble") and path.suffix == ".png"
        elif kind in ("fignimble.export", "fignimble.provenance"):
            allowed = path.is_relative_to(self.workspace / ".gewu" / "outputs")
        else:
            allowed = False
        if not allowed:
            raise ProtocolError("INVALID_RESOURCE", "This file is not a %s of the project" % kind)
        current = self.reference(path, kind)
        if ref.get("revision", current["revision"]) != current["revision"]:
            raise ProtocolError("STALE_REVISION", "The resource changed; refresh it first")
        return {"kind": "file", "path": str(path), "mimeType": current["mimeType"],
                "revision": current["revision"]}

    # --- snapshots ---

    def _scene(self, result: dict, figure: str, revision: str) -> dict:
        """The render, with every file path turned into a resource the view can fetch."""
        scene = dict(result)
        scene["schemaVersion"] = "fignimble.scene/v1"
        scene["figure"] = figure
        scene["documentRevision"] = revision
        scene.pop("thumb", None)
        scene.pop("preview", None)
        if scene.get("file"):
            scene["file"] = Path(scene["file"]).relative_to(self.project).as_posix()
        def with_sprite(info: dict) -> dict:
            item = dict(info)
            sprite = item.pop("sprite", None)
            if sprite and Path(sprite["file"]).is_file():
                ref = self.reference(Path(sprite["file"]), "fignimble.sprite")
                item["sprite"] = {**ref, "x": sprite["x"], "y": sprite["y"], "w": sprite["w"], "h": sprite["h"]}
            return item

        scene["elements"] = [with_sprite(info) for info in result.get("elements", [])]
        scene["labels"] = [with_sprite(info) for info in result.get("labels", [])]
        return scene

    def snapshot(self, figure: str, result: dict, px: float) -> tuple[str, dict]:
        revision = self.document_revision()
        ident = hashlib.sha256(
            json.dumps([revision, figure, result.get("file"), px, result.get("dark", False)]).encode()
        ).hexdigest()[:16]
        directory = self.cache / "snapshots" / ident
        scene = self._scene(result, figure, revision)
        if not directory.exists():
            directory.mkdir(parents=True)
            for key in ("preview", "thumb"):
                src = result.get(key)
                if src and Path(src).is_file():
                    shutil.copy2(src, directory / f"{key}.png")
            (directory / "scene.json").write_text(json.dumps(scene, sort_keys=True, allow_nan=False) + "\n")
        preview = directory / "preview.png"
        thumb = directory / "thumb.png"
        self.snapshots[ident] = {"figure": figure, "revision": revision, "px": px,
                                 "oids": {i["oid"] for i in result.get("elements", []) + result.get("labels", [])}}
        while len(self.snapshots) > 8:
            self.snapshots.pop(next(iter(self.snapshots)))
        self.version += 1
        return ident, {
            "snapshotId": ident,
            "revision": revision,
            "scene": self.reference(directory / "scene.json", "fignimble.scene"),
            "preview": self.reference(preview, "fignimble.preview") if preview.is_file() else None,
            "thumb": self.reference(thumb, "fignimble.thumb") if thumb.is_file() else None,
            "limits": {"elements": MAX_ELEMENTS, "sceneBytes": SCENE_LIMIT},
        }

    def use_snapshot(self, snapshot_id: str, figure: str) -> dict:
        snap = self.snapshots.get(snapshot_id)
        if snap is None:
            raise ProtocolError("STALE_SNAPSHOT", "That preview is gone; call figure again")
        if snap["figure"] != figure:
            raise ProtocolError("STALE_SNAPSHOT", "That preview is of another figure")
        if snap["revision"] != self.document_revision():
            raise ProtocolError("STALE_SNAPSHOT", "The project changed since that preview; refresh it first")
        return snap

    # --- tools ---

    def call(self, tool: str, args: dict, context: dict, control):
        args = dict(args, _callId=context.get("callId"))
        try:
            handler = getattr(self, f"tool_{tool}", None)
            if handler is None:
                raise ProtocolError("INVALID_CALL", "Unsupported Fignimble tool")
            if tool in ("state", "figure", "source", "render", "preflight", "editor_state", "assets", "journals"):
                return handler(args, control)
            with self.foreground_lock:
                if control.cancelled.is_set():
                    raise ProtocolError("CANCELLED", "The call was cancelled before it ran")
                return handler(args, control)
        except ProtocolError as error:
            return {"ok": False, "error": error.payload, "resources": []}
        except (KeyError, TypeError, ValueError, OSError) as error:
            return {"ok": False, "error": {"code": "INVALID_CALL", "message": str(error)[:1000],
                                           "retryable": False}, "resources": []}

    @staticmethod
    def _success(data, resources=(), warnings=None, changes=None):
        out = {"ok": True, "data": data, "resources": [ref_only(ref) for ref in resources if ref]}
        if warnings:
            out["warnings"] = list(warnings)
        if changes:
            out["changes"] = changes
        return out

    def tool_state(self, args, _control):
        cursor, limit = page_args(args)
        state = self.engine.request("state", timeout=60)
        revision = self.document_revision()
        figures = state.get("figures", [])
        window = figures[cursor:cursor + limit]
        items = []
        for fig in window:
            item = {"name": fig["name"], "file": fig["file"], "error": fig.get("error"),
                    "warnings": fig.get("warnings", 0)}
            thumb = fig.get("thumb")
            if thumb and Path(thumb).is_file():
                item["thumb"] = self.reference(Path(thumb), "fignimble.thumb")
            items.append(item)
        data = {"project": self.project.relative_to(self.workspace).as_posix() or ".",
                "revision": revision, "figures": items,
                "canUndo": bool(state.get("canUndo")), "canRedo": bool(state.get("canRedo")),
                "undoLabel": state.get("undoLabel"), "redoLabel": state.get("redoLabel"),
                "engine": {"version": self._version(), "preview": True, "cancel": True},
                "limits": {"cursor": cursor, "limit": limit, "total": len(figures),
                           "next": cursor + limit if cursor + limit < len(figures) else None}}
        return self._success(data)

    def _version(self) -> str:
        for path in (self.plugin_root, self.engine_root.parent, self.project):
            version = path / "VERSION"
            if version.is_file():
                return version.read_text().strip()
        return "unknown"

    def tool_figure(self, args, control):
        cursor, limit = page_args(args)
        name = self.figure_name(args)
        result = self.engine.request("figure", name=name, pxPerMM=float(args.get("pxPerMM", 12)),
                                     preview=True, timeout=200, control=control)
        if result.get("error"):
            raise ProtocolError("RENDER_FAILED", result["error"][:2000])
        if len(result.get("elements", [])) + len(result.get("labels", [])) > MAX_ELEMENTS:
            raise ProtocolError("LIMIT_EXCEEDED",
                                f"This figure has more than {MAX_ELEMENTS} elements; split it into figures")
        sid, refs = self.snapshot(name, result, float(args.get("pxPerMM", 12)))
        scene = json.loads((self.cache / "snapshots" / sid / "scene.json").read_text())
        elements = scene["elements"][cursor:cursor + limit]
        warnings = result.get("warnings", [])
        data = {"figure": name, "size": result.get("size"),
                "dark": bool(result.get("dark")), "elements": elements,
                "labels": scene.get("labels", []), "guides": scene.get("guides", []),
                "style": result.get("style"), "labelStyle": result.get("labelStyle"),
                "journal": result.get("journal"),
                "warnings": {"errors": len([w for w in warnings if w["level"] == "error"]),
                             "warnings": len([w for w in warnings if w["level"] == "warning"]),
                             "total": len(warnings)},
                "page": {"cursor": cursor, "limit": limit, "total": len(scene["elements"]),
                         "next": cursor + limit if cursor + limit < len(scene["elements"]) else None},
                **refs}
        resources = [ref for ref in (refs["scene"], refs["preview"], refs["thumb"]) if ref]
        resources += [i["sprite"] for i in elements if i.get("sprite")]
        return self._success(data, resources)

    def figure_name(self, args) -> str:
        name = args.get("figure")
        if not isinstance(name, str) or not name:
            raise ProtocolError("INVALID_ARGUMENT", "figure is required")
        return name

    def tool_render(self, args, control):
        name = self.figure_name(args)
        result = self.engine.request("figure", name=name, pxPerMM=float(args.get("pxPerMM", 12)),
                                     preview=True, dark=bool(args.get("dark", False)),
                                     timeout=200, control=control)
        if result.get("error"):
            raise ProtocolError("RENDER_FAILED", result["error"][:2000])
        sid, refs = self.snapshot(name, result, float(args.get("pxPerMM", 12)))
        warnings = result.get("warnings", [])
        data = {"figure": name, "size": result.get("size"), "dark": bool(result.get("dark")),
                "elements": len(result.get("elements", [])), "warnings": len(warnings),
                **refs}
        resources = [ref for ref in (refs["scene"], refs["preview"], refs["thumb"]) if ref]
        return self._success(data, resources)

    def tool_preflight(self, args, control):
        cursor, limit = page_args(args)
        name = self.figure_name(args)
        result = self.engine.request("figure", name=name, pxPerMM=4, preview=False, timeout=200, control=control)
        if result.get("error"):
            raise ProtocolError("RENDER_FAILED", result["error"][:2000])
        warnings = result.get("warnings", [])
        counts = {level: len([w for w in warnings if w["level"] == level])
                  for level in ("error", "warning", "info")}
        window = warnings[cursor:cursor + limit]
        data = {"figure": name, "counts": counts, "warnings": window,
                "page": {"cursor": cursor, "limit": limit, "total": len(warnings),
                         "next": cursor + limit if cursor + limit < len(warnings) else None},
                "revision": self.document_revision()}
        return self._success(data, warnings=[w["message"] for w in window if w["level"] == "error"])

    def tool_new_figure(self, args, control):
        before = self.source_revisions()
        expected = args.get("expectedRevision")
        if expected is not None:
            self.check_revision(expected)
        name = args.get("name") or "fig"
        if not isinstance(name, str):
            raise ProtocolError("INVALID_ARGUMENT", "name must be a string")
        result = self.engine.request("new_figure", name=name, width=float(args.get("width", 183)),
                                     height=float(args.get("height", 120)), journal=args.get("journal"),
                                     strict=True, timeout=60, control=control)
        if not result.get("ok"):
            message = str(result.get("error") or "The figure was not created")
            code = "ALREADY_EXISTS" if message.startswith("ALREADY_EXISTS") else "EDIT_FAILED"
            raise ProtocolError(code, message.replace("ALREADY_EXISTS: ", "")[:2000])
        changes, resources = self.changes(before)
        data = {"figure": result["name"], "revision": self.document_revision()}
        return self._success(data, resources, changes=changes)

    def tool_source(self, args, _control):
        rel = args.get("file")
        if not isinstance(rel, str) or not rel.endswith(".py"):
            raise ProtocolError("INVALID_ARGUMENT", "file must be a project .py path")
        path = inside(self.project, rel)
        if not path.is_file():
            raise ProtocolError("FILE_UNAVAILABLE", "There is no such file in the project")
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        try:
            start = max(0, int(args.get("startLine", 0)))
            count = min(400, max(1, int(args.get("maxLines", 120))))
        except (TypeError, ValueError):
            raise ProtocolError("INVALID_ARGUMENT", "startLine and maxLines must be integers") from None
        window = lines[start:start + count]
        ref = self.reference(path, "fignimble.source")
        data = {"file": path.relative_to(self.project).as_posix(), "revision": ref["revision"],
                "totalLines": len(lines), "startLine": start,
                "text": "\n".join(window), "truncated": start + count < len(lines), "source": ref}
        return self._success(data, [ref])

    def tool_edit_source(self, args, control):
        rel = args.get("file")
        text = args.get("text")
        if not isinstance(rel, str) or not rel.endswith(".py"):
            raise ProtocolError("INVALID_ARGUMENT", "file must be a project .py path")
        if not isinstance(text, str):
            raise ProtocolError("INVALID_ARGUMENT", "text is required")
        if len(text.encode()) > 256 * 1024:
            raise ProtocolError("LIMIT_EXCEEDED", "Source files are limited to 256 KiB")
        path = inside(self.project, rel)
        if "expectedRevision" not in args:
            raise ProtocolError("INVALID_ARGUMENT", "expectedRevision is required (null to create a file)")
        expected = args["expectedRevision"]
        current = sha256(path) if path.is_file() else None
        if expected != current:
            raise ProtocolError("STALE_REVISION", "The file changed since it was read; reload it first")
        before = self.source_revisions()
        result = self.engine.request("write_source", file=str(path), text=text,
                                     figure=args.get("figure"), preview=True,
                                     expectedRevision=expected, timeout=200, control=control)
        changes, resources = self.changes(before)
        revision = self.document_revision()
        ref = self.reference(path, "fignimble.source") if path.is_file() else None
        if not result.get("ok"):
            raise ProtocolError("EDIT_FAILED", str(result.get("error") or "The file was not written")[:2000])
        data = {"file": path.relative_to(self.project).as_posix(), "revision": revision,
                "fileRevision": ref["revision"] if ref else None}
        if ref:
            data["source"] = ref
        figure = args.get("figure")
        if figure and result.get("figure"):
            sid, refs = self.snapshot(figure, result["figure"], 12)
            data.update(refs)
            resources = [ref, refs["scene"], refs["preview"]]
        return self._success(data, [r for r in resources if r], changes=changes)

    def tool_edit(self, args, control):
        figure = self.figure_name(args)
        op = args.get("op")
        if op not in EDIT_OPS:
            raise ProtocolError("INVALID_ARGUMENT", f"op must be one of: {', '.join(sorted(EDIT_OPS))}")
        revision = self.check_revision(args.get("expectedRevision"))
        snap = self.use_snapshot(args.get("snapshotId"), figure)
        for key in ELEMENT_LISTS:
            for oid in args.get(key) or []:
                if str(oid) not in snap["oids"]:
                    raise ProtocolError("STALE_SNAPSHOT", f"Element {oid} is not in that preview; refresh it first")
        payload = {k: v for k, v in args.items()
                   if k not in ("figure", "expectedRevision", "snapshotId")}
        before = self.source_revisions()
        result = self.engine.request("edit", figure=figure, pxPerMM=snap["px"], preview=True, timeout=200,
                                     control=control, **payload)
        changes, resources = self.changes(before)
        if not result.get("ok"):
            raise ProtocolError("EDIT_FAILED", str(result.get("error") or "The edit was refused")[:2000])
        data = {"figure": figure, "revision": self.document_revision(), "unchanged": bool(result.get("unchanged"))}
        if result.get("figure"):
            sid, refs = self.snapshot(figure, result["figure"], snap["px"])
            data.update(refs)
            data["select"] = result.get("select", [])
            resources = [refs["scene"], refs["preview"], refs["thumb"]]
        self.dirty = True
        return self._success(data, [r for r in resources if r], changes=changes)

    def _history(self, args, control, command):
        revision = self.check_revision(args.get("expectedRevision"))
        before = self.source_revisions()
        result = self.engine.request(command, figure=args.get("figure"), preview=True, timeout=200, control=control)
        changes, resources = self.changes(before)
        if not result.get("ok"):
            message = str(result.get("error") or "Nothing to " + command)
            code = "UNDO_CONFLICT" if "changed since" in message else "EDIT_FAILED"
            raise ProtocolError(code, message[:2000], retryable=False)
        data = {"label": result.get("label"), "revision": self.document_revision()}
        figure = args.get("figure")
        if figure and result.get("figure"):
            sid, refs = self.snapshot(figure, result["figure"], 12)
            data.update(refs)
            resources = [refs["scene"], refs["preview"]]
        return self._success(data, [r for r in resources if r], changes=changes)

    def tool_undo(self, args, control):
        return self._history(args, control, "undo")

    def tool_redo(self, args, control):
        return self._history(args, control, "redo")

    def tool_import_asset(self, args, control):
        figure = self.figure_name(args)
        path = from_uri(self.workspace, args["path"]) if str(args.get("path", "")).startswith("workspace:///") \
            else inside(self.workspace, args.get("path", ""))
        if not path.is_file():
            raise ProtocolError("FILE_UNAVAILABLE", "There is no such file in the workspace")
        self.check_revision(args.get("expectedRevision"))
        self.use_snapshot(args.get("snapshotId"), figure)
        before = self.source_revisions()
        result = self.engine.request("import_file", figure=figure, path=str(path),
                                     x=float(args.get("x", 5)), y=float(args.get("y", 5)),
                                     w=args.get("w"), label=args.get("label"), preview=True,
                                     pxPerMM=float(args.get("pxPerMM", 12)), timeout=200, control=control)
        changes, resources = self.changes(before)
        if not result.get("ok"):
            raise ProtocolError("EDIT_FAILED", str(result.get("error") or "The file was not imported")[:2000])
        data = {"figure": figure, "revision": self.document_revision(),
                "file": result.get("file")}
        if result.get("figure"):
            sid, refs = self.snapshot(figure, result["figure"], 12)
            data.update(refs)
            resources = [refs["scene"], refs["preview"]]
        return self._success(data, [r for r in resources if r], changes=changes)

    def tool_export(self, args, control):
        figure = self.figure_name(args)
        fmt = str(args.get("format") or "").lower()
        if fmt not in EXPORTS:
            raise ProtocolError("INVALID_ARGUMENT", f"format must be one of: {', '.join(sorted(EXPORTS))}")
        revision = self.check_revision(args.get("expectedRevision"))
        call_dir = hashlib.sha256(str(args.get("_callId") or os.urandom(8)).encode()).hexdigest()[:16]
        output = self.workspace / ".gewu" / "outputs" / call_dir
        output.mkdir(parents=True, exist_ok=False)
        path = output / f"{figure}.{fmt}"
        result = self.engine.request("export", figure=figure, path=str(path), format=fmt,
                                     dpi=int(args.get("dpi", 600)), journal=args.get("journal"),
                                     dark=bool(args.get("dark", False)), timeout=600, control=control)
        if not result.get("ok"):
            raise ProtocolError("EXPORT_FAILED", str(result.get("error") or "The export failed")[:2000])
        if not path.is_file() or path.stat().st_size == 0:
            raise ProtocolError("EXPORT_FAILED", "The engine did not write a readable file")
        provenance = {
            "schemaVersion": "fignimble.export/v1",
            "figure": figure, "format": fmt, "dpi": int(args.get("dpi", 600)),
            "journal": args.get("journal"), "dark": bool(args.get("dark", False)),
            "documentRevision": revision,
            "engineVersion": self._version(),
            "output": path.name, "sha256": sha256(path), "bytes": path.stat().st_size,
            "resolution": result.get("resolution"), "warnings": result.get("warnings", []),
        }
        (output / "provenance.json").write_text(json.dumps(provenance, sort_keys=True, indent=2) + "\n")
        export_ref = self.reference(path, "fignimble.export")
        prov_ref = self.reference(output / "provenance.json", "fignimble.provenance")
        data = {"figure": figure, "format": fmt, "filename": path.name,
                "sha256": provenance["sha256"], "bytes": provenance["bytes"],
                "resolution": result.get("resolution", {}), "export": export_ref,
                "provenance": prov_ref, "revision": self.document_revision()}
        return self._success(data, [export_ref, prov_ref], warnings=result.get("warnings"))

    # --- view-only tools ---

    def tool_editor_state(self, args, _control):
        try:
            after = int(args.get("afterVersion", -1))
        except (TypeError, ValueError):
            raise ProtocolError("INVALID_ARGUMENT", "afterVersion must be an integer") from None
        state = self.engine.request("state", timeout=30)
        data = {"version": self.version, "changed": self.version != after,
                "dirty": self.dirty, "revision": self.document_revision(),
                "canUndo": bool(state.get("canUndo")), "canRedo": bool(state.get("canRedo")),
                "undoLabel": state.get("undoLabel"), "redoLabel": state.get("redoLabel")}
        return self._success(data)

    def tool_assets(self, args, _control):
        cursor, limit = page_args(args)
        base = inside(self.workspace, args.get("directory", ""))
        if not base.is_dir():
            raise ProtocolError("FILE_UNAVAILABLE", "There is no such folder in the workspace")
        allowed = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".pdf", ".svg", ".py", ".csv", ".tsv"}
        items = []
        for dirpath, dirs, files in os.walk(base):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
            for name in sorted(files):
                path = Path(dirpath) / name
                if path.suffix.lower() in allowed and path.is_file():
                    items.append({"path": path.relative_to(self.workspace).as_posix(),
                                  "bytes": path.stat().st_size, "kind": path.suffix.lower().lstrip(".")})
        window = items[cursor:cursor + limit]
        data = {"assets": window, "page": {"cursor": cursor, "limit": limit, "total": len(items),
                                           "next": cursor + limit if cursor + limit < len(items) else None}}
        return self._success(data)

    def tool_journals(self, args, _control):
        return self._success({"journals": self.engine.request("journals", timeout=30)})


if __name__ == "__main__":
    adapter = Adapter()
    try:
        serve(activate=adapter.activate, call=adapter.call, resolve=adapter.resolve,
              deactivate=adapter.deactivate)
    finally:
        try:
            adapter.deactivate({})
        except ProtocolError:
            pass
