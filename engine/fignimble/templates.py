"""Starting points for new projects, figures and panels, and what a coding agent is told about a project."""

from __future__ import annotations

from pathlib import Path

from . import journals


def style_py(journal: str | None) -> str:
    if journal:
        return f'''"""The look every figure of this project shares: font, text size, line widths and panel labels.
Change it here and every figure follows."""
from fignimble import *

STYLE = Style.journal("{journal}", labels=Labels.journal("{journal}"), palette="okabe-ito")
'''
    return '''"""The look every figure of this project shares: font, text size, line widths and panel labels.
Change it here and every figure follows."""
from fignimble import *

STYLE = Style(font="Arial", size=7, linewidth=0.6, labels=Labels(format="{}", case="lower", size=8, weight="bold"),
              palette="okabe-ito")
'''


def figure_py(width: float, height: float, with_example: bool = False) -> str:
    body = ""
    if with_example:
        # two panels side by side, 4 mm from the edges and from each other, whatever the width
        w = round((width - 12) / 2, 1)
        body = (f'\nfig.panel("panels/example.py", x=4, y=3, w={w:g}, h=60)\n'
                f'fig.panel("panels/example.py", x={8 + w:g}, y=3, w={w:g}, h=60, args={{"kind": "bars"}})\n')
    return f'''from fignimble import *
from style import STYLE

fig = Figure(width={width:g}, height={height:g}, style=STYLE)
{body}'''


def panel_py(name: str = "example") -> str:
    return '''"""A panel: draw(fig) gets a matplotlib Figure exactly the panel's size. Fonts, text sizes and line widths come
from the project's style, so leave them out here and every panel will match."""
import numpy as np


def draw(fig, kind="lines"):
    ax = fig.add_subplot()
    x = np.linspace(0, 10, 100)
    if kind == "bars":
        ax.bar(["A", "B", "C"], [3, 5, 2], color="#4c72b0")
        ax.set_ylabel("Count")
    else:
        ax.plot(x, np.sin(x), label="sin")
        ax.plot(x, np.cos(x), label="cos")
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Signal")
        ax.legend()
'''


def new_project(folder: str, journal: str | None = "nature") -> dict:
    """A new project folder with a style, a first figure and an example panel."""
    d = Path(folder)
    if d.exists() and any(p for p in d.iterdir() if not p.name.startswith(".")):
        raise FileExistsError(f"{d} is not empty")
    (d / "panels").mkdir(parents=True, exist_ok=True)
    (d / "images").mkdir(exist_ok=True)
    width = journals.width(journal, "double") if journal else 183
    (d / "style.py").write_text(style_py(journal), encoding="utf-8")
    (d / "fig1.py").write_text(figure_py(width, 100, with_example=True), encoding="utf-8")
    (d / "panels" / "example.py").write_text(panel_py(), encoding="utf-8")
    (d / ".gitignore").write_text(".fignimble/\n", encoding="utf-8")
    return {"ok": True, "project": str(d.resolve()), "figure": "fig1"}


AGENT_FILES = ("CLAUDE.md", "AGENTS.md", "GEMINI.md")
AGENT_MARK = "<!-- written by Fignimble; removed when Fignimble closes the project -->"

