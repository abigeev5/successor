"""File storage for media (audio, video, images) under STORAGE_DIR.

Files never get public URLs; paths are generated here (never taken from the client), so there is
no path traversal. The type is detected from the first bytes (D-037).
"""

import hashlib
import uuid
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import Settings
from app.core.db import Base, Timestamps, UUIDPk, str_enum
from app.core.errors import AppError


class AssetKind(StrEnum):
    AUDIO = "audio"
    VIDEO = "video"
    IMAGE = "image"


class Asset(UUIDPk, Timestamps, Base):
    __tablename__ = "assets"

    kind: Mapped[AssetKind] = mapped_column(str_enum(AssetKind, "asset_kind"))
    storage_path: Mapped[str] = mapped_column(String(500))  # relative to STORAGE_DIR
    mime: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64))
    duration_ms: Mapped[int | None]
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    handover_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("handovers.id", ondelete="CASCADE"), index=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UnsupportedMedia(AppError):
    status_code = 415
    code = "unsupported_media"
    detail = "Формат файла не поддерживается"


class FileTooLarge(AppError):
    status_code = 413
    code = "file_too_large"
    detail = "Файл слишком большой"


# (mime, extension, kind) by signature.
def sniff_media(head: bytes) -> tuple[str, str, AssetKind] | None:
    if head.startswith(b"\x1a\x45\xdf\xa3"):  # EBML: webm / matroska; video tracks have V_VP8/V_VP9/V_AV1
        if b"V_VP" in head or b"V_AV1" in head or b"V_MPEG4" in head:
            return "video/webm", "webm", AssetKind.VIDEO
        return "audio/webm", "webm", AssetKind.AUDIO
    if head.startswith(b"OggS"):
        return "audio/ogg", "ogg", AssetKind.AUDIO
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "audio/wav", "wav", AssetKind.AUDIO
    if head.startswith(b"ID3") or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio/mpeg", "mp3", AssetKind.AUDIO
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand.startswith(b"M4A"):
            return "audio/mp4", "m4a", AssetKind.AUDIO
        if brand == b"qt  ":
            return "video/quicktime", "mov", AssetKind.VIDEO
        return "video/mp4", "mp4", AssetKind.VIDEO
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png", AssetKind.IMAGE
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg", AssetKind.IMAGE
    return None


def absolute_path(settings: Settings, asset: Asset) -> Path:
    return settings.storage_dir / asset.storage_path


def _target(settings: Settings, asset_id: uuid.UUID, handover_id: uuid.UUID | None, ext: str) -> Path:
    relative = Path(str(handover_id or "common")) / f"{asset_id}.{ext}"
    (settings.storage_dir / relative).parent.mkdir(parents=True, exist_ok=True)
    return relative


def store_stream(
    settings: Settings,
    source: BinaryIO,
    *,
    expected_kind: AssetKind,
    max_bytes: int,
    owner_id: uuid.UUID | None,
    handover_id: uuid.UUID | None,
) -> Asset:
    """Copies a large file (a video up to 1 GB) in chunks and returns an Asset NOT added to a session.

    Blocking: run it in a thread and add the asset to the session in the event loop.
    """
    head = source.read(4096)
    sniffed = sniff_media(head)
    if sniffed is None or sniffed[2] != expected_kind:
        raise UnsupportedMedia()
    mime, ext, _ = sniffed
    asset_id = uuid.uuid4()
    relative = _target(settings, asset_id, handover_id, ext)
    target = settings.storage_dir / relative
    digest = hashlib.sha256(head)
    size = len(head)
    try:
        with target.open("wb") as out:
            out.write(head)
            while chunk := source.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise FileTooLarge(f"Файл больше {max_bytes // (1024 * 1024)} МБ")
                digest.update(chunk)
                out.write(chunk)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return Asset(
        id=asset_id,
        kind=expected_kind,
        storage_path=str(relative),
        mime=mime,
        size_bytes=size,
        sha256=digest.hexdigest(),
        owner_id=owner_id,
        handover_id=handover_id,
    )


async def save_bytes(
    db: AsyncSession,
    settings: Settings,
    data: bytes,
    *,
    expected_kind: AssetKind,
    max_bytes: int,
    owner_id: uuid.UUID | None,
    handover_id: uuid.UUID | None,
) -> Asset:
    """Validates and stores a file; adds an Asset to the session (no commit)."""
    if len(data) > max_bytes:
        raise FileTooLarge(f"Файл больше {max_bytes // (1024 * 1024)} МБ")
    sniffed = sniff_media(data[:4096])
    if sniffed is None or sniffed[2] != expected_kind:
        raise UnsupportedMedia()
    mime, ext, _ = sniffed
    asset_id = uuid.uuid4()
    relative = _target(settings, asset_id, handover_id, ext)
    (settings.storage_dir / relative).write_bytes(data)
    asset = Asset(
        id=asset_id,
        kind=expected_kind,
        storage_path=str(relative),
        mime=mime,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        owner_id=owner_id,
        handover_id=handover_id,
    )
    db.add(asset)
    return asset
