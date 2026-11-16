import numpy as np

from fignimble import is_dark


def draw(fig, genes=("GAPDH", "CD3E", "MS4A1", "LYZ")):
    """Expression of a few genes across time."""
    ax = fig.add_subplot()
    t = np.linspace(0, 24, 60)
    for i, g in enumerate(genes):
        ax.plot(t, np.sin(t / 4 + i) + 2 * i, label=g)
    ax.set_xlabel("Time (h)")
    ax.set_ylabel("log expression")
    ax.legend(loc="upper left", ncols=2)


def bars(fig):
    """Mean expression per condition."""
    ax = fig.add_subplot()
    rng = np.random.default_rng(1)
    means = [1.0, 1.3, 2.4, 2.1]
    ax.bar(range(4), means, yerr=rng.uniform(0.1, 0.3, 4), color=["#999999", "#999999", "#d1495b", "#d1495b"],
           capsize=2, width=0.7, ecolor="white" if is_dark() else "black")
    ax.set_xticks(range(4), ["WT", "KO", "WT+", "KO+"])
    ax.set_ylabel("Fold change")
    ax.set_ylim(0, 3.4)
