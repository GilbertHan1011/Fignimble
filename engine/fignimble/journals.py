"""Figure sizes and label conventions of some journals.

Widths are in millimetres. They follow the journals' author guidelines as of 2026; check the current guidelines
before submitting, since journals revise them.
"""

JOURNALS = {
    "nature": {
        "name": "Nature",
        "widths": {"single": 89, "double": 183},
        "font": "Arial",
        "font_size": 7,
        "min_font": 5,
        "labels": {"case": "lower", "weight": "bold", "size": 8, "format": "{}"},
    },
    "science": {
        "name": "Science",
        "widths": {"single": 57, "double": 121, "triple": 184},
        "font": "Helvetica",
        "font_size": 7,
        "min_font": 5,
        "labels": {"case": "upper", "weight": "bold", "size": 9, "format": "{}"},
    },
    "cell": {
        "name": "Cell Press",
        "widths": {"single": 85, "one-and-a-half": 114, "double": 174},
        "font": "Arial",
        "font_size": 7,
        "min_font": 6,
        "labels": {"case": "upper", "weight": "bold", "size": 9, "format": "{}"},
    },
    "pnas": {
        "name": "PNAS",
        "widths": {"single": 87, "one-and-a-half": 114, "double": 178},
        "font": "Arial",
        "font_size": 7,
        "min_font": 6,
        "labels": {"case": "upper", "weight": "bold", "size": 9, "format": "{}"},
    },
    "elife": {
        "name": "eLife",
        "widths": {"single": 85, "double": 178},
        "font": "Arial",
        "font_size": 7,
        "min_font": 6,
        "labels": {"case": "upper", "weight": "bold", "size": 9, "format": "{}"},
    },
}


def width(journal: str, columns="double") -> float:
    """The figure width (mm) of `journal` for `columns` ("single", "double", 1, 2, ...)."""
    j = JOURNALS[journal.lower()]
    if isinstance(columns, int):
        columns = {1: "single", 2: "double", 3: "triple"}.get(columns, "double")
    if columns not in j["widths"]:
        raise ValueError(f"{j['name']} has no {columns!r} width; it has {', '.join(j['widths'])}")
    return float(j["widths"][columns])
