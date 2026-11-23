"""Pictures: the fallback for what PowerPoint cannot express, placed behind native text."""

import io

from pptx.shapes.shapetree import SlideShapes

from nativedeck.model import PictureItem
from nativedeck.writer.units import place


def add_picture(shapes: SlideShapes, item: PictureItem) -> None:
    """Add a picture of one part of the slide where it was measured."""
    shapes.add_picture(io.BytesIO(item.png), *place(item.box))
