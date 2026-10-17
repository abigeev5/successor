"""Screen recordings (SPEC 7.6): upload → worker → steps, blurred screenshots, procedure draft."""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import jobs
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.storage import Asset, AssetKind
from app.modules.analytics.models import ProductEvent
from app.modules.identity.models import UserRole
from app.modules.recordings.models import TranscriptSegment
from app.providers.asr.base import Segment, Transcript
from app.providers.llm.fake import FakeRule
from app.providers.ocr.base import OcrBox
from tests.factories import give_consent, login, make_handover, make_org_unit, make_process, make_user

SEGMENT_PROMPT = "Перед тобой расшифровка записи экрана"
STEPS = {
    "steps": [
        {
            "idx": 2,
            "title": "Оформить направление",
            "action": "Нажать «Оформить» и распечатать",
            "rationale": None,
            "start_ms": 5_000,
            "end_ms": 11_000,
        },
        {
            "idx": 1,
            "title": "Найти студента",
            "action": "Ввести фамилию в поиске",
            "rationale": "так быстрее, чем по номеру",
            "start_ms": 0,
            "end_ms": 6_000,
        },
        {"idx": 3, "title": "За концом записи", "action": "", "start_ms": 30_000, "end_ms": 40_000},
    ]
}


def _ffmpeg(args: list[str], out: Path) -> bytes:
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args, str(out)], check=True)
    return out.read_bytes()


@pytest.fixture(scope="module")
def videos(tmp_path_factory: pytest.TempPathFactory) -> dict[str, bytes]:
    if shutil.which("ffmpeg") is None:
        if os.environ.get("REQUIRE_DB") == "1":
            pytest.fail("ffmpeg не установлен")
        pytest.skip("ffmpeg не установлен")
    d = tmp_path_factory.mktemp("video")
    src = ["-f", "lavfi", "-i", "testsrc=size=320x240:rate=5"]
    return {
        "voice": _ffmpeg(
            [
                *src,
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440",
                "-t",
                "12",
                "-c:v",
                "libvpx",
                "-b:v",
                "200k",
                "-c:a",
                "libopus",
            ],
            d / "voice.webm",
        ),
        "silent": _ffmpeg([*src, "-t", "3", "-c:v", "libvpx"], d / "silent.webm"),
    }


class StubASR:
    name = "stub"

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def transcribe(self, audio_path: Path, language: str = "ru") -> Transcript:
        if self.fail:
            raise RuntimeError("model is not downloaded")
        return Transcript(
            [
                Segment(0, 5_500, "Сначала ищу студента по фамилии, так быстрее."),
                Segment(5_500, 11_500, "Потом нажимаю оформить и печатаю направление."),
            ],
            duration_ms=12_000,
        )


class PhoneOCR:
    """Every frame «shows» a phone number in its top-left corner."""

    name = "stub"

    def read(self, image_path: Path) -> list[OcrBox]:
        return [
            OcrBox("Телефон:", 5, 5, 60, 14, line="1"),
            OcrBox("+7 912 345-67-89", 70, 5, 120, 14, line="1"),
        ]

    async def health(self) -> bool:
        return True


@pytest.fixture
async def world(db: AsyncSession, app: FastAPI) -> dict[str, Any]:
    unit = await make_org_unit(db)
    manager = await make_user(db, UserRole.MANAGER, org_unit=unit)
    expert = await make_user(db, UserRole.EXPERT, org_unit=unit)
    successor = await make_user(db, UserRole.SUCCESSOR, org_unit=unit)
    stranger = await make_user(db, UserRole.EXPERT, org_unit=unit)
    process = await make_process(db, unit, "Оформление пересдач")
    handover = await make_handover(
        db, org_unit=unit, manager=manager, expert=expert, successor=successor, processes=[process]
    )
    await db.commit()
    app.state.providers.asr = StubASR()
    app.state.providers.ocr = PhoneOCR()
    app.state.providers.llm.rules = [FakeRule.from_dict({"match": SEGMENT_PROMPT, "response_json": STEPS})]
    return locals()


async def upload(
    client: httpx.AsyncClient, world: dict[str, Any], data: bytes, **form: str
) -> httpx.Response:
    fields = {"handover_id": str(world["handover"].id), "title": "Направление на пересдачу", **form}
    return await client.post(
        "/api/recordings", data=fields, files={"video": ("rec.webm", data, "video/webm")}
    )


async def run_job(app: FastAPI) -> None:
    assert await jobs.run_one(get_sessionmaker(), get_settings(), app.state.providers)


async def test_upload_needs_consent_and_a_video(
    client: httpx.AsyncClient, db: AsyncSession, world: dict[str, Any], videos: dict[str, bytes]
) -> None:
    await login(client, world["expert"])
    assert (await upload(client, world, videos["voice"])).status_code == 403  # no consent yet
    await give_consent(db, world["expert"], world["handover"])
    await db.commit()
    png = (Path(__file__).parents[1] / "fixtures" / "pii" / "student_card.png").read_bytes()
    assert (await upload(client, world, png)).status_code == 415
    assert (await upload(client, world, videos["voice"], title="  ")).status_code == 400
    other = await make_process(db, world["unit"], "Чужой процесс")
    await db.commit()
    assert (await upload(client, world, videos["voice"], process_id=str(other.id))).status_code == 400
    created = await upload(client, world, videos["voice"], process_id=str(world["process"].id))
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "uploaded"

    await login(client, world["successor"])
    assert (await upload(client, world, videos["voice"])).status_code == 403


