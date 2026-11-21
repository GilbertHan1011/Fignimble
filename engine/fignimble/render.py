"""Rendering a figure file: run it, draw each element, compose them into one vector page, check the result.

Every element becomes a *piece*: a drawing that does not depend on where the element is, cached by a hash of what
it looks like. Moving an element therefore re-uses its drawing; resizing a panel redraws only that panel. Panels
and text are drawn by matplotlib, and everything is composed into a PDF page with PyMuPDF, which keeps panels and
vector pictures as vectors. The editor gets one transparent picture (sprite) per piece, to move about on screen.
"""

from __future__ import annotations

import hashlib
import inspect
import io
import json
import logging
import math
import os
import re
import shutil
import subprocess
import tempfile
import runpy
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import matplotlib

matplotlib.use("Agg")
import matplotlib.colors as mcolors  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pymupdf  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.figure import Figure as MplFigure  # noqa: E402

import matplotlib.lines  # noqa: E402
from . import api, journals, layout, tables  # noqa: E402

logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
sys.dont_write_bytecode = True          # running a project's code leaves no __pycache__ in it
pymupdf.TOOLS.mupdf_display_errors(False)

MM = 72 / 25.4                     # points per millimetre
RASTER = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp")
VECTOR = (".pdf", ".svg")
SKIP_DIRS = {".fignimble", ".git", "__pycache__", ".venv", "venv", "node_modules", ".ipynb_checkpoints"}


CACHE_VERSION = 7                  # bump when a change to drawing makes cached pieces wrong


def _h(*parts) -> str:
    return hashlib.sha1(json.dumps((CACHE_VERSION, parts), sort_keys=True, default=str).encode()).hexdigest()[:20]


def rgb(c):
    if c is None:
        return None
    return tuple(mcolors.to_rgb(c))


def is_figure_source(text: str) -> bool:
    """A .py file that makes a figure (and is not a panel or a style module)."""
    return "fignimble" in text and "Figure(" in text


def image_aspect(source: str, crop=None, rotation: float = 0) -> float:
    """Width / height of a picture file after `crop` and `rotation`."""
    p = Path(source)
    ext = p.suffix.lower()
    if ext in VECTOR:
        with pymupdf.open(str(p)) as d:
            r = d[0].rect
            w, h = r.width, r.height
    else:
        from PIL import Image
        with Image.open(str(p)) as im:
            w, h = im.size
    if crop:
        l, t, r_, b = crop
        w, h = w * (1 - l - r_), h * (1 - t - b)
    if rotation:
        a = math.radians(rotation)
        c, s_ = abs(math.cos(a)), abs(math.sin(a))
        w, h = w * c + h * s_, w * s_ + h * c
    return w / h if h > 0 else 1.0


@dataclass
class Piece:
    """One element's drawing. `box` (x, y, w, h mm) is where it goes on the figure; `draw(page, ox, oy)` draws it
    with its box's top-left at (ox, oy) points. `pad` (mm) is how far it may draw outside its box (strokes)."""
    oid: str
    kind: str
    box: tuple
    key: str
    draw: Callable
    pad: float = 0.0
    meta: dict = field(default_factory=dict)


