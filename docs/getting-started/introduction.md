# Introduction

Most scientific figures are assembled the same way: each panel is plotted in Python or R and saved as a PDF, and the
panels are then arranged, lettered, aligned and annotated by hand in Illustrator. The second half is slow, it has to
be redone whenever a panel changes, and nothing records how the figure was put together.

Fignimble replaces that second half. A figure is a short Python file:

```python
from fignimble import *
from style import STYLE                       # shared by every figure of the paper

fig = Figure(width=183, height=118, style=STYLE)        # millimetres; 183 mm = Nature double column

fig.panel("panels/expression.py", x=4, y=3, w=56, h=52)            # lettered a
fig.panel("panels/scatter.py", x=65, y=3, w=56, h=52)              # lettered b
fig.image("images/cells.png", x=4, y=63, w=52)                     # pictures are panels too
fig.text("Treated", x=30, y=104, size=7, weight="bold", align="center")
fig.arrow(57, 82, 64, 82, width=0.6)
fig.bracket(147, 169, 67, text="**")                               # a significance bracket
```

and each panel is a matplotlib function that draws into a figure of exactly the panel's size:

```python
def draw(fig, genes=("GAPDH", "CD3E")):
    ax = fig.add_subplot()
    ...
```

Fignimble shows the figure and lets you edit it as you would in a drawing app. Dragging a panel changes its `x` and
`y` in the figure file; resizing it re-runs its code at the new size; retyping an axis label changes the string in
the panel's code. You can also edit the code yourself, in Fignimble's code pane or any editor, or ask a coding agent
to. All three change the same files, and Fignimble redraws within a second whenever they change.

## What you get

- **Automatic panel letters**, in reading order, re-lettered when panels move, styled once for every figure.
- **Panels that redraw at their size**, so their text and lines are the size the journal sees.
- **One style for every panel**: font, text size, line widths and colours, set in `style.py`.
- **Journal presets** for 40 journals: column widths, fonts, label convention and the resolutions they require.
- **Plot areas that line up** across a row or column, whatever the tick labels, as
  [patchwork](https://patchwork.data-imaginist.com) does for ggplot.
- **Preflight**: small text, low-resolution pictures, colours colour-blind readers confuse, elements off the page.
- **Export** to vector PDF, EPS and SVG with real text, and to TIFF, PNG and JPEG at the journal's resolution.
- **A dark version** of every figure for talks, from the same code.
- **An AI agent in the terminal** that knows how the project works and can look at its own renders.

## Requirements

Fignimble runs on macOS 13 or later, on Apple Silicon and Intel Macs. It draws with Python 3, which it can install
for you the first time it opens. See [installation](installation.md).
