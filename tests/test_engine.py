"""Engine tests: canvas edits become the right source edits, undo works with edits made in between.

    PYTHONPATH=engine .venv/bin/python -m pytest tests
"""

import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))

from fignimble.core import Session  # noqa: E402
from fignimble import srcedit  # noqa: E402


@pytest.fixture(scope="module")
def session(tmp_path_factory):
    d = tmp_path_factory.mktemp("proj") / "demo"
    # a fixed copy of the demo project (the one in examples/ is for people to play with)
    shutil.copytree(ROOT / "tests" / "fixtures" / "demo", d, ignore=shutil.ignore_patterns(".fignimble", "__pycache__"))
    s = Session(str(d), sys.executable)
    yield s
    s.close()


def fig_text(s):
    return (s.project / "fig1.py").read_text()


def el(res, kind, n=0):
    return [e for e in res["elements"] if e["kind"] == kind][n]


def edit(s, **a):
    r = s.edit({"figure": "fig1", **a})
    assert r["ok"], r.get("error")
    return r


def test_render(session):
    r = session.api_figure({"name": "fig1"})
    assert not r.get("error"), r.get("error")
    assert [l["text"] for l in r["labels"]] == list("abcdef")
    assert all(Path(e["sprite"]["file"]).exists() for e in r["elements"])
    assert session.api_state()["figures"][0]["name"] == "fig1"


def test_move_and_undo(session):
    before = fig_text(session)
    r = edit(session, op="move", oids=["1"], dx=3, dy=-1.5)
    assert 'fig.panel("panels/scatter.py", x=68, y=1.5, w=56, h=52)' in fig_text(session)
    assert el(r["figure"], "panel", 1)["box"][:2] == [68, 1.5]
    session.undo({"figure": "fig1"})
    assert fig_text(session) == before


def test_resize_image_keeps_aspect(session):
    edit(session, op="resize", oid="3", box=[4, 63, 40, 30])
    assert 'fig.image("images/cells.png", x=4, y=63, w=40)' in fig_text(session)
    session.undo({"figure": "fig1"})


def test_text_edit_and_new_kwarg(session):
    edit(session, op="set", oid="6", props={"text": "Control", "color": "#d1495b"})
    t = fig_text(session)
    assert 'fig.text("Control", x=30, y=104, size=7, weight="bold", align="center", color="#d1495b")' in t
    session.undo({"figure": "fig1"})


def test_labels_reorder_when_panels_move(session):
    # moving panel b below panel f's row makes it last in reading order
    r = edit(session, op="move", oids=["1"], dx=60, dy=60)
    names = {l["panel"]: l["text"] for l in r["figure"]["labels"]}
    assert names["0"] == "a" and names["2"] == "b" and names["1"] == "e"
    session.undo({"figure": "fig1"})


def test_label_style_goes_to_style_py(session):
    r = edit(session, op="labels", props={"format": "({})", "case": "upper"})
    style = (session.project / "style.py").read_text()
    assert 'Labels.journal("nature", dx=-3, dy=-1, format="({})", case="upper")' in style
    assert r["figure"]["labels"][0]["text"] == "(A)"
    session.undo({"figure": "fig1"})


def test_move_one_label(session):
    edit(session, op="move", oids=["L3"], dx=0, dy=-4)
    assert 'fig.image("images/cells.png", x=4, y=63, w=52, label_dy=-4)' in fig_text(session)
    session.undo({"figure": "fig1"})


def test_delete_duplicate_insert(session):
    before = fig_text(session)
    r = edit(session, op="duplicate", oids=["6"])
    assert fig_text(session).count('"Treated"') == 2
    assert r["select"] == ["7"]
    r = edit(session, op="delete", oids=["7"])
    assert fig_text(session) == before
    r = edit(session, op="insert", kind="rect", props={"x": 10, "y": 10, "w": 20, "h": 10, "stroke": "#ff0000"})
    assert 'fig.rect(x=10, y=10, w=20, h=10, stroke="#ff0000")' in fig_text(session)
    assert r["select"] == ["9"]
    for _ in range(3):
        session.undo({"figure": "fig1"})
    assert fig_text(session) == before