class Renderer:
    def __init__(self, project: str, cache: str | None = None):
        self.project = Path(project).resolve()
        self.cache = Path(cache) if cache else self.project / ".fignimble"
        for d in ("pieces", "sprites", "out", "images"):
            (self.cache / d).mkdir(parents=True, exist_ok=True)
        self._docs: dict[str, pymupdf.Document] = {}
        self._cwd = Path.cwd()                   # rendering moves into the project; relative paths mean this one
        self.dark = False

    # --- running user code ---

    def _purge_modules(self):
        root = str(self.project)
        for name, mod in list(sys.modules.items()):
            f = getattr(mod, "__file__", None) or ""
            if name != "__main__" and f and os.path.isfile(f) and os.path.abspath(f).startswith(root + os.sep):
                del sys.modules[name]

    def _enter(self):
        os.chdir(self.project)
        if str(self.project) not in sys.path:
            sys.path.insert(0, str(self.project))

    def resolve(self, file: str) -> Path:
        """A figure file given relative to the working directory, or else to the project."""
        p = Path(file)
        if not p.is_absolute():
            p = self._cwd / p if (self._cwd / p).exists() else self.project / p
        return p.resolve()

    def run_figure(self, file: str) -> api.Figure:
        """Run a figure file; the Figure it made (its first)."""
        file = self.resolve(file)
        self._enter()
        self._purge_modules()
        api._FIGURES.clear()
        plt.close("all")
        runpy.run_path(str(Path(file).resolve()), run_name="__fignimble__")
        if not api._FIGURES:
            raise RuntimeError(f"{Path(file).name} does not make a Figure (fig = Figure(width=..., height=...))")
        return api._FIGURES[0]

    def fingerprint(self) -> str:
        """What a panel can read besides its own code: every other file of the project except figure files."""
        items = []
        for dirpath, dirs, files in os.walk(self.project):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
            for f in files:
                p = Path(dirpath) / f
                if f.endswith(".py"):
                    try:
                        if is_figure_source(p.read_text(encoding="utf-8", errors="replace")):
                            continue
                    except OSError:
                        continue
                try:
                    st = p.stat()
                except OSError:
                    continue
                items.append((str(p.relative_to(self.project)), st.st_mtime_ns, st.st_size))
        return _h(sorted(items))

    # --- pieces ---

    def _doc(self, path: str) -> pymupdf.Document:
        d = self._docs.get(path)
        if d is None:
            d = pymupdf.open(path)
            if not d.is_pdf:
                d = pymupdf.open("pdf", d.convert_to_pdf())
            self._docs[path] = d
        return d

    def _show_pdf(self, path: str, page, rect, clip=None):
        page.show_pdf_page(rect, self._doc(path), 0, clip=clip, keep_proportion=False)

    def _panel_code(self, props: dict):
        """(code text, function or None, file path or None, name for errors) of a panel's source."""
        src = props["source"]
        if callable(src):
            try:
                code = inspect.getsource(src)
            except (OSError, TypeError):
                code = repr(src.__code__.co_code)
            return code, src, None, src.__name__
        path = (self.project / src).resolve()
        return path.read_text(encoding="utf-8"), None, path, src

    def _panel_fn(self, props, fn, path):
        if fn is not None:
            return fn
        self._enter()
        ns = runpy.run_path(str(path), run_name="__fignimble_panel__")
        fn = ns.get(props["function"])
        if not callable(fn):
            raise RuntimeError(f"{props['source']} has no function {props['function']}(fig)")
        return fn

    def _draw_panel(self, fn, args, w, h, rc, collect, target=None, background=None, texts=None, colors=None,
                    text_style=None):
        """Draw a panel: (pdf bytes, its plot area's margins in mm (l, t, r, b) or None, legend entries taken out,
        the texts it shows [{key, text, box (mm in the panel), size, rotation}])."""
        with matplotlib.rc_context(rc):
            fig = plt.figure(figsize=(w / 25.4, h / 25.4))
            try:
                api._DARK[0] = self.dark
                fn(fig, **args)
                _set_colors(fig, colors)
                entries = _take_legends(fig) if collect else []
                _set_texts(fig, texts, ticks=False)
                _set_text_style(fig, text_style, ticks=False)
                fig.canvas.draw()                    # lays it out (constrained layout), so the axes are where they go
                if _set_texts(fig, texts, ticks=True) | _set_text_style(fig, text_style, ticks=True):
                    fig.canvas.draw()
                area = _plot_area(fig)
                margins = None
                if area is not None:
                    x0, y0, x1, y1 = area
                    margins = [x0 * w, (1 - y1) * h, (1 - x1) * w, y0 * h]
                    if target is not None and any(abs(a - b) > 0.05 for a, b in zip(margins, target)):
                        _remap(fig, area, target, w, h)
                        fig.canvas.draw()
                found = _measure_texts(fig, h)
                marks = _measure_marks(fig, h)
                buf = io.BytesIO()
                # rasters inside the panel (imshow, rasterized scatters) at print resolution
                fig.savefig(buf, format="pdf", facecolor=background or "none", dpi=600)
            finally:
                api._DARK[0] = False
                plt.close("all")
        return buf.getvalue(), margins, entries, found, marks

    def _panel_base(self, props, w, h, rc, deps, collect, background=None) -> dict:
        """The panel drawn at its size, as its own code lays it out: {pdf, margins, entries} or {error}."""
        try:
            code, fn, path, where = self._panel_code(props)
        except OSError as exc:
            return {"error": f"can't read panel code {props['source']}: {exc}"}
        key = _h("panel", code, None if fn else props["source"], props["function"], props["args"], round(w, 3),
                 round(h, 3), rc, deps, bool(collect), background, props.get("texts") or {}, props.get("colors") or {},
                 props.get("text_style") or {})
        pdf, meta = self.cache / "pieces" / f"{key}.pdf", self.cache / "pieces" / f"{key}.json"
        if pdf.exists() and meta.exists():
            return {"pdf": str(pdf), "key": key, **json.loads(meta.read_text())}
        try:
            data, margins, entries, found, marks = self._draw_panel(self._panel_fn(props, fn, path), props["args"], w, h,
                                                                    rc, collect, background=background,
                                                                    texts=props.get("texts"), colors=props.get("colors"),
                                                                    text_style=props.get("text_style"))
        except Exception:                               # noqa: BLE001
            return {"error": _user_traceback(where)}
        _write(pdf, data)
        meta.write_text(json.dumps({"margins": margins, "entries": entries, "texts": found, "marks": marks}))
        ekey = _h("entries", code, None if fn else props["source"], props["function"], props["args"], rc, deps)
        (self.cache / "pieces" / f"{ekey}.entries.json").write_text(json.dumps(entries))
        return {"pdf": str(pdf), "key": key, "margins": margins, "entries": entries, "texts": found, "marks": marks}

    def _panel_aligned(self, props, w, h, rc, deps, collect, base, target, background=None) -> tuple[str, dict]:
        """The panel redrawn with its plot area at `target` margins (mm): (pdf, {texts, marks})."""
        if not base.get("margins") or target is None or all(abs(a - b) <= 0.05 for a, b in zip(base["margins"], target)):
            return base["pdf"], {"texts": base.get("texts") or [], "marks": base.get("marks") or []}
        target = [round(v, 2) for v in target]
        key = _h(base["key"], target)
        pdf, meta = self.cache / "pieces" / f"{key}.pdf", self.cache / "pieces" / f"{key}.texts.json"
        if not (pdf.exists() and meta.exists()):
            code, fn, path, where = self._panel_code(props)
            data, _, _, found, marks = self._draw_panel(self._panel_fn(props, fn, path), props["args"], w, h, rc,
                                                        collect, target, background, props.get("texts"),
                                                        props.get("colors"), props.get("text_style"))
            _write(pdf, data)
            meta.write_text(json.dumps({"texts": found, "marks": marks}))
        return str(pdf), json.loads(meta.read_text())

    def _entries(self, props, w, h, rc, deps) -> list:
        """The legend entries of a panel, for a layout that collects them (they don't depend on its size)."""
        try:
            code, fn, path, where = self._panel_code(props)
        except OSError:
            return []
        ekey = _h("entries", code, None if fn else props["source"], props["function"], props["args"], rc, deps)
        f = self.cache / "pieces" / f"{ekey}.entries.json"
        if f.exists():
            return json.loads(f.read_text())
        return self._panel_base(props, w, h, rc, deps, True).get("entries", [])

    def legend_piece(self, entries: list, rc: dict, title=None, ncol: int = 1, size=None) -> tuple[str, float, float]:
        """(pdf, w, h) of a legend drawn by matplotlib from entries ({label, kind, color, ...})."""
        entries = [{**e, "color": self.c(e.get("color")), "edgecolor": self.c(e.get("edgecolor"))} for e in entries]
        key = _h("legend", entries, rc, title, ncol, size)
        out = self.cache / "pieces" / f"{key}.pdf"
        if not out.exists():
            with matplotlib.rc_context(rc):
                fig = MplFigure(figsize=(4, 4))
                fig.legend(handles=[_proxy(e) for e in entries], labels=[e["label"] for e in entries],
                           loc="upper left", frameon=False, ncols=max(1, int(ncol)), title=title,
                           fontsize=size or rc.get("legend.fontsize"), title_fontsize=size or rc.get("legend.fontsize"),
                           borderpad=0, borderaxespad=0, handlelength=1.4, handletextpad=0.5, labelspacing=0.35)
                buf = io.BytesIO()
                fig.savefig(buf, format="pdf", bbox_inches="tight", pad_inches=0.01, transparent=True)
            _write(out, buf.getvalue())
        r = self._doc(str(out))[0].rect
        return str(out), r.width / MM, r.height / MM

    def table_piece(self, rows: list, header: bool, size: float, family: list, color: str, width: float | None,
                    decimals=None, align=None) -> tuple[str, float, float]:
        """(pdf, w mm, h mm) of a table: columns as wide as their text (widened evenly to `width`), numbers to the
        right, a rule above and below the header and at the bottom."""
        color = self.c(color)
        shown, auto = tables.cells(rows, header, decimals)
        al = tables.resolve_align(align, auto)
        key = _h("table", shown, al, header, size, family, color, width)
        out = self.cache / "pieces" / f"{key}.pdf"
        meta = out.with_suffix(".json")
        if not (out.exists() and meta.exists()):
            rc = {"pdf.fonttype": 42, "font.family": "sans-serif", "font.sans-serif": family}
            pad, rh, rule = size * 0.9, size * 1.55, 0.6          # points
            with matplotlib.rc_context(rc):
                fig = MplFigure(figsize=(2, 2), dpi=72)
                canvas = FigureCanvasAgg(fig)
                r = canvas.get_renderer()
                n = len(al)
                cw = [0.0] * n
                for i, row in enumerate(shown):
                    for j, c in enumerate(row):
                        if c:
                            t = fig.text(0, 0, c, fontsize=size, fontweight="bold" if header and i == 0 else "normal")
                            cw[j] = max(cw[j], t.get_window_extent(r).width)
                            t.remove()
                cw = [c + 2 * pad for c in cw]
                W = sum(cw) or 10.0
                if width and width * MM > W:
                    cw = [c + (width * MM - W) / max(n, 1) for c in cw]
                    W = width * MM
                H = rh * len(shown) + 2 * rule
                fig.set_size_inches(W / 72, H / 72)
                xs = [sum(cw[:j]) for j in range(n)]
                for i, row in enumerate(shown):
                    y = rule + rh * (i + 0.5)
                    for j, c in enumerate(row):
                        x = {"l": xs[j] + pad, "c": xs[j] + cw[j] / 2, "r": xs[j] + cw[j] - pad}[al[j]]
                        fig.text(x / W, 1 - y / H, c, fontsize=size, color=color, va="center_baseline",
                                 ha={"l": "left", "c": "center", "r": "right"}[al[j]],
                                 fontweight="bold" if header and i == 0 else "normal")
                lines = [(rule / 2, rule), (H - rule / 2, rule)]
                if header and len(shown) > 1:
                    lines.append((rule + rh, rule * 0.6))
                for y, lw in lines:
                    fig.add_artist(matplotlib.lines.Line2D([0, 1], [1 - y / H] * 2, transform=fig.transFigure,
                                                           color=color, linewidth=lw, solid_capstyle="butt"))
                buf = io.BytesIO()
                fig.savefig(buf, format="pdf", transparent=True)
            _write(out, buf.getvalue())
            meta.write_text(json.dumps({"w": W / MM, "h": H / MM}))
        m = json.loads(meta.read_text())
        return str(out), m["w"], m["h"]

    def c(self, color):
        """A colour as drawn: in dark mode, greys (black text and lines) turn light and light greys dark."""
        if color is None or not self.dark:
            return color
        try:
            r, g, b = mcolors.to_rgb(color)
        except ValueError:
            return color
        if max(r, g, b) - min(r, g, b) > 0.08:
            return color
        v = 1 - (r + g + b) / 3
        return mcolors.to_hex((v, v, v))

    def rc_for(self, style) -> dict:
        rc = style.rcparams()
        if self.dark:
            rc.update(DARK_RC)
            rc.update({k: v for k, v in style.rc.items()})
        return rc

    def text_piece(self, text: str, size: float, weight: str, style: str, color: str, rotation: float,
                   family: list, align: str = "left", width: float | None = None,
                   keep_color: bool = False, opacity: float = 1.0) -> tuple[str, float, float]:
        """(pdf, w mm, h mm) of a text drawn by matplotlib, tight to its box. The text may hold markup (**bold**,
        *italic*, ^{sup}, _{sub}); with `width` (mm) its lines wrap."""
        color = color if keep_color else self.c(color)
        key = _h("text", text, size, weight, style, color, rotation, family, align, width, opacity)
        out = self.cache / "pieces" / f"{key}.pdf"
        if not out.exists():
            rc = {"pdf.fonttype": 42, "font.family": "sans-serif", "font.sans-serif": family, **_math_rc(family)}
            with matplotlib.rc_context(rc):
                fig = MplFigure(figsize=(2, 2))
                FigureCanvasAgg(fig)                     # to measure lines while wrapping
                shown = _rich(text, weight == "bold", width, fig, dict(fontsize=size, fontweight=weight,
                                                                       fontstyle=style))
                fig.text(0, 0, shown, fontsize=size, fontweight=weight, fontstyle=style, color=color,
                         rotation=rotation, multialignment=align, rotation_mode="anchor", alpha=opacity)
                buf = io.BytesIO()
                fig.savefig(buf, format="pdf", bbox_inches="tight", pad_inches=0, transparent=True)
            tmp = out.with_suffix(".tmp")
            tmp.write_bytes(buf.getvalue())
            tmp.replace(out)
        r = self._doc(str(out))[0].rect
        return str(out), r.width / MM, r.height / MM

    def _raster(self, src: Path, crop, opacity: float, aspect_box: float | None, rotation: float = 0,
                flip: str | None = None) -> tuple[str, int, int]:
        """A PNG of a raster picture cropped, mirrored and turned (and cut to `aspect_box` for "cover"):
        (path, px wide, px high)."""
        st = src.stat()
        key = _h("img", str(src), st.st_mtime_ns, st.st_size, crop, opacity, aspect_box, rotation, flip)
        out = self.cache / "images" / f"{key}.png"
        from PIL import Image
        if out.exists():
            with Image.open(out) as im:
                return str(out), im.width, im.height
        with Image.open(src) as im:
            im = im.convert("RGBA") if im.mode not in ("RGB", "RGBA") or opacity < 1 else im.copy()
            if aspect_box and rotation and round(rotation) % 180 == 90:
                aspect_box = 1 / aspect_box            # cut before turning: the box is turned too
            W, H = im.size
            l, t, r, b = crop or (0, 0, 0, 0)
            box = [W * l, H * t, W * (1 - r), H * (1 - b)]
            if aspect_box:
                bw, bh = box[2] - box[0], box[3] - box[1]
                if bw / bh > aspect_box:
                    nw = bh * aspect_box
                    box[0] += (bw - nw) / 2
                    box[2] = box[0] + nw
                else:
                    nh = bw / aspect_box
                    box[1] += (bh - nh) / 2
                    box[3] = box[1] + nh
            im = im.crop(tuple(int(round(v)) for v in box))
            if flip in ("h", "v"):
                im = im.transpose(Image.FLIP_LEFT_RIGHT if flip == "h" else Image.FLIP_TOP_BOTTOM)
            if rotation:
                im = im.convert("RGBA").rotate(rotation, expand=True, resample=Image.BICUBIC)
            if opacity < 1:
                a = im.getchannel("A").point(lambda v: int(v * opacity))
                im.putalpha(a)
            im.save(out)
            return str(out), im.width, im.height

    def image_box(self, props: dict) -> tuple:
        h = props["h"]
        if h is None:
            h = props["w"] / image_aspect(str(self.project / props["source"]), props["crop"], props.get("rotation") or 0)
        return (props["x"], props["y"], props["w"], h)

    def image_piece(self, p: dict, box: tuple, oid: str, fit: str) -> Piece:
        """A picture filling `box` (mm) as `fit` says: contain, cover or stretch."""
        src = (self.project / p["source"]).resolve()
        x, y, w, h = box
        ext = src.suffix.lower()
        meta = {"source": str(src)}
        rot = p.get("rotation") or 0
        if ext in VECTOR:
            if p.get("flip"):
                raise ValueError("flip works for PNG, TIFF and JPEG pictures; PDF and SVG can be turned, not flipped")
            if round(rot) % 90:
                raise ValueError("PDF and SVG pictures turn in quarter turns (90, 180, 270)")
            quarter = round(rot) % 180 == 90
            doc = self._doc(str(src))
            pr = doc[0].rect
            l, t, r, b = p["crop"] or (0, 0, 0, 0)
            clip = pymupdf.Rect(pr.x0 + pr.width * l, pr.y0 + pr.height * t, pr.x1 - pr.width * r, pr.y1 - pr.height * b)
            dest = (0, 0, w, h)
            aspect = clip.height / clip.width if quarter else clip.width / clip.height
            if fit == "contain":
                dest = _contain(aspect, w, h)
            elif fit == "cover":
                clip = _cover_clip(clip, (h / w) if quarter else (w / h))
            st = src.stat()
            key = _h("vec", str(src), st.st_mtime_ns, st.st_size, tuple(clip), dest, rot)

            def draw(page, ox, oy, clip=clip, dest=dest):
                rect = pymupdf.Rect(ox + dest[0] * MM, oy + dest[1] * MM, ox + (dest[0] + dest[2]) * MM,
                                    oy + (dest[1] + dest[3]) * MM)
                page.show_pdf_page(rect, self._doc(str(src)), 0, clip=clip, keep_proportion=False, rotate=-rot)
            meta.update(vector=True, pdf=str(src), scale=(dest[2] * MM) / (clip.height if quarter else clip.width),
                        clip=tuple(clip), dest=dest)
            return Piece(oid, "image", box, key, draw, meta=meta)
        png, pw, ph = self._raster(src, p["crop"], p["opacity"], (w / h) if fit == "cover" else None, rot, p.get("flip"))
        dest = _contain(pw / ph, w, h) if fit == "contain" else (0, 0, w, h)
        key = _h("ras", png, dest)

        def draw(page, ox, oy, dest=dest):
            rect = pymupdf.Rect(ox + dest[0] * MM, oy + dest[1] * MM, ox + (dest[0] + dest[2]) * MM,
                                oy + (dest[1] + dest[3]) * MM)
            page.insert_image(rect, filename=png, keep_proportion=False)
        meta.update(vector=False, px=(pw, ph), dpi=pw / (dest[2] / 25.4) if dest[2] > 0 else 0, dest=dest,
                    turned=bool(rot and round(rot) % 90))
        return Piece(oid, "image", box, key, draw, meta=meta)

    # --- the figure ---

    def pieces(self, fig: api.Figure) -> tuple[list[Piece], list[dict], list[dict]]:
        """The figure's pieces in drawing order, a description of each element, and its labels.

        Panels are planned first (layouts solved, legends collected), then drawn and measured, then the plot
        areas of panels that share an edge are lined up, and only then are the pieces made."""
        style = fig.style
        api._STYLE[0] = style
        rc = self.rc_for(style)
        family = rc["font.sans-serif"]
        deps = self.fingerprint()
        dests: dict[int, tuple] = {}                # id(picture Element or Node) -> where the picture is drawn (mm)
        rasters: dict[int, dict] = {}               # id(picture) -> its piece's meta, for scale bars
        zooms = []
        _sync_zooms(fig, self.project)
        steps, infos, panels = [], [], []           # steps: Pieces, or panel jobs (dicts) drawn after aligning
        boxes: dict[int, tuple] = {}                # id(Element or Node) -> box, for insets
        oids: dict[int, str] = {}                   # id(Element or Node) -> oid

        def code_info(props):
            """Where the code that draws a panel is: its file, and the line of its function."""
            src = props["source"]
            if callable(src):
                return {"file": inspect.getsourcefile(src), "line": src.__code__.co_firstlineno}
            path = (self.project / src).resolve()
            line = 1
            try:
                text = path.read_text(encoding="utf-8")
                m = re.search(rf"^[ \t]*def[ \t]+{re.escape(props.get('function') or 'draw')}[ \t]*\(", text, re.M)
                if m:
                    line = text[:m.start()].count("\n") + 1
            except OSError:
                pass
            return {"file": str(path), "line": line, "function": props.get("function") or "draw"}

        def panel_job(oid, props, box, align, collect, background=None):
            steps.append({"oid": oid, "props": props, "box": box, "align": align and not (props.get("rotation") or 0),
                          "collect": collect, "background": background})

        def picture(obj, pc):
            d = pc.meta.get("dest") or (0, 0, pc.box[2], pc.box[3])
            dests[id(obj)] = (pc.box[0] + d[0], pc.box[1] + d[1], d[2], d[3])
            rasters[id(obj)] = pc.meta
            return pc

        for i, e in enumerate(fig.elements):
            oid = str(i)
            p = e.props
            info = {"oid": oid, "kind": e.kind, "method": e.method, "site": e.site, "props": _jsonable(p),
                    "group": p.get("group"), "name": p.get("name"), "locked": bool(p.get("locked")),
                    "hidden": bool(p.get("hidden"))}
            if p.get("hidden"):
                try:
                    box = self.image_box(p) if e.kind == "image" else e.box
                except Exception:                          # noqa: BLE001
                    box = _rough_box(e)
                boxes[id(e)] = box
                oids[id(e)] = oid
                info["box"] = [round(v, 4) for v in box]
                infos.append(info)
                continue
            try:
                if e.kind == "panel":
                    box = (p["x"], p["y"], p["w"], p["h"])
                    info["code"] = code_info(p)
                    panel_job(oid, p, box, style.align_axes, False)
                    panels.append((p, oid, box))
                elif e.kind == "image":
                    box = self.image_box(p)
                    pc = picture(e, self.image_piece(p, box, oid, p["fit"] if p["h"] is not None else "stretch"))
                    steps.append(pc)
                    info["code"] = {"file": pc.meta["source"], "line": 1}
                    panels.append((p, oid, box))
                elif e.kind == "layout":
                    box = e.box
                    at = len(infos)
                    info["children"], info["dividers"] = self._plan_layout(i, e, rc, deps, steps, infos, panels,
                                                                           boxes, oids, code_info, panel_job, style,
                                                                           dests, rasters)
                elif e.kind == "inset":
                    host = boxes.get(id(e.host))
                    if host is None:
                        raise ValueError("an inset's `within` must be a panel placed before it")
                    hx, hy, hw, hh = host
                    box = (hx + p["x"] * hw, hy + p["y"] * hh, p["w"] * hw, p["h"] * hh)
                    item = e.node
                    info.update(inner=item.kind, item=_jsonable(item.props), itemSite=item.site,
                                itemMethod=item.method, host=oids.get(id(e.host)))
                    if item.kind == "panel":
                        info["code"] = code_info(item.props)
                        panel_job(oid, item.props, box, False, False, self.c(fig.props["background"]) or "#FFFFFF")
                    else:
                        pc = picture(e, self.image_piece(item.props, box, oid, item.props["fit"]))
                        dests[id(item)] = dests[id(e)]
                        rasters[id(item)] = pc.meta
                        steps.append(pc)
                    if item.props.get("label") not in (None, "auto") or p.get("label"):
                        panels.append(({**item.props, "label": p.get("label") or item.props.get("label")}, oid, box))
                elif e.kind == "text":
                    size = p["size"] or style.size
                    fam = [p["font"]] + family if p["font"] else family
                    pdf, w, h = self.text_piece(p["text"], size, p["weight"], p["style"], p["color"], p["rotation"],
                                                fam, p["align"], p.get("width"), opacity=p.get("opacity", 1.0))
                    x0 = p["x"] - {"left": 0, "center": w / 2, "right": w}.get(p["align"], 0)
                    box = (x0, p["y"], w, h)
                    steps.append(_pdf_piece(self, oid, "text", box, pdf, meta={"pdf": pdf, "scale": 1.0, "size": size}))
                elif e.kind == "table":
                    size = p["size"] or style.size
                    fam = [p["font"]] + family if p["font"] else family
                    rows = p["rows"] if p.get("rows") is not None else tables.read_rows(self.resolve(p["source"]))
                    pdf, w, h = self.table_piece(rows, p["header"], size, fam, p["color"], p.get("w"),
                                                 p.get("decimals"), p.get("align"))
                    box = (p["x"], p["y"], w, h)
                    steps.append(_pdf_piece(self, oid, "table", box, pdf, meta={"pdf": pdf, "scale": 1.0, "size": size}))
                elif e.kind == "legend":
                    pdf, w, h = self.legend_piece(_legend_entries(p), rc, p["title"], p["ncol"], p["size"])
                    box = (p["x"], p["y"], w, h)
                    steps.append(_pdf_piece(self, oid, "legend", box, pdf, meta={"size": p["size"] or style.size}))
                elif e.kind in ("line", "rect", "ellipse"):
                    pc = _shape_piece(oid, e, self.c)
                    box = pc.box
                    steps.append(pc)
                elif e.kind == "path":
                    pc = _path_piece(oid, e, self.c)
                    box = pc.box
                    steps.append(pc)
                elif e.kind == "zoom":
                    zooms.append((len(steps), e, info))
                    box = (0, 0, 0, 0)
                elif e.kind == "scalebar":
                    host = e.host
                    meta = rasters.get(id(host))
                    if meta is None or id(host) not in dests:
                        raise ValueError("a scale bar goes on a picture placed before it (fig.image, or an Image)")
                    if meta.get("vector") or meta.get("turned"):
                        raise ValueError("a scale bar needs a PNG, TIFF or JPEG picture (not PDF/SVG, not turned)")
                    pc = self._scalebar_piece(oid, p, dests[id(host)], meta, family, style)
                    box = pc.box
                    info["host"] = oids.get(id(host))
                    info["anchor"] = pc.meta["anchor"]
                    info["dest"] = [round(v, 4) for v in dests[id(host)]]
                    steps.append(pc)
                elif e.kind == "bracket":
                    size = p["size"] or style.size
                    pdf, tw, th = self.text_piece(p["text"], size, "normal", "normal", p["color"], 0, family, "center")
                    pc = _bracket_piece(self, oid, e, pdf, tw, th)
                    pc.meta["size"] = size
                    box = pc.box
                    steps.append(pc)
                else:
                    continue
            except Exception as exc:                     # noqa: BLE001 - a bad element must not sink the figure
                box = _rough_box(e)
                info["error"] = f"{type(exc).__name__}: {exc}"
                steps.append(_error_piece(oid, box, info["error"]))
            boxes[id(e)] = box
            oids[id(e)] = oid
            info["box"] = [round(v, 4) for v in box]
            if e.kind == "layout":
                infos.insert(at, info)                  # the layout before its children
            else:
                infos.append(info)

        # draw every panel as its code lays it out, and measure its plot area
        # zoom boxes, once everything they join is placed
        for at, e, info in reversed(zooms):
            try:
                pc, region = self._zoom_piece(info["oid"], e, boxes, dests)
                steps.insert(at, pc)
                info["box"] = [round(v, 4) for v in region]
                info["source"], info["target"] = oids.get(id(e.source)), oids.get(id(e.target))
                src_rect = dests.get(id(e.source)) or boxes.get(id(e.source))
                info["sourceBox"] = [round(v, 4) for v in src_rect]
            except Exception as exc:                   # noqa: BLE001
                info["error"] = f"{type(exc).__name__}: {exc}"
        jobs = [s_ for s_ in steps if isinstance(s_, dict)]
        for j in jobs:
            _, _, w, h = j["box"]
            if round(j["props"].get("rotation") or 0) % 180 == 90:
                w, h = h, w                             # drawn upright, then turned into its box
            j["size"] = (w, h)
            j["base"] = self._panel_base(j["props"], w, h, rc, deps, j["collect"], j["background"])
        targets = _align_targets(jobs) if jobs else {}
        pieces = []
        for s_ in steps:
            if not isinstance(s_, dict):
                pieces.append(s_)
                continue
            oid, box, base = s_["oid"], s_["box"], s_["base"]
            info = next((x for x in infos if x["oid"] == oid), None)
            if base.get("error"):
                if info is not None:
                    info["error"] = base["error"]
                pieces.append(_error_piece(oid, box, base["error"]))
                continue
            try:
                pdf, found = self._panel_aligned(s_["props"], s_["size"][0], s_["size"][1], rc, deps, s_["collect"],
                                                 base, targets.get(oid), s_["background"])
            except Exception:                           # noqa: BLE001
                pdf, found = base["pdf"], {"texts": base.get("texts") or [], "marks": base.get("marks") or []}
            texts, marks = found.get("texts") or [], found.get("marks") or []
            rot = s_["props"].get("rotation") or 0
            if info is not None:
                info["margins"] = base.get("margins")
                info["aligned"] = targets.get(oid)
                if not rot:                             # where its texts and marks are, to retype and recolour them
                    info["texts"] = [{**t, "box": [round(box[0] + t["box"][0], 3), round(box[1] + t["box"][1], 3),
                                                   round(t["box"][2], 3), round(t["box"][3], 3)]} for t in texts]
                    info["marks"] = [{**m, "box": [round(box[0] + m["box"][0], 3), round(box[1] + m["box"][1], 3),
                                                   round(m["box"][2], 3), round(m["box"][3], 3)]} for m in marks]
                else:
                    info["marks"] = [{**m, "box": [0, 0, 0, 0]} for m in marks]

            def draw(page, ox, oy, pdf=pdf, w=box[2], h=box[3], rot=rot):
                page.show_pdf_page(pymupdf.Rect(ox, oy, ox + w * MM, oy + h * MM), self._doc(pdf), 0,
                                   keep_proportion=False, rotate=-rot)
            pieces.append(Piece(oid, "panel", box, _h("p", pdf, rot), draw, meta={"pdf": pdf, "scale": 1.0}))
        label_pieces, label_infos = self._labels(fig, panels, family)
        # labels are drawn above everything
        return pieces + label_pieces, infos, label_infos

    def _plan_layout(self, i, e, rc, deps, steps, infos, panels, boxes, oids, code_info, panel_job, style,
                     dests=None, rasters=None):
        """Solve a layout: its children's boxes (as panel jobs and pieces) and its draggable dividers."""
        p = e.props
        x, y, w, h = e.box
        cells = (x, y, w, h)
        legend = None
        if p["guides"] == "collect":
            leaves0, _ = layout.solve(e.node, cells, p["gap"], p["widths"], p["heights"], e.site)
            seen, entries = set(), []
            for leaf, lb in leaves0:
                if isinstance(leaf, api.Panel):
                    for en in self._entries(leaf.props, lb[2], lb[3], rc, deps):
                        k = json.dumps(en, sort_keys=True)
                        if k not in seen:
                            seen.add(k)
                            entries.append(en)
            if entries:
                # a legend under the panels runs across, one beside them runs down (as in patchwork)
                pdf, lw, lh = self.legend_piece(entries, rc, ncol=len(entries) if p["legend"] == "bottom" else 1)
                if p["legend"] == "bottom":
                    cells = (x, y, w, max(h - lh - p["gap"], 1))
                    lbox = (x + (w - lw) / 2, y + h - lh, lw, lh)
                else:
                    cells = (x, y, max(w - lw - p["gap"], 1), h)
                    lbox = (x + w - lw, y + (h - lh) / 2, lw, lh)
                legend = (pdf, lbox)
        leaves, dividers = layout.solve(e.node, cells, p["gap"], p["widths"], p["heights"], e.site)
        children = []
        for k, (leaf, lb) in enumerate(leaves):
            oid = f"{i}.{k}"
            boxes[id(leaf)] = lb
            oids[id(leaf)] = oid
            if isinstance(leaf, api.Spacer):
                continue
            info = {"oid": oid, "kind": leaf.kind, "method": leaf.method, "site": leaf.site,
                    "props": _jsonable(leaf.props), "parent": str(i), "group": None, "name": leaf.props.get("name"),
                    "box": [round(v, 4) for v in lb]}
            if isinstance(leaf, api.Panel):
                info["code"] = code_info(leaf.props)
                panel_job(oid, leaf.props, lb, style.align_axes and p["align"], p["guides"] == "collect")
            else:
                pc = self.image_piece(leaf.props, lb, oid, leaf.props["fit"])
                d = pc.meta.get("dest") or (0, 0, lb[2], lb[3])
                dests[id(leaf)] = (lb[0] + d[0], lb[1] + d[1], d[2], d[3])
                rasters[id(leaf)] = pc.meta
                info["code"] = {"file": pc.meta["source"], "line": 1}
                steps.append(pc)
            panels.append((leaf.props, oid, lb))
            infos.append(info)
            children.append(oid)
        if legend:
            pdf, lbox = legend
            loid = f"{i}.legend"
            steps.append(_pdf_piece(self, loid, "legend", lbox, pdf, meta={"size": style.size}))
            infos.append({"oid": loid, "kind": "legend", "method": "collected", "site": e.site, "props": {},
                          "parent": str(i), "group": None, "name": None, "box": [round(v, 4) for v in lbox]})
            children.append(loid)
        divs = [{**d, "at": round(d["at"], 3), "from": round(d["from"], 3), "to": round(d["to"], 3)} for d in dividers]
        return children, divs

    def _zoom_piece(self, oid, e, boxes, dests):
        """The zoom box's rectangle on its source and the lines to its target; and the rectangle (mm)."""
        p = e.props
        src = dests.get(id(e.source)) or boxes.get(id(e.source))
        tgt = dests.get(id(e.target)) or boxes.get(id(e.target))
        if src is None or tgt is None:
            raise ValueError("a zoom joins two panels or pictures placed before it")
        rx, ry, rw, rh = p["region"]
        reg = (src[0] + rx * src[2], src[1] + ry * src[3], rw * src[2], rh * src[3])
        lines = _zoom_lines(reg, tgt) if p["lines"] else []
        xs = [reg[0], reg[0] + reg[2], tgt[0], tgt[0] + tgt[2]]
        ys = [reg[1], reg[1] + reg[3], tgt[1], tgt[1] + tgt[3]]
        box = (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
        col = rgb(self.c(p["color"]))
        key = _h("zoom", reg, tgt, lines, p["width"], p["dash"], col)

        def draw(page, ox, oy):
            X = lambda v: ox + (v - box[0]) * MM          # noqa: E731
            Y = lambda v: oy + (v - box[1]) * MM          # noqa: E731
            sh = page.new_shape()
            sh.draw_rect(pymupdf.Rect(X(reg[0]), Y(reg[1]), X(reg[0] + reg[2]), Y(reg[1] + reg[3])))
            for (a, b) in lines:
                sh.draw_line(pymupdf.Point(X(a[0]), Y(a[1])), pymupdf.Point(X(b[0]), Y(b[1])))
            sh.finish(color=col, width=p["width"], dashes=_dashes(p["dash"], p["width"]))
            sh.commit()
        return Piece(oid, "zoom", box, key, draw, pad=p["width"] / MM), reg

    def _scalebar_piece(self, oid, p, dest, meta, family, style) -> Piece:
        """A scale bar on a picture: its length from the picture's pixels and `pixel_size`."""
        pw = meta["px"][0]
        mm_per_px = dest[2] / pw
        bar = p["length"] / p["pixel_size"] * mm_per_px
        size = p["size"] or style.size
        label = f"{p['length']:g} {p['unit']}"
        tpdf, tw, th = (self.text_piece(label, size, "bold", "normal", p["color"], 0, family, "center", keep_color=True)
                        if p["label"] else (None, 0.0, 0.0))
        gap = 0.5 if p["label"] else 0.0
        w = max(bar, tw)
        h = p["thickness"] + gap + th
        if p["x"] is not None and p["y"] is not None:
            bx = dest[0] + p["x"] * dest[2]
            by = dest[1] + p["y"] * dest[3]             # the bar's bottom
        else:
            corner, m = p["corner"], p["margin"]
            bx = dest[0] + m if "left" in corner else dest[0] + dest[2] - m - bar
            by = dest[1] + m + h if "upper" in corner else dest[1] + dest[3] - m
        box = (min(bx, bx + bar / 2 - tw / 2), by - h, w, h)
        col = rgb(p["color"])
        key = _h("scalebar", bar, p["thickness"], tpdf, tw, th, col, box[2:], bx - box[0])

        def draw(page, ox, oy):
            x0 = ox + (bx - box[0]) * MM
            yb = oy + h * MM
            page.draw_rect(pymupdf.Rect(x0, yb - p["thickness"] * MM, x0 + bar * MM, yb), color=None, fill=col, width=0)
            if tpdf:
                cx = x0 + bar / 2 * MM
                self._show_pdf(tpdf, page, pymupdf.Rect(cx - tw / 2 * MM, oy, cx + tw / 2 * MM, oy + th * MM))
        return Piece(oid, "scalebar", box, key, draw, meta={"size": size, "bar": bar, "anchor": [round(bx, 4), round(by, 4)]})

    def _labels(self, fig, panels, family):
        lab = fig.labels
        lp = lab.props
        panels = [(e, oid, box) for e, oid, box in panels if not e.get("hidden")]
        auto = [(e, oid, box) for e, oid, box in panels if e.get("label") == "auto"]
        if lp["order"] == "reading":
            auto = _reading_order(auto)
        explicit = {e["label"] for e, _, _ in panels if isinstance(e.get("label"), str) and e["label"] != "auto"}
        names, n = {}, 0
        for e, oid, box in auto:
            while True:
                n += 1
                t = lab.text(n)
                if t not in explicit:
                    break
            if t:                                       # numbering "none": no letters
                names[oid] = t
        for e, oid, box in panels:
            if isinstance(e.get("label"), str) and e["label"] != "auto":
                names[oid] = e["label"]
        # where each label goes: panel corner + the shared offset, lined up by rows and columns, then its own nudge
        base = {oid: [box[0] + lp["dx"], box[1] + lp["dy"]] for e, oid, box in panels if oid in names}
        if lp["align"] and base:
            for axis in (1, 0):
                keys = sorted(base, key=lambda k: base[k][axis])
                group = []
                for k in keys + [None]:
                    if k is not None and group and base[k][axis] - base[group[0]][axis] <= 3.0:
                        group.append(k)
                        continue
                    if group:
                        m = min(base[g][axis] for g in group)
                        for g in group:
                            base[g][axis] = m
                    group = [k] if k is not None else []
        fam = [lp["font"]] + family if lp["font"] else family
        pieces, infos = [], []
        for e, oid, box in panels:
            if oid not in names:
                continue
            pdf, w, h = self.text_piece(names[oid], lp["size"], lp["weight"], lp["style"], lp["color"], 0, fam)
            x = base[oid][0] + (e.get("label_dx") or 0)
            y = base[oid][1] + (e.get("label_dy") or 0)
            lb = (x, y, w, h)
            loid = f"L{oid}"
            pieces.append(_pdf_piece(self, loid, "label", lb, pdf, meta={"pdf": pdf, "scale": 1.0, "size": lp["size"]}))
            infos.append({"oid": loid, "kind": "label", "panel": oid, "text": names[oid],
                          "auto": e.get("label") == "auto", "box": [round(v, 4) for v in lb]})
        return pieces, infos

    def compose(self, fig: api.Figure, pieces: list[Piece]) -> pymupdf.Document:
        doc = pymupdf.open()
        page = doc.new_page(width=fig.width * MM, height=fig.height * MM)
        bg = self.c(fig.props["background"])
        if bg:
            page.draw_rect(page.rect, color=None, fill=rgb(bg), width=0)
        for pc in pieces:
            pc.draw(page, pc.box[0] * MM, pc.box[1] * MM)
        return doc

    def sprite(self, pc: Piece, px_per_mm: float) -> dict:
        """A transparent PNG of one piece: {file, x, y, w, h} (mm, where it goes on the figure)."""
        pad = pc.pad + 0.5
        x, y, w, h = pc.box
        W, H = max(w + 2 * pad, 0.2), max(h + 2 * pad, 0.2)
        out = self.cache / "sprites" / f"{_h(pc.key, round(px_per_mm, 2), round(W, 3), round(H, 3))}.png"
        if not out.exists():
            doc = pymupdf.open()
            page = doc.new_page(width=W * MM, height=H * MM)
            pc.draw(page, pad * MM, pad * MM)
            z = px_per_mm / MM
            pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=True)
            tmp = out.with_suffix(".tmp.png")
            pix.save(str(tmp))
            tmp.replace(out)
        return {"file": str(out), "x": x - pad, "y": y - pad, "w": W, "h": H}

    def render(self, file: str, px_per_mm: float = 12.0, sprites: bool = True, thumb_px: int = 320,
               dark: bool = False) -> dict:
        """Run and draw a figure file: what the editor shows and edits. `dark`: its dark version."""
        self._docs.clear()
        self.dark = dark
        file = str(self.resolve(file))
        name = Path(file).stem
        try:
            fig = self.run_figure(file)
        except Exception:                              # noqa: BLE001
            return {"figure": name, "file": str(Path(file).resolve()), "error": _user_traceback(Path(file).name)}
        pieces, infos, labels = self.pieces(fig)
        doc = self.compose(fig, pieces)
        out = self.cache / "out"
        page = doc[0]
        z = thumb_px / max(page.rect.width, page.rect.height)
        thumb = out / f"{name}{'.dark' if dark else ''}.thumb.png"
        page.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=False).save(str(thumb))
        by_oid = {i["oid"]: i for i in infos + labels}
        if sprites:
            for pc in pieces:
                if pc.oid in by_oid:
                    by_oid[pc.oid]["sprite"] = self.sprite(pc, px_per_mm)
        st, lab = fig.style, fig.labels
        return {
            "figure": name,
            "file": str(Path(file).resolve()),
            "size": [fig.width, fig.height],
            "background": self.c(fig.props["background"]),
            "dark": dark,
            "figureSite": fig.site,
            "figureProps": _jsonable(fig.props),
            "style": {"props": _jsonable(st.props), "site": st.site, "rc": _jsonable(st.rc),
                      "palette": [[k, v] for k, v in api.palette_colors(st.props.get("palette")).items()]},
            "palettes": api.PALETTES,
            "labelStyle": {"props": _jsonable(lab.props), "site": lab.site, "preset": lab.preset,
                           "viaFigure": lab is not st.labels},
            "journal": _journal_info(fig),
            "elements": infos,
            "labels": labels,
            "guides": [{"x": g["x"], "y": g["y"], "site": g["site"]} for g in fig.guides],
            "warnings": self.preflight(fig, pieces, infos, labels),
            "thumb": str(thumb),
            "pxPerMM": px_per_mm,
        }

    # --- checks ---

    def preflight(self, fig, pieces, infos, labels) -> list[dict]:
        """What a journal's production office would complain about."""
        st = fig.style
        min_font, min_dpi = st.min_font, st.min_dpi
        names = {l["panel"]: l["text"] for l in labels}
        warn = []

        def who(oid):
            info = next((i for i in infos if i["oid"] == oid), None)
            if oid in names:
                return f"panel {names[oid]}"
            if info and info["kind"] == "text":
                return f"text “{info['props']['text'][:24]}”"
            return f"{info['kind'] if info else 'element'} {oid}"

        for info in infos:
            if info.get("error"):
                warn.append({"level": "error", "oid": info["oid"],
                             "message": f"{who(info['oid'])} failed: {info['error'].strip().splitlines()[-1]}"})
        for pc in pieces:
            m = pc.meta
            if pc.kind in ("text", "label", "bracket") and m.get("size", 99) < min_font - 1e-6:
                warn.append({"level": "warning", "oid": pc.oid,
                             "message": f"{who(pc.oid)}: {m['size']:g} pt text is below the {min_font:g} pt minimum"})
            if m.get("pdf") and pc.kind in ("panel", "image"):
                try:
                    page = self._doc(m["pdf"])[0]
                except Exception:                      # noqa: BLE001
                    continue
                s = m.get("scale", 1.0)
                facts = self._facts(m["pdf"], page)
                if facts["min_size"] and facts["min_size"] * s < min_font - 0.05:
                    warn.append({"level": "warning", "oid": pc.oid,
                                 "message": f"{who(pc.oid)}: text as small as {facts['min_size'] * s:.1f} pt "
                                            f"(minimum {min_font:g} pt)"})
                if facts["type3"]:
                    warn.append({"level": "warning", "oid": pc.oid,
                                 "message": f"{who(pc.oid)}: Type 3 font {facts['type3']}; journals want TrueType or "
                                            "Type 1 (pdf.fonttype 42)"})
                for im in facts["images"]:
                    bw = (im["bbox"][2] - im["bbox"][0]) * s / 72
                    if bw > 0.2 and im["width"] / bw < min_dpi * 0.98:
                        warn.append({"level": "warning", "oid": pc.oid,
                                     "message": f"{who(pc.oid)}: a picture at {im['width'] / bw:.0f} dpi "
                                                f"(minimum {min_dpi:g})"})
                        break
            if pc.kind == "image" and not m.get("vector") and 0 < m.get("dpi", 1e9) < min_dpi * 0.98:
                warn.append({"level": "warning", "oid": pc.oid,
                             "message": f"{who(pc.oid)}: {m['dpi']:.0f} dpi at this size (minimum {min_dpi:g}); "
                                        "make it smaller or use a larger picture"})
        W, H = fig.width, fig.height
        for info in infos + labels:
            x, y, w, h = info["box"]
            if x < -0.01 or y < -0.01 or x + w > W + 0.01 or y + h > H + 0.01:
                warn.append({"level": "warning", "oid": info["oid"],
                             "message": f"{who(info.get('panel', info['oid']))}"
                                        f"{' label' if info['kind'] == 'label' else ''} reaches outside the figure"})
        for w_ in _colour_vision(infos, fig):
            if w_["oid"] is not None:
                w_["message"] = who(w_["oid"]) + w_["message"][w_["message"].index(":"):]
            warn.append(w_)
        seen = {}
        for l in labels:
            if l["text"] in seen:
                warn.append({"level": "warning", "oid": l["oid"], "message": f"two panels are labelled {l['text']}"})
            seen[l["text"]] = 1
        j = _journal_info(fig)
        if j and not j["fits"]:
            warn.append({"level": "info", "oid": None,
                         "message": f"{j['name']} figures are {', '.join(f'{v:g}' for v in j['widths'].values())} mm "
                                    f"wide; this one is {W:g} mm"})
        return warn

    _facts_cache: dict = {}

    def _facts(self, pdf: str, page) -> dict:
        """What preflight needs from a panel's PDF (smallest text, Type 3 fonts, pictures), once per drawing."""
        got = self._facts_cache.get(pdf)
        if got is None:
            sizes = [sp["size"] for b in page.get_text("dict").get("blocks", []) for ln in b.get("lines", [])
                     for sp in ln.get("spans", []) if sp.get("text", "").strip()]
            got = {"min_size": min(sizes) if sizes else None,
                   "type3": next((f[3] for f in page.get_fonts() if f[2] == "Type3"), None),
                   "images": [{"bbox": tuple(i["bbox"]), "width": i["width"]} for i in page.get_image_info()]}
            self._facts_cache[pdf] = got
        return got

    def export(self, file: str, path: str, fmt: str | None = None, dpi: int = 600, dark: bool = False,
               cmyk: bool = False, outline: bool = False, journal: str | None = None) -> dict:
        """Write the figure to `path` as PDF, SVG, EPS, PNG, TIFF or JPEG (`dark`: its dark version). `cmyk`
        converts colours for print (PDF, EPS, TIFF, JPEG); `outline` turns text into shapes (PDF, EPS, SVG).
        PDF/EPS conversions use Ghostscript.

        Resolution follows `journal` (else the style's journal, else the usual standard; see journals.dpi): a
        TIFF or JPEG is written at least at the dpi asked for line art, or for combination figures when the figure
        holds pictures; an EPS has anything Ghostscript must rasterize drawn at the line-art dpi. The file written
        is then measured, and pictures below the dpi asked for photographs are reported (`resolution`, warnings)."""
        self._docs.clear()
        self.dark = dark
        path = str(Path(path) if Path(path).is_absolute() else self._cwd / path)
        fig = self.run_figure(file)
        pieces, infos, labels = self.pieces(fig)
        doc = self.compose(fig, pieces)
        fmt = (fmt or Path(path).suffix.lstrip(".")).lower()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        if fmt == "png" and cmyk:
            raise ValueError("PNG has no CMYK; export a TIFF or a PDF")
        journal = (journal or fig.style.props.get("journal") or None)
        need = journals.dpi(journal)
        kind = "combination" if doc[0].get_image_info() else "line"
        notes = []
        used = int(dpi)
        if fmt in ("tif", "tiff", "jpg", "jpeg") and used < need[kind]:
            notes.append(f"{used} dpi raised to {need[kind]} dpi: {self._jname(journal)} that of {kind} figures")
            used = need[kind]
        if fmt in ("pdf", "eps"):
            doc.set_metadata({"creator": "Fignimble", "producer": "Fignimble (PyMuPDF)", "title": Path(file).stem})
            if fmt == "pdf" and not (cmyk or outline):
                doc.save(path, garbage=3, deflate=True)
            else:
                with tempfile.TemporaryDirectory() as tmp:
                    src = str(Path(tmp) / "in.pdf")
                    doc.save(src, garbage=3, deflate=True)
                    _ghostscript(src, path, fmt, cmyk, outline, dpi=need["line"])
        elif fmt == "svg":
            Path(path).write_text(doc[0].get_svg_image(text_as_path=outline), encoding="utf-8")
        elif fmt in ("png", "tif", "tiff", "jpg", "jpeg"):
            z = used / 72
            alpha = fmt == "png" and not self.c(fig.props["background"])
            pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=alpha)
            from PIL import Image
            im = Image.frombytes("RGBA" if alpha else "RGB", (pix.width, pix.height), pix.samples)
            if cmyk:
                im = _to_cmyk(im)
            if fmt == "png":
                im.save(path, dpi=(used, used))
            elif fmt in ("tif", "tiff"):
                im.save(path, dpi=(used, used), compression="tiff_lzw")
            else:
                im.save(path, dpi=(used, used), quality=95)
        else:
            raise ValueError(f"can't export {fmt}; use pdf, svg, eps, png, tiff or jpg")
        res = self._check_resolution(path, fmt, fig, pieces, need, kind, journal)
        res["notes"] = notes + res.get("notes", [])
        errors = [i for i in infos if i.get("error")]
        return {"ok": True, "path": str(Path(path).resolve()), "format": fmt, "resolution": res,
                "warnings": [f"element {i['oid']} failed: {i['error'].strip().splitlines()[-1]}" for i in errors]
                + res["problems"]}

    @staticmethod
    def _jname(journal):
        j = journals.JOURNALS.get((journal or "").lower())
        return j["name"] + " asks" if j else "journals ask"

    def _check_resolution(self, path, fmt, fig, pieces, need, kind, journal) -> dict:
        """Measure the file written: a raster's own dpi as printed, or every picture inside a PDF or EPS."""
        out = {"journal": journal, "kind": kind, "need": need, "problems": [], "notes": []}
        who = self._jname(journal)
        if fmt in ("png", "tif", "tiff", "jpg", "jpeg"):
            from PIL import Image
            with Image.open(path) as im:
                got = im.size[0] / (fig.width / 25.4)
                out["dpi"] = round(got)
                tag = im.info.get("dpi")
            out["ok"] = got >= need[kind] * 0.99
            if not out["ok"]:                            # a PNG is a preview or for slides: said, not a problem
                (out["notes"] if fmt == "png" else out["problems"]).append(
                    f"{out['dpi']} dpi; {who} {need[kind]} dpi of {kind} figures")
            if tag and abs(float(tag[0]) - got) > 1:
                out["problems"].append(f"the file says {float(tag[0]):.0f} dpi but holds {got:.0f}")
            return out
        if fmt == "svg":
            out["ok"] = True
            return out
        check, tmp = path, None
        if fmt == "eps":
            gs = _gs()
            if gs is None:
                out["ok"] = None
                out["notes"].append("not measured (no Ghostscript)")
                return out
            tmp = tempfile.TemporaryDirectory()
            check = str(Path(tmp.name) / "back.pdf")
            subprocess.run([gs, "-dNOPAUSE", "-dBATCH", "-dSAFER", "-dQUIET", "-dEPSCrop", "-sDEVICE=pdfwrite",
                            f"-sOutputFile={check}", path], capture_output=True)
        try:
            with pymupdf.open(check) as d:
                page = d[0]
                sx = fig.width * MM / page.rect.width                 # an EPS may come back at another scale
                worst = None
                for im in page.get_image_info():
                    bx0, by0, bx1, by1 = im["bbox"]
                    wi = (bx1 - bx0) * sx / 72
                    if wi < 0.2 or not im.get("width"):
                        continue
                    got = im["width"] / wi
                    cx, cy = (bx0 + bx1) / 2 * sx / MM, (by0 + by1) / 2 * sx / MM
                    oid = next((pc.oid for pc in reversed(pieces) if pc.box[0] <= cx <= pc.box[0] + pc.box[2]
                                and pc.box[1] <= cy <= pc.box[1] + pc.box[3]), None)
                    if worst is None or got < worst[0]:
                        worst = (got, oid)
                    if got < need["photo"] * 0.98:
                        out["problems"].append(f"a picture{f' in element {oid}' if oid else ''} is {got:.0f} dpi as "
                                               f"printed; {who} {need['photo']} dpi: use a larger picture or "
                                               "print it smaller")
        except Exception as exc:                          # noqa: BLE001
            out["ok"] = None
            out["notes"].append(f"not measured ({exc})")
            return out
        finally:
            if tmp:
                tmp.cleanup()
        out["pictures"] = round(worst[0]) if worst else None
        out["ok"] = not out["problems"]
        return out


