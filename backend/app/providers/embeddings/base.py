from typing import Protocol


class EmbeddingsProvider(Protocol):
    name: str
    model: str
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]:
        """L2-normalized vectors, one per text."""
        ...

    async def health(self) -> bool: ...
