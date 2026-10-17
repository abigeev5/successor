"""Deleting an employee's data (SPEC 7.3; docs/architecture.md, 5.2 and 6.6).

privacy does not know what other modules store: each module that keeps an employee's data registers
a DataEraser. Erasers delete their rows and files and report which knowledge sources are gone;
privacy publishes `SourcesErased`, and knowledge archives the cards left without sources.
"""

import uuid
from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.events import Event, bus
from app.core.storage import Asset, erase_file


@dataclass(frozen=True)
class ErasedSource:
    """A knowledge source that no longer exists. `source_type` is a knowledge SourceType value."""

    source_type: str
    source_id: uuid.UUID


@dataclass(frozen=True)
class SourcesErased(Event):
    handover_id: uuid.UUID
    user_id: uuid.UUID | None
    sources: tuple[ErasedSource, ...]


@dataclass
class Erased:
    """What an eraser removed: counts by kind (e.g. {"recordings": 1}), sources and files."""

    counts: dict[str, int] = field(default_factory=dict)
    sources: list[ErasedSource] = field(default_factory=list)
    files: int = 0


class DataEraser(Protocol):
    async def describe(
        self, db: AsyncSession, *, user_id: uuid.UUID, handover_id: uuid.UUID
    ) -> dict[str, int]:
        """What is stored now: counts by kind, the same keys as in `Erased.counts`."""
        ...

    async def erase(
        self, db: AsyncSession, settings: Settings, *, user_id: uuid.UUID, handover_id: uuid.UUID
    ) -> Erased: ...


_erasers: list[DataEraser] = []


def register(eraser: DataEraser) -> None:
    _erasers.append(eraser)


def clear() -> None:
    _erasers.clear()


async def sources_erased(
    db: AsyncSession, *, handover_id: uuid.UUID, user_id: uuid.UUID | None, sources: list[ErasedSource]
) -> None:
    """Tells knowledge which sources are gone (also used when one recording is deleted)."""
    if sources:
        await bus.publish(db, SourcesErased(handover_id=handover_id, user_id=user_id, sources=tuple(sources)))


async def _own_files(db: AsyncSession, user_id: uuid.UUID, handover_id: uuid.UUID) -> list[Asset]:
    stmt = select(Asset).where(
        Asset.owner_id == user_id, Asset.handover_id == handover_id, Asset.deleted_at.is_(None)
    )
    return list((await db.execute(stmt)).scalars())


async def describe(db: AsyncSession, *, user_id: uuid.UUID, handover_id: uuid.UUID) -> dict[str, int]:
    counts: dict[str, int] = {}
    for eraser in _erasers:
        counts.update(await eraser.describe(db, user_id=user_id, handover_id=handover_id))
    files = await _own_files(db, user_id, handover_id)
    counts["files"] = len(files)
    counts["files_bytes"] = sum(f.size_bytes for f in files)
    return counts


async def erase(
    db: AsyncSession, settings: Settings, *, user_id: uuid.UUID, handover_id: uuid.UUID
) -> Erased:
    """Runs every eraser, then removes the rest of the user's files in the handover. No commit."""
    total = Erased()
    for eraser in _erasers:
        part = await eraser.erase(db, settings, user_id=user_id, handover_id=handover_id)
        total.counts.update(part.counts)
        total.sources.extend(part.sources)
        total.files += part.files
    for asset in await _own_files(db, user_id, handover_id):  # e.g. a voice answer that was never sent
        if erase_file(settings, asset):
            total.files += 1
    await sources_erased(db, handover_id=handover_id, user_id=user_id, sources=total.sources)
    return total
