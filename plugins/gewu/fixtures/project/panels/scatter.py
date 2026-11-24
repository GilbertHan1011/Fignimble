"""A panel: draw(fig) gets a matplotlib Figure exactly the panel's size."""
import numpy as np


def draw(fig):
    ax = fig.add_subplot()
    x = np.linspace(0, 10, 60)
    ax.plot(x, np.sin(x), label="sin")
    ax.plot(x, np.cos(x), label="cos")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Signal")
    ax.legend()