# --- helpers ---

def _contain(aspect: float, w: float, h: float) -> tuple:
    if w / h > aspect:
        dw = h * aspect
        return ((w - dw) / 2, 0, dw, h)
    dh = w / aspect
    return (0, (h - dh) / 2, w, dh)


def _cover_clip(clip, aspect_box: float):
    c = pymupdf.Rect(clip)
    if c.width / c.height > aspect_box:
        nw = c.height * aspect_box
        c.x0 += (c.width - nw) / 2
        c.x1 = c.x0 + nw
    else:
        nh = c.width / aspect_box
        c.y0 += (c.height - nh) / 2
        c.y1 = c.y0 + nh
    return c


def _reading_order(items):
    """Rows top to bottom (a panel starts a new row when its top is clearly below the row's first), left to right
    within a row."""
    items = sorted(items, key=lambda t: (t[2][1], t[2][0]))
    rows = []
    for it in items:
        if rows:
            first = rows[-1][0][2]
            if it[2][1] - first[1] < min(8.0, 0.4 * max(first[3], 1)):
                rows[-1].append(it)
                continue
        rows.append([it])
    return [it for row in rows for it in sorted(row, key=lambda t: t[2][0])]


def _pdf_piece(r: Renderer, oid, kind, box, pdf, meta=None) -> Piece:
    def draw(page, ox, oy, pdf=pdf, w=box[2], h=box[3]):
        r._show_pdf(pdf, page, pymupdf.Rect(ox, oy, ox + w * MM, oy + h * MM))
    return Piece(oid, kind, box, _h(kind, pdf, box[2], box[3]), draw, meta=meta or {})


