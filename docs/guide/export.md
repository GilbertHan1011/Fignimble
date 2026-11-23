# Preflight and export

## Preflight

Every render checks what a journal's production office would. The status bar counts the warnings, the figure's
thumbnail shows them, and **View ▸ Preflight** (<kbd>⌥</kbd><kbd>⌘</kbd><kbd>P</kbd>) lists them; click one to select
the element.

<img class="fg-shot" src="../../assets/preflight.jpg" alt="The preflight list in the drawer">

- text below the minimum size, inside panels too (superscripts and subscripts excepted);
- pictures below the minimum resolution at their printed size;
- Type 3 fonts, which journals reject;
- elements and letters reaching outside the figure;
- two panels with the same letter;
- colours colour-blind readers confuse;
- a figure width that isn't one of the journal's columns;
- panels whose code fails, with the error, and what to do when a package is missing.

`fignimble check` runs it on every figure of a project and exits with status 1 on problems, for scripts and CI.

## Export

**File ▸ Export Figure…** (<kbd>⌘</kbd><kbd>E</kbd>) writes the figure as:

| Format | What you get |
|---|---|
| PDF, EPS, SVG | vector, with real, editable TrueType text |
| TIFF (LZW), PNG, JPEG | pixels, at the resolution you set |

The dialog asks which journal to meet (the style's by default) and the resolution, from 300 to 2400 dpi. A TIFF or
JPEG below what the journal asks is raised to it: 1200 dpi for line art, 600 with pictures (Cell Press 1000 and 500).
For PDF and EPS the resolution is that of what panels draw as pixels, such as heatmaps. After writing, Fignimble
measures the file: its dpi, or each picture inside a PDF or EPS against what the journal asks for photographs.

For print: **CMYK** (PDF, EPS, TIFF, JPEG) and **text as outlines** (PDF, EPS, SVG). These and EPS use
[Ghostscript](https://www.ghostscript.com) (`brew install ghostscript`).

**File ▸ Export All Figures as PDF…** (<kbd>⇧</kbd><kbd>⌘</kbd><kbd>E</kbd>) writes every figure of the project.

From a terminal:

```bash
fignimble export fig1.py fig1.pdf
fignimble export fig1.py fig1.tiff --journal cell
fignimble export fig1.py fig1.eps --cmyk --outline
fignimble export fig1.py fig1-dark.pdf --dark
```

## The clipboard

**Edit ▸ Copy Figure as Picture** (<kbd>⇧</kbd><kbd>⌘</kbd><kbd>C</kbd>, or <kbd>⌘</kbd><kbd>C</kbd> with nothing
selected) puts the whole figure on the clipboard as vector PDF and a 600 dpi PNG, for Word, PowerPoint, Keynote,
Illustrator, mail or chat. Copy and paste also move elements between figures, and a picture pasted from another app is
saved into `images/`.

## Tables

Journals want tables as text: **File ▸ Export Table as Word…** writes a table of the figure as an editable Word table.
See [tables](annotating.md#tables).
