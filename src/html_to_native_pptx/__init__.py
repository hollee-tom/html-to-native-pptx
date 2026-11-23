"""High-fidelity HTML to native, editable PowerPoint."""

from html_to_native_pptx.convert import convert, measure
from html_to_native_pptx.errors import ConversionError
from html_to_native_pptx.model import MeasuredDeck
from html_to_native_pptx.writer import deck_pptx

__version__ = "0.1.0"
__all__ = ["MeasuredDeck", "ConversionError", "convert", "deck_pptx", "measure"]
