# Engine protocol

The app starts `python -m fignimble.rpc` (with `PYTHONPATH` at `engine/`) and talks to it in JSON lines, as Manimble
does: a request `{"id": 7, "cmd": "figure", "name": "fig1"}`, a response `{"id": 7, "result": {...}}` or
`{"id": 7, "error": "..."}`, and events with no id. The engine renders in a separate worker process
(`fignimble.worker`), restarted if a panel's code crashes it or runs over 180 s.

Coordinates are millimetres from the figure's top-left corner, y down.

## Commands

| cmd | arguments | result |
|---|---|---|
| `open` | `project` (folder) | `{ok, project}`; writes the agent instruction files the project lacks |
| `close` | | `{ok}`; removes them again |
| `new_project` | `dir`, `journal?` | `{ok, project, figure}` |
| `state` | | `{project, figures: [{name, file, thumb, error, warnings}], canUndo, canRedo, undoLabel, redoLabel, panels}` |
| `figure` | `name`, `pxPerMM?` (sprite resolution), `dark?` (show dark versions from now on) | a render (below) |
| `edit` | `figure`, `op`, op arguments, `pxPerMM?` | `{ok, error?, figure, select?}`: the render after the edit, and the new elements to select |
| `write_source` | `file`, `text`, `figure?` | `{ok, figure?}`; one undo step |
| `undo`, `redo` | `figure?` | `{ok, label, figure}` or `{ok: false, error}` |
| `export` | `figure`, `path`, `format?` (pdf, eps, svg, png, tiff, jpg), `dpi?`, `journal?`, `cmyk?`, `outline?`, `dark?` | `{ok, path, warnings, resolution: {journal, kind, need, dpi?, pictures?, ok, notes}}`; the app's Copy Figure exports a PDF and a PNG this way for the pasteboard |
| `new_figure` | `name`, `width`, `height` | `{ok, name}` |
| `new_panel` | `figure`, `name`, `x, y, w, h` | as `edit`, plus `file` (the new panel file) |
| `import_file` | `figure`, `path`, `x`, `y`, `w?`, `label?` | as `edit`; pictures are copied into `images/`, `.py` files become panels; `label: null` gives no letter |
| `journals` | | the journal presets (sizes, fonts, labels, `dpi: {photo, combination, line}`) |
| `export_table` | `figure`, `oid`, `path`, `title?` | `{ok, path}`: a table element as a Word file |
| `remote_hosts` | | `{hosts}` from `~/.ssh/config` |
| `remote_list` | `host`, `path?` | `{ok, host, path, entries: [{name, dir}]}`: folders and .py files there |
| `import_remote` | `figure`, `host`, `path`, `x`, `y` | as `import_file`, plus `file`: the panel code copied into `panels/` |
| `update_remote` | `file`, `figure?` | as `write_source`: the panel code fetched again from where its first line says |

## Edit operations

`set {oid, props}` (any arguments of the element's call; a label's `text`), `move {oids, dx, dy, labels?: "all"}`,
`resize {oid, box}`, `endpoints {oid, x1, y1, x2, y2}`, `delete {oids}`, `duplicate {oids, dx, dy}`,
`order {oids, how: front|back|forward|backward}`, `align {oids, how, to: selection|key|figure, key?}`,
`distribute {oids, axis: h|v, gap?}`, `match {oids, what: width|height|both}`, `group {oids}`, `ungroup {oids}`,
`insert {kind, props}`, `figure {props}`, `style {props}`, `labels {props}`, `guide_add {x | y}`,
`guide_move {index, value}`, `guide_delete {index}`, `divider {oid (a layout), index (of its dividers), delta mm}`,
`make_layout {oids, gap?}`, `release_layout {oid}`, `panel_text {oid, key, text, old}` (retype a text a panel draws),
`panel_text_style {oid, key, text, props: {size?, color?, weight?, style?}}` (written into the panel's code when the
text is the literal of one `ax.set_xlabel(...)`, `ax.text(...)`…, else `text_style=` on the panel), `panel_text_reset
{oid, key}`, `panel_color {oid, keys, color, old}`.

A panel inside a layout has a `parent` (the layout's oid, its own oid being `<layout>.<n>`); moving it moves the
layout. A layout lists its `children` and its `dividers` (`{axis: col|row, index, at, from, to, sizes, editable}`).
An inset has `host`, `inner` (panel or image) and `item` (its panel's settings); `set` sends its x, y, w, h, label
to the inset call and the rest to the panel's. `figure` and `export` take `dark` (the figure's dark version).

An edit that would overwrite a value the code computes (`x=a.right + 2`) is refused with the line that controls it.

## A render

```
{figure, file, size: [w, h], background, journal?, figureSite, figureProps,
 style: {props, site}, labelStyle: {props, site, preset},
 elements: [{oid, kind, method, box: [x, y, w, h], props, site: {file, line}, group, sprite: {file, x, y, w, h},
             code?: {file, line}, error?}],
 labels: [{oid: "L<panel oid>", panel, text, auto, box, sprite}],
 guides: [{x, y}], warnings: [{level: error|warning|info, oid, message}], thumb, pxPerMM}
```

Each sprite is a transparent PNG of one element at `pxPerMM`; drawing them in order (elements, then labels) on the
figure's background reproduces the figure.

## Events

`changed` (a file of the project changed outside an edit: render again), `rendered` (`figure`: a background render,
for its thumbnail).
