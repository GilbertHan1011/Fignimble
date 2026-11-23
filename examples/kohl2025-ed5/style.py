"""Nature's figure style: Arial 7 pt, lower-case bold labels."""
from fignimble import *

STYLE = Style.journal("nature", labels=Labels.journal("nature", dx=-2, dy=-0.5, format="{}", case="lower"))
