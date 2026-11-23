"""High-fidelity HTML to native, editable PowerPoint."""

from html_to_native_pptx.convert import convert, measure
from html_to_native_pptx.errors import ConversionError
from html_to_native_pptx.fontfiles import FontResponses
from html_to_native_pptx.measurer import (
    BACKGROUND,
    MARK,
    SERIES_PROPERTIES,
    WHOLE,
    measure_deck,
    measure_script,
)
from html_to_native_pptx.model import DeckFont, MeasuredDeck
from html_to_native_pptx.writer import deck_pptx

__version__ = "0.1.0"
__all__ = [
    "BACKGROUND",
    "MARK",
    "SERIES_PROPERTIES",
    "WHOLE",
    "ConversionError",
    "DeckFont",
    "FontResponses",
    "MeasuredDeck",
    "convert",
    "deck_pptx",
    "measure",
    "measure_deck",
    "measure_script",
]
