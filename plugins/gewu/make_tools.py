#!/usr/bin/env python3
"""Write tools.schema.json: the tools the Fignimble adapter offers GeWu."""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAGE = {"cursor": {"type": "integer", "minimum": 0},
        "limit": {"type": "integer", "minimum": 1, "maximum": 200}}
REV = {"type": ["string", "null"]}
REF = {"type": "object", "required": ["uri", "type", "revision"],
       "properties": {"uri": {"type": "string"}, "type": {"type": "string"},
                      "mimeType": {"type": "string"}, "revision": {"type": "string"}}}
MAYBE_REF = {"anyOf": [REF, {"type": "null"}]}
SNAPSHOT = {"snapshotId": {"type": "string"}, "revision": {"type": "string"},
            "scene": REF, "preview": MAYBE_REF, "thumb": MAYBE_REF}


def out(required, properties):
    return {"type": "object", "required": required, "properties": properties}


def tool(name, description, props, required=(), output=None, ui=False, effect="read"):
    return {
        "name": name,
        "description": description,
        "effect": effect,
        "target": "backend",
        "exposeToAgent": not ui,
        "inputSchema": {"type": "object",
                        "additionalProperties": name == "edit",
                        "required": list(required), "properties": props},
        "outputSchema": output or out(["revision"], {"revision": {"type": "string"}}),
    }


