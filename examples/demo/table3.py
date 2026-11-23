from fignimble import *
from style import STYLE

fig = Figure(width=52.7, height=21.7, style=STYLE)
fig.table("tables/table3.csv", x=3, y=3, color="#0433FF")
