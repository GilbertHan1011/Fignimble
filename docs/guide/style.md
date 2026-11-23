# Labels, style and journals

## One style for every panel

Every figure of a project imports the `Style` in `style.py`:

```python
from fignimble import *

STYLE = Style.journal("nature", labels=Labels.journal("nature"), palette="okabe-ito")
```

A `Style` sets the font, the text size, line widths, whether axes have top and right spines, and the colours panels
plot with, for every panel. Plots made at different times, by different people, match. Change `style.py` (or the
**Style** section of the inspector with nothing selected) and every figure follows.

```python
STYLE = Style(font="Arial", size=7, linewidth=0.6, despine=True, min_font=5, min_dpi=300,
              labels=Labels(format="{}", case="lower", size=8, weight="bold"), palette="okabe-ito")
```

`rc={...}` passes any other matplotlib settings to every panel.

## Panel letters

Panels and pictures are lettered in reading order and re-lettered when they move. `Labels` sets their look for
every figure:

| Setting | Values |
|---|---|
| `format` | `"{}"`, `"({})"`, `"{}."`, … |
| `case` | `"lower"` or `"upper"` |
| `numbering` | `"alpha"` (a … z, aa, ab …), `"roman"`, `"arabic"`, or `"none"` |
| `size`, `weight`, `font` | the letters' type |
| `dx`, `dy` | the offset from each panel's corner, in mm |

Letters in a row or a column line up. Dragging a letter moves all of them, since they share one offset;
<kbd>⌥</kbd>-drag nudges one. A panel can have a letter of its own (`label="a'"`) or none (`label=None`), and
`label_dx`, `label_dy` nudge its letter alone. **Labels ▸ No Letters** turns letters off for a journal that adds its
own.

## Journal presets

`Style.journal("cell")` and `Labels.journal("cell")` set what the journal asks for: font and sizes, the panel label
convention, the minimum text size and resolutions. The inspector's **Width for a journal…** menu sets the figure to
one of its column widths. Fignimble has 40 presets, computational biology's especially: the Nature Portfolio, Cell
Press, PLOS, Oxford, BMC, Genome Research, Molecular Systems Biology, eLife, Frontiers, IEEE/ACM TCBB, Science and
PNAS. See [journal presets](../reference/journals.md), and check the journal's current guidelines before
submitting.

## Units and sizes

Figure and element sizes are in millimetres; text sizes in points. Nature's double column is 183 mm; a single column
89 mm.
