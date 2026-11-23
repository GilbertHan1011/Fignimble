from fignimble import *
from style import STYLE

fig = Figure(width=52.1, height=10.3, style=STYLE)
fig.table("tables/table1.csv", x=3, y=3)
