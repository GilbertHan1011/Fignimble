"""Panels a-i: MPOA neurons before and after food deprivation, with HCN block, NPY, Npy knockdown (a-d) and the NPY
receptor antagonists (e-i). From NPS_ephys/ephys_analysis.ipynb: a from cell 39, b cell 8, c cell 10, d cell 64,
e cell 40, g cell 13, i cell 63. The notebook has no cells for f and h; they are drawn the way g is, from the same
table. Brackets: the comparisons the published figure marks, with p values computed by the tests the caption names."""

from panels.common import (ANT_GROUPS, ANT_LABELS, RED, SIX, SIX_GROUPS, SIX_LABELS, boxstrip, bars, bracket,
                           end_labels, ephys, family_p, interaction_pvalues, ramp_lines, ramps, significance_bars,
                           silent_percent, stars)

RAMP_STATES = ["Pre", "Agg+", "Agg-", "NPY 10nM", "NPY 100nM", "NPY Antag", "NPY1R", "NPY2R", "NPY-KD", "ZD7288",
               "Ramp_Agrp_KD"]


def silent(fig):
    """a: % silent at rest, Pre to KD-Y (Fisher's exact test, Benjamini-Hochberg)."""
    df = ephys()
    df = df[df.ID_mouse != "JKAJ37.6g"]                 # left out in the notebook's silent-proportion cells
    ax = fig.add_subplot()
    bars(ax, SIX_GROUPS, silent_percent(df, "Behaviour_6hFD", SIX_GROUPS), SIX, SIX_LABELS, ylim=(0, 100), nbins=2,
         ylabel="Silent neurons (%)")
    p = family_p(df.dropna(subset=["I_zero_reclassified"]), "I_zero_reclassified", "Behaviour_6hFD", "fisher")
    bracket(ax, 0, 3, 108, stars(p[("Pre", "ZD7288")]))
    bracket(ax, 0, 4, 122, stars(p[("Pre", "npy_100")]))
    for k, (t, c) in enumerate([("Pre", "gray"), ("Agg$^{+}$", RED), ("Agg$^{-}$", "tab:blue")]):
        ax.text(1.0, 1.12 - k * 0.13, t, color=c, transform=ax.transAxes, ha="right", va="top")


def vm(fig):
    """b: resting membrane potential (Mann-Whitney U, Benjamini-Hochberg)."""
    df = ephys()
    ax = fig.add_subplot()
    boxstrip(ax, df, "Behaviour_6hFD", "Vm", SIX_GROUPS, SIX, SIX_LABELS, ylim=(-80, 0), ylabel="Vm (mV)")
    p = family_p(df, "Vm", "Behaviour_6hFD")
    bracket(ax, 1, 5, -12, stars(p[("Agg+", "npykd")]))


def ri(fig):
    """c: input resistance (Mann-Whitney U, Benjamini-Hochberg)."""
    df = ephys()
    ax = fig.add_subplot()
    boxstrip(ax, df, "Behaviour_6hFD", "Input_Resistance", SIX_GROUPS, SIX, SIX_LABELS, ylim=(0, 1600), nbins=2,
             ylabel="RI (MΩ)")
    p = family_p(df, "Input_Resistance", "Behaviour_6hFD")
    bracket(ax, 0, 1, 1180, stars(p[("Pre", "Agg+")]))
    bracket(ax, 0, 3, 1380, stars(p[("Pre", "ZD7288")]))


def excitability(fig):
    """d: spikes per injected current, Pre, Agg+, ZD and KD-Y (mixed model; bars where ZD differs)."""
    df = ramps(RAMP_STATES)
    combos = [("ZD7288", "Pre"), ("ZD7288", "NPY-KD"), ("ZD7288", "Agg+")]
    result = interaction_pvalues(df, "num_spike", combos)
    plot = df[df.state.isin(["ZD7288", "Pre", "Agg+", "NPY-KD"])]
    plot = plot[~plot.filename.str.contains("062025")]
    colors = {"Pre": "gray", "Agg+": RED, "ZD7288": "#3D1c02", "NPY-KD": "#8F3B5A"}
    ax = fig.add_subplot()
    ramp_lines(ax, plot, "state", ["Pre", "Agg+", "ZD7288", "NPY-KD"], colors)
    ax.set_ylim(-0.1, 18)
    ax.set_yticks([0, 4, 8, 12, 16])
    significance_bars(ax, result, combos, colors, base_y=0.8)
    end_labels(ax, [("Pre", "gray", 0.92), ("KD-Y", "#8F3B5A", 0.80), ("Agg$^{+}$", RED, 0.50), ("ZD", "#3D1c02", 0.32)])


def silent_antagonists(fig):
    """e: % silent at rest with the NPY receptor antagonists."""
    df = ephys()
    df = df[df.ID_mouse != "JKAJ37.6g"]
    ax = fig.add_subplot()
    bars(ax, ANT_GROUPS, silent_percent(df, "Behaviour_6hFD", ANT_GROUPS), [RED] * 4, ANT_LABELS, ylim=(0, 100),
         nbins=2, ylabel="Silent neurons (%)")


def antagonists(fig, column="Ih_at_-120mV"):
    """f, g, h: Vm, sag and input resistance with the antagonists (g is cell 13; f and h the same for their columns)."""
    ylim, nbins, label = {"Vm": ((-80, 0), 3, "Vm (mV)"), "Ih_at_-120mV": ((-2, 30), 3, "Sag (mV)"),
                          "Input_Resistance": ((0, 1600), 2, "RI (MΩ)")}[column]
    ax = fig.add_subplot()
    boxstrip(ax, ephys(), "Behaviour_6hFD", column, ANT_GROUPS, [RED] * 4, ANT_LABELS, ylim=ylim, nbins=nbins,
             ylabel=label)
    if column == "Ih_at_-120mV":
        ax.set_yticks([0, 15, 30])


def excitability_antagonists(fig):
    """i: spikes per injected current with the antagonists (cell 63)."""
    df = ramps(RAMP_STATES)
    combos = [("Agg+", "NPY Antag"), ("Agg+", "NPY1R"), ("Agg+", "NPY2R")]
    result = interaction_pvalues(df, "num_spike", combos)
    plot = df[df.state.isin(["Agg+", "NPY Antag", "NPY1R", "NPY2R"])]
    colors = {"Agg+": RED, "NPY Antag": "orchid", "NPY1R": "pink", "NPY2R": "salmon"}
    ax = fig.add_subplot()
    ramp_lines(ax, plot, "state", ["Agg+", "NPY Antag", "NPY1R", "NPY2R"], colors)
    ax.set_ylim(-0.1, 22)
    ax.set_yticks([0, 5, 10, 15, 20])
    significance_bars(ax, result, combos, colors, base_y=1.0)
    end_labels(ax, [("Ant-Y", "orchid", 0.95), ("Ant-Y2", "salmon", 0.83), ("Ant-Y1", "pink", 0.71),
                    ("Agg$^{+}$", RED, 0.40)])
