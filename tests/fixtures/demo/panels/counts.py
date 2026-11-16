import numpy as np


def draw(fig, genes=("GAPDH", "CD3E", "MS4A1", "LYZ")):
    """Cumulative read counts per gene: large numbers, so wide tick labels."""
    ax = fig.add_subplot()
    t = np.linspace(0, 24, 60)
    for i, g in enumerate(genes):
        ax.plot(t, 2000 * (i + 1) * t ** 1.2 / 24, label=g)
    ax.set_xlabel("Time (h)")
    ax.set_ylabel("Reads")
    ax.legend(loc="upper left")


def zoom(fig):
    """A close-up for an inset."""
    ax = fig.add_subplot()
    t = np.linspace(0, 4, 40)
    ax.plot(t, np.sin(t / 4), color="C0")
    ax.set_xticks([0, 4])
    ax.set_yticks([])
