from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class OcrBox:
    text: str
    x: int
    y: int
    width: int
    height: int
    confidence: float = 1.0


class OCRProvider(Protocol):
    name: str

    def read(self, image_path: Path) -> list[OcrBox]: ...

    async def health(self) -> bool: ...
