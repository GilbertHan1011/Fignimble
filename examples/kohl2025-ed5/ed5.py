"""Extended Data Fig. 5 of Cao, M. et al. "Integration of hunger and hormonal state gates infant-directed aggression",
Nature 648, 138-145 (2025), doi:10.1038/s41586-025-09651-2, rebuilt from the authors' code and data
(github.com/FrancisCrickInstitute/negative_parental_switch, NPS_ephys); CC BY 4.0, adapted (see README.md).
Panels a-i: panels/pharmacology.py; k-p and r-w: panels/resampled.py; y-ak: panels/estrous.py. The schematics
j, q and x are drawn here (their grey boxes carry the letters), with BioCartoon icons: "C57 MOUSE" by Long Li
(SciDraw SD016325) and "Rat pup P1" by Antonis Asiminas (SciDraw SD016414), CC BY 4.0."""
from fignimble import *
from style import STYLE

fig = Figure(width=183, height=228, style=STYLE)

PH, RS, ES = "panels/pharmacology.py", "panels/resampled.py", "panels/estrous.py"
MOUSE = dict(crop=(0.007, 0.128, 0.003, 0.241), flip="h")      # without its page margins, facing left
GRAY, YELLOW = "#EBEBEB", "#FAF0CC"
PRE, POST, AGG_P, AGG_N = "#8C8C8C", "#E8892B", "#D62728", "#1F77B4"

# a-d
fig.panel(PH, x=2, y=1, w=44, h=33, function="silent")
fig.panel(PH, x=47, y=1, w=42, h=33, function="vm")
fig.panel(PH, x=90, y=1, w=44, h=33, function="ri")
fig.panel(PH, x=135, y=1, w=46, h=33, function="excitability")

# e-i
fig.panel(PH, x=2, y=37, w=36, h=32, function="silent_antagonists")
fig.panel(PH, x=39, y=37, w=34, h=32, function="antagonists", args={"column": "Vm"})
fig.panel(PH, x=74, y=37, w=34, h=32, function="antagonists")
fig.panel(PH, x=109, y=37, w=34, h=32, function="antagonists", args={"column": "Input_Resistance"})
fig.panel(PH, x=144, y=37, w=37, h=32, function="excitability_antagonists")

# j: Pre against Post, Post 60% Agg+ and 40% Agg-
fig.rect(3, 75, 11.5, 26, stroke=None, fill=GRAY, label="auto")
fig.rect(15, 75, 11.5, 26, stroke=None, fill=YELLOW)
fig.text("Pre", x=8.75, y=76, color=PRE, align="center")
fig.text("Post", x=20.75, y=76, color=POST, align="center")
fig.image("images/mouse.svg", x=4, y=84, w=9.5, label=None, **MOUSE)
fig.image("images/pup.svg", x=3.6, y=88, w=3.4, label=None)
fig.image("images/mouse.svg", x=16, y=80.5, w=9.5, label=None, **MOUSE)
fig.text("vs", x=20.75, y=86.3, align="center")
fig.image("images/mouse.svg", x=16, y=92, w=9.5, label=None, **MOUSE)
fig.image("images/pup.svg", x=15.6, y=96, w=3.4, label=None)
fig.text("Agg^{+}\n(60%)", x=31, y=79, color=AGG_P, align="center")
fig.text("Agg^{–}\n(40%)", x=31, y=92, color=AGG_N, align="center")
fig.arrow(28, 77.5, 26.8, 77.5, color=AGG_P, width=0.4, head=1.0)
fig.line(31, 85, 31, 91, color=AGG_N, width=0.4)

# k-p
fig.panel(RS, x=36, y=73, w=24, h=29, function="box", args={"column": "sag", "pair": True})
fig.panel(RS, x=60, y=73, w=24, h=29, function="box", args={"column": "ri"})
fig.panel(RS, x=84, y=73, w=24, h=29, function="box", args={"column": "firing", "pair": True})
fig.panel(RS, x=108, y=73, w=25, h=29, function="cumulative", args={"star": True})
fig.panel(RS, x=133, y=73, w=20, h=29, function="silent")
fig.panel(RS, x=153, y=73, w=29, h=29, function="excitability")