def _dashes(dash, width):
    if dash == "dashed":
        return f"[{3 * max(width, 0.5):.2f} {2 * max(width, 0.5):.2f}] 0"
    if dash == "dotted":
        return f"[{0.01:.2f} {2 * max(width, 0.5):.2f}] 0"
    return None


def _shape_piece(oid: str, e: api.Element, c=lambda v: v) -> Piece:
    p = dict(e.props)
    kind = e.kind
    if kind == "line":
        a0, b0 = (p["x1"], p["y1"]), (p["x2"], p["y2"])
        q = _control(a0, b0, p.get("curve") or 0)
        xs, ys = [a0[0], b0[0]] + ([q[0]] if q else []), [a0[1], b0[1]] + ([q[1]] if q else [])
        x0, y0 = min(xs), min(ys)
        box = (x0, y0, max(xs) - x0, max(ys) - y0)
        pad = max(p["head"] if p["arrow"] else 0, p["width"] / MM) + 0.3
        rel = lambda v: ((v[0] - x0) * MM, (v[1] - y0) * MM)          # noqa: E731
        a, b, cq = rel(a0), rel(b0), (rel(q) if q else None)
        key = _h("line", a, b, cq, {k: p.get(k) for k in ("width", "color", "arrow", "dash", "head", "tip")}, c(p["color"]))

        def draw(page, ox, oy):
            P = lambda v: pymupdf.Point(ox + v[0], oy + v[1])          # noqa: E731
            pts = [P(a), P(b)] if cq is None else [P(a), P(cq), P(b)]
            _stroke(page, pts, cq is not None, False, p, rgb(c(p["color"])), None)
        return Piece(oid, "line", box, key, draw, pad=pad)

    box = (p["x"], p["y"], p["w"], p["h"])
    pad = p["width"] / MM / 2 + 0.2
    key = _h(kind, box[2:], {k: p.get(k) for k in ("stroke", "fill", "width", "radius", "dash", "opacity")},
             c(p.get("stroke")), c(p.get("fill")))

    def draw(page, ox, oy):
        r = pymupdf.Rect(ox, oy, ox + p["w"] * MM, oy + p["h"] * MM)
        sh = page.new_shape()
        if kind == "ellipse":
            sh.draw_oval(r)
        elif p.get("radius"):
            sh.draw_rect(r, radius=min(0.5, p["radius"] / max(min(p["w"], p["h"]), 1e-6)))
        else:
            sh.draw_rect(r)
        sh.finish(color=rgb(c(p["stroke"])), fill=rgb(c(p["fill"])), width=p["width"] if p["stroke"] else 0,
                  dashes=_dashes(p["dash"], p["width"]), fill_opacity=p["opacity"], stroke_opacity=p["opacity"])
        sh.commit()
    return Piece(oid, kind, box, key, draw, pad=pad)


