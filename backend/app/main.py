import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.core.config import Settings, get_settings
from app.core.db import dispose_engine
from app.core.errors import install_error_handlers
from app.core.health import router as system_router
from app.core.http import check_offline_config
from app.core.logging import setup_logging
from app.modules.handovers.router import router as handovers_router
from app.modules.identity.router import admin_router as users_admin_router
from app.modules.identity.router import auth_router, users_router
from app.modules.interview.router import router as interviews_router
from app.modules.knowledge.router import router as cards_router
from app.modules.org.router import admin_router as org_admin_router
from app.modules.org.router import processes_router
from app.modules.privacy.router import router as consents_router
from app.providers.registry import build_providers
from app.wiring import wire

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging()
    bad_urls = check_offline_config(settings)
    if bad_urls:
        raise RuntimeError(f"OFFLINE_MODE=true, но указаны нелокальные адреса моделей: {', '.join(bad_urls)}")
    if settings.jwt_secret == "change-me":
        log.warning("JWT_SECRET не задан (значение по умолчанию). Допустимо только для демо-стенда.")
    wire()

    app = FastAPI(title="Преемник API", version=__version__, lifespan=lifespan)
    # Built eagerly (not in lifespan) so a bad provider config fails at startup and tests get providers.
    app.state.providers = build_providers(settings)
    install_error_handlers(app)
    routers = (
        system_router,
        auth_router,
        users_router,
        users_admin_router,
        org_admin_router,
        processes_router,
        handovers_router,
        consents_router,
        interviews_router,
        cards_router,
    )
    for router in routers:
        app.include_router(router, prefix="/api")
    return app


app = create_app()
