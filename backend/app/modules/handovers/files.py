"""`GET /assets/{id}`: files of a handover (video, screenshots, voice) with access checks and Range.

Files have no public URLs (SPEC 12). Successors see recording videos and screenshots of their
handover, but not raw interview audio (SPEC 7.1, D-061).
"""

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.errors import NotFound
from app.core.storage import Asset, AssetKind, absolute_path
from app.modules import audit
from app.modules.handovers.access import HandoverRole, ensure_handover_access
from app.modules.identity.deps import current_user
from app.modules.identity.models import User

router = APIRouter(prefix="/assets", tags=["assets"])
NOT_FOUND = "Файл не найден"
VIEW_AUDIT_WINDOW = timedelta(minutes=30)  # a player sends many Range requests for one viewing


@router.get("/{asset_id}", response_class=FileResponse)
async def get_asset(
    asset_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    asset = await db.get(Asset, asset_id)
    if asset is None or asset.deleted_at is not None or asset.handover_id is None:
        raise NotFound(NOT_FOUND, code="asset_not_found")
    access = await ensure_handover_access(db, user, asset.handover_id, list(HandoverRole))
    if access.role is HandoverRole.SUCCESSOR and asset.kind is AssetKind.AUDIO:
        raise NotFound(NOT_FOUND, code="asset_not_found")
    path = absolute_path(settings, asset)
    if not path.is_file():
        raise NotFound(NOT_FOUND, code="asset_not_found")
    if asset.kind is AssetKind.VIDEO:  # «просмотр записи экрана» is audited (SPEC 12)
        logged = await audit.record_once(
            db,
            action="recording.viewed",
            entity="asset",
            entity_id=asset.id,
            user_id=user.id,
            within=VIEW_AUDIT_WINDOW,
            meta={"handover_id": str(asset.handover_id)},
        )
        if logged:
            await db.commit()
    # Starlette answers Range requests (206) itself, so video seeks to a step without full download.
    return FileResponse(path, media_type=asset.mime, headers={"Cache-Control": "private, max-age=3600"})
