"""What the panels of Extended Data Fig. 5 share: the data, the colours, and the helpers the authors' notebooks repeat in
every cell (NPS_ephys/ephys_analysis.ipynb, resampled_ephys.ipynb and ephys_utils.py in
github.com/FrancisCrickInstitute/negative_parental_switch). The notebooks drew each panel on its own figure, sized in
inches and scaled down in Illustrator; here each panel draws at its size in the figure, so marker sizes and line widths
are the published ones rather than the notebooks'."""

import re
from itertools import combinations
from pathlib import Path

import matplotlib.colors as mcolors
import numpy as np
import pandas as pd
import seaborn as sns
import statsmodels.formula.api as smf
from matplotlib.patches import Rectangle
from matplotlib.ticker import MaxNLocator
from scipy import stats
from statsmodels.stats.multitest import multipletests

from fignimble import cached

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

RED, BLUE, ORANGE = "tab:red", "tab:blue", "tab:orange"
SIX = ["gray", RED, BLUE, "gray", "gray", RED]
SIX_GROUPS = ["Pre", "Agg+", "Agg-", "ZD7288", "npy_100", "npykd"]
SIX_LABELS = ["Pre", "Agg$^{+}$", "Agg$^{-}$", "ZD", "NPY", "KD-Y"]
ANT_GROUPS = ["Agg+", "npy_antag", "npy1r_antag", "npy2r_antag"]
ANT_LABELS = ["Agg$^{+}$", "Ant-Y", "Ant-Y1", "Ant-Y2"]
PRE_POST = ["gray", ORANGE]
ESTROUS = ["P", "E", "M", "D"]
ESTROUS_LABELS = ["P", "O", "M", "D"]          # the figure calls oestrus O, the data E
ESTROUS_GRAYS = ["#707070", "#939393", "#B7B7B7", "#DBDBDB"]

POINT = 2.2           # strip plot marker size (pt)
LW = 0.6              # box and bar outlines (pt)


# --- data ---

def ephys(after_bj=False) -> pd.DataFrame:
    """The per-cell table. `after_bj`: the later export with more Pre cells, which resampled_ephys.ipynb uses."""
    d = pd.read_csv(DATA / ("sampled_ephys_data_after_adding_BJ.csv" if after_bj else "sampled_ephys_data.csv"))
    # one cell is classed "slent" in the later export: a typo for silent
    d["I_zero_reclassified"] = d["I_zero_reclassified"].replace("slent", "silent")
    return d


def process_df_state(df_state: pd.DataFrame, states) -> pd.DataFrame:
    """Spikes per current step of each recording, from the ramp events (ephys_utils.process_df_state, unchanged
    but for working on a copy)."""
    df_state = df_state.rename(columns={"I_Injected(pA)": "Injected"})
    current_cat = np.arange(25, 175, 10)
    df_state["Injected"] = pd.Categorical(df_state["Injected"], current_cat).as_ordered()
    df_state = df_state.sort_values("Injected").dropna()
    df_state["state"] = pd.Categorical(df_state["state"], states).as_ordered()
    unique_combinations = df_state[["filename", "state"]].drop_duplicates()
    all_combinations = (unique_combinations.assign(dummy=1)
                        .merge(pd.DataFrame({"Injected": current_cat, "dummy": 1}), on="dummy").drop("dummy", axis=1))
    df_state_full = all_combinations.merge(df_state, on=["filename", "Injected", "state"], how="left")
    num_spike = (df_state.groupby(by=["filename", "Injected", "state"], observed=False)["Event start "].nunique()
                 .reset_index(name="num_spike"))
    num_spike = all_combinations.merge(num_spike, on=["filename", "Injected", "state"], how="left").fillna({"num_spike": 0})
    df_all = (df_state_full.groupby(["filename", "Injected", "state"], observed=False).first().reset_index()
              .drop_duplicates())
    latency = (df_state.groupby(["filename", "Injected", "state"], observed=False)["Event start "].min()
               .reset_index(name="latency_event_start"))
    df_all = pd.merge(df_all, num_spike, on=["filename", "Injected", "state"])
    df_all = pd.merge(df_all, latency, on=["filename", "Injected", "state"])
    df_all["latency"] = df_all["latency_event_start"] - df_all["Ramp_start"]
    df_all["Injected"] = df_all["Injected"].astype(int)
    return df_all