# q: the same in dioestrus only
fig.text("Dioestrus only", x=14.75, y=104.5, align="center")
fig.line(3, 106.3, 5.6, 106.3, width=0.4)
fig.line(23.9, 106.3, 26.5, 106.3, width=0.4)
fig.rect(3, 108, 11.5, 26, stroke=None, fill=GRAY, label="auto")
fig.rect(15, 108, 11.5, 26, stroke=None, fill=YELLOW)
fig.text("Pre", x=8.75, y=109, color=PRE, align="center")
fig.text("Post", x=20.75, y=109, color=POST, align="center")
fig.image("images/mouse.svg", x=4, y=117, w=9.5, label=None, **MOUSE)
fig.image("images/pup.svg", x=3.6, y=121, w=3.4, label=None)
fig.image("images/mouse.svg", x=16, y=113.5, w=9.5, label=None, **MOUSE)
fig.text("vs", x=20.75, y=119.3, align="center")
fig.image("images/mouse.svg", x=16, y=125, w=9.5, label=None, **MOUSE)
fig.image("images/pup.svg", x=15.6, y=129, w=3.4, label=None)

# r-w
fig.panel(RS, x=36, y=106, w=24, h=29, function="box", args={"column": "sag", "group": "diestrus", "pair": True})
fig.panel(RS, x=60, y=106, w=24, h=29, function="box", args={"column": "ri", "group": "diestrus", "pair": True})
fig.panel(RS, x=84, y=106, w=24, h=29, function="box", args={"column": "firing", "group": "diestrus"})
fig.panel(RS, x=108, y=106, w=25, h=29, function="cumulative", args={"group": "diestrus"})
fig.panel(RS, x=133, y=106, w=20, h=29, function="silent", args={"group": "diestrus"})
fig.panel(RS, x=153, y=106, w=29, h=29, function="excitability", args={"group": "diestrus"})

# x: recordings at each oestrous stage, before food deprivation
fig.rect(6, 140, 15, 27, stroke=None, fill=GRAY, label="auto", label_dx=-4)
fig.text("Pre", x=13.5, y=141, color=PRE, align="center")
fig.image("images/mouse.svg", x=8.5, y=145.5, w=10, label=None, **MOUSE)
fig.text("P  O  M  D", x=13.5, y=152.5, align="center")
fig.line(8, 156, 19, 156, width=0.4)
for tx in (8, 11.7, 15.3, 19):
    fig.line(tx, 155, tx, 156, width=0.4)
fig.text("whole-cell\nrecordings\n(MPOA)", x=13.5, y=157.5, size=5, align="center", color="#555555")

# y-ac
fig.panel(ES, x=24, y=138, w=29, h=31, function="box", args={"column": "Vm"})
fig.panel(ES, x=54, y=138, w=29, h=31, function="silent")
fig.panel(ES, x=84, y=138, w=31, h=31, function="box", args={"column": "Input_Resistance"})
fig.panel(ES, x=116, y=138, w=32, h=31, function="cumulative")
fig.panel(ES, x=149, y=138, w=32, h=31, function="sag")

# ad-ai
fig.panel(ES, x=2, y=171, w=28, h=29, function="sag_vs_switching")
fig.panel(ES, x=31, y=171, w=30, h=29, function="box", args={"column": "rheobase_at_-60mV_(pA)"})
fig.panel(ES, x=61, y=171, w=30, h=29, function="box", args={"column": "CaT"})
fig.panel(ES, x=91, y=171, w=30, h=29, function="box", args={"column": "AP_halfwidth"})
fig.panel(ES, x=121, y=171, w=30, h=29, function="box", args={"column": "AP_ampl"})
fig.panel(ES, x=151, y=171, w=30, h=29, function="box", args={"column": "isi_s"})

# aj, ak
fig.panel(ES, x=2, y=202, w=29, h=25, function="box", args={"column": "AHP_(mV)"})
fig.panel(ES, x=32, y=202, w=34, h=25, function="excitability")
