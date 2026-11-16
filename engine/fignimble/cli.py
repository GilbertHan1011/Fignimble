"""The fignimble command: render, check and export figures from a terminal (and let a coding agent see its work).

    fignimble new myproject [--journal nature]     a new project: style.py, fig1.py, panels/example.py
    fignimble snapshot fig1.py [--dpi 150]         render to .fignimble/snapshots/fig1.png and print the path
    fignimble info fig1.py [--json]                elements, boxes (mm), labels and preflight warnings
    fignimble check [fig1.py ...]                  preflight warnings of every figure; exit status 1 if any
    fignimble export fig1.py fig1.pdf [--dpi 600]  PDF, SVG, EPS, PNG, TIFF or JPEG (--cmyk, --outline for print)
    (snapshot and export take --dark: the figure's dark version, for talks)
    fignimble journals                             the journal presets and their column widths
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _project_of(fig: Path) -> Path:
    """The project of a figure file: the folder holding it (and style.py, panels/ ...)."""
    return fig.resolve().parent


def _figures(project: Path) -> list[Path]:
    from .render import is_figure_source
    return [p for p in sorted(project.glob("*.py")) if is_figure_source(p.read_text(encoding="utf-8", errors="replace"))]


def _renderer(fig: Path):
    from .render import Renderer
    return Renderer(str(_project_of(fig)))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="fignimble", description="Multi-panel figures for publication, from Python.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new", help="make a new project")
    p.add_argument("folder")
    p.add_argument("--journal", default="nature", help="nature, science, cell, pnas, elife, or none")
    p = sub.add_parser("snapshot", help="render a figure to PNG and print where")
    p.add_argument("figure")
    p.add_argument("--dpi", type=int, default=150)
    p.add_argument("--output", "-o")
    p.add_argument("--dark", action="store_true", help="the figure's dark version")
    p = sub.add_parser("info", help="describe a figure: elements, labels, warnings")
    p.add_argument("figure")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("check", help="preflight check figures")
    p.add_argument("figures", nargs="*")
    p = sub.add_parser("export", help="export a figure")
    p.add_argument("figure")
    p.add_argument("output")
    p.add_argument("--dpi", type=int, default=600)
    p.add_argument("--dark", action="store_true", help="the figure's dark version")
    p.add_argument("--cmyk", action="store_true", help="CMYK colours for print (PDF, EPS, TIFF, JPEG)")
    p.add_argument("--outline", action="store_true", help="text as shapes (PDF, EPS, SVG)")
    sub.add_parser("journals", help="list journal presets")
    a = ap.parse_args(argv)

    if a.cmd == "new":
        from .templates import new_project
        r = new_project(a.folder, None if a.journal == "none" else a.journal)
        print(f"made {r['project']} (fig1.py, style.py, panels/example.py)")
        return 0
    if a.cmd == "journals":
        from .journals import JOURNALS
        for k, j in JOURNALS.items():
            ws = ", ".join(f"{n} {w} mm" for n, w in j["widths"].items())
            lab = j["labels"]
            print(f"{k:8} {j['name']:12} {ws}; {j['font']} {j['font_size']} pt (min {j['min_font']}); labels "
                  f"{lab['weight']} {lab['case']}case {lab['size']} pt")
        return 0
    if a.cmd == "snapshot":
        fig = Path(a.figure)
        r = _renderer(fig)
        out = Path(a.output) if a.output else r.cache / "snapshots" / f"{fig.stem}{'.dark' if a.dark else ''}.png"
        res = r.export(str(fig.resolve()), str(out.resolve()), "png", dpi=a.dpi, dark=a.dark)
        print(res["path"])
        for w in res["warnings"]:
            print("warning:", w, file=sys.stderr)
        return 0
    if a.cmd == "export":
        fig = Path(a.figure)
        res = _renderer(fig).export(str(fig.resolve()), str(Path(a.output).resolve()), dpi=a.dpi, dark=a.dark,
                                    cmyk=a.cmyk, outline=a.outline)
        print(f"wrote {res['path']}")
        for w in res["warnings"]:
            print("warning:", w, file=sys.stderr)
        return 0
    if a.cmd == "info":
        fig = Path(a.figure)
        res = _renderer(fig).render(str(fig.resolve()), sprites=False)
        if a.json:
            print(json.dumps(res, indent=1))
            return 0
        if res.get("error"):
            print(res["error"])
            return 1
        _describe(res)
        return 0
    if a.cmd == "check":
        figs = [Path(f) for f in a.figures] or _figures(Path.cwd())
        bad = 0
        for fig in figs:
            res = _renderer(fig).render(str(fig.resolve()), sprites=False)
            if res.get("error"):
                print(f"{fig.name}: does not run\n{res['error']}")
                bad += 1
                continue
            ws = res["warnings"]
            print(f"{fig.name}: {'ok' if not ws else ''}")
            for w in ws:
                print(f"  {w['level']}: {w['message']}")
            bad += sum(1 for w in ws if w["level"] != "info")
        return 1 if bad else 0
    return 2


def _describe(res: dict):
    W, H = res["size"]
    j = res.get("journal")
    print(f"{Path(res['file']).name}: {W:g} x {H:g} mm" + (f" ({j['name']})" if j else ""))
    lp = res["labelStyle"]["props"]
    print(f"labels: format {lp['format']!r}, {lp['case']}case, {lp['size']} pt {lp['weight']}, offset "
          f"({lp['dx']}, {lp['dy']}) mm, order {lp['order']}")
    labels = {l["panel"]: l["text"] for l in res["labels"]}
    print("elements (drawing order; x, y, w, h in mm):")
    for e in res["elements"]:
        x, y, w, h = e["box"]
        p = e["props"]
        if e["kind"] == "inset":
            p = e["item"]
        what = {"panel": lambda: f"{p['source']}" + (f":{p['function']}" if p.get("function") != "draw" else ""),
                "inset": lambda: f"{p['source']}" + (f":{p['function']}" if p.get("function", "draw") != "draw" else "")
                + f" in #{e.get('host')}",
                "layout": lambda: f"{len(e.get('children', []))} parts, gap {p['gap']} mm"
                + (", legends collected" if p.get("guides") == "collect" else ""),
                "image": lambda: p["source"], "text": lambda: repr(p["text"]),
                "bracket": lambda: repr(p["text"])}.get(e["kind"], lambda: "")()
        lab = f" [{labels[e['oid']]}]" if e["oid"] in labels else ""
        line = e.get("site", {}).get("line")
        print(f"  #{e['oid']:<3} {e['kind']:8}{lab:5} {x:7.1f} {y:7.1f} {w:7.1f} {h:7.1f}  {what}  (line {line})")
        if e.get("error"):
            print("       ERROR " + e["error"].strip().replace("\n", "\n       "))
    if res["warnings"]:
        print("preflight:")
        for w in res["warnings"]:
            print(f"  {w['level']}: {w['message']}")
    else:
        print("preflight: no problems")


if __name__ == "__main__":
    sys.exit(main())