def ramps(states, upper=False) -> pd.DataFrame:
    """The ramp recordings as spikes per current step. `upper`: file names as the per-cell table has them. A copy,
    since panels change it."""
    return _ramps(tuple(states), upper).copy()


@cached("data/ramps_all.csv")
def _ramps(states, upper) -> pd.DataFrame:
    df = pd.read_csv(DATA / "ramps_all.csv")
    if upper:
        df["filename"] = df["filename"].str.replace(".xlsx", "").str.upper()
    return process_df_state(df, states)


# --- statistics ---

@cached()
def interaction_pvalues(df, prop, combos, state_col="state", group_var="filename") -> pd.DataFrame:
    """Mixed linear model per pair of groups, spikes ~ current x group with the recording as random effect; the
    interaction's p value at each current step, Benjamini-Hochberg corrected (ephys_utils.test_interaction_pvalues).
    Kept by Fignimble (@cached) until the data or this file changes: the models take a few seconds each."""
    rows = []
    for combo in combos:
        sub = df[df[state_col].isin(combo)].dropna(subset=["filename"]).copy()
        sub[state_col] = sub[state_col].astype("object")
        sub["Injected"] = pd.Categorical(sub["Injected"]).as_ordered()
        model = smf.mixedlm(f"{prop} ~ Injected * {state_col}", sub, groups=sub[group_var]).fit()
        for term in model.pvalues.index:
            if "Injected" in term and state_col in term:
                m = re.search(r"Injected\[T\.([^\]]+)\]", term)
                rows.append({"comparison": f"{combo[0]} vs {combo[1]}", "interaction": term,
                             "injected": float(m.group(1)) if m else np.nan, "pvalue": model.pvalues[term]})
    out = pd.DataFrame(rows)
    if not out.empty:
        reject, corrected, _, _ = multipletests(out["pvalue"], alpha=0.05, method="fdr_bh")
        out["pvalue_corrected"], out["reject_null"] = corrected, reject
    return out


def stars(p: float) -> str:
    return "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "n.s."


def pairwise(df, col, group_col, pairs, test="u", correct=True) -> dict:
    """p values of `pairs` of groups: Mann-Whitney U ("u") of `col`, or Fisher's exact test ("fisher") of the
    silent cells, two-sided, Benjamini-Hochberg corrected over `pairs` when `correct`."""
    ps = []
    for a, b in pairs:
        if test == "fisher":
            t = [[(df.loc[df[group_col] == g, col] == "silent").sum(), (df.loc[df[group_col] == g, col] != "silent").sum()]
                 for g in (a, b)]
            ps.append(stats.fisher_exact(t)[1])
        else:
            ps.append(stats.mannwhitneyu(df.loc[df[group_col] == a, col].dropna(),
                                         df.loc[df[group_col] == b, col].dropna(), alternative="two-sided")[1])
    if correct and len(ps) > 1:
        ps = list(multipletests(ps, method="fdr_bh")[1])
    return dict(zip(pairs, ps))


# the comparisons the caption names for panels a-c, "between Pre, Agg+ and Agg-; Pre, ZD and NPY; Agg+ and KD-Y",
# each family corrected on its own (which gives the published stars)
FAMILIES = [list(combinations(["Pre", "Agg+", "Agg-"], 2)), list(combinations(["Pre", "ZD7288", "npy_100"], 2)),
            [("Agg+", "npykd")]]


def family_p(df, col, group_col, test="u") -> dict:
    """p values of every pair in FAMILIES, Benjamini-Hochberg corrected within its family."""
    return {k: v for fam in FAMILIES for k, v in pairwise(df, col, group_col, fam, test).items()}


# --- drawing ---

def boxstrip(ax, data, x, y, order, palette, labels=None, ylim=None, nbins=3, ylabel="", rotation=45,
             box_alpha=0.5, edge="auto"):
    """A box plot over the cells as dots, as every box plot in the notebooks (boxes at half opacity, no fliers)."""
    data = data[data[x].isin(order)]
    sns.boxplot(x=x, y=y, data=data, order=order, hue=x, hue_order=order, palette=palette, legend=False,
                saturation=1, linewidth=LW, showfliers=False, boxprops=dict(alpha=box_alpha), width=0.7, ax=ax)
    np.random.seed(1)                    # the jitter, the same at every render
    sns.stripplot(x=x, y=y, data=data, order=order, hue=x, hue_order=order, palette=palette, legend=False,
                  jitter=True, size=POINT, linewidth=0.3, edgecolor=edge, alpha=0.5, zorder=0, ax=ax)
    _finish(ax, labels or order, ylim, nbins, ylabel, rotation)