def _bracket_piece(r: Renderer, oid, e, pdf, tw, th) -> Piece:
    p = e.props
    x0, x1 = min(p["x1"], p["x2"]), max(p["x1"], p["x2"])
    gap = 0.4
    top = p["y"] - th - gap
    box = (min(x0, (x0 + x1) / 2 - tw / 2), top, max(x1 - x0, tw), th + gap + p["tick"])
    key = _h("bracket", pdf, x1 - x0, p["tick"], p["width"], r.c(p["color"]), box[2:])

    def draw(page, ox, oy):
        # coordinates relative to the box's top-left
        bx, by = box[0], box[1]
        X = lambda v: ox + (v - bx) * MM          # noqa: E731
        Y = lambda v: oy + (v - by) * MM          # noqa: E731
        sh = page.new_shape()
        sh.draw_polyline([pymupdf.Point(X(x0), Y(p["y"] + p["tick"])), pymupdf.Point(X(x0), Y(p["y"])),
                          pymupdf.Point(X(x1), Y(p["y"])), pymupdf.Point(X(x1), Y(p["y"] + p["tick"]))])
        sh.finish(color=rgb(r.c(p["color"])), width=p["width"], closePath=False)
        sh.commit()
        cx = (x0 + x1) / 2
        r._show_pdf(pdf, page, pymupdf.Rect(X(cx - tw / 2), Y(top), X(cx + tw / 2), Y(top + th)))
    return Piece(oid, "bracket", box, key, draw, pad=p["width"] / MM)


