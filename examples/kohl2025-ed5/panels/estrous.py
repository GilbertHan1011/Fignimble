"""Panels y-ak: MPOA neurons of virgin females before food deprivation, by oestrous stage (P, O, M, D; oestrus is E in
the data). From the "Estrous cycle influence" cells of NPS_ephys/ephys_analysis.ipynb: z from cell 67, ac cell 77,
ad cell 76, ae-aj cells 70-75 (its quick_plot), ak cell 57. y, aa and ab have no cells of their own (the notebook's
cell 68 drew a property only when its ANOVA was significant); they are drawn as the others are.

Fixed on the way: cell 76 plots a table `corr` that the notebook never makes (it stops with a NameError); here it is
the % of neurons with sag per stage joined to the stage's switching rate (data/estrous_data.csv), which is what
panel ad shows. Cells 70-75 read `state_df` and `non_silent` left over from earlier cells; here they are made
explicitly. The figure gives the inter-spike interval in seconds; the data have milliseconds."""

import matplotlib
import numpy as np
import pandas as pd
import seaborn as sns
import statsmodels.formula.api as smf

from panels.common import (DATA, ESTROUS, ESTROUS_GRAYS, ESTROUS_LABELS, LW, POINT, bars, end_labels, ephys,
                           interaction_pvalues, ramp_lines, ramps, significance_bars, silent_percent, stars)

# cell 76's bars of % with sag go from black to light gray (seaborn's "gray" palette), as in the figure
SAG_GRAYS = sns.color_palette("gray", 4)


def cells(non_silent=False, later=False) -> pd.DataFrame:
    """Pre cells by stage (cell 67): no 2025 recordings, classified at rest, P to E counted as P and D to P as D.
    `later`: from the later table, 2025 included."""
    df = ephys(after_bj=later)
    if not later:
        df = df[~df.experiment_day.str.contains("2025")]
    df = df[df.I_zero_reclassified.isin(["silent", "phasic", "tonic"])]
    df = df.assign(estrous_stage=df.estrous_stage.replace({"P to E": "P", "D to P": "D"}))
    df = df[(df.Behaviour_6hFD == "Pre") & df.estrous_stage.isin(ESTROUS)]
    if non_silent:                       # spike shape needs spikes
        df = df[df.I_zero_reclassified != "silent"]
    return df


PROPS = {  # column: (y label, cells with spikes only, y limits, ticks)
    "Vm": ("Vm (mV)", False, (-75, 0), [0, -30, -60]),
    "Input_Resistance": ("RI (MΩ)", False, (0, 1600), [0, 500, 1000, 1500]),
    "rheobase_at_-60mV_(pA)": ("Rheobase (pA)", False, (0, 150), [0, 50, 100, 150]),
    "CaT": ("CaT (mV)", False, (0, 45), [0, 15, 30, 45]),
    "AP_halfwidth": ("AP halfwidth\n(ms)", True, (0, 12), [4, 8, 12]),
    "AP_ampl": ("AP amplitude\n(mV)", True, (0, 150), [0, 50, 100, 150]),
    "isi_s": ("ISI (s)", True, (0, 45), [0, 15, 30, 45]),
    "AHP_(mV)": ("AHP (mV)", True, (-65, 0), [0, -25, -50]),
}


def box(fig, column="Vm"):
    """y, aa, ae-aj: one property by stage (quick_plot, with the stage greys of cell 68)."""
    label, spiking, ylim, ticks = PROPS[column]
    df = cells(non_silent=spiking)
    if column == "isi_s":
        df = df.assign(isi_s=df["isi_(ms)"] / 1000)
    ax = fig.add_subplot()
    sns.boxplot(x="estrous_stage", y=column, data=df, order=ESTROUS, hue="estrous_stage", hue_order=ESTROUS,
                palette=ESTROUS_GRAYS, legend=False, saturation=1, linewidth=LW, showfliers=False, width=0.7,
                boxprops=dict(alpha=0.7), ax=ax)
    np.random.seed(1)                    # the jitter, the same at every render
    sns.stripplot(x="estrous_stage", y=column, data=df, order=ESTROUS, color="gray", jitter=True, size=POINT,
                  linewidth=0.3, edgecolor="dimgray", alpha=0.5, ax=ax)
    ax.set_xticks(range(4))
    ax.set_xticklabels(ESTROUS_LABELS)
    ax.set_xlabel("")
    ax.set_ylabel(label)
    ax.set_ylim(*ylim)
    ax.set_yticks(ticks)
    sns.despine(ax=ax)


def silent(fig):
    """z: % silent at rest by stage (cell 67, Pre). The published bars are those of the later table with the 2025
    recordings (25.6, 45.5, 32.5, 31.9%), not of cell 67's (24.2, 37.5, 30.0, 27.3%, the caption's n), so it is
    drawn from that."""
    ax = fig.add_subplot()
    bars(ax, ESTROUS, silent_percent(cells(later=True), "estrous_stage", ESTROUS), ["gray"] * 4, ESTROUS_LABELS,
         ylim=(0, 48), rotation=0, ylabel="% Silent\nneurons", width=0.7)
    ax.set_yticks([0, 20, 40])