def bars(ax, cats, values, palette, labels=None, ylim=None, nbins=3, ylabel="", rotation=45, alpha=0.7, width=0.8):
    ax.bar(range(len(cats)), values, color=palette, alpha=alpha, width=width)
    ax.set_xlim(-0.6, len(cats) - 0.4)
    _finish(ax, labels or cats, ylim, nbins, ylabel, rotation)


def _finish(ax, labels, ylim, nbins, ylabel, rotation):
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=rotation, ha="right" if rotation else "center",
                       rotation_mode="anchor" if rotation else "default")
    ax.set_xlabel("")
    ax.set_ylabel(ylabel)
    if ylim:
        ax.set_ylim(*ylim)
    ax.yaxis.set_major_locator(MaxNLocator(nbins))
    sns.despine(ax=ax)


def silent_percent(df, group_col, groups, col="I_zero_reclassified") -> list:
    """% of cells silent at rest in each group (the notebooks' crosstab of the classification)."""
    df = df[df[group_col].isin(groups)].dropna(subset=[col])
    return [100 * (df.loc[df[group_col] == g, col] == "silent").mean() for g in groups]


def bracket(ax, i, j, y, text, drop=0.03):
    """A significance bracket from category i to j at height y (data units)."""
    lo, hi = ax.get_ylim()
    d = (hi - lo) * drop
    ax.plot([i, i, j, j], [y - d, y, y, y - d], lw=0.5, color="black", clip_on=False)
    ax.text((i + j) / 2, y - d * 0.4, text, ha="center", va="bottom", clip_on=False)


def ramp_lines(ax, df, hue, order, colors, errorbar=("se", 1), lw=0.9, alpha=1.0):
    sns.lineplot(data=df, x="Injected", y="num_spike", hue=hue, hue_order=order, palette=colors, err_style="bars",
                 errorbar=errorbar, linewidth=lw, alpha=alpha, err_kws={"elinewidth": 0.5}, seed=1, legend=False, ax=ax)
    ax.set_xlabel("Current (pA)")
    ax.set_ylabel("Evoked spikes")
    ax.set_xticks([50, 100, 150])
    sns.despine(ax=ax)


def significance_bars(ax, result, combos, colors, base_y=0.0, y_shift=None, height=None, width=10):
    """The current steps where two groups' curves differ, as bars along the bottom, darker the smaller p
    (ephys_utils.plot_significance_bars_shifted), with the key at the top left as in the figure."""
    lo, hi = ax.get_ylim()
    height = height or (hi - lo) * 0.025
    y_shift = (hi - lo) * 0.035 if y_shift is None else y_shift
    for i, combo in enumerate(combos):
        c = (np.array(mcolors.to_rgb(colors[combo[0]])) + np.array(mcolors.to_rgb(colors[combo[1]]))) / 2
        rows = result[(result["comparison"] == f"{combo[0]} vs {combo[1]}") & result["reject_null"]]
        for _, r in rows.iterrows():
            p = r["pvalue_corrected"]
            alpha = 0.8 if p < 0.001 else 0.5 if p < 0.01 else 0.2
            ax.add_patch(Rectangle((r["injected"] - width / 2, base_y + i * y_shift), width, height, color=c,
                                   alpha=alpha, linewidth=0, zorder=10))
    for k, (label, alpha) in enumerate([("***", 0.8), ("**", 0.5), ("*", 0.2)]):
        y = 0.97 - k * 0.075
        ax.add_patch(Rectangle((0.02, y - 0.02), 0.09, 0.035, transform=ax.transAxes, color="gray", alpha=alpha,
                               linewidth=0, clip_on=False))
        ax.text(0.13, y - 0.025, label, transform=ax.transAxes, fontsize=5, va="bottom")


def end_labels(ax, labels):
    """Group names in their colours at the right end of the curves: [(text, colour, y in axes fraction)]."""
    for text, color, y in labels:
        ax.text(1.02, y, text, color=color, transform=ax.transAxes, va="center", clip_on=False)
