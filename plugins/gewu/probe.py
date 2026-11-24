#!/usr/bin/env python3
"""Functional smoke check for a staged Fignimble plugin.

Renders a new figure and lowers it to PNG and PDF with the engine in this
package, using the interpreter that runs this script. Prints one JSON object;
exit status 1 when any step fails.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile

HERE = Path(__file__).resolve().parent


def main() -> int:
    engine = HERE / "engine"
    if not (engine / "fignimble" / "rpc.py").is_file():
        print(json.dumps({"ok": False, "error": "the package has no engine"}))
        return 1
    os.environ.setdefault("MPLBACKEND", "Agg")
    sys.path.insert(0, str(engine))
    try:
        from fignimble import templates
        from fignimble.render import Renderer
    except Exception as error:                              # noqa: BLE001
        print(json.dumps({"ok": False, "error": f"{type(error).__name__}: {error}"}))
        return 1
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp) / "project"
        templates.new_project(str(root), "nature")
        (root / "panels" / "p.py").write_text(
            "import numpy as np\n\n\ndef draw(fig):\n    fig.add_subplot().plot(np.arange(4))\n")
        figure = root / "fig1.py"
        figure.write_text(figure.read_text() + 'fig.panel("panels/p.py", x=4, y=4, w=80, h=50)\n')
        renderer = Renderer(str(root))
        try:
            png = renderer.export(str(figure), str(root / "fig1.png"), "png", dpi=300)
            pdf = renderer.export(str(figure), str(root / "fig1.pdf"), "pdf", dpi=600)
        except Exception as error:                          # noqa: BLE001
            print(json.dumps({"ok": False, "error": f"{type(error).__name__}: {error}"[:2000]}))
            return 1
        sizes = {"png": (root / "fig1.png").stat().st_size, "pdf": (root / "fig1.pdf").stat().st_size}
        ok = sizes["png"] > 500 and sizes["pdf"] > 500
        print(json.dumps({"ok": ok, "engine": "fignimble", "files": sizes,
                          "png": png.get("ok", True), "pdf": pdf.get("ok", True),
                          "python": Path(sys.executable).name}))
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
