import csv
import io
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.modules.analytics import service
from app.modules.analytics.domain.metrics import csv_rows
from app.modules.analytics.schemas import AuditEntryOut, HandoverProgressOut, MetricsOut, RiskMapOut
from app.modules.identity.deps import current_user, require_roles
from app.modules.identity.models import User, UserRole

router = APIRouter(tags=["dashboard"])
MANAGERS = require_roles(UserRole.MANAGER, UserRole.ADMIN)


@router.get("/dashboard/risk", response_model=RiskMapOut)
async def risk(
    org_unit_id: uuid.UUID | None = None,
    user: User = Depends(MANAGERS),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RiskMapOut:
    return await service.risk_map(db, settings, user, org_unit_id)


@router.get("/handovers/{handover_id}/progress", response_model=HandoverProgressOut)
async def progress(
    handover_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HandoverProgressOut:
    return await service.progress(db, settings, user, handover_id)


async def _metrics(
    handover_id: uuid.UUID | None = None,
    org_unit_id: uuid.UUID | None = None,
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    user: User = Depends(MANAGERS),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MetricsOut:
    return await service.metrics(
        db,
        settings,
        user,
        handover_id=handover_id,
        org_unit_id=org_unit_id,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/dashboard/metrics", response_model=MetricsOut)
async def metrics(data: MetricsOut = Depends(_metrics)) -> MetricsOut:
    return data


@router.get("/dashboard/metrics.csv", response_class=Response)
async def metrics_csv(data: MetricsOut = Depends(_metrics)) -> Response:
    """For the financial model and the jury report: «Показатель;Значение», UTF-8 with BOM for Excel."""
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";")
    writer.writerow(["Показатель", "Значение"])
    period = f"{data.date_from or '…'} — {data.date_to or '…'}"
    writer.writerow(["Период", period])
    writer.writerows(csv_rows(data.model_dump()))
    return Response(
        content="﻿" + out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="metrics.csv"'},
    )


@router.get("/audit", response_model=list[AuditEntryOut])
async def audit_log(
    entity: str | None = None,
    entity_id: uuid.UUID | None = None,
    limit: int = Query(100, ge=1, le=500),
    user: User = Depends(MANAGERS),
    db: AsyncSession = Depends(get_db),
) -> list[AuditEntryOut]:
    return await service.audit_log(db, user, entity=entity, entity_id=entity_id, limit=limit)
