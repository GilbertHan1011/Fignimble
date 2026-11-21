"""Tables: read from CSV/TSV (or given as rows), formatted the same way on the figure and in Word.

Journals want tables as editable text, not pictures, so a table on a figure can also be written as a .docx with a
real Word table (header in bold, rules above and below the header and at the bottom, as in a printed paper).
"""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape


def read_rows(source: str | Path) -> list[list[str]]:
    """The rows of a .csv, .tsv or .txt file (the delimiter is guessed)."""
    text = Path(source).read_text(encoding="utf-8-sig", errors="replace")
    if Path(source).suffix.lower() == ".tsv":
        delim = "\t"
    else:
        try:
            delim = csv.Sniffer().sniff(text[:4096], delimiters=",\t;|").delimiter
        except csv.Error:
            delim = ","
    return [r for r in csv.reader(io.StringIO(text), delimiter=delim) if any(c.strip() for c in r)]


def _number(s) -> float | None:
    if isinstance(s, (int, float)) and not isinstance(s, bool):
        return float(s)
    try:
        return float(str(s).replace(",", "").replace("−", "-").strip())
    except ValueError:
        return None


def cells(rows: list, header: bool = True, decimals=None) -> tuple[list[list[str]], list[str]]:
    """The rows as the strings shown, padded to one width, and each column's alignment: "r" when every body cell
    is a number, else "l". `decimals` rounds numbers that have decimals (whole numbers stay whole): one number
    for every column, or a list with one per column (None leaves a column as written)."""
    n = max((len(r) for r in rows), default=0)
    places = list(decimals) if isinstance(decimals, (list, tuple)) else [decimals] * n
    places += [None] * (n - len(places))
    out = []
    for i, r in enumerate(rows):
        row = []
        for j, c in enumerate(list(r) + [""] * (n - len(r))):
            v = _number(c)
            whole = isinstance(c, int) or (isinstance(c, str) and not any(ch in c for ch in ".eE"))
            if places[j] is not None and v is not None and not whole and not (header and i == 0):
                row.append(f"{v:.{int(places[j])}f}")
            else:
                row.append("" if c is None else str(c))
        out.append(row)
    body = out[1:] if header else out
    align = ["r" if body and all(_number(r[j]) is not None or not r[j].strip() for r in body)
             and any(r[j].strip() for r in body) else "l" for j in range(n)]
    return out, align


def resolve_align(align, auto: list[str]) -> list[str]:
    """`align` as given ("lrr", ["l", "c"], "center") over the automatic one."""
    if not align:
        return auto
    if isinstance(align, str) and align in ("left", "center", "right"):
        return [align[0]] * len(auto)
    given = [str(a)[0].lower() for a in align]
    return [given[j] if j < len(given) and given[j] in "lcr" else auto[j] for j in range(len(auto))]


# --- Word ---

_CT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>"""
_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>"""
_CORE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:title>{title}</dc:title><dc:creator>Fignimble</dc:creator></cp:coreProperties>"""
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def write_docx(rows: list, path: str | Path, header: bool = True, decimals=None, align=None,
               font: str = "Arial", size: float = 7, title: str | None = None) -> str:
    """Write the table to a Word file: a real table (editable in Word), the figure's font and size, the header
    bold, a rule above and below the header and one at the bottom. `title` goes above it as a paragraph."""
    shown, auto = cells(rows, header, decimals)
    al = resolve_align(align, auto)
    half = max(2, int(round(size * 2)))                     # Word sizes are in half points
    rpr = f'<w:rPr><w:rFonts w:ascii="{escape(font)}" w:hAnsi="{escape(font)}" w:cs="{escape(font)}"/><w:sz w:val="{half}"/></w:rPr>'
    rprb = rpr.replace("<w:sz ", "<w:b/><w:sz ")             # the schema's order: rFonts, b, sz

    def para(text, bold=False, jc="left"):
        runs = []
        for k, line in enumerate(str(text).split("\n")):
            if k:
                runs.append("<w:r><w:br/></w:r>")
            runs.append(f'<w:r>{rprb if bold else rpr}<w:t xml:space="preserve">{escape(line)}</w:t></w:r>')
        return f'<w:p><w:pPr><w:spacing w:before="0" w:after="0"/><w:jc w:val="{jc}"/></w:pPr>{"".join(runs)}</w:p>'

    jcs = {"l": "left", "c": "center", "r": "right"}
    body = []
    if title:
        body.append(para(title, bold=True))
    rule = '<w:{side} w:val="single" w:sz="{sz}" w:space="0" w:color="000000"/>'
    tbl = ['<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/><w:tblBorders>'
           + rule.format(side="top", sz=8) + rule.format(side="bottom", sz=8)
           + '</w:tblBorders><w:tblLayout w:type="autofit"/>'
           '<w:tblCellMar><w:left w:w="80" w:type="dxa"/><w:right w:w="80" w:type="dxa"/></w:tblCellMar></w:tblPr>']
    # column widths (twentieths of a point) from the longest text in each, which Word's autofit then refines
    widths = [int(max(len(r[j]) for r in shown) * size * 0.6 * 20 + 2 * 80 + 120) for j in range(len(al))]
    tbl.append("<w:tblGrid>" + "".join(f'<w:gridCol w:w="{w}"/>' for w in widths) + "</w:tblGrid>")
    for i, r in enumerate(shown):
        head = header and i == 0
        tr = ["<w:tr>" + ("<w:trPr><w:tblHeader/></w:trPr>" if head else "")]
        for j, c in enumerate(r):
            borders = ("<w:tcBorders>" + rule.format(side="bottom", sz=4) + "</w:tcBorders>") if head else ""
            tr.append(f'<w:tc><w:tcPr><w:tcW w:w="{widths[j]}" w:type="dxa"/>{borders}</w:tcPr>'
                      f"{para(c, bold=head, jc=jcs[al[j]])}</w:tc>")
        tbl.append("".join(tr) + "</w:tr>")
    tbl.append("</w:tbl>")
    body.append("".join(tbl))
    body.append('<w:p/><w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
                '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>')
    doc = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:document xmlns:w="{_W}"><w:body>'
           + "".join(body) + "</w:body></w:document>")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CT)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("docProps/core.xml", _CORE.format(title=escape(title or path.stem)))
        z.writestr("word/document.xml", doc)
    return str(path.resolve())