def test_order(session):
    before = fig_text(session)
    edit(session, op="order", oids=["0"], how="front")
    lines = [l for l in fig_text(session).splitlines() if l.startswith("fig.")]
    assert lines[-1].startswith('fig.panel("panels/expression.py", x=4')
    session.undo({"figure": "fig1"})
    assert fig_text(session) == before


def test_align_distribute(session):
    edit(session, op="align", oids=["0", "1", "2"], how="top")
    edit(session, op="align", oids=["3", "4"], how="left", to="figure")
    t = fig_text(session)
    assert 'fig.image("images/schematic.svg", x=0, y=63' in t
    session.undo({"figure": "fig1"})
    session.undo({"figure": "fig1"})


def test_figure_size(session):
    edit(session, op="figure", props={"height": 125})
    assert "fig = Figure(width=183, height=125, style=STYLE)" in fig_text(session)
    session.undo({"figure": "fig1"})


def test_computed_value_refused(session):
    p = session.project / "fig1.py"
    before = p.read_text()
    p.write_text(before.replace('fig.text("Treated", x=30,', 'fig.text("Treated", x=24 + 6,'))
    session.renders.clear()
    r = session.edit({"figure": "fig1", "op": "move", "oids": ["6"], "dx": 1, "dy": 0})
    assert not r["ok"] and "computed" in r["error"]
    p.write_text(before)


def test_undo_after_agent_edit(session):
    """An agent edits another line after our edit: undo keeps the agent's line."""
    edit(session, op="move", oids=["0"], dx=1, dy=0)
    p = session.project / "fig1.py"
    t = p.read_text().replace('fig.arrow(57, 82, 64, 82', 'fig.arrow(55, 82, 64, 82')
    p.write_text(t)
    r = session.undo({"figure": "fig1"})
    assert r["ok"]
    t = p.read_text()
    assert 'fig.panel("panels/expression.py", x=4, y=3' in t and "fig.arrow(55, 82" in t
    p.write_text(t.replace("fig.arrow(55, 82", "fig.arrow(57, 82"))


def test_guides_and_groups(session):
    before = fig_text(session)
    r = edit(session, op="guide_add", x=91.5)
    assert r["figure"]["guides"][0]["x"] == 91.5
    edit(session, op="guide_move", index=0, value=90)
    assert "fig.guide(x=90)" in fig_text(session)
    edit(session, op="group", oids=["6", "7"])
    assert fig_text(session).count('group="g1"') == 2
    edit(session, op="ungroup", oids=["6", "7"])
    edit(session, op="guide_delete", index=0)
    assert fig_text(session) == before


def test_srcedit_remove_and_multiline():
    text = 'fig.panel(\n    "a.py",\n    x=1,\n    y=2,\n    label_dx=3,\n)\n'
    src = srcedit.Source(text)
    call = src.calls("panel")[0]
    new = srcedit.apply(text, srcedit.set_args(src, call, "panel", {"label_dx": srcedit.REMOVE, "x": 5, "w": 9}))
    assert new == 'fig.panel(\n    "a.py",\n    x=5,\n    y=2, w=9,\n)\n'


def fig2_text(s):
    return (s.project / "fig2.py").read_text()


def edit2(s, **a):
    r = s.edit({"figure": "fig2", **a})
    assert r["ok"], r.get("error")
    return r