def _error_piece(oid, box, err) -> Piece:
    msg = err.strip().splitlines()[-1] if err.strip() else "error"

    def draw(page, ox, oy):
        r = pymupdf.Rect(ox, oy, ox + box[2] * MM, oy + box[3] * MM)
        page.draw_rect(r, color=(0.85, 0.2, 0.2), fill=(1, 0.93, 0.93), width=0.6)
        page.insert_textbox(r + (4, 4, -4, -4), "! " + msg, fontsize=6, fontname="helv",
                            color=(0.6, 0.1, 0.1))
    return Piece(oid, "error", box, _h("err", msg, box[2:]), draw)


def _rough_box(e) -> tuple:
    p = e.props
    if "x1" in p:
        return (min(p["x1"], p["x2"]), min(p.get("y1", p.get("y", 0)), p.get("y2", p.get("y", 0))),
                max(abs(p["x2"] - p["x1"]), 5), 5)
    return (p.get("x", 0), p.get("y", 0), p.get("w") or 20, p.get("h") or 15)


def _journal_info(fig):
    j = fig.props.get("journal")
    if not j or j not in journals.JOURNALS:
        return None
    info = journals.JOURNALS[j]
    fits = any(abs(fig.width - w) < 0.6 for w in info["widths"].values())
    return {"key": j, "name": info["name"], "widths": info["widths"], "fits": fits}


def _jsonable(v):
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if callable(v):
        return f"<function {getattr(v, '__name__', '?')}>"
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    return repr(v)


def _user_traceback(where: str) -> str:
    """The traceback of the exception being handled, without fignimble's own frames."""
    etype, exc, tb = sys.exc_info()
    frames = [f for f in traceback.extract_tb(tb) if os.path.dirname(os.path.abspath(f.filename)) != api._HERE
              and "runpy" not in f.filename]
    lines = traceback.format_list(frames[-6:]) + traceback.format_exception_only(etype, exc)
    return f"in {where}:\n" + "".join(lines)


DARK_RC = {
    "text.color": "#FFFFFF", "axes.labelcolor": "#FFFFFF", "axes.edgecolor": "#FFFFFF", "xtick.color": "#FFFFFF",
    "ytick.color": "#FFFFFF", "axes.facecolor": "none", "figure.facecolor": "none", "grid.color": "#4D4D4D",
    "patch.edgecolor": "#FFFFFF", "lines.color": "#FFFFFF", "hatch.color": "#FFFFFF", "legend.labelcolor": "#FFFFFF",
    "boxplot.boxprops.color": "#FFFFFF", "boxplot.whiskerprops.color": "#FFFFFF", "boxplot.capprops.color": "#FFFFFF",
    "boxplot.medianprops.color": "#FFFFFF", "boxplot.flierprops.markeredgecolor": "#FFFFFF",
}


def _write(path: Path, data: bytes):
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def _plot_area(fig):
    """The union of the boxes the layout gave the panel's axes (not colorbars), in figure fractions (x0, y0, x1,
    y1), or None. The allotted box, not the drawn one: a plot of fixed aspect (imshow) draws smaller than its box,
    and its whitespace isn't a margin to line others up to."""
    boxes = [a.get_position(original=True) for a in fig.axes if a.get_visible() and not hasattr(a, "_colorbar")]
    if not boxes:
        return None
    return (min(b.x0 for b in boxes), min(b.y0 for b in boxes), max(b.x1 for b in boxes), max(b.y1 for b in boxes))


def _remap(fig, area, target, w, h):
    """Move every axes so the plot area takes the target margins (l, t, r, b mm), keeping their arrangement."""
    x0, y0, x1, y1 = area
    l, t, r, b = target
    nx0, nx1 = l / w, 1 - r / w
    ny0, ny1 = b / h, 1 - t / h
    if nx1 - nx0 < 0.2 * (x1 - x0) or ny1 - ny0 < 0.2 * (y1 - y0):
        return                                       # no room: leave it as its code laid it out
    sx, sy = (nx1 - nx0) / (x1 - x0), (ny1 - ny0) / (y1 - y0)
    fig.set_layout_engine("none")
    for a in fig.axes:
        p = a.get_position(original=True)
        a.set_position([nx0 + (p.x0 - x0) * sx, ny0 + (p.y0 - y0) * sy, p.width * sx, p.height * sy])


def _align_targets(jobs) -> dict:
    """Margins that line up the plot areas of panels sharing an edge: for each side, the largest margin of the
    panels whose box has that edge in the same place (as patchwork does for a row or a column)."""
    out = {}
    live = [j for j in jobs if j["align"] and j["base"].get("margins")]
    for j in live:
        out[j["oid"]] = list(j["base"]["margins"])
    for side, edge in ((0, lambda b: b[0]), (1, lambda b: b[1]), (2, lambda b: b[0] + b[2]), (3, lambda b: b[1] + b[3])):
        groups = {}
        for j in live:
            groups.setdefault(round(edge(j["box"]), 1), []).append(j)
        for g in groups.values():
            if len(g) > 1:
                m = max(j["base"]["margins"][side] for j in g)
                for j in g:
                    out[j["oid"]][side] = m
    return out


def _take_legends(fig) -> list:
    """Take the legends out of a panel: their entries ({label, kind, color, ...}), for a collected legend."""
    from matplotlib.collections import Collection
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    out = []
    legends = [a.get_legend() for a in fig.axes if a.get_legend() is not None] + list(fig.legends)
    for lg in legends:
        for h, t in zip(lg.legend_handles, lg.get_texts()):
            e = {"label": t.get_text()}
            try:
                if isinstance(h, Line2D):
                    ls, mk = h.get_linestyle(), h.get_marker()
                    has_marker = mk not in (None, "None", "", " ")
                    e.update(kind="marker" if ls in ("None", "", " ") else "line", color=mcolors.to_hex(h.get_color()),
                             linestyle=ls, linewidth=h.get_linewidth(), marker=mk if has_marker else None,
                             markersize=h.get_markersize())
                elif isinstance(h, Patch):
                    e.update(kind="patch", color=mcolors.to_hex(h.get_facecolor()),
                             edgecolor=mcolors.to_hex(h.get_edgecolor()) if h.get_linewidth() else None)
                elif isinstance(h, Collection):
                    fc = h.get_facecolor()
                    e.update(kind="marker", marker="o", color=mcolors.to_hex(fc[0]) if len(fc) else "#000000",
                             markersize=5)
                else:
                    e.update(kind="patch", color="#888888")
            except (ValueError, TypeError, IndexError):
                e.update(kind="patch", color="#888888")
            out.append(e)
        lg.remove()
    return out


def _legend_entries(p: dict) -> list:
    """fig.legend's {label: colour or settings} as entries."""
    out = []
    for label, v in p["entries"].items():
        e = {"label": str(label)}
        if isinstance(v, dict):
            e.update(v)
            e.setdefault("kind", "marker" if p.get("marker") and "linestyle" not in v else
                     ("line" if "linestyle" in v or "linewidth" in v else "patch"))
        else:
            e.update(color=v, kind="marker" if p.get("marker") else "patch")
        if e["kind"] == "marker":
            e.setdefault("marker", p.get("marker") or "o")
        out.append(e)
    return out


def _proxy(e: dict):
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    color = e.get("color") or "#000000"
    if e.get("kind") == "line":
        return Line2D([], [], color=color, linestyle=e.get("linestyle") or "-", linewidth=e.get("linewidth") or 1.2,
                      marker=e.get("marker") or None, markersize=e.get("markersize") or 4)
    if e.get("kind") == "marker":
        return Line2D([], [], color=color, linestyle="None", marker=e.get("marker") or "o",
                      markersize=e.get("markersize") or 4)
    return Patch(facecolor=color, edgecolor=e.get("edgecolor") or "none")



def _control(a, b, curve):
    """The control point of a line bent by `curve` (a fraction of its length, + to the left of its direction)."""
    if not curve:
        return None
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy) or 1.0
    return ((a[0] + b[0]) / 2 + dy / n * curve * n, (a[1] + b[1]) / 2 - dx / n * curve * n)


