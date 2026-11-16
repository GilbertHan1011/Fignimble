"""Figure 3: a micrograph with a scale bar and a magnified region, annotations with rich text and curved arrows."""
from fignimble import *
from style import STYLE

fig = Figure(width=183, height=95, style=STYLE)

cells = fig.image("images/cells.png", x=4, y=3, w=80)
detail = fig.inset(Image("images/cells.png"), within=cells, x=1.08, y=0.0, w=0.55, h=0.55, label="b")
fig.zoom(cells, detail, region=(0.55, 0.1, 0.25, 0.25), color="#F2C14E", width=0.7)
fig.scalebar(cells, length=50, unit="µm", pixel_size=0.325)
fig.panel("panels/scatter.py", x=142, y=3, w=40, h=46, texts={"ax0.xlabel": "tSNE 1", "ax0.ylabel": "tSNE 2"})
fig.text("**GFP**^{+} cells express *Cd3e* at 10^{3}-fold the level of CD8_{a}^{−} cells, measured over three independent replicates.",
         x=4, y=70, size=7, width=78)
fig.arrow(96, 80, 120, 66, width=0.8, curve=0.25, tip="stealth", color="#d1495b")
fig.path([(130, 60), (140, 72), (152, 62), (165, 78)], smooth=True, width=1, arrow="end", tip="open", stroke="#00798c")
fig.image("images/schematic.svg", x=128, y=58, w=26, rotation=90)
fig.image("images/cells.png", x=160, y=60, w=21, flip="h", rotation=15)
fig.rect(100, 40, 20, 10, hidden=True)