def test_layout_render_and_alignment(session):
    r = session.render("fig2")
    assert not r.get("error"), r.get("error")
    kinds = {e["oid"]: e["kind"] for e in r["elements"]}
    assert kinds["0"] == "layout" and kinds["0.legend"] == "legend" and kinds["1"] == "inset"
    assert [l["text"] for l in r["labels"]] == list("abcd")
    el = {e["oid"]: e for e in r["elements"]}
    # c and d share a row: their plot areas get the same top and bottom margins; a and c the same left margin
    c, d, a = el["0.2"]["aligned"], el["0.3"]["aligned"], el["0.0"]["aligned"]
    assert c[1] == d[1] and c[3] == d[3] and a[0] == c[0]
    assert el["0.3"]["margins"][0] > el["0.2"]["margins"][0]          # d's wide tick labels
    # the gene legend of a and d is shown once
    assert el["0.legend"]["box"][2] > 30


def test_layout_edits(session):
    before = fig2_text(session)
    edit2(session, op="move", oids=["0.1"], dx=2, dy=0)                # a panel in a layout moves the layout
    assert "x=6, y=3, w=177, h=104" in fig2_text(session)
    session.undo({"figure": "fig2"})
    r = session.render("fig2")
    col = next(i for i, d in enumerate(el2(r, "0")["dividers"]) if d["axis"] == "col")
    edit2(session, op="divider", oid="0", index=col, delta=10)
    assert "widths=[" in fig2_text(session) and "widths=[1, 1, 1.2]" not in fig2_text(session)
    session.undo({"figure": "fig2"})
    edit2(session, op="set", oid="0.3", props={"function": "zoom"})
    assert 'counts = Panel("panels/counts.py", function="zoom")' in fig2_text(session)
    session.undo({"figure": "fig2"})
    edit2(session, op="move", oids=["1"], dx=-5.16, dy=0)               # the inset, in fractions of its panel
    assert 'within=counts, x=0.44' in fig2_text(session) or 'within=counts, x=0.45' in fig2_text(session)
    session.undo({"figure": "fig2"})
    r = session.edit({"figure": "fig2", "op": "delete", "oids": ["0.2"]})
    assert not r["ok"] and "part of a layout" in r["error"]
    edit2(session, op="delete", oids=["0.legend"])                      # stops collecting the legends
    assert 'guides="collect"' not in fig2_text(session)
    session.undo({"figure": "fig2"})
    assert fig2_text(session) == before


def el2(r, oid):
    return next(e for e in r["elements"] if e["oid"] == oid)


def test_dark(session):
    r = session.render("fig1", dark=True)
    assert r["dark"] and r["background"] == "#000000"
    assert session.render("fig1", dark=False)["background"] == "#FFFFFF"


def test_make_and_release_layout(session):
    before = fig_text(session)
    r = edit(session, op="make_layout", oids=["0", "1", "2"], gap=5)
    t = fig_text(session)
    assert 'expression = Panel("panels/expression.py")' in t and 'scatter = Panel("panels/scatter.py")' in t
    assert "fig.layout(Grid(expression, scatter, heatmap, ncol=3), x=4, y=3, w=178, h=52, gap=5)" in t
    lay = next(e for e in r["figure"]["elements"] if e["kind"] == "layout")
    assert len(lay["children"]) == 3
    assert [l["text"] for l in r["figure"]["labels"]][:3] == ["a", "b", "c"]
    edit(session, op="release_layout", oid=lay["oid"])
    t = fig_text(session)
    assert "Panel(" not in t and "layout(" not in t and t.count("fig.panel(") == 4
    session.undo({"figure": "fig1"})
    session.undo({"figure": "fig1"})
    assert fig_text(session) == before


def fig3_text(s):
    return (s.project / "fig3.py").read_text()


def edit3(s, **a):
    r = s.edit({"figure": "fig3", **a})
    assert r["ok"], r.get("error")
    return r