def _tip(sh, to, ux, uy, L, kind, col, width) -> float:
    """Draw an arrowhead at `to` pointing along (ux, uy); how far the line should stop short of it."""
    if L <= 0:
        return 0.0
    wx, wy = -uy * L * 0.38, ux * L * 0.38
    base = pymupdf.Point(to.x - ux * L, to.y - uy * L)
    if kind == "bar":
        sh.draw_line(pymupdf.Point(to.x + wx * 1.2, to.y + wy * 1.2), pymupdf.Point(to.x - wx * 1.2, to.y - wy * 1.2))
        sh.finish(color=col, width=width)
        return 0.0
    if kind == "dot":
        sh.draw_circle(to, L * 0.3)
        sh.finish(color=None, fill=col, width=0)
        return L * 0.3
    if kind == "open":
        sh.draw_polyline([base + (wx, wy), to, base - (wx, wy)])
        sh.finish(color=col, width=width, closePath=False, lineJoin=1)
        return 0.0
    if kind == "stealth":
        notch = pymupdf.Point(to.x - ux * L * 0.65, to.y - uy * L * 0.65)
        sh.draw_polyline([to, base + (wx * 1.1, wy * 1.1), notch, base - (wx * 1.1, wy * 1.1), to])
        sh.finish(color=None, fill=col, closePath=True, width=0)
        return L * 0.6
    sh.draw_polyline([to, base + (wx, wy), base - (wx, wy), to])
    sh.finish(color=None, fill=col, closePath=True, width=0)
    return L * 0.75


def _stroke(page, pts, curved, closed, p, col, fill):
    """A line, curve or polyline through `pts` (page points) with p's arrowheads, dashes, width and opacity.
    curved: pts are (start, control, end) of a bend, or (with closed/smooth handled by the caller) ignored."""
    L = (p.get("head") or 1.6) * MM
    tip = p.get("tip") or "triangle"
    sh = page.new_shape()
    pts = list(pts)

    def unit(frm, to):
        dx, dy = to.x - frm.x, to.y - frm.y
        n = math.hypot(dx, dy) or 1.0
        return dx / n, dy / n

    if p.get("arrow") and not closed and len(pts) >= 2:
        if p["arrow"] in ("end", "both"):
            ux, uy = unit(pts[-2], pts[-1])
            cut = _tip(sh, pts[-1], ux, uy, L, tip, col, p["width"])
            pts[-1] = pymupdf.Point(pts[-1].x - ux * cut, pts[-1].y - uy * cut)
        if p["arrow"] in ("start", "both"):
            ux, uy = unit(pts[1], pts[0])
            cut = _tip(sh, pts[0], ux, uy, L, tip, col, p["width"])
            pts[0] = pymupdf.Point(pts[0].x - ux * cut, pts[0].y - uy * cut)
    if curved and len(pts) == 3:
        s0, q, e0 = pts
        sh.draw_bezier(s0, s0 + (q - s0) * (2 / 3), e0 + (q - e0) * (2 / 3), e0)
    elif p.get("smooth") and len(pts) > 2:
        for a, c1, c2, b in _catmull(pts, closed):
            sh.draw_bezier(a, c1, c2, b)
    else:
        sh.draw_polyline(pts + ([pts[0]] if closed else []))
    sh.finish(color=col, fill=fill, width=p["width"] if col is not None else 0, closePath=closed,
              dashes=_dashes(p.get("dash"), p["width"]), lineCap=1 if p.get("dash") == "dotted" else 0, lineJoin=1,
              fill_opacity=p.get("opacity", 1.0), stroke_opacity=p.get("opacity", 1.0))
    sh.commit()


def _catmull(pts, closed):
    """Bezier segments of a smooth curve through the points (Catmull-Rom)."""
    n = len(pts)
    out = []
    for i in range(n if closed else n - 1):
        p0 = pts[(i - 1) % n] if (closed or i > 0) else pts[i]
        p1, p2 = pts[i], pts[(i + 1) % n]
        p3 = pts[(i + 2) % n] if (closed or i + 2 < n) else p2
        out.append((p1, p1 + (p2 - p0) * (1 / 6), p2 - (p3 - p1) * (1 / 6), p2))
    return out


def _path_piece(oid: str, e, c=lambda v: v) -> Piece:
    p = e.props
    xs, ys = [q[0] for q in p["points"]], [q[1] for q in p["points"]]
    x0, y0 = min(xs), min(ys)
    box = (x0, y0, max(xs) - x0, max(ys) - y0)
    pad = max(p["head"] if p["arrow"] else 0, p["width"] / MM) + (2.0 if p["smooth"] else 0.3)
    rel = [((q[0] - x0) * MM, (q[1] - y0) * MM) for q in p["points"]]
    key = _h("path", rel, {k: p.get(k) for k in ("closed", "smooth", "stroke", "fill", "width", "dash", "arrow", "tip",
                                               "head", "opacity")}, c(p["stroke"]), c(p["fill"]))

    def draw(page, ox, oy):
        pts = [pymupdf.Point(ox + a, oy + b) for a, b in rel]
        _stroke(page, pts, False, p["closed"], p, rgb(c(p["stroke"])), rgb(c(p["fill"])) if p["fill"] else None)
    return Piece(oid, "path", box, key, draw, pad=pad)


def _zoom_lines(reg, tgt):
    """The two lines from a zoom box to its magnified view: from the box's sides facing the view."""
    rx, ry, rw, rh = reg
    tx, ty, tw, th = tgt
    dx = (tx + tw / 2) - (rx + rw / 2)
    dy = (ty + th / 2) - (ry + rh / 2)
    if abs(dx) * th >= abs(dy) * tw:                    # side by side
        if dx > 0:
            return [((rx + rw, ry), (tx, ty)), ((rx + rw, ry + rh), (tx, ty + th))]
        return [((rx, ry), (tx + tw, ty)), ((rx, ry + rh), (tx + tw, ty + th))]
    if dy > 0:
        return [((rx, ry + rh), (tx, ty)), ((rx + rw, ry + rh), (tx + tw, ty))]
    return [((rx, ry), (tx, ty + th)), ((rx + rw, ry), (tx + tw, ty + th))]


def _picture_props(obj):
    """The settings of a picture: a fig.image Element, an inset of an Image, or an Image in a layout."""
    if isinstance(obj, api.Element):
        if obj.kind == "image":
            return obj.props
        if obj.kind == "inset" and isinstance(obj.node, api.Image):
            return obj.node.props
        return None
    if isinstance(obj, api.Image):
        return obj.props
    return None


def _sync_zooms(fig, project):
    """Zoom boxes with sync: crop a magnified picture of the same file to the box (before anything is drawn)."""
    for e in fig.elements:
        if e.kind != "zoom" or not e.props.get("sync"):
            continue
        sp, tp = _picture_props(e.source), _picture_props(e.target)
        if not sp or not tp or Path(project / sp["source"]).resolve() != Path(project / tp["source"]).resolve():
            continue
        l, t, r, b = sp.get("crop") or (0, 0, 0, 0)
        rx, ry, rw, rh = e.props["region"]
        fx0, fx1 = l + rx * (1 - l - r), l + (rx + rw) * (1 - l - r)
        fy0, fy1 = t + ry * (1 - t - b), t + (ry + rh) * (1 - t - b)
        tp["crop"] = (round(fx0, 5), round(fy0, 5), round(1 - fx1, 5), round(1 - fy1, 5))


def _text_artists(fig) -> dict:
    """The texts of a panel by a stable key: ax0.xlabel, ax0.ytick3, ax1.legend2, fig.suptitle, ..."""
    out = {}
    for i, ax in enumerate(fig.axes):
        k = f"ax{i}"
        for name, t in (("xlabel", ax.xaxis.label), ("ylabel", ax.yaxis.label), ("title", ax.title),
                        ("ltitle", getattr(ax, "_left_title", None)), ("rtitle", getattr(ax, "_right_title", None))):
            if t is not None:
                out[f"{k}.{name}"] = t
        for j, t in enumerate(ax.get_xticklabels()):
            out[f"{k}.xtick{j}"] = t
        for j, t in enumerate(ax.get_yticklabels()):
            out[f"{k}.ytick{j}"] = t
        lg = ax.get_legend()
        if lg is not None:
            for j, t in enumerate(lg.get_texts()):
                out[f"{k}.legend{j}"] = t
            out[f"{k}.legendtitle"] = lg.get_title()
        for j, t in enumerate(ax.texts):
            out[f"{k}.text{j}"] = t
    for j, t in enumerate(fig.texts):
        out[f"fig.text{j}"] = t
    for name in ("_suptitle", "_supxlabel", "_supylabel"):
        t = getattr(fig, name, None)
        if t is not None:
            out[f"fig.{name.strip('_')}"] = t
    for n, lg in enumerate(fig.legends):
        for j, t in enumerate(lg.get_texts()):
            out[f"fig.legend{n}.{j}"] = t
    return out


def _set_texts(fig, texts, ticks: bool) -> bool:
    """Put the editor's retyped texts in place (tick labels after a first draw, when they exist)."""
    if not texts:
        return False
    arts = _text_artists(fig)
    changed = False
    if not ticks:
        for k, v in texts.items():
            if "tick" not in k and k in arts:
                arts[k].set_text(v)
                changed = True
        return changed
    for i, ax in enumerate(fig.axes):
        for axis, which in (("x", ax.xaxis), ("y", ax.yaxis)):
            keys = {int(k.rsplit("tick", 1)[1]): v for k, v in texts.items()
                    if k.startswith(f"ax{i}.{axis}tick") and k.rsplit("tick", 1)[1].isdigit()}
            if not keys:
                continue
            locs = which.get_ticklocs()
            labels = [t.get_text() for t in which.get_ticklabels()]
            for j, v in keys.items():
                if j < len(labels):
                    labels[j] = v
            (ax.set_xticks if axis == "x" else ax.set_yticks)(locs, labels)
            changed = True
    return changed


_TEXT_PROPS = {"size": "fontsize", "color": "color", "weight": "fontweight", "style": "fontstyle"}


def _set_text_style(fig, styles, ticks: bool) -> bool:
    """Give texts the editor restyled their size, colour, weight and slant (tick labels after a first draw)."""
    if not styles:
        return False
    arts = _text_artists(fig)
    changed = False
    for k, st in styles.items():
        if ("tick" in k) != ticks or k not in arts or not isinstance(st, dict):
            continue
        t = arts[k]
        for name, v in st.items():
            if name in _TEXT_PROPS and v is not None:
                getattr(t, "set_" + _TEXT_PROPS[name])(v)
                changed = True
    return changed


def _is_bold(weight) -> bool:
    if isinstance(weight, (int, float)):
        return weight >= 600
    return str(weight) in ("semibold", "demibold", "demi", "bold", "heavy", "extra bold", "black")


def _measure_texts(fig, h) -> list:
    """Where the panel's texts are: [{key, text, box (x, y, w, h mm from the panel's top-left), size, rotation,
    color, bold, italic}]."""
    import matplotlib.colors as mcolors
    r = fig.canvas.get_renderer()
    out = []
    for k, t in _text_artists(fig).items():
        try:
            if not t.get_visible() or not t.get_text().strip():
                continue
            b = t.get_window_extent(r)
        except Exception:                                # noqa: BLE001
            continue
        if b.width <= 0:
            continue
        d = fig.dpi
        try:
            color = mcolors.to_hex(t.get_color()).upper()
        except ValueError:
            color = None
        out.append({"key": k, "text": t.get_text(), "size": t.get_fontsize(), "rotation": t.get_rotation(),
                    "color": color, "bold": _is_bold(t.get_fontweight()), "italic": t.get_fontstyle() in ("italic", "oblique"),
                    "box": [round(b.x0 / d * 25.4, 3), round(h - b.y1 / d * 25.4, 3), round(b.width / d * 25.4, 3),
                            round(b.height / d * 25.4, 3)]})
    return out[:400]


_FONT_NAMES: dict = {}


def _math_rc(family) -> dict:
    """Mathtext in the text's own font, so **bold**, ^{2} and _{i} match the words around them."""
    key = tuple(family)
    name = _FONT_NAMES.get(key)
    if name is None:
        from matplotlib import font_manager
        try:
            path = font_manager.findfont(font_manager.FontProperties(family=list(family)), fallback_to_default=True)
            name = font_manager.get_font(path).family_name
        except Exception:                                # noqa: BLE001
            name = "DejaVu Sans"
        _FONT_NAMES[key] = name
    rc = {"mathtext.fontset": "custom", "mathtext.rm": name, "mathtext.it": f"{name}:italic",
          "mathtext.bf": f"{name}:bold", "mathtext.sf": name}
    if "mathtext.bfit" in matplotlib.rcParams:
        rc["mathtext.bfit"] = f"{name}:italic:bold"
    return rc


