import numpy as np


def draw(fig):
    """An embedding of single cells, coloured by cluster."""
    ax = fig.add_subplot()
    rng = np.random.default_rng(0)
    for k, c in enumerate(["#00798c", "#d1495b", "#edae49", "#66a182"]):
        centre = rng.normal(0, 4, 2)
        pts = rng.normal(centre, 1.0, (150, 2))
        ax.scatter(pts[:, 0], pts[:, 1], s=2, color=c, label=f"cluster {k + 1}", linewidths=0)
    ax.set_xlabel("UMAP 1")
    ax.set_ylabel("UMAP 2")
    ax.set_xticks([]); ax.set_yticks([])
    ax.legend(markerscale=3, handletextpad=0.1, loc="best")