def test_new_elements_render(session):
    r = session.render("fig3")
    assert not r.get("error"), r.get("error")
    el = {e["oid"]: e for e in r["elements"]}
    assert not any(e.get("error") for e in r["elements"]), [e.get("error") for e in r["elements"]]
    assert el["2"]["kind"] == "zoom" and el["2"]["target"] == "1"
    assert el["3"]["kind"] == "scalebar" and el["3"]["host"] == "0"
    assert el["10"]["hidden"] and "sprite" not in el["10"]
    keys = {t["key"]: t["text"] for t in el["4"]["texts"]}
    assert keys["ax0.xlabel"] == "tSNE 1" and keys["ax0.legend0"] == "cluster 1"
    assert el["5"]["box"][3] > 5                          # the long text wrapped onto two lines


def test_retype_panel_text(session):
    before = (session.project / "panels" / "scatter.py").read_text()
    # a literal in the panel's code: the code changes
    edit3(session, op="panel_text", oid="4", key="ax0.legend0", text="T cells", old="cluster 1")
    assert (session.project / "panels" / "scatter.py").read_text() == before  # f-string label: not a literal
    assert 'texts={"ax0.xlabel": "tSNE 1", "ax0.ylabel": "tSNE 2", "ax0.legend0": "T cells"}' in fig3_text(session)
    session.undo({"figure": "fig3"})
    edit3(session, op="panel_text", oid="4", key="ax0.title", text="Clusters", old=None)
    r = session.render("fig3")
    assert any(t["text"] == "Clusters" for t in next(e for e in r["elements"] if e["oid"] == "4")["texts"])
    session.undo({"figure": "fig3"})
    r = session.edit({"figure": "fig1", "op": "panel_text", "oid": "0", "key": "ax0.xlabel", "text": "Time (min)",
                      "old": "Time (h)"})
    assert r["ok"], r.get("error")
    assert 'ax.set_xlabel("Time (min)")' in (session.project / "panels" / "expression.py").read_text()
    session.undo({"figure": "fig1"})


def test_crop_rotate_flip(session):
    before = fig3_text(session)
    edit3(session, op="crop", oid="0", box=[14, 3, 70, 60])             # cut 10 mm off the left
    t = fig3_text(session)
    assert 'fig.image("images/cells.png", x=14, y=3, w=70, crop=(0.125, 0, 0, 0))' in t
    edit3(session, op="crop", oid="0", box=[4, 3, 80, 60])              # and back
    assert 'cells = fig.image("images/cells.png", x=4, y=3, w=80)' in fig3_text(session)
    edit3(session, op="rotate", oids=["9"], by=-15)
    assert 'fig.image("images/cells.png", x=160, y=60, w=21, flip="h")' in fig3_text(session)
    edit3(session, op="flip", oids=["9"], axis="h")
    assert 'fig.image("images/cells.png", x=160, y=60, w=21)' in fig3_text(session)
    for _ in range(4):
        session.undo({"figure": "fig3"})
    assert fig3_text(session) == before


def test_move_zoom_scalebar_path(session):
    before = fig3_text(session)
    edit3(session, op="move", oids=["2"], dx=8, dy=0)                    # 8 mm of an 80 mm picture
    assert "region=(0.65, 0.1, 0.25, 0.25)" in fig3_text(session)
    r = edit3(session, op="move", oids=["3"], dx=-40, dy=0)
    assert "scalebar(cells, length=50, unit=\"µm\", pixel_size=0.325, x=" in fig3_text(session)
    edit3(session, op="move", oids=["7"], dx=1, dy=1)
    assert "[(131, 61), (141, 73)" in fig3_text(session)
    for _ in range(3):
        session.undo({"figure": "fig3"})
    assert fig3_text(session) == before


def test_lock_hide_paste_style(session):
    before = fig3_text(session)
    edit3(session, op="set", oid="5", props={"locked": True})
    assert "width=78, locked=True)" in fig3_text(session)
    edit3(session, op="set", oid="5", props={"locked": False})
    edit3(session, op="paste_style", oids=["6", "7"], props={"color": "#123456", "stroke": "#123456", "width": 2,
                                                              "size": 9})
    t = fig3_text(session)
    assert 'fig.arrow(96, 80, 120, 66, width=2, curve=0.25, tip="stealth", color="#123456")' in t
    assert 'stroke="#123456"' in t
    for _ in range(3):
        session.undo({"figure": "fig3"})
    assert fig3_text(session) == before


