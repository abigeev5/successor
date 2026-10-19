"""Registry of SourceResolver: modules that own sources tell knowledge how to show them.

knowledge is below interview/recordings/gaps, so it cannot import them; they register here instead.
"""

import uuid
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.knowledge.domain.sources import SourceType


@dataclass(frozen=True)
class ResolvedSource:
    label: str  # «Реплика 12 · интервью 17.10»
    context: str | None  # full text around the quote; hidden from successors
    link: dict[str, str] | None = None  # where the UI can open it, e.g. {"session_id": "..."}


class SourceResolver(Protocol):
    source_type: SourceType

    async def resolve(self, db: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, ResolvedSource]: ...


_resolvers: dict[SourceType, SourceResolver] = {}


def register(resolver: SourceResolver) -> None:
    _resolvers[resolver.source_type] = resolver


def get(source_type: SourceType) -> SourceResolver | None:
    return _resolvers.get(source_type)


def clear() -> None:
    _resolvers.clear()
