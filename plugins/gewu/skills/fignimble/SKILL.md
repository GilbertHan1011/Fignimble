---
name: fignimble
description: Use when laying out a publication figure in a GeWu Fignimble project (multi-panel figures, panel letters, patchwork layouts, mm positions, journal export), or when a figure project, panel source, preflight warning or figure export is mentioned.
---

# Fignimble figures in GeWu

A figure project is Python. `fig1.py` places elements in millimetres from the
top-left (y down); `panels/*.py` draw matplotlib panels; `style.py` holds the one
shared `Style` and `Labels`. The GeWu plugin's tools and the Preview canvas edit
the same files through the Fignimble engine, including one undo history.

## Use the tools, not the 3-D desktop app

`state` → `figure` → `edit` → `preflight` → `export`.

- `figure` returns `revision` (project sources) and `snapshotId` (this render).
  Every `edit` needs both; `edit_source`/`new_figure`/`export`/`undo`/`redo` need
  the revision. On `STALE_REVISION` or `STALE_SNAPSHOT`, read again instead of
  retrying with old values.
- `edit` takes one native operation: `move {oids, dx, dy}`, `resize {oid, box}`
  (`box` is `[x, y, w, h]` mm), `align {oids, how, to}`, `distribute {oids, axis}`,
  `insert {kind, props}`, `delete`, `duplicate`, `group`, `make_layout`,
  `divider {oid, index, delta}`, `set {oid, props}`, `panel_text`, `panel_color`,
  `crop`, `rotate`, `flip` and the other names in the tool schema.
- Positions stay literal numbers so they remain draggable. Do not compute
  coordinates in an expression like `x=a.right + 2`; keep numbers.
- Panel letters are automatic and re-lettered when panels move. Never draw a
  letter yourself, and keep fonts/sizes in `Style`/`Labels` unless the user asks
  for an exception.
- Picture imports go through `import_asset` with a workspace path. The engine
  copies them into the project's `images/`, `tables/` or `panels/`.
- `export` writes a new file per call with `provenance.json`; report the file,
  format, dpi, journal and any warnings. Do not claim a journal's font or dpi
  when preflight reports a fallback or a shortfall.

## Looking at your work

`figure`/`render` return a preview resource the GeWu UI can show; read the
returned element boxes and `preflight` counts. A stale preview is never proof of
the current state. Re-render after a source change.

## Source edits

`source` reads with `revision`; `edit_source` sends that revision (or `null` to
create a file). Use it for panel code, `style.py` and figure calls the canvas
operations do not cover. One save is one undo step.

## Limits

Undo is per running instance. Files are replaced atomically per file; a
multi-file edit is not a filesystem transaction. CMYK/EPS/outline exports need
Ghostscript, which the core runtime does not provide.