def test_copy_paste_between_figures(session):
    before1, before3 = fig_text(session), fig3_text(session)
    c = session.copy({"figure": "fig3", "oids": ["6", "5"]})
    r = session.paste({"figure": "fig1", "code": c["code"], "dx": 0, "dy": 0})
    assert r["ok"], r.get("error")
    t = fig_text(session)
    assert "fig.arrow(96, 80, 120, 66" in t and "GFP" in t and len(r["select"]) == 2
    session.undo({"figure": "fig1"})
    c = session.copy({"figure": "fig3", "oids": ["2"]})                  # a zoom needs its pictures
    r = session.paste({"figure": "fig1", "code": c["code"]})
    assert not r["ok"] and "cells" in r["error"]
    c = session.copy({"figure": "fig2", "oids": ["0.1"]})               # a layout brings its Panel lines
    r = session.paste({"figure": "fig2", "code": c["code"], "dx": 0, "dy": 0})
    assert r["ok"], r.get("error")
    assert "expression2 = Panel(" in fig2_text(session)
    session.undo({"figure": "fig2"})
    assert fig_text(session) == before1 and fig3_text(session) == before3


def test_undo_to_and_exports(session, tmp_path):
    n = len(session.history)
    edit3(session, op="move", oids=["5"], dx=1, dy=0)
    edit3(session, op="move", oids=["5"], dx=1, dy=0)
    assert session.api_state()["history"][-1] == "Move"
    session.undo_to({"n": n, "figure": "fig3"})
    assert len(session.history) == n and len(session.redo) == 2
    session.undo_to({"n": n + 2, "figure": "fig3"})
    assert len(session.history) == n + 2
    session.undo_to({"n": n, "figure": "fig3"})
    for fmt, extra in (("eps", {}), ("pdf", {"cmyk": True, "outline": True}), ("tiff", {"cmyk": True})):
        out = tmp_path / f"f.{fmt}"
        r = session.export({"figure": "fig3", "path": str(out), "format": fmt, "dpi": 150, **extra})
        assert r["ok"] and out.stat().st_size > 1000
    from PIL import Image
    assert Image.open(tmp_path / "f.tiff").mode == "CMYK"


def test_add_scalebar_and_zoom(session):
    before = fig_text(session)
    r = edit(session, op="add_scalebar", oid="3", props={"length": 20, "pixel_size": 0.5})
    t = fig_text(session)
    assert 'cells = fig.image("images/cells.png"' in t and "fig.scalebar(cells, length=20, unit=\"µm\", pixel_size=0.5)" in t
    assert any(e["kind"] == "scalebar" for e in r["figure"]["elements"])
    r = edit(session, op="add_zoom", oids=["3"])
    t = fig_text(session)
    assert 'cells_zoom = fig.inset(Image("images/cells.png"), within=cells' in t and "fig.zoom(cells, cells_zoom" in t
    z = next(e for e in r["figure"]["elements"] if e["kind"] == "zoom")
    assert not z.get("error"), z.get("error")
    session.undo({"figure": "fig1"})
    session.undo({"figure": "fig1"})
    assert fig_text(session) == before


def test_panel_text_only_for_panels(session):
    r = session.edit({"figure": "fig1", "op": "panel_text", "oid": "3", "key": "ax0.xlabel", "text": "x", "old": ""})
    assert not r["ok"] and "only the texts of a panel" in r["error"]


