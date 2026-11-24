# Fignimble for GeWu

Lay out publication figures inside GeWu. The plugin opens a Fignimble project
from the workspace and shows a real editor in the Preview panel: drag and resize
panels, align and distribute, drive patchwork layouts, edit text and the shared
style, undo/redo, read preflight warnings and export. The same figure is a set
of Python files, and every canvas gesture is one Fignimble engine edit, so the
files and the canvas never disagree.

The desktop Fignimble is a macOS AppKit app and cannot run in an iframe. This
plugin reuses everything below it: the engine's renderer, the AST source edits,
the undo history and the JSON-lines protocol. The web page is a second client
of that engine, as `apps/windows/README.md` in Fignimble intends.

## What it offers

- **Figures**: thumbnails, millimetre canvas with rulers-equivalent geometry,
  zoom/pan, dark version, sprites drawn from one native render.
- **Arrange**: select, marquee, move, resize, line endpoints, keyboard nudges,
  align, distribute, match, group, order, lock/hide, guides.
- **Layouts**: make/release layout, divider grips, gap and widths written back
  to `widths=`/`heights=`; automatic panel letters and one shared `Labels`
  style.
- **Content**: insert text, arrows, lines, rectangles, ellipses and brackets;
  crop/rotate/flip pictures; edit a panel's drawn texts and colours; import
  PNG/JPEG/TIFF/PDF/SVG, panel `.py` and CSV/TSV from the workspace.
- **Code**: a source pane for the figure, `style.py` and the selected panel,
  with revision-checked saves in the same undo history as canvas edits.
- **Quality and output**: native preflight (font sizes, picture dpi, Type 3
  fonts, out-of-figure elements, duplicate labels, journal width) and PDF, SVG,
  PNG, TIFF or JPEG export with a provenance record.

## Tools

Agent-visible: `state`, `figure`, `new_figure`, `import_asset`, `edit`, `source`,
`edit_source`, `render`, `preflight`, `undo`, `redo`, `export`.
View-only: `editor_state`, `assets`, `journals`.

A useful order is `state` → `figure` → `edit` (with the `revision` and
`snapshotId` that `figure` returned) → `preflight` → `export`. Writes are
refused when the project or the preview changed meanwhile; re-read instead of
retrying blindly.

## Install

Development (an interpreter with `engine/requirements.txt`):

```sh
python3 plugins/gewu/package.py --sdk-root "$GEWU/sdk/python" \
  --python /path/to/venv/bin/python --out /path/to/staged-fignimble
gewu plugin install /path/to/staged-fignimble
gewu plugin check fignimble --probe --workspace /path/to/workspace \
  --settings /path/to/settings.json --resource workspace:///figures/paper1 \
  --resource-type fignimble.project
```

Then choose a workspace folder as the project (`fignimble.project`) and open
**Figure editor**. See [INSTALL.md](INSTALL.md) for the release and repair path.

## Layout of a project

```text
figures/paper1/
  fig1.py style.py panels/*.py images/* tables/* requirements.txt .fignimble/
```

Python is the editable source. `.fignimble/` is the engine's render cache;
`.gewu/` holds snapshots, exports and logs and is never part of the project's
document revision.

## Verify

```sh
PYTHONPATH=engine python -m pytest -q tests            # Fignimble engine
python -m pytest -q plugins/gewu/tests                 # adapter, exports, package
node --test plugins/gewu/tests/geometry.test.mjs
python scripts/plugin-conformance.py --package STAGE --settings fixtures/settings.json \
  --workspace WORKSPACE --scenario fixtures/contract.json --schema-root GEWU/gewu-protocol/schema
```

Browser tests are registered through GeWu's `application-plugin.spec.mjs`; see
`tests/gui.spec.mjs`.

## Honest limits

Undo lives in the running instance (as in Fignimble); it survives a page reload,
not a server restart. A CLI install appears after the next Plugins-panel refresh
on a host with the plugin-list reconcile; older hosts need a restart. Multi-file writes are revision-checked and each file is
replaced atomically, but they are not a cross-file transaction. Uploading a file
from the browser uses GeWu's Files panel; the plugin imports from the workspace.
Complex marks that predate this plugin's operations are shown from the render and
can still be edited in the source pane. CMYK/EPS/outline conversion needs
Ghostscript, which the core runtime does not install.
