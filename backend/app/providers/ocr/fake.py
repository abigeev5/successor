"""FakeOCR: boxes from `<image name>.ocr.json` next to the image ([] if there is no such file)."""

import json
from dataclasses import dataclass
from pathlib import Path

from app.providers.ocr.base import OcrBox


@dataclass
class FakeOCR:
    name: str = "fake"

    def read(self, image_path: Path) -> list[OcrBox]:
        path = image_path.with_suffix(".ocr.json")
        if not path.is_file():
            return []
        return [OcrBox(**box) for box in json.loads(path.read_text(encoding="utf-8"))]

    async def health(self) -> bool:
        return True
