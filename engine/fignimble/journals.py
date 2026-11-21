"""Figure sizes, label conventions and resolutions of some journals.

Widths are in millimetres. `dpi` is the least resolution, as printed, asked of raster figures and of the pictures
inside vector ones: "photo" for photographs and micrographs alone (halftones), "combination" for pictures with text
or line art, "line" for line art alone (plots, diagrams, text). Widths and fonts follow the journals' author
guidelines as of 2026; the resolutions are the usual production values (300/600/1200, Cell Press 300/500/1000).
Check the current guidelines before submitting, since journals revise them.
"""

JOURNALS = {
    "nature": {
        "name": "Nature",
        "dpi": {"photo": 300, "combination": 600, "line": 1200},
        "widths": {"single": 89, "double": 183},
        "font": "Arial",
        "font_size": 7,
        "min_font": 5,
        "labels": {"case": "lower", "weight": "bold", "size": 8, "format": "{}"},
    },
    "science": {
        "name": "Science",
        "dpi": {"photo": 300, "combination": 600, "line": 1200},
        "widths": {"single": 57, "double": 121, "triple": 184},
        "font": "Helvetica",
        "font_size": 7,
        "min_font": 5,
        "labels": {"case": "upper", "weight": "bold", "size": 9, "format": "{}"},
    },
    "cell": {
        "name": "Cell Press",
        "dpi": {"photo": 300, "combination": 500, "line": 1000},
        "widths": {"single": 85, "one-and-a-half": 114, "double": 174},
        "font": "Arial",
        "font_size": 7,
        "min_font": 6,
        "labels": {"case": "upper", "weight": "bold", "size": 9, "format": "{}"},
    },
    "pnas": {
        "name": "PNAS",
        "dpi": {"photo": 300, "combination": 600, "line": 1200},
        "widths": {"single": 87, "one-and-a-half": 114, "double": 178},
        "font": "Arial",
        "font_size": 7,
        "min_font": 6,
        "labels": {"case": "upper", "weight": "bold", "size": 9, "format": "{}"},
    },
    "elife": {
        "name": "eLife",
        "dpi": {"photo": 300, "combination": 600, "line": 1200},
        "widths": {"single": 85, "double": 178},
        "font": "Arial",
        "font_size": 7,
        "min_font": 6,
        "labels": {"case": "upper", "weight": "bold", "size": 9, "format": "{}"},
    },
}


# what most journals ask when no journal is named (and the usual production standard)
DEFAULT_DPI = {"photo": 300, "combination": 600, "line": 1200}


def dpi(journal: str | None) -> dict:
    """The resolutions (dpi) `journal` asks for: {photo, combination, line}."""
    j = JOURNALS.get((journal or "").lower())
    return dict(j["dpi"]) if j else dict(DEFAULT_DPI)


def width(journal: str, columns="double") -> float:
    """The figure width (mm) of `journal` for `columns` ("single", "double", 1, 2, ...)."""
    j = JOURNALS[journal.lower()]
    if isinstance(columns, int):
        columns = {1: "single", 2: "double", 3: "triple"}.get(columns, "double")
    if columns not in j["widths"]:
        raise ValueError(f"{j['name']} has no {columns!r} width; it has {', '.join(j['widths'])}")
    return float(j["widths"][columns])
