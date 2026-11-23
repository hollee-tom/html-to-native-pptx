"""Draws the synthetic corpus's pictures, so no photograph or third-party image is needed."""

import math
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

OUT = Path(__file__).parent / "images"


def landscape(width: int, height: int, seed: int) -> Image.Image:
    """Layered hills under a gradient sky with soft noise, a stand-in for a stock photograph."""
    rng = random.Random(seed)
    y = np.linspace(0, 1, height)[:, None]
    x = np.linspace(0, 1, width)[None, :]
    sky = np.stack(
        [60 + 150 * y + 0 * x, 90 + 110 * y + 0 * x, 170 + 60 * y + 0 * x], axis=-1
    )
    image = sky.copy()
    for layer in range(4):
        phase, amp = rng.uniform(0, 6), rng.uniform(0.05, 0.12)
        ridge = 0.45 + layer * 0.14 + amp * np.sin(x * rng.uniform(2, 5) * math.pi + phase)
        mask = (y > ridge)[..., None]
        shade = 70 - layer * 14
        colour = np.array([shade, shade + 40 - layer * 6, shade + 10])[None, None, :]
        image = np.where(mask, colour + 25 * np.sin(y * 20)[..., None], image)
    noise = np.random.default_rng(seed).normal(0, 6, image.shape)
    result = Image.fromarray(np.clip(image + noise, 0, 255).astype("uint8"))
    return result.filter(ImageFilter.GaussianBlur(1.2))


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    landscape(1280, 720, 1).save(OUT / "backdrop.jpg", quality=82)
    landscape(640, 400, 7).save(OUT / "card.jpg", quality=82)
