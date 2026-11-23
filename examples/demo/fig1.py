from fignimble import *
from style import STYLE

fig = Figure(width=183, height=118, style=STYLE)

fig.panel("panels/expression.py", x=4, y=3, w=56, h=52)
fig.panel("panels/scatter.py", x=65, y=3, w=56, h=52, label="b")
fig.panel("panels/heatmap.py", x=126, y=3, w=56, h=52)
fig.image("images/cells.png", x=4, y=63, w=52)
fig.image("images/schematic.svg", x=65, y=63, w=56, h=None)
fig.panel("panels/expression.py", x=129, y=63, w=53, h=50, function="bars")
fig.text("Treated", x=30, y=104, size=7, weight="bold", align="center")
fig.arrow(57, 82, 64, 82, width=0.6)
fig.bracket(147, 169, 67, text="**")
fig.panel("panels/panel.py", x=11.8, y=116.4, w=60, h=45)