def cumulative(fig):
    """ab: baseline firing by stage, as cumulative fractions."""
    ax = fig.add_subplot()
    sns.ecdfplot(data=cells(), x="Firing_freq_(Hz)_I0", hue="estrous_stage", hue_order=ESTROUS,
                 palette=["#555555", "#777777", "#999999", "#CCCCCC"], linewidth=1.0, legend=False,
                 stat="proportion", ax=ax)
    ax.set_xlabel("Baseline\nfreq. (Hz)")
    ax.set_ylabel("Fraction")
    ax.set_xlim(0, 9)
    ax.set_xticks([0, 4, 8])
    ax.set_yticks([0, 0.5, 1])
    ax.set_yticklabels(["0.0", "0.5", "1.0"])
    sns.despine(ax=ax, trim=True)
    for k, (t, c) in enumerate(zip(ESTROUS_LABELS, ["#555555", "#777777", "#999999", "#CCCCCC"])):
        ax.text(0.42 + k * 0.13, 0.48, t, color=c, transform=ax.transAxes, va="center", fontsize=8)


def sag_percent() -> pd.DataFrame:
    """% of Pre cells with a voltage sag, by stage (cell 76)."""
    df = cells().dropna(subset=["Ih_at_-120mV"])          # cells with a sag measured (the caption's n)
    return pd.DataFrame({"estrous_stage": ESTROUS,
                         "yes": [100 * (df.loc[df.estrous_stage == s, "Ih_at_-120mV"] > 0).mean() for s in ESTROUS]})


def sag(fig):
    """ac: % of neurons with a sag by stage (cell 77)."""
    ax = fig.add_subplot()
    bars(ax, ESTROUS, sag_percent()["yes"], SAG_GRAYS, ESTROUS_LABELS, ylim=(0, 100), rotation=0, alpha=1.0,
         ylabel="Neurons with\nsag (%)", width=0.8)
    ax.set_yticks([0, 50, 100])


def sag_vs_switching(fig):
    """ad: % of neurons with sag against the stage's rate of switching to aggression (linear regression). The
    notebook's cell 76 stops here: `corr` is this table."""
    rate = pd.read_csv(DATA / "estrous_data.csv")
    rate = rate.rename(columns={"Unnamed: 0": "estrous_stage", "0": "switching"})
    corr = sag_percent().merge(rate, on="estrous_stage")
    fit = smf.ols("switching ~ yes", data=corr).fit()
    ax = fig.add_subplot()
    sns.regplot(x="yes", y="switching", data=corr, ci=None, color="#4C72B0", scatter_kws={"s": 6},
                line_kws={"lw": 1.0}, ax=ax, truncate=False)
    ax.set_xlim(48, 102)
    ax.set_ylim(0, 100)
    ax.set_xticks([50, 100])
    ax.set_yticks([0, 50, 100])
    ax.set_xlabel("Neurons with\nsag (%)")
    ax.set_ylabel("% Agg$^{+}$")
    sns.despine(ax=ax)
    ax.text(0.45, 0.82, stars(fit.f_pvalue), transform=ax.transAxes, ha="center")


def excitability(fig):
    """ak: spikes per injected current by stage (cells 56-57; they read the later table, cell 52's)."""
    steps = ramps(["Pre"], upper=True)
    df = ephys(after_bj=True).rename(columns={"experiment_day": "filename"})
    df["filename"] = df["filename"].str.upper()
    steps = steps[steps.state == "Pre"].merge(
        df[df.Behaviour_6hFD == "Pre"][["filename", "estrous_stage", "ID_mouse", "Ih_at_-120mV"]], on="filename",
        how="left")
    steps.loc[steps.estrous_stage == "P<E", "estrous_stage"] = "E"
    steps.loc[steps.filename == "S2C1 24072023", "estrous_stage"] = "E"
    plot = steps[steps.estrous_stage.isin(ESTROUS)].dropna(subset=["estrous_stage", "Ih_at_-120mV", "Injected",
                                                                     "num_spike"])
    combos = [("P", "D"), ("P", "E"), ("P", "M"), ("E", "M"), ("E", "D"), ("M", "D")]
    result = interaction_pvalues(plot, "num_spike", combos, state_col="estrous_stage")
    greys = matplotlib.colormaps["Greys"]
    grays = dict(zip(ESTROUS, [greys(v) for v in (0.8, 0.6, 0.4, 0.2)]))
    ax = fig.add_subplot()
    ramp_lines(ax, plot, "estrous_stage", ESTROUS, grays, errorbar=("ci", 58), lw=1.0)
    ax.set_ylim(-0.5, 23)
    ax.set_yticks([0, 10, 20])
    significance_bars(ax, result, combos, grays, base_y=1.2, y_shift=0.6)
    end_labels(ax, [("D", grays["D"], 0.80), ("M", grays["M"], 0.62), ("P", grays["P"], 0.52),
                    ("O", grays["E"], 0.38)])
