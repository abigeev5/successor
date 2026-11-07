from dataclasses import dataclass
from pathlib import Path


@dataclass
class FakeVLM:
    name: str = "fake"
    description: str = "Описание экрана (заглушка FakeVLM)"

    async def describe(self, image_path: Path, prompt: str) -> str:
        return self.description

    async def health(self) -> bool:
        return True
