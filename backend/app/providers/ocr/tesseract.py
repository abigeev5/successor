"""OCR with the Tesseract CLI (`rus+eng`), word boxes from its TSV output.

No Python binding: the `tesseract` binary and its language data come from the OS package
(`tesseract-ocr`, `tesseract-ocr-rus`) and work offline.
"""

import csv
import io
import shutil
import subprocess
from pathlib import Path

from app.providers.ocr.base import OcrBox

TIMEOUT_S = 60


class OCRError(RuntimeError):
    pass


def parse_tsv(tsv: str) -> list[OcrBox]:
    """Word rows (level 5) with text; the line key keeps words of one text line together."""
    boxes = []
    for row in csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE):
        text = (row.get("text") or "").strip()
        if row.get("level") != "5" or not text:
            continue
        boxes.append(
            OcrBox(
                text=text,
                x=int(row["left"]),
                y=int(row["top"]),
                width=int(row["width"]),
                height=int(row["height"]),
                confidence=max(float(row["conf"]), 0.0) / 100,
                line=f"{row['page_num']}.{row['block_num']}.{row['par_num']}.{row['line_num']}",
            )
        )
    return boxes


class TesseractOCR:
    name = "tesseract"

    def __init__(self, languages: str = "rus+eng") -> None:
        self.languages = languages

    def read(self, image_path: Path) -> list[OcrBox]:
        try:
            result = subprocess.run(
                ["tesseract", str(image_path), "stdout", "-l", self.languages, "tsv"],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_S,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise OCRError(f"Tesseract не запустился: {exc}") from exc
        if result.returncode != 0:
            raise OCRError(f"Tesseract завершился с ошибкой: {result.stderr.strip()[:200]}")
        return parse_tsv(result.stdout)

    async def health(self) -> bool:
        return shutil.which("tesseract") is not None
