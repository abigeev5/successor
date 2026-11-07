"""System endpoints: /api/health (availability of db and models) and /api/meta (stand info for the UI)."""

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.core.config import Settings, get_settings
from app.core.db import get_db

router = APIRouter(tags=["system"])


class ComponentHealth(BaseModel):
    ok: bool
    provider: str | None = None
    detail: str | None = None


class HealthOut(BaseModel):
    status: str  # "ok" | "degraded"
    components: dict[str, ComponentHealth]


class MetaOut(BaseModel):
    demo_mode: bool
    offline_mode: bool
    version: str


async def _provider_health(provider: Any) -> ComponentHealth:
    try:
        return ComponentHealth(ok=await provider.health(), provider=provider.name)
    except Exception as exc:
        return ComponentHealth(ok=False, provider=getattr(provider, "name", None), detail=type(exc).__name__)


@router.get("/health", response_model=HealthOut)
async def health(request: Request, db: AsyncSession = Depends(get_db)) -> HealthOut:
    components: dict[str, ComponentHealth] = {}
    try:
        await db.execute(text("SELECT 1"))
        components["db"] = ComponentHealth(ok=True)
    except Exception as exc:
        components["db"] = ComponentHealth(ok=False, detail=type(exc).__name__)

    providers = request.app.state.providers
    for name in ("llm", "embeddings", "asr", "ocr", "vlm"):
        provider = getattr(providers, name)
        if provider is not None:
            components[name] = await _provider_health(provider)

    status = "ok" if all(c.ok for c in components.values()) else "degraded"
    return HealthOut(status=status, components=components)


@router.get("/meta", response_model=MetaOut)
async def meta(settings: Settings = Depends(get_settings)) -> MetaOut:
    return MetaOut(demo_mode=settings.demo_mode, offline_mode=settings.offline_mode, version=__version__)
