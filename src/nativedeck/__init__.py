"""High-fidelity HTML to native, editable PowerPoint."""

from nativedeck.convert import convert, measure
from nativedeck.errors import NativedeckError
from nativedeck.model import MeasuredDeck
from nativedeck.writer import deck_pptx

__version__ = "0.1.0"
__all__ = ["MeasuredDeck", "NativedeckError", "convert", "deck_pptx", "measure"]