AGENT_TEXT = AGENT_MARK + '''
# Editing figures in this project with Fignimble

This folder is a Fignimble project: publication figures with several panels, each figure written in Python. The user
sees the figures in Fignimble, a figure editor, while you edit the code here, and edits them by hand there too (moving,
resizing, retyping). Fignimble re-renders a figure about a second after you save a file. (This file was written by
Fignimble and is not part of the project; don't edit it.)

## How a project is laid out

- **Figure files** are the top-level `.py` files that make a `Figure` (`fig1.py`, `fig2.py`, ...). Each places
  elements on its figure, one call per element. Units are **millimetres**, from the figure's **top-left corner, y
  pointing down**.
- **Panels** are drawn by Python files, usually in `panels/`. A panel file has a function `draw(fig, ...)` that gets
  a matplotlib `Figure` of exactly the panel's size (`fig.add_subplot()`, `fig.subplots(2, 2)`, `fig.colorbar(...)`
  all work). `fig.panel("panels/x.py", function="other", args={"gene": "CD3E"})` calls `other(fig, gene="CD3E")`,
  so one file can draw several panels.
- **`style.py`** holds the `Style` every figure imports: font, text size, line widths, and the `Labels` (a, b, c...).

```python
from fignimble import *
from style import STYLE

fig = Figure(width=183, height=120, style=STYLE)
fig.panel("panels/expression.py", x=2, y=2, w=88, h=55)           # labelled a automatically
fig.image("images/gel.png", x=93, y=2, w=88)                       # pictures are panels too (b); h follows aspect
fig.text("Treated", x=40, y=60, size=7, weight="bold", align="center")
fig.arrow(60, 70, 80, 70)                       # also fig.line, fig.rect, fig.ellipse, fig.bracket(x1, x2, y, "**")
```

Panels can also be laid out **patchwork style**: the layout gives each panel its place, lines up their plot areas
across rows and columns, and can collect the legends they share into one:

```python
a, b, c, d = Panel("panels/a.py"), Panel("panels/b.py"), Panel("panels/c.py"), Image("images/gel.png")
fig.layout((a | b | c) / (d | Spacer()), x=0, y=0, w=183, h=120, heights=[2, 1], gap=4)     # | beside, / below
fig.layout(Grid(a, b, c, d, ncol=2), x=0, y=0, w=183, h=120)                               # + wraps into a grid
fig.layout(Design("""
    AAB
    CDB
""", A=a, B=b, C=c, D=d), x=0, y=0, w=183, h=120, widths=[1, 1, 1.5], guides="collect", legend="bottom")
fig.inset(Panel("panels/zoom.py"), within=a, x=0.6, y=0.05, w=0.35, h=0.35)   # fractions of a's box
fig.legend({"WT": "#999999", "KO": "#d1495b"}, x=150, y=5)                   # one legend shared by panels
```

`Row(..., widths=[2, 1])`, `Column(..., heights=[...])`, `Grid(..., ncol=, nrow=)` give a part of a layout its own
sizes. Panels on the figure are lined up the same way whenever they share an edge (`Style(align_axes=False)` turns
this off). Prefer a layout for regular grids of plots, and free `fig.panel(...)` for figures arranged by hand.

Every figure also has a **dark version** for talks (`fignimble snapshot fig1.py --dark`): fignimble turns the style's
text and axes white and the background black. Colours panel code sets itself stay as they are, so in panel code
use `"white" if is_dark() else "black"` (from fignimble) wherever you would write black.

Annotations: `fig.text("**bold** *italic* 10^{3} CD8_{a}", width=60)` (markup; `width` wraps), `fig.arrow(...,
curve=0.3, tip="stealth")`, `fig.path(points, smooth=True, closed=True, fill=...)`, `fig.scalebar(picture, length=50,
unit="µm", pixel_size=0.325)`, `fig.zoom(picture, inset, region=(x, y, w, h))` (fractions; the inset of the same
picture is cropped to the region). Pictures take `rotation=` and `flip="h"`. `Style(palette={"WT": "#999999", ...})`
sets the colours panels plot with (or a named one: `palette="okabe-ito"`, colour-blind safe); use `color("WT")` in
panel code rather than repeating hex codes, and keep colour-blind readers in mind (`fignimble info` warns about colours
they can't tell apart). A panel's `texts={"ax0.xlabel": "..."}`, `text_style={"ax0.legend0": {"size": 8, "color": "#...", "weight": "bold"}}`
and `colors={"ax0.line1": "#..."}` hold texts, text settings and colours the user changed on the canvas: leave them alone, or move them into the panel's code and remove the entries. `locked=True` / `hidden=True` are the user's layer settings: keep them.

Other options: `label=None` (no letter) or `label="a'"` on a panel; `fit=`/`crop=` on images; `group="g1"` to keep
elements together; `fig.guide(x=91.5)` for an editor guide line. Run `python -c "import fignimble; help(fignimble.Figure)"`
for every argument.

## Look at what you made

- `fignimble snapshot fig1.py` renders the figure to a PNG and prints its path. Open that picture to check your work.
- `fignimble info fig1.py` lists every element with its box (mm), the panel labels, and the preflight warnings (text
  below the journal's minimum size, low-resolution pictures, elements outside the figure).
- `fignimble export fig1.py fig1.pdf` writes the figure (PDF, SVG, PNG, TIFF; `--dark` for its dark version). Don't run
  other renderers.

## Keep the figures editable by hand

Fignimble moves and resizes an element by rewriting the numbers in the call that made it, so:

- Give `x`, `y`, `w`, `h` (and line ends) as **literal numbers**. A computed position (`x=a.right + 2`) can't be
  dragged; use one only when asked to tie elements together.
- **Never draw panel letters yourself** (no `fig.text("a", ...)`, no `ax.set_title("a")`). Labels are automatic, in
  reading order, styled by `Labels` in `style.py`; to change their look, change that one `Labels(...)`.
- In panel code, **don't set font sizes, font families or line widths, and don't call `plt.figure`, `figsize`,
  `savefig`, `tight_layout` or `plt.show`**. The style sets fonts and sizes so all panels match, and Fignimble lays out and
  saves each panel at its size. (Use `fig` rather than `plt` where you can.)
- Don't reformat or reorder code you weren't asked to change: the order of the calls is the stacking order, and the
  user's own edits are in those lines.

## Working with the user

- Make one change at a time and say which figure and panel it touched.
- If a panel fails, Fignimble shows it red with the error, and `fignimble info` prints it. Fix the code.
- The user's Undo in Fignimble undoes only Fignimble's own edits, not yours.
'''


def write_agent_files(project: Path) -> list[str]:
    """Agent instructions under each agent's file name, where the project has none of its own."""
    made = []
    for n in AGENT_FILES:
        p = project / n
        if not p.exists():
            p.write_text(AGENT_TEXT, encoding="utf-8")
            made.append(n)
    return made


def remove_agent_files(project: Path, names: list[str]):
    for n in names:
        p = project / n
        try:
            if p.read_text(encoding="utf-8") == AGENT_TEXT:
                p.unlink()
        except OSError:
            pass
