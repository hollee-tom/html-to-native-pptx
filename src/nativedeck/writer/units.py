"""Units: PowerPoint counts in EMU and points, the page in CSS pixels."""

from pptx.util import Emu

from nativedeck.model import Box

EMU_PER_PIXEL = 9525
"""A CSS pixel is 9525 EMU at 96 dpi."""
POINTS_PER_PIXEL = 0.75
"""A CSS pixel is three quarters of a point."""


def emu(pixels: float) -> Emu:
    """A length in pixels as PowerPoint's unit."""
    return Emu(round(pixels * EMU_PER_PIXEL))


def place(box: Box) -> tuple[Emu, Emu, Emu, Emu]:
    """A box's left, top, width and height in PowerPoint's unit, never narrower than one pixel."""
    return emu(box.x), emu(box.y), emu(max(box.width, 1)), emu(max(box.height, 1))