async def test_processing_makes_steps_blurred_screenshots_and_a_procedure_draft(
    client: httpx.AsyncClient, db: AsyncSession, app: FastAPI, world: dict[str, Any], videos: dict[str, bytes]
) -> None:
    await give_consent(db, world["expert"], world["handover"])
    await db.commit()
    await login(client, world["expert"])
    rid = (await upload(client, world, videos["voice"], process_id=str(world["process"].id))).json()["id"]
    await run_job(app)

    rec = (await client.get(f"/api/recordings/{rid}")).json()
    assert rec["status"] == "ready" and rec["error"] is None and rec["duration_ms"] == 12_000
    # LLM steps came unordered, overlapping and partly out of the recording: fixed by code.
    assert [(s["idx"], s["title"], s["start_ms"], s["end_ms"]) for s in rec["steps"]] == [
        (1, "Найти студента", 0, 6_000),
        (2, "Оформить направление", 6_000, 11_000),
    ]
    assert all(s["screenshot_asset_id"] and s["screenshot_blurred"] for s in rec["steps"])
    segments = (await db.execute(select(TranscriptSegment))).scalars().all()
    assert len(segments) == 2

    card = (await client.get(f"/api/cards/{rec['card_id']}")).json()
    assert (card["type"], card["status"], card["origin"], card["title"]) == (
        "procedure",
        "draft",
        "recording",
        "Направление на пересдачу",
    )
    assert card["process_id"] == str(world["process"].id)
    shot = rec["steps"][0]["screenshot_asset_id"]
    assert f"![Шаг 1](/api/assets/{shot})" in card["body_md"]
    assert "_Почему так:_ так быстрее, чем по номеру" in card["body_md"]
    first = card["sources"][0]
    assert first["label"] == "Запись «Направление на пересдачу», шаг 1 · 00:00–00:06"
    assert first["link"]["video_asset_id"] == rec["video_asset_id"] and first["start_ms"] == 0

    image = await client.get(f"/api/assets/{shot}")
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"
    names = set((await db.execute(select(ProductEvent.name))).scalars())
    assert {"recording_uploaded", "recording_processed"} <= names


async def test_video_streams_with_range_and_access_rules(
    client: httpx.AsyncClient, db: AsyncSession, app: FastAPI, world: dict[str, Any], videos: dict[str, bytes]
) -> None:
    await give_consent(db, world["expert"], world["handover"])
    await db.commit()
    await login(client, world["expert"])
    video_id = (await upload(client, world, videos["voice"])).json()["video_asset_id"]
    part = await client.get(f"/api/assets/{video_id}", headers={"Range": "bytes=0-99"})
    assert part.status_code == 206 and len(part.content) == 100
    assert part.headers["content-range"].startswith("bytes 0-99/")

    audio = Asset(
        kind=AssetKind.AUDIO,
        storage_path="x/voice.webm",
        mime="audio/webm",
        size_bytes=1,
        sha256="0",
        owner_id=world["expert"].id,
        handover_id=world["handover"].id,
    )
    db.add(audio)
    await db.commit()

    await login(client, world["successor"])  # the video of their handover — yes; raw interview audio — no
    assert (await client.get(f"/api/assets/{video_id}")).status_code == 200
    assert (await client.get(f"/api/assets/{audio.id}")).status_code == 404
    assert (
        await client.get("/api/recordings", params={"handover_id": str(world["handover"].id)})
    ).status_code == 403

    await login(client, world["stranger"])
    assert (await client.get(f"/api/assets/{video_id}")).status_code == 403


async def test_failures_are_explained_and_can_be_retried(
    client: httpx.AsyncClient, db: AsyncSession, app: FastAPI, world: dict[str, Any], videos: dict[str, bytes]
) -> None:
    await give_consent(db, world["expert"], world["handover"])
    await db.commit()
    await login(client, world["expert"])
    silent = (await upload(client, world, videos["silent"])).json()["id"]
    await run_job(app)
    failed = (await client.get(f"/api/recordings/{silent}")).json()
    assert failed["status"] == "failed" and "нет звука" in failed["error"]

    app.state.providers.asr = StubASR(fail=True)
    rid = (await upload(client, world, videos["voice"])).json()["id"]
    await run_job(app)
    assert "распознать речь" in (await client.get(f"/api/recordings/{rid}")).json()["error"]

    app.state.providers.asr = StubASR()
    retried = await client.post(f"/api/recordings/{rid}/retry")
    assert retried.json()["status"] == "uploaded" and retried.json()["error"] is None
    assert (await client.post(f"/api/recordings/{rid}/retry")).status_code == 409
    await run_job(app)
    assert (await client.get(f"/api/recordings/{rid}")).json()["status"] == "ready"
    listed = (await client.get("/api/recordings", params={"handover_id": str(world["handover"].id)})).json()
    assert {r["id"]: r["status"] for r in listed} == {silent: "failed", rid: "ready"}