def test_palettes_and_colour_vision(session):
    r = session.render("fig1")
    assert any("deuteranopia" in w["message"] for w in r["warnings"])          # matplotlib's default red and green
    edit(session, op="style", props={"palette": "okabe-ito"})
    assert 'palette="okabe-ito"' in (session.project / "style.py").read_text()
    r = session.render("fig1")
    assert r["style"]["palette"][0] == ["0", "#E69F00"]
    assert not any("look alike" in w["message"] and w["oid"] == "0" for w in r["warnings"])
    session.undo({"figure": "fig1"})


def test_recolour_panel_marks(session):
    r = session.render("fig1")
    bars = next(e for e in r["elements"] if e["oid"] == "5")
    red = [m["key"] for m in bars["marks"] if m["color"] == "#D1495B"]
    assert red == ["ax0.patch2", "ax0.patch3"]
    # the colour is written twice in the code (two bars): an override for those marks
    edit(session, op="panel_color", oid="5", keys=red, color="#0072B2", old="#D1495B")
    t = fig_text(session)
    assert 'colors={"ax0.patch2": "#0072B2", "ax0.patch3": "#0072B2"}' in t
    r = session.render("fig1")
    assert sum(m["color"] == "#0072B2" for m in next(e for e in r["elements"] if e["oid"] == "5")["marks"]) == 2
    session.undo({"figure": "fig1"})
    # written once in the panel's code: the code changes
    r = session.edit({"figure": "fig3", "op": "panel_color", "oid": "4", "keys": ["ax0.coll1"], "color": "#000000",
                      "old": "#D1495B"})
    assert r["ok"], r.get("error")
    assert '"#000000", "#edae49"' in (session.project / "panels" / "scatter.py").read_text()
    session.undo({"figure": "fig3"})


def test_restyle_panel_text(session):
    expr = session.project / "panels" / "expression.py"
    before = expr.read_text()
    r = session.render("fig1")
    xl = next(t for t in next(e for e in r["elements"] if e["oid"] == "0")["texts"] if t["key"] == "ax0.xlabel")
    assert xl["color"] and xl["bold"] is False and xl["italic"] is False
    # a literal of one ax.set_xlabel(...) in the panel's code: that call gets the settings
    edit(session, op="panel_text_style", oid="0", key="ax0.xlabel", text="Time (h)",
         props={"size": 8, "color": "#D55E00", "weight": "bold"})
    assert 'ax.set_xlabel("Time (h)", fontsize=8, color="#D55E00", fontweight="bold")' in expr.read_text()
    r = session.render("fig1")
    xl = next(t for t in next(e for e in r["elements"] if e["oid"] == "0")["texts"] if t["key"] == "ax0.xlabel")
    assert xl["size"] == 8 and xl["color"] == "#D55E00" and xl["bold"]
    session.undo({"figure": "fig1"})
    assert expr.read_text() == before
    # a text the code doesn't hold as a literal (a legend entry from an f-string): the panel's text_style
    edit3(session, op="panel_text_style", oid="4", key="ax0.legend0", text="cluster 1",
          props={"color": "#0072B2", "style": "italic"})
    assert '"ax0.legend0": {"color": "#0072B2", "style": "italic"}' in fig3_text(session)
    r = session.render("fig3")
    lg = next(t for t in next(e for e in r["elements"] if e["oid"] == "4")["texts"] if t["key"] == "ax0.legend0")
    assert lg["color"] == "#0072B2" and lg["italic"]
    # a text the panel already retypes (texts=) is restyled beside it
    edit3(session, op="panel_text_style", oid="4", key="ax0.xlabel", text="tSNE 1", props={"size": 9})
    assert '"ax0.xlabel": {"size": 9}' in fig3_text(session)
    # Reset drops both the retyping and the restyling of that text
    edit3(session, op="panel_text_reset", oid="4", key="ax0.xlabel")
    t = fig3_text(session)
    assert '"ax0.xlabel"' not in t and '"ax0.legend0": {"color"' in t
    session.undo({"figure": "fig3"})
    session.undo({"figure": "fig3"})
    session.undo({"figure": "fig3"})
    assert "text_style" not in fig3_text(session)
