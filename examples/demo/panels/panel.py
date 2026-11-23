"""A panel: draw(fig) gets a matplotlib Figure exactly the panel's size. Fonts, text sizes and line widths come
from the project's style, so leave them out here and every panel will match."""
import numpy as np


def draw(fig, kind="lines"):
    ax = fig.add_subplot()
    x = np.linspace(0, 10, 100)
    if kind == "bars":
        ax.bar(["A", "B", "C"], [3, 5, 2], color="#4c72b0")
        ax.set_ylabel("Count")
    else:
        ax.plot(x, np.sin(x), label="sin")
        ax.plot(x, np.cos(x), label="cos")
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Signal")
        ax.legend()
