"""Panels k-p and r-w: Pre against Post, where Post is 60% Agg+ and 40% Agg- cells and Pre is sampled to match
Post's spread of oestrous stages (k-p), and Pre against Post in dioestrus only (r-w). From
NPS_ephys/resampled_ephys.ipynb: the sampling is its cells 2 and 3, k-m and r-t the box plots its preprocess_plot
draws, n/u cells 5 and 7, o/v cells 4 and 6, p/w cells 12 and 13. Stars: Mann-Whitney U, two-sided, as the
caption says."""

import pandas as pd
import seaborn as sns
from scipy import stats

from panels.common import ORANGE, PRE_POST, boxstrip, bars, bracket, ephys, ramp_lines, ramps, silent_percent, stars

RAMP_STATES = ["Pre", "Agg+", "Agg-", "NPY 10nM", "NPY 100nM", "NPY Antag", "NPY1R", "NPY2R", "NPY-KD", "ZD7288"]
COLUMNS = {"sag": ("Ih_at_-120mV", "Sag (mV)", (0, 24), [0, 8, 16, 24]),
           "ri": ("Input_Resistance", "RI (MΩ)", None, None),
           "firing": ("Firing_freq_(Hz)_I0", "Firing freq (Hz)", None, [0, 5, 10, 15])}


def sampled(group="weighted") -> pd.DataFrame:
    """The cells compared: "weighted" (cell 2) or "diestrus" (cell 3), with pre_post_state Pre or Post."""
    ephys_ = ephys(after_bj=True)
    ephys_["pre_post_state"] = ephys_["Behaviour_6hFD"].apply(lambda x: "Pre" if x == "Pre" else "Post")
    filtered = ephys_[ephys_.Behaviour_6hFD.isin(["Pre", "Agg+", "Agg-"])]
    if group == "diestrus":
        agg = ephys_[(ephys_.Behaviour_6hFD == "Agg+") & ephys_.estrous_stage.isin(["D", "D to P"])]
        pre = filtered[(filtered.Behaviour_6hFD == "Pre") & filtered.estrous_stage.isin(["D", "D to P"])]
        return pd.concat([pre, agg], ignore_index=True)
    agg = ephys_[ephys_.Behaviour_6hFD == "Agg+"]
    no_agg = ephys_[ephys_.Behaviour_6hFD == "Agg-"].sample(n=int(agg.shape[0] * 0.25), random_state=40)
    stages = pd.concat([agg, no_agg]).estrous_stage.replace({"P to E": "P", "D to P": "D"})
    pre = filtered[filtered.Behaviour_6hFD == "Pre"]
    counts = (stages.value_counts(normalize=True) * pre.shape[0]).astype(int) // 1.5
    # each stage's Pre cells sampled to Post's proportions; stages Post doesn't have give 20 cells (or all of
    # theirs), as in the notebook (pandas 3 no longer hands groupby.apply the stage column, so this loops)
    parts = [x.sample(n=min(int(counts.get(stage, 20)), len(x)), random_state=42)
             for stage, x in pre.groupby("estrous_stage")]
    return pd.concat([*parts, agg, no_agg])


def box(fig, column="sag", group="weighted", pair=False):
    """k-m, r-t: a property, Pre against Post (pair: the bracket the figure shows)."""
    col, label, ylim, ticks = COLUMNS[column]
    df = sampled(group)
    ax = fig.add_subplot()
    boxstrip(ax, df, "pre_post_state", col, ["Pre", "Post"], PRE_POST, ylim=ylim, nbins=3, ylabel=label)
    if ticks:
        ax.set_yticks(ticks)
    if pair:
        p = stats.mannwhitneyu(df.loc[df.pre_post_state == "Pre", col].dropna(),
                               df.loc[df.pre_post_state == "Post", col].dropna(), alternative="two-sided")[1]
        top = ax.get_ylim()[1]
        bracket(ax, 0, 1, top * 1.02, stars(p))


def cumulative(fig, group="weighted", star=False):
    """n, u: baseline firing as cumulative fractions (the star is the U test of m)."""
    df = sampled(group)
    ax = fig.add_subplot()
    sns.ecdfplot(data=df, x="Firing_freq_(Hz)_I0", hue="pre_post_state", hue_order=["Pre", "Post"],
                 palette=["dimgray", ORANGE], linewidth=1.0, legend=False, stat="proportion", ax=ax)
    ax.set_xlabel("Baseline\nfreq. (Hz)")
    ax.set_ylabel("Fraction")
    ax.set_xlim(0, 9)
    ax.set_xticks([0, 4, 8])
    ax.set_yticks([0, 0.5, 1])
    ax.set_yticklabels(["0.0", "0.5", "1.0"])
    sns.despine(ax=ax, trim=True)
    if star:
        col = "Firing_freq_(Hz)_I0"
        p = stats.mannwhitneyu(df.loc[df.pre_post_state == "Pre", col].dropna(),
                               df.loc[df.pre_post_state == "Post", col].dropna(), alternative="two-sided")[1]
        ax.text(0.5, 0.97, stars(p), transform=ax.transAxes, ha="center", va="center")


def silent(fig, group="weighted"):
    """o, v: % silent at rest."""
    df = sampled(group)
    ax = fig.add_subplot()
    bars(ax, ["Pre", "Post"], silent_percent(df, "pre_post_state", ["Pre", "Post"]), PRE_POST, ylim=(0, 60),
         ylabel="Silent\nNeurons (%)")
    ax.set_yticks([0, 20, 40, 60])


def excitability(fig, group="weighted"):
    """p, w: spikes per injected current (cells 12 and 13)."""
    df = sampled(group).rename(columns={"experiment_day": "filename"})
    df["filename"] = df["filename"].str.upper()
    steps = ramps(RAMP_STATES)
    steps["filename"] = steps["filename"].str.replace(".xlsx", "").str.upper()
    combined = steps.merge(df, on="filename", how="inner")
    ax = fig.add_subplot()
    ramp_lines(ax, combined, "pre_post_state", ["Pre", "Post"], ["gray", ORANGE], errorbar=("ci", 58), lw=1.0,
               alpha=0.8)
    if group == "diestrus":
        ax.set_ylabel("Evoked spikes")
        ax.set_yticks([5, 10, 15, 20])
    else:
        ax.set_ylabel("Evoked Spikes")
        ax.set_yticks([4, 8, 12, 16])
    ax.text(1.0, 1.06, "Pre", color="darkgray", transform=ax.transAxes, ha="right", va="bottom")
    ax.text(1.0, 0.36, "Post", color=ORANGE, transform=ax.transAxes, ha="right", va="top")
