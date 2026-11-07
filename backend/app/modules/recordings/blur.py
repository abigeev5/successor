"""Gaussian blur of rectangles on an image, in place (4 px margin, no original kept)."""

from pathlib import Path

import cv2

MARGIN_PX = 4


def blur_regions(image: Path, rects: list[tuple[int, int, int, int]], margin: int = MARGIN_PX) -> None:
    img = cv2.imread(str(image))
    if img is None:
        raise ValueError(f"Не удалось открыть изображение {image.name}")
    height, width = img.shape[:2]
    for x, y, w, h in rects:
        x0, y0 = max(0, x - margin), max(0, y - margin)
        x1, y1 = min(width, x + w + margin), min(height, y + h + margin)
        if x1 <= x0 or y1 <= y0:
            continue
        kernel = max(31, (y1 - y0) // 2 * 2 + 1)  # odd, at least as tall as the text
        roi = img[y0:y1, x0:x1]
        for _ in range(2):  # two passes: one leaves large text guessable
            roi = cv2.GaussianBlur(roi, (kernel, kernel), 0)
        img[y0:y1, x0:x1] = roi
    if not cv2.imwrite(str(image), img):
        raise ValueError(f"Не удалось сохранить изображение {image.name}")
