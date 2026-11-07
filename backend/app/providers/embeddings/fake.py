"""Deterministic embeddings: same text → same vector; shared words → closer vectors.

Hashing trick: every word goes to a bucket with a sign; the vector is then L2-normalized.
"""

import hashlib
import math
import re
from dataclasses import dataclass

_WORD = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return _WORD.findall(text.lower().replace("ё", "е"))


@dataclass
class FakeEmbeddings:
    dim: int = 1024
    name: str = "fake"
    model: str = "fake-hash"

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in tokenize(text):
            digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
            value = int.from_bytes(digest, "big")
            vec[value % self.dim] += 1.0 if (value >> 63) & 1 else -1.0
        norm = math.sqrt(sum(x * x for x in vec))
        return [x / norm for x in vec] if norm else vec

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    async def health(self) -> bool:
        return True
