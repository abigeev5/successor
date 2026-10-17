from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.storage import Asset
from app.modules.identity.models import UserRole
from app.modules.interview.models import InterviewMessage
from app.providers.asr.base import Segment, Transcript
from tests.factories import give_consent, login, make_handover, make_org_unit, make_user

# Minimal audio-only webm: EBML magic + an Opus track id.
WEBM_AUDIO = b"\x1a\x45\xdf\xa3" + b"\x00" * 32 + b"A_OPUS" + b"\x00" * 200


class StubASR:
    name = "stub"

    def __init__(self, duration_ms: int) -> None:
        self.duration_ms = duration_ms
        self.paths: list[Path] = []

    def transcribe(self, audio_path: Path, language: str = "ru") -> Transcript:
        self.paths.append(audio_path)
        return Transcript([Segment(0, 1000, "Сначала открываю портал")], duration_ms=self.duration_ms)


@pytest.fixture
async def session_id(client: httpx.AsyncClient, db: AsyncSession) -> str:
    unit = await make_org_unit(db)
    manager = await make_user(db, UserRole.MANAGER, org_unit=unit)
    expert = await make_user(db, UserRole.EXPERT, org_unit=unit)
    handover = await make_handover(db, org_unit=unit, manager=manager, expert=expert)
    await give_consent(db, expert, handover)
    await db.commit()
    await login(client, expert)
    return (await client.post("/api/interviews", json={"handover_id": str(handover.id)})).json()["id"]  # type: ignore[no-any-return]


async def upload(client: httpx.AsyncClient, sid: str, data: bytes) -> httpx.Response:
    return await client.post(
        f"/api/interviews/{sid}/audio", files={"file": ("voice.webm", data, "audio/webm")}
    )


async def test_voice_answer_is_recognized_and_linked(
    app: FastAPI, client: httpx.AsyncClient, db: AsyncSession, session_id: str
) -> None:
    asr = StubASR(duration_ms=3000)
    app.state.providers.asr = asr
    response = await upload(client, session_id, WEBM_AUDIO)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    assert body["text"] == "Сначала открываю портал" and body["duration_ms"] == 3000

    asset = await db.get(Asset, body["asset_id"])
    assert asset is not None and asset.mime == "audio/webm" and asset.duration_ms == 3000
    stored = get_settings().storage_dir / asset.storage_path
    assert stored.read_bytes() == WEBM_AUDIO and asr.paths == [stored]

    sent = await client.post(
        f"/api/interviews/{session_id}/messages",
        json={"text": "Сначала открываю портал.", "audio_asset_id": body["asset_id"]},
    )
    assert any(m["has_audio"] for m in sent.json()["messages"])
    message = (
        await db.execute(select(InterviewMessage).where(InterviewMessage.audio_asset_id.is_not(None)))
    ).scalar_one()
    assert message.content == "Сначала открываю портал."


async def test_too_long_voice_is_rejected_and_deleted(
    app: FastAPI, client: httpx.AsyncClient, db: AsyncSession, session_id: str
) -> None:
    app.state.providers.asr = StubASR(duration_ms=150_000)
    response = await upload(client, session_id, WEBM_AUDIO)
    assert response.status_code == 413
    assert response.json()["code"] == "audio_too_long"
    assert (await db.execute(select(Asset))).first() is None
    assert not any(get_settings().storage_dir.rglob("*.webm"))


async def test_not_audio_is_rejected(app: FastAPI, client: httpx.AsyncClient, session_id: str) -> None:
    app.state.providers.asr = StubASR(duration_ms=1000)
    response = await upload(client, session_id, b"%PDF-1.7 not audio")
    assert response.status_code == 415
    assert response.json()["detail"] == "Формат файла не поддерживается"
