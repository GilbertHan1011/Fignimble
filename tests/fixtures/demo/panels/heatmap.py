import numpy as np


def draw(fig):
    """Correlation between samples."""
    ax = fig.add_subplot()
    rng = np.random.default_rng(2)
    m = np.corrcoef(rng.normal(size=(8, 30)))
    im = ax.imshow(m, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(8), [f"S{i + 1}" for i in range(8)], rotation=90)
    ax.set_yticks(range(8), [f"S{i + 1}" for i in range(8)])
    fig.colorbar(im, ax=ax, shrink=0.7, label="Pearson r")
