# Colour and dark versions

## Palettes

`Style(palette=...)` sets the colours every panel plots with, in turn:

- a named palette: `"okabe-ito"` (the default for new projects, which colour-blind readers can tell apart),
  `"tol-bright"`, `"tol-muted"`, `"tol-vibrant"`, `"colorbrewer-set2"`, `"colorbrewer-dark2"`, `"tableau"`;
- a list of colours;
- or names mapped to colours, `{"WT": "#999999", "KO": "#d1495b"}`, used in panel code as `color("KO")` so a
  condition has the same colour in every panel.

Every colour well in the inspector has a hex field and the palette's swatches, and the picker's eyedropper takes any
colour on the screen.

## Colour vision

Preflight warns when two colours of a panel, or of the annotations, that most people tell apart look alike to readers
with deuteranopia, protanopia or tritanopia. **View ▸ Colour Vision** shows the whole figure as those readers would
see it, or as a greyscale print.

<img class="fg-shot" src="../../assets/colour-vision.jpg" alt="The figure shown as a reader with deuteranopia sees it">

## Dark versions

Every figure has a dark version for talks, made from the same code: the style's text and axes turn white, the
background black, and black annotations white. **View ▸ Dark Version of Figure** (<kbd>⌥</kbd><kbd>⌘</kbd><kbd>D</kbd>,
or the moon in the toolbar) shows it, the export dialog has a *Dark version* box, and
`fignimble export fig1.py fig1-dark.pdf --dark` writes it.

<img class="fg-shot" src="../../assets/dark.jpg" alt="The dark version of a figure">

Colours that panel code sets itself stay as they are; use `is_dark()` in panel code to choose
(`"white" if is_dark() else "black"`).

The app itself follows the system's light or dark appearance, or **View ▸ Appearance** chooses one.
