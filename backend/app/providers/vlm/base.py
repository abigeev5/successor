from pathlib import Path
from typing import Protocol


class VLMProvider(Protocol):
    name: str

    async def describe(self, image_path: Path, prompt: str) -> str: ...

    async def health(self) -> bool: ...
