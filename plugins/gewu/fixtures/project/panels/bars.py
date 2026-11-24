"""A second panel, drawn by its `bars` function."""
import numpy as np


def bars(fig):
    ax = fig.add_subplot()
    ax.bar(["A", "B", "C"], [3, 5, 2], color="#4c72b0")
    ax.set_ylabel("Count")
