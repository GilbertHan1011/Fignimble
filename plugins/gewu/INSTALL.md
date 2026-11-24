# Install Fignimble in GeWu

## 1. A Python with the engine's dependencies

Fignimble needs **Python 3.11+** with `matplotlib`, `PyMuPDF<2`, `Pillow` and
`NumPy`. Nothing else is required for the core profile (no Ghostscript, TeX,
BioCartoon or ffmpeg).

```sh
python3 -m venv ~/venvs/fignimble
~/venvs/fignimble/bin/pip install matplotlib "pymupdf<2" pillow numpy
```

Check it once:

```sh
~/venvs/fignimble/bin/python -c "import matplotlib, fitz, PIL, numpy; print('ok')"
```

## 2. Stage and install a local package

From a Fignimble checkout (this plugin lives in `plugins/gewu/`):

```sh
GEWU=/data3/litian/projects/GeWu           # your GeWu checkout
python3 plugins/gewu/package.py --sdk-root "$GEWU/sdk/python" \
  --python ~/venvs/fignimble/bin/python \
  --out /tmp/fignimble-0.1.0/package
"$GEWU/target/debug/gewu" plugin install /tmp/fignimble-0.1.0/package
```

The staging step copies the adapter, web editor, skill, the pinned GeWu Python
SDK and the Fignimble engine, and binds the interpreter in the launcher. It
rejects an existing output directory and compiled bytecode.

Functional probe:

```sh
cd /tmp/fignimble-0.1.0/package
~/venvs/fignimble/bin/python probe.py
```

`probe.py` renders a new figure to PNG and PDF with the packaged engine and
prints one JSON object; a non-zero exit status is the failure.

## 3. Settings

```json
{
  "plugins": {
    "fignimble": {
      "enabled": true,
      "package": "/tmp/fignimble-0.1.0/package",
      "settings": {
        "python": "/home/you/venvs/fignimble/bin/python",
        "engineRoot": "/path/to/Fignimble/engine"
      },
      "sources": {
        "adapter": "/path/to/Fignimble/plugins/gewu",
        "application": "/path/to/Fignimble"
      }
    }
  }
}
```

`settings` can be `{}`: a locally staged package already binds its interpreter
and carries its engine. Set them only to override for development. Marketplace
installs use the host-provided runtime instead and need no paths.

A host built with the plugin-list reconcile (GeWu 2026-11-24 or later) picks up a
CLI install on the next Plugins-panel refresh or `plugin_list` call, without a
restart. Older hosts only read `~/.gewu/plugins/state.json` at startup, so there
restart GeWu after `gewu plugin install`/`plugin uninstall`.

## 4. Open a project

In the Applications panel bind a workspace folder with resource type
`fignimble.project`, e.g. `figures/paper1`, then **Open**. An empty folder is
allowed: name a figure and press **New figure**. Files created by the desktop app
open unchanged, and files written here open in the desktop app and the CLI.

## 5. Marketplace release (maintainers)

```sh
python3 plugins/gewu/build-release.py --gewu-root "$GEWU" \
  --out /tmp/fignimble-0.1.0/release \
  --marketplace-root /data3/litian/projects/gewu-marketplace \
  --base-url https://plugin.regulogen.cn --created-at 2026-11-24T00:00:00Z
```

This uses GeWu's own `plugin-release.py`, adds the engine and `VERSION`, and
writes a `gewu.release/v2` record with the runtime plan
(`runtime-plan.json`: external interpreter first, host-managed micromamba
second). Publish exactly the record's digests; do not rebuild after signing.

## 6. Repair

- **`DEPENDENCIES_MISSING` / `PYTHON_UNAVAILABLE`**: the selected interpreter
  cannot import matplotlib/fitz/PIL/numpy. Install them; do not point at a
  different project's environment silently.
- **`PROJECT_IN_USE`**: another GeWu instance holds the project. Close it; the
  lock is `<workspace>/.gewu/fignimble/<key>/engine.lock`.
- **`STALE_REVISION`**: the project files changed after they were read (an
  agent, the desktop app, or a second editor). Call `state`/`figure` again.
- **`STALE_SNAPSHOT`**: the preview is older than the project. Refresh before
  moving the selected element.
- **A render failed**: the previous preview stays on screen and the error is in
  `figure`/`preflight`; fix the panel code in the source pane.
- **Fonts**: the runtime has DejaVu; other families fall back. The preflight and
  export report says which font was used, so a journal's Arial requirement is
  never claimed silently.
