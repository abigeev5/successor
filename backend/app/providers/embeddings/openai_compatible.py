"""Embeddings over an OpenAI-compatible API: `llama-server --embeddings` with a bge-m3 GGUF (D-035).

POST {base_url}/embeddings. Synchronous by design (EmbeddingsProvider), call it via asyncio.to_thread.
"""

import asyncio
import math

import httpx

from app.core.config import Settings
from app.core.http import make_sync_http_client


class EmbeddingsError(Exception):
    pass


def l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector))
    return [x / norm for x in vector] if norm else vector


class OpenAICompatibleEmbeddings:
    name = "openai_compatible"

    def __init__(self, settings: Settings, *, client: httpx.Client | None = None) -> None:
        if not settings.embeddings_base_url:
            raise ValueError("EMBEDDINGS_BASE_URL не задан")
        self.model = settings.embeddings_model
        self.dim = settings.embeddings_dim
        self._base = settings.embeddings_base_url.rstrip("/")
        key = settings.embeddings_api_key
        self._client = client or make_sync_http_client(
            settings, headers={"Authorization": f"Bearer {key}"} if key else {}
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = self._client.post(
                f"{self._base}/embeddings", json={"model": self.model, "input": texts}
            )
            response.raise_for_status()
            items = sorted(response.json()["data"], key=lambda item: item["index"])
            vectors = [l2_normalize([float(x) for x in item["embedding"]]) for item in items]
        except httpx.HTTPError as exc:
            raise EmbeddingsError(f"Сервер эмбеддингов недоступен: {type(exc).__name__}") from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise EmbeddingsError("Неожиданный формат ответа сервера эмбеддингов") from exc
        if len(vectors) != len(texts) or any(len(v) != self.dim for v in vectors):
            raise EmbeddingsError(f"Ожидалось {len(texts)} векторов размерности {self.dim} (EMBEDDINGS_DIM)")
        return vectors

    async def health(self) -> bool:
        try:
            response = await asyncio.to_thread(self._client.get, f"{self._base}/models", timeout=5)
            return response.status_code == 200
        except httpx.HTTPError:
            return False