TOOLS = [
    tool("state", "List the project's figures, current revision, undo/redo and engine capabilities. "
                  "Start here; every write needs the revision it returns.", dict(PAGE),
         output=out(["project", "revision", "figures"],
                    {"project": {"type": "string"}, "revision": {"type": "string"},
                     "figures": {"type": "array", "items": {"type": "object"}},
                     "canUndo": {"type": "boolean"}, "canRedo": {"type": "boolean"},
                     "undoLabel": {"type": ["string", "null"]}, "redoLabel": {"type": ["string", "null"]},
                     "engine": {"type": "object"}, "limits": {"type": "object"}})),
    tool("figure", "Read one figure: millimetre size, elements, labels, style, guides and warnings, plus a "
                   "preview, scene and sprite resources. Use its snapshotId for canvas edits.",
         {"figure": {"type": "string", "minLength": 1}, **PAGE,
          "pxPerMM": {"type": "number", "minimum": 1, "maximum": 30}}, ["figure"],
         output=out(["figure", "snapshotId", "revision", "elements"],
                    {"figure": {"type": "string"}, "size": {"type": "array"},
                     "elements": {"type": "array", "items": {"type": "object"}},
                     "labels": {"type": "array"}, "guides": {"type": "array"},
                     "warnings": {"type": "object"}, "page": {"type": "object"},
                     "style": {"type": "object"}, "labelStyle": {"type": "object"},
                     "journal": {"type": ["object", "null"]}, **SNAPSHOT})),
    tool("new_figure", "Create a figure file (and style.py when the project has none). An existing name is "
                       "an error; nothing is renamed.",
         {"name": {"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"},
          "width": {"type": "number", "exclusiveMinimum": 0, "maximum": 1000},
          "height": {"type": "number", "exclusiveMinimum": 0, "maximum": 1000},
          "journal": {"type": "string"}, "expectedRevision": REV},
         ["name", "width", "height"], effect="write",
         output=out(["figure", "revision"], {"figure": {"type": "string"}, "revision": {"type": "string"}})),
    tool("import_asset", "Place a workspace image (PNG/JPEG/TIFF/PDF/SVG), panel .py or CSV/TSV on a figure. "
                         "Files inside the workspace are copied into the project by the engine.",
         {"figure": {"type": "string"}, "path": {"type": "string", "minLength": 1},
          "x": {"type": "number"}, "y": {"type": "number"}, "w": {"type": "number", "exclusiveMinimum": 0},
          "label": {"type": ["string", "null"]}, "expectedRevision": {"type": "string"},
          "snapshotId": {"type": "string"}}, ["figure", "path", "expectedRevision", "snapshotId"],
         effect="write",
         output=out(["figure", "revision"], {"figure": {"type": "string"}, "revision": {"type": "string"},
                                            "file": {"type": "string"}, **SNAPSHOT})),
    tool("edit", "Change the figure with one native Fignimble operation: set, move, resize, endpoints, insert, "
                 "delete, duplicate, order, align, distribute, match, group, ungroup, figure, style, labels, "
                 "guide_*, panel_text*, panel_color, make_layout, release_layout, divider, crop, rotate, flip. "
                 "OIDs are the ones in that preview and the write needs its revision.",
         {"figure": {"type": "string"}, "expectedRevision": {"type": "string"},
          "snapshotId": {"type": "string"},
          "op": {"type": "string", "enum": [
              "set", "move", "resize", "endpoints", "insert", "delete", "duplicate", "order",
              "align", "distribute", "match", "group", "ungroup", "figure", "style", "labels",
              "guide_add", "guide_move", "guide_delete", "guide_clear", "panel_text",
              "panel_text_style", "panel_text_reset", "panel_color", "make_layout",
              "release_layout", "divider", "crop", "rotate", "flip"]},
          "oids": {"type": "array", "items": {"type": "string"}, "maxItems": 500}},
         ["figure", "expectedRevision", "snapshotId", "op"], effect="write",
         output=out(["figure", "revision"], {"figure": {"type": "string"}, "revision": {"type": "string"},
                                            "unchanged": {"type": "boolean"}, "select": {"type": "array"},
                                            **SNAPSHOT})),
    tool("source", "Read a figure, style or panel Python file, a bounded number of lines at a time.",
         {"file": {"type": "string", "pattern": "\\.py$"},
          "startLine": {"type": "integer", "minimum": 0},
          "maxLines": {"type": "integer", "minimum": 1, "maximum": 400}}, ["file"],
         output=out(["file", "revision", "text"],
                    {"file": {"type": "string"}, "revision": {"type": "string"},
                     "text": {"type": "string"}, "startLine": {"type": "integer"},
                     "totalLines": {"type": "integer"}, "truncated": {"type": "boolean"},
                     "source": REF})),
    tool("edit_source", "Write a project Python file after checking its revision (null creates a file). "
                        "The write is one undo step in the same history as canvas edits.",
         {"file": {"type": "string", "pattern": "\\.py$"}, "text": {"type": "string"},
          "expectedRevision": REV, "figure": {"type": "string"}},
         ["file", "text", "expectedRevision"], effect="write",
         output=out(["file", "revision"], {"file": {"type": "string"}, "revision": {"type": "string"},
                                          "source": REF, **SNAPSHOT})),
    tool("render", "Render a figure now: a full PNG preview, the scene resource and its warnings.",
         {"figure": {"type": "string"}, "dark": {"type": "boolean"},
          "pxPerMM": {"type": "number", "minimum": 1, "maximum": 30}}, ["figure"],
         output=out(["figure", "revision"], {"figure": {"type": "string"}, "revision": {"type": "string"},
                                            "size": {"type": "array"}, "elements": {"type": "integer"},
                                            "warnings": {"type": "integer"}, **SNAPSHOT})),
    tool("preflight", "The journal's quality checks for a figure: text size, picture dpi, Type 3 fonts, "
                      "out-of-figure elements, duplicate labels and figure width.",
         {"figure": {"type": "string"}, **PAGE}, ["figure"],
         output=out(["figure", "counts", "warnings"],
                    {"figure": {"type": "string"}, "counts": {"type": "object"},
                     "warnings": {"type": "array", "items": {"type": "object"}},
                     "page": {"type": "object"}, "revision": {"type": "string"}})),
    tool("undo", "Undo the last edit (canvas or source). A conflict with someone else's newer edit is "
                 "reported, and the history is kept.",
         {"expectedRevision": {"type": "string"}, "figure": {"type": "string"}},
         ["expectedRevision"], effect="write",
         output=out(["revision"], {"revision": {"type": "string"}, "label": {"type": ["string", "null"]},
                                  "figure": {"type": "string"}, **SNAPSHOT})),
    tool("redo", "Redo the last undone edit.", {"expectedRevision": {"type": "string"}, "figure": {"type": "string"}},
         ["expectedRevision"], effect="write",
         output=out(["revision"], {"revision": {"type": "string"}, "label": {"type": ["string", "null"]},
                                  "figure": {"type": "string"}, **SNAPSHOT})),
    tool("export", "Export a figure as PDF, SVG, PNG, TIFF or JPEG, with the journal's resolution rules, "
                   "and return the file plus provenance.",
         {"figure": {"type": "string"}, "format": {"type": "string", "enum": ["pdf", "svg", "png", "tiff", "jpg"]},
          "dpi": {"type": "integer", "minimum": 72, "maximum": 2400},
          "journal": {"type": "string"}, "dark": {"type": "boolean"},
          "expectedRevision": {"type": "string"}},
         ["figure", "format", "expectedRevision"], effect="write",
         output=out(["figure", "format", "sha256", "export"],
                    {"figure": {"type": "string"}, "format": {"type": "string"},
                     "filename": {"type": "string"}, "sha256": {"type": "string"},
                     "bytes": {"type": "integer"}, "resolution": {"type": "object"},
                     "export": REF, "provenance": REF, "revision": {"type": "string"}})),
    tool("editor_state", "The editor's change counter and undo state; poll it to notice outside edits.", dict(PAGE),
         ui=True,
         output=out(["version", "revision"], {"version": {"type": "integer"}, "changed": {"type": "boolean"},
                                             "dirty": {"type": "boolean"}, "revision": {"type": "string"},
                                             "canUndo": {"type": "boolean"}, "canRedo": {"type": "boolean"},
                                             "undoLabel": {"type": ["string", "null"]},
                                             "redoLabel": {"type": ["string", "null"]}})),
    tool("assets", "Files in the workspace that can be placed on a figure.",
         {"directory": {"type": "string"}, **PAGE}, ui=True,
         output=out(["assets"], {"assets": {"type": "array"}, "page": {"type": "object"}})),
    tool("journals", "The journal presets (widths, fonts, label style, resolutions).", {}, ui=True,
         output=out(["journals"], {"journals": {"type": "object"}})),
]


def main():
    (HERE / "tools.schema.json").write_text(json.dumps(TOOLS, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"tools": len(TOOLS), "agent": len([t for t in TOOLS if t["exposeToAgent"]])}))


if __name__ == "__main__":
    main()
