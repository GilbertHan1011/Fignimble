# Extended Data Fig. 5, rebuilt in Fignimble

Extended Data Fig. 5 of Cao, M. *et al.* "Integration of hunger and hormonal state gates infant-directed aggression",
*Nature* **648**, 138–145 (2025), [doi:10.1038/s41586-025-09651-2](https://doi.org/10.1038/s41586-025-09651-2)
(open access at [PMC12675289](https://pmc.ncbi.nlm.nih.gov/articles/PMC12675289/)): 37 panels, a to ak, rebuilt from
the authors' code and data ([FrancisCrickInstitute/negative_parental_switch](https://github.com/FrancisCrickInstitute/negative_parental_switch),
`NPS_ephys`). The authors saved each panel as its own PDF and assembled the figure by hand; here the figure is
`ed5.py`, and every panel is a function in `panels/`.

Open `ed5.py` in Fignimble. The panels need pandas, seaborn, statsmodels and scipy in Fignimble's Python:

```
"$HOME/Library/Application Support/Fignimble/python/bin/python3" -m pip install pandas seaborn statsmodels scipy
```

| Panels | Code | From |
|---|---|---|
| a-i | `panels/pharmacology.py` | `ephys_analysis.ipynb`, cells 8, 10, 13, 39, 40, 63, 64 |
| k-p, r-w | `panels/resampled.py` | `resampled_ephys.ipynb` |
| y-ak | `panels/estrous.py` | `ephys_analysis.ipynb`, cells 56-57, 67-77 |
| j, q, x | `ed5.py` | drawn in Fignimble with BioCartoon icons |

The cell counts match the caption for every panel checked: a, k-w, y and aa-aj.

## Fixed or filled in

- **ad**: the notebook's cell 76 stops with `NameError: name 'corr' is not defined`. `corr` is the % of neurons with
  a sag per oestrous stage joined to the stage's switching rate (`data/estrous_data.csv`).
- **f, h**: the notebook has no cells for them. They are drawn the same way as g (cell 13), from the same table.
- **y, aa, ab**: drawn only when an ANOVA came out significant (cell 68), so the notebook has no plotting code for
  them. They are drawn the same way as the neighbouring panels.
- **ae-aj**: cells 70-75 read variables left over from earlier cells. Here they are built explicitly.
- **ai**: the figure gives seconds; the data are in milliseconds.
- **o, v**: one Post cell is classed `slent` in the later data table, a typo for silent. The published bars count it
  as not silent (11/27 and 5/12); here it counts as silent (12/27 and 6/12).
- **z**: the published bars (25.6, 45.5, 32.5, 31.9%) are from the later table with the 2025 recordings, not from
  cell 67's selection, which the caption's n describes. The panel is drawn from the later table, to match the figure.
- **Stars** are recomputed with the tests the caption names. For a-c, Benjamini-Hochberg is applied within each
  comparison family the caption lists, which reproduces every published star. **ad** differs: the regression of
  four stages gives p = 0.004 (**) and R² = 0.99, where the caption gives P = 0.006 and R² = 0.035 and the figure
  shows *.

## Credit and license

The article, its figures, and the authors' code and data (Cao, Ammari, Chen, Wai, Jamieson, Liang, Husain, Sahni,
Legrave, Salgarella, MacRae, Strom and Kohl; The Francis Crick Institute) are licensed under the
[Creative Commons Attribution 4.0 International License](https://creativecommons.org/licenses/by/4.0/). This
project is an adaptation of Extended Data Fig. 5 and of the code and data in `NPS_ephys` of
[FrancisCrickInstitute/negative_parental_switch](https://github.com/FrancisCrickInstitute/negative_parental_switch).
Changes made: the notebook cells were rewritten as Fignimble panel functions, the figure was assembled in Fignimble,
the schematics were redrawn, and the fixes listed above were applied. It is shared under the same license.

The schematics use "C57 MOUSE" by Long Li (SciDraw, SD016325) and "Rat pup P1" by Antonis Asiminas (SciDraw,
SD016414), both CC BY 4.0, from BioCartoon.
