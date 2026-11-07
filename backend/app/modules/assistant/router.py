import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.modules.assistant import service
from app.modules.assistant.schemas import AnswerOut, AskIn, FeedbackIn
from app.modules.identity.deps import current_user
from app.modules.identity.models import User
from app.providers.registry import Providers

router = APIRouter(prefix="/assistant", tags=["assistant"])


def providers(request: Request) -> Providers:
    return request.app.state.providers  # type: ignore[no-any-return]


@router.post("/ask", response_model=AnswerOut)
async def ask(
    data: AskIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    p: Providers = Depends(providers),
) -> AnswerOut:
    """The full answer after the groundedness check (no streaming)."""
    return await service.ask(db, p, settings, user, data.handover_id, data.question)


@router.post("/{qa_id}/feedback", response_model=AnswerOut)
async def feedback(
    qa_id: uuid.UUID, data: FeedbackIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> AnswerOut:
    return await service.feedback(db, user, qa_id, data.helpful, data.comment)


@router.get("/history", response_model=list[AnswerOut])
async def history(
    handover_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> list[AnswerOut]:
    return await service.history(db, user, handover_id)