_MARKUP = re.compile(r"(\$[^$]*\$)|\*\*(.+?)\*\*|\*(.+?)\*|\^\{(.+?)\}|_\{(.+?)\}")


def _runs(text: str) -> list:
    """Markup as runs [(text, kind)]: plain, math, bold, italic, sup, sub."""
    out, at = [], 0
    for m in _MARKUP.finditer(text):
        if m.start() > at:
            out.append((text[at:m.start()], "plain"))
        kind = ["math", "bold", "italic", "sup", "sub"][next(i for i in range(5) if m.group(i + 1) is not None)]
        out.append((m.group(m.lastindex), kind))
        at = m.end()
    if at < len(text):
        out.append((text[at:], "plain"))
    return out


def _mt(s: str) -> str:
    """Text written inside mathtext."""
    s = s.replace("\\", r"\backslash ")
    for ch in "{}_^$%#&":
        s = s.replace(ch, "\\" + ch)
    return s.replace(" ", r"\ ")


def _as_mathtext(runs, bold_base: bool) -> str:
    rm = r"\mathbf" if bold_base else r"\mathrm"
    out = []
    for t, kind in runs:
        if kind == "plain":
            out.append(t.replace("$", r"\$"))
        elif kind == "math":
            out.append(t if t.startswith("$") else f"${t}$")
        elif kind == "bold":
            out.append(rf"$\mathbf{{{_mt(t)}}}$")
        elif kind == "italic":
            out.append(rf"$\mathit{{{_mt(t)}}}$" if not bold_base else rf"$\mathbfit{{{_mt(t)}}}$"
                       if "mathtext.bfit" in matplotlib.rcParams else rf"$\mathit{{{_mt(t)}}}$")
        elif kind == "sup":
            out.append(rf"$^{{{rm}{{{_mt(t)}}}}}$")
        else:
            out.append(rf"$_{{{rm}{{{_mt(t)}}}}}$")
    return "".join(out)


def _rich(text: str, bold_base: bool, width, fig, props) -> str:
    """The string matplotlib draws for a text with markup, its lines wrapped at `width` mm."""
    runs = _runs(text)
    plain = all(k in ("plain", "math") for _, k in runs)
    if not width:
        return text if plain else _as_mathtext(runs, bold_base)
    r = fig.canvas.get_renderer()

    def measure(line_runs) -> float:
        t = fig.text(0, 0, _as_mathtext(line_runs, bold_base), **props)
        w = t.get_window_extent(r).width / fig.dpi * 25.4
        t.remove()
        return w

    lines = []
    for para in text.split("\n"):
        words = []                                       # words as lists of runs
        cur = []
        for t, kind in _runs(para):
            if kind in ("plain", "bold", "italic"):
                parts = t.split(" ")
                for i, w in enumerate(parts):
                    if i > 0:
                        words.append(cur)
                        cur = []
                    if w:
                        cur.append((w, kind))
            else:
                cur.append((t, kind))
        words.append(cur)
        words = [w for w in words if w]
        line = []
        for w in words:
            trial = line + ([(" ", "plain")] if line else []) + w
            if line and measure(trial) > width:
                lines.append(line)
                line = list(w)
            else:
                line = trial
        lines.append(line)
    return "\n".join(_as_mathtext(l, bold_base) for l in lines)


def _gs():
    return shutil.which("gs") or next((p for p in ("/opt/homebrew/bin/gs", "/usr/local/bin/gs") if Path(p).exists()), None)


def _ghostscript(src: str, dest: str, fmt: str, cmyk: bool, outline: bool, dpi: int = 1200):
    """Convert with Ghostscript. `dpi`: the resolution of anything it has to rasterize (EPS has no transparency),
    and pictures keep their pixels (no downsampling)."""
    gs = _gs()
    if gs is None:
        raise RuntimeError("EPS, CMYK PDF and outlined text need Ghostscript: brew install ghostscript")
    args = [gs, "-dNOPAUSE", "-dBATCH", "-dSAFER", "-dQUIET", f"-r{int(dpi)}",
            "-dDownsampleColorImages=false", "-dDownsampleGrayImages=false", "-dDownsampleMonoImages=false",
            "-sDEVICE=" + ("eps2write" if fmt == "eps" else "pdfwrite"), f"-sOutputFile={dest}"]
    if cmyk:
        args += ["-sColorConversionStrategy=CMYK", "-dProcessColorModel=/DeviceCMYK"]
    if outline:
        args += ["-dNoOutputFonts"]
    r = subprocess.run(args + [src], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("Ghostscript failed: " + (r.stderr or r.stdout).strip()[-400:])


def _to_cmyk(im):
    """A picture in CMYK for print, through the system's generic CMYK profile when there is one."""
    from PIL import ImageCms
    prof = Path("/System/Library/ColorSync/Profiles/Generic CMYK Profile.icc")
    im = im.convert("RGB")
    if prof.exists():
        try:
            srgb = ImageCms.createProfile("sRGB")
            return ImageCms.profileToProfile(im, srgb, str(prof), outputMode="CMYK")
        except Exception:                                # noqa: BLE001
            pass
    return im.convert("CMYK")



def _color_artists(fig) -> dict:
    """The coloured marks of a panel by a stable key: ax0.line1, ax0.coll0 (scatters, fills), ax0.patch3 (bars)."""
    out = {}
    for i, ax in enumerate(fig.axes):
        if hasattr(ax, "_colorbar"):
            continue
        for j, a in enumerate(ax.lines):
            out[f"ax{i}.line{j}"] = a
        for j, a in enumerate(ax.collections):
            out[f"ax{i}.coll{j}"] = a
        for j, a in enumerate(ax.patches):
            out[f"ax{i}.patch{j}"] = a
    return out


def _artist_color(a):
    """The single colour of a mark as #RRGGBB, or None (colour-mapped, invisible)."""
    from matplotlib.collections import Collection
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    try:
        if isinstance(a, Line2D):
            line = a.get_linestyle() not in ("None", "", " ")
            marker = a.get_marker() not in (None, "None", "", " ")
            if not a.get_visible() or not (line or marker):
                return None
            if line:
                return mcolors.to_hex(a.get_color())
            # markers only (error-bar caps, dots): the colour they are drawn in
            unfilled = str(a.get_marker()) in "_|x+1234" or a.get_markerfacecolor() in ("none", "None")
            return mcolors.to_hex(a.get_markeredgecolor() if unfilled else a.get_markerfacecolor())
        if isinstance(a, Collection):
            if a.get_array() is not None and len(a.get_array()) > 1:
                return None                              # colour-mapped
            fc = a.get_facecolor()
            if len(fc) == 0 or all(c[3] == 0 for c in fc):
                fc = a.get_edgecolor()
            if len(fc) == 0:
                return None
            first = mcolors.to_hex(fc[0])
            return first if all(mcolors.to_hex(c) == first for c in fc) else None
        if isinstance(a, Patch):
            fc = a.get_facecolor()
            return mcolors.to_hex(fc if fc[3] > 0 else a.get_edgecolor())
    except (ValueError, TypeError, IndexError):
        return None
    return None


def _set_colors(fig, colors):
    """Recolour marks the editor recoloured (and the legend's swatches of the same colour)."""
    if not colors:
        return
    from matplotlib.collections import Collection
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    arts = _color_artists(fig)
    swaps = {}
    for k, c in colors.items():
        a = arts.get(k)
        if a is None:
            continue
        old = _artist_color(a)
        if isinstance(a, Line2D):
            a.set_color(c)
            a.set_markeredgecolor(c)
            a.set_markerfacecolor(c)
        elif isinstance(a, Collection):
            a.set_facecolor(c)
            if a.get_linewidths() is not None and len(a.get_edgecolor()):
                a.set_edgecolor(c)
        elif isinstance(a, Patch):
            a.set_facecolor(c)
        if old:
            swaps[old] = c
    legends = [ax.get_legend() for ax in fig.axes if ax.get_legend() is not None] + list(fig.legends)
    for lg in legends:
        for h in lg.legend_handles:
            hc = _artist_color(h)
            if hc in swaps:
                if isinstance(h, Line2D):
                    h.set_color(swaps[hc])
                    h.set_markerfacecolor(swaps[hc])
                    h.set_markeredgecolor(swaps[hc])
                elif isinstance(h, (Collection, Patch)):
                    h.set_facecolor(swaps[hc])


def _measure_marks(fig, h) -> list:
    """The panel's coloured marks: [{key, color, box (mm in the panel)}]."""
    r = fig.canvas.get_renderer()
    out = []
    for k, a in _color_artists(fig).items():
        c = _artist_color(a)
        if not c:
            continue
        try:
            b = a.get_window_extent(r)
        except Exception:                                # noqa: BLE001
            continue
        if not (b.width > 0 or b.height > 0) or not all(map(math.isfinite, (b.x0, b.y0, b.x1, b.y1))):
            continue
        d = fig.dpi
        out.append({"key": k, "color": c.upper(),
                    "box": [round(b.x0 / d * 25.4, 3), round(h - b.y1 / d * 25.4, 3), round(b.width / d * 25.4, 3),
                            round(b.height / d * 25.4, 3)]})
    return out[:600]


# colour vision deficiencies (Machado et al. 2009, severity 1), applied in linear RGB
_CVD = {
    "deuteranopia": ((0.367322, 0.860646, -0.227968), (0.280085, 0.672501, 0.047413), (-0.011820, 0.042940, 0.968881)),
    "protanopia": ((0.152286, 1.052583, -0.204868), (0.114503, 0.786281, 0.099216), (-0.003882, -0.048116, 1.051998)),
    "tritanopia": ((1.255528, -0.076749, -0.178779), (-0.078411, 0.930809, 0.147602), (0.004733, 0.691367, 0.303900)),
}


def _lin(v):
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def _lab(rgb_lin):
    r, g, b = rgb_lin
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116   # noqa: E731
    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def _de(a, b) -> float:
    return math.dist(_lab(a), _lab(b))


def _seen_as(color: str, kind: str):
    lin = tuple(_lin(v) for v in mcolors.to_rgb(color))
    m = _CVD[kind]
    return tuple(min(1.0, max(0.0, sum(m[i][j] * lin[j] for j in range(3)))) for i in range(3))


def _colourful(c: str) -> bool:
    r, g, b = mcolors.to_rgb(c)
    return max(r, g, b) - min(r, g, b) > 0.12


def _clashes(colors) -> list:
    """Pairs of colours that most people tell apart but some can't: [(a, b, [deficiencies])]."""
    cs = sorted({c.upper() for c in colors if c and _colourful(c)})
    out = []
    for i, a in enumerate(cs):
        for b in cs[i + 1:]:
            la, lb = tuple(_lin(v) for v in mcolors.to_rgb(a)), tuple(_lin(v) for v in mcolors.to_rgb(b))
            if _de(la, lb) < 20:
                continue
            kinds = [k for k in _CVD if _de(_seen_as(a, k), _seen_as(b, k)) < 9]
            if kinds:
                out.append((a, b, kinds))
    return out


def _colour_vision(infos, fig) -> list:
    """Preflight: colours in a panel (or among the annotations) that look alike to colour-blind readers."""
    warn = []
    for info in infos:
        marks = info.get("marks") or []
        if not marks:
            continue
        for a, b, kinds in _clashes(m["color"] for m in marks)[:3]:
            warn.append({"level": "warning", "oid": info["oid"], "colors": [a, b],
                         "message": f"{info.get('kind')} {info['oid']}: {a} and {b} look alike with "
                                    f"{', '.join(kinds)}; use a colour-blind-safe palette or tell them apart another way"})
    notes = [e["props"].get(k) for e in infos if e["kind"] in ("text", "line", "rect", "ellipse", "path", "bracket")
             for k in ("color", "stroke", "fill") if isinstance(e["props"].get(k), str)]
    for a, b, kinds in _clashes(notes)[:3]:
        warn.append({"level": "warning", "oid": None, "colors": [a, b],
                     "message": f"annotations in {a} and {b} look alike with {', '.join(kinds)}"})
    return warn
