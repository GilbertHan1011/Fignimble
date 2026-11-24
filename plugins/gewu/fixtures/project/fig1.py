from fignimble import *
from style import STYLE

fig = Figure(width=120, height=60, style=STYLE)
fig.panel("panels/scatter.py", x=4, y=4, w=50, h=44)
fig.panel("panels/bars.py", x=60, y=4, w=50, h=44, function="bars")
fig.image("images/test.svg", x=4, y=50, w=24)
fig.text("Fixture", x=34, y=52, size=7)
