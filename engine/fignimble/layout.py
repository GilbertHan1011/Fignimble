"""Solving patchwork-style layouts: every Row, Column, Grid and Design is a grid of tracks with relative sizes,
and every item fills a rectangle of cells. Nested nodes get the rectangle of their cells and are solved in it."""

from __future__ import annotations

import math

from . import api


def grid_of(node: api.Node):
    """(nrow, ncol, cells [(item, r0, c0, r1, c1)], widths, heights) of a node."""
    p = node.props
    if isinstance(node, api.Row):
        n = len(node.items)
        return 1, n, [(it, 0, i, 1, i + 1) for i, it in enumerate(node.items)], p["widths"], None
    if isinstance(node, api.Column):
        n = len(node.items)
        return n, 1, [(it, i, 0, i + 1, 1) for i, it in enumerate(node.items)], None, p["heights"]
    if isinstance(node, api.Grid):
        n = len(node.items)
        ncol, nrow = p["ncol"], p["nrow"]
        if ncol is None and nrow is None:
            ncol = math.ceil(math.sqrt(n))
        if ncol is None:
            ncol = math.ceil(n / nrow)
        if nrow is None:
            nrow = math.ceil(n / ncol)
        if ncol * nrow < n:
            raise ValueError(f"a {nrow} x {ncol} grid has no room for {n} items")
        cells = []
        for i, it in enumerate(node.items):
            r, c = (divmod(i, ncol) if p["byrow"] else divmod(i, nrow)[::-1])
            cells.append((it, r, c, r + 1, c + 1))
        return nrow, ncol, cells, p["widths"], p["heights"]
    if isinstance(node, api.Design):
        rows = node.rows
        nrow, ncol = len(rows), len(rows[0])
        cells = []
        for letter in dict.fromkeys(ch for r in rows for ch in r):
            if letter in "#.":
                continue
            if letter not in node.areas:
                raise ValueError(f"the design has area {letter!r} but no {letter}=... for it")
            where = [(r, c) for r in range(nrow) for c in range(ncol) if rows[r][c] == letter]
            r0, r1 = min(r for r, _ in where), max(r for r, _ in where) + 1
            c0, c1 = min(c for _, c in where), max(c for _, c in where) + 1
            if len(where) != (r1 - r0) * (c1 - c0):
                raise ValueError(f"area {letter!r} of the design is not a rectangle")
            cells.append((node.areas[letter], r0, c0, r1, c1))
        return nrow, ncol, cells, p["widths"], p["heights"]
    raise TypeError(f"not a layout: {node!r}")


def _tracks(total: float, n: int, weights, gap: float) -> list[float]:
    w = list(weights) if weights else [1.0] * n
    if len(w) != n:
        w = (w + [1.0] * n)[:n]
    avail = max(total - gap * (n - 1), 0.0)
    s = sum(float(v) for v in w) or 1.0
    return [avail * float(v) / s for v in w]


def solve(node, box: tuple, gap: float, widths=None, heights=None, layout_site=None, path=()):
    """Leaves [(item, box)] and dividers [{...}] of a node laid out in box (x, y, w, h mm).

    A divider is a boundary between two tracks that can be dragged: where it is, what it separates, and which
    call's `widths`/`heights` changing it rewrites (the node's own call, or the fig.layout call for the outermost
    node when that one is made with operators or the layout gives its sizes)."""
    if not isinstance(node, (api.Row, api.Column, api.Grid, api.Design)):
        return [(node, box)], []
    x, y, w, h = box
    g = node.props.get("gap")
    g = gap if g is None else g
    nrow, ncol, cells, ws, hs = grid_of(node)
    ws = widths or ws
    hs = heights or hs
    cw = _tracks(w, ncol, ws, g)
    rh = _tracks(h, nrow, hs, g)
    xs = [x + sum(cw[:i]) + g * i for i in range(ncol + 1)]
    ys = [y + sum(rh[:i]) + g * i for i in range(nrow + 1)]
    leaves, dividers = [], []
    # whose widths/heights a drag rewrites
    if not path and (widths or heights or node.site is None):
        owner = {"site": layout_site, "method": "layout", "widths": "widths", "heights": "heights"}
    elif node.site is not None:
        owner = {"site": node.site, "method": node.method,
                 "widths": "widths" if not isinstance(node, api.Column) else None,
                 "heights": "heights" if not isinstance(node, api.Row) else None}
    else:
        owner = None
    for axis, sizes, edges, cross_edges, ncross, end in (("col", cw, xs, ys, nrow, y + h), ("row", rh, ys, xs, ncol, x + w)):
        n = len(sizes)
        param = owner and owner["widths" if axis == "col" else "heights"]
        for i in range(n - 1):
            at = edges[i + 1] - g / 2
            # only where it is a gap: not across an item that spans both tracks (patchwork's "AAB" areas)
            def crossed(t):
                for _, r0, c0, r1, c1 in cells:
                    a0, a1, b0, b1 = (c0, c1, r0, r1) if axis == "col" else (r0, r1, c0, c1)
                    if a0 <= i and a1 >= i + 2 and b0 <= t < b1:
                        return True
                return False
            t = 0
            while t < ncross:
                if crossed(t):
                    t += 1
                    continue
                t0 = t
                while t < ncross and not crossed(t):
                    t += 1
                lo = cross_edges[t0]
                hi = cross_edges[t] - g if t < ncross else end
                dividers.append({"axis": axis, "index": i, "at": at, "from": lo, "to": hi,
                                 "sizes": [round(v, 3) for v in sizes], "site": owner and owner["site"],
                                 "method": owner and owner["method"], "param": param, "editable": bool(param)})
    for k, (item, r0, c0, r1, c1) in enumerate(cells):
        cbox = (xs[c0], ys[r0], xs[c1] - g - xs[c0] if c1 < ncol else x + w - xs[c0],
                ys[r1] - g - ys[r0] if r1 < nrow else y + h - ys[r0])
        sub_leaves, sub_div = solve(item, cbox, gap, path=path + (k,))
        leaves += sub_leaves
        dividers += sub_div
    return leaves, dividers
