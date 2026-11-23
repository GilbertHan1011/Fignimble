# The Fignimble window

<img class="fg-shot" src="../../assets/editor.jpg" alt="The Fignimble window with a panel selected">

- **Figures** (top left): a thumbnail of each figure file in the project, with its count of preflight warnings.
  Click one to open it; **+** makes a new one (**File ▸ New Figure…**, <kbd>⌘</kbd><kbd>N</kbd>).
- **Layers** (bottom left): every element of the figure, top to bottom, with its panel letter. The eye hides an
  element and the lock stops the pointer from catching it (**Object ▸ Lock**, <kbd>⌘</kbd><kbd>2</kbd>;
  **Hide**, <kbd>⌘</kbd><kbd>3</kbd>).
- **Canvas** (middle): the figure on a page, with rulers in millimetres. The toolbar above it has the tools and
  buttons for a new panel, a picture and BioCartoon icons.
- **Inspector** (right): the selected element's position and size in millimetres and its settings. With nothing
  selected, the figure's size, the shared style and the panel label style.
- **Drawer** (bottom): the code, preflight list, history and terminals.

## Selecting and moving

Click to select, <kbd>⇧</kbd>-click to add, or drag a marquee. Drag to move: **smart guides** snap to other
elements' edges and centres, the figure's edges and centre, and guides you drag out of the rulers; equal-spacing
hints show when gaps match. Hold <kbd>⌘</kbd> while dragging to turn snapping off. Arrow keys nudge by 0.5 mm
(<kbd>⇧</kbd> 5 mm, <kbd>⌥</kbd> 0.1 mm).

Drag a handle to resize (<kbd>⇧</kbd> keeps the proportions; pictures always keep theirs). Lines and arrows have end
handles (<kbd>⇧</kbd> snaps to 45°).

## Arranging

The inspector and the **Object** menu align a selection (left, centre, right, top, middle, bottom) to itself, to the
first selected element or to the figure; distribute with equal gaps or a fixed gap; match widths and heights; group
and ungroup (<kbd>⌘</kbd><kbd>G</kbd>); and change the stacking order, which is the order of the lines in the
figure file (<kbd>⌘</kbd><kbd>]</kbd>, <kbd>⌘</kbd><kbd>[</kbd>).

## Tools

| Tool | Key | Draws |
|---|---|---|
| Select | <kbd>V</kbd> | |
| Text | <kbd>T</kbd> | a text, or a text box when you drag |
| Line | <kbd>L</kbd> | a line |
| Arrow | <kbd>A</kbd> | an arrow |
| Rectangle | <kbd>R</kbd> | a rectangle |
| Ellipse | <kbd>E</kbd> | an ellipse |
| Bracket | <kbd>B</kbd> | a significance bracket |
| Pen | <kbd>P</kbd> | a path: click points, double-click or Return to finish, click the first point to close |
| Zoom | <kbd>Z</kbd> | drag a box to zoom to it; <kbd>⌥</kbd>-click zooms out |

## Viewing

Zoom with <kbd>⌘</kbd><kbd>+</kbd> and <kbd>⌘</kbd><kbd>−</kbd>, a pinch, or <kbd>⌘</kbd>-scroll;
<kbd>⌘</kbd><kbd>0</kbd> fits the figure and <kbd>⌘</kbd><kbd>1</kbd> shows it at actual size. Scroll or
space-drag to pan. **View ▸ Grid** and **Snap to Grid** help with regular layouts.

## History

**View ▸ History** (<kbd>⌥</kbd><kbd>⌘</kbd><kbd>⇧</kbd><kbd>H</kbd>) lists every edit; click a step to go back to
it. Undo and redo (<kbd>⌘</kbd><kbd>Z</kbd>, <kbd>⇧</kbd><kbd>⌘</kbd><kbd>Z</kbd>) cover canvas and code-pane edits.

<img class="fg-shot" src="../../assets/history.jpg" alt="The history list in the drawer">

## Dropping files

Drop PNG, TIFF, JPEG, PDF or SVG files on the canvas to place them as pictures, `.py` files to place them as
panels, and CSV or TSV files to place them as tables. They are copied into the project.
