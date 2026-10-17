"""Manager dashboard (SPEC 7.9, 7.10) and the audit log (SPEC 12): risk changes after approval (M4)."""

from datetime import date, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import AssetKind
from app.modules.audit.models import AuditLog
from app.modules.identity.models import UserRole
from app.modules.interview.models import InterviewMessage, InterviewSession, MessageRole
from app.modules.knowledge.domain.sources import CardOrigin, SourceType
from app.modules.knowledge.models import CardSource, CardStatus, KnowledgeCard
from app.modules.org.models import HolderLevel, ProcessHolder
from tests.factories import login, make_asset, make_handover, make_org_unit, make_process, make_user


@pytest.fixture
async def world(db: AsyncSession) -> dict[str, Any]:
    unit = await make_org_unit(db)
    other_unit = await make_org_unit(db)
    manager = await make_user(db, UserRole.MANAGER, org_unit=unit)
    other_manager = await make_user(db, UserRole.MANAGER, org_unit=other_unit)
    expert = await make_user(db, UserRole.EXPERT, org_unit=unit)
    colleague = await make_user(db, UserRole.EXPERT, org_unit=unit)
    successor = await make_user(db, UserRole.SUCCESSOR, org_unit=unit)
    report = await make_process(db, unit, "Отчёт о движении контингента", criticality=3)
    retakes = await make_process(db, unit, "Оформление пересдач", criticality=2)
    handover = await make_handover(
        db, org_unit=unit, manager=manager, expert=expert, successor=successor, processes=[report, retakes]
    )
    handover.deadline = date.today() + timedelta(days=21)
    db.add_all(
        [
            ProcessHolder(process_id=report.id, user_id=expert.id, level=HolderLevel.OWNER),
            ProcessHolder(process_id=retakes.id, user_id=expert.id, level=HolderLevel.OWNER),
            ProcessHolder(process_id=retakes.id, user_id=colleague.id, level=HolderLevel.KNOWS),
            ProcessHolder(process_id=report.id, user_id=successor.id, level=HolderLevel.LEARNING),
        ]
    )
    session = InterviewSession(handover_id=handover.id, expert_id=expert.id, active_seconds=600)
    db.add(session)
    await db.flush()
    message = InterviewMessage(
        session_id=session.id, seq=2, role=MessageRole.EXPERT, content="Отчёт сдаю до пятого числа."
    )
    db.add(message)
    await db.flush()
    drafts = {}
    for card_type in ("procedure", "rule"):
        card = KnowledgeCard(
            handover_id=handover.id,
            process_id=report.id,
            type=card_type,
            title=f"Отчёт: {card_type}",
            summary="Суть",
            body_md="Текст",
            origin=CardOrigin.INTERVIEW,
            status=CardStatus.DRAFT,
        )
        db.add(card)
        await db.flush()
        db.add(
            CardSource(
                card_id=card.id,
                source_type=SourceType.INTERVIEW_MESSAGE,
                source_id=message.id,
                quote="сдаю до пятого числа",
            )
        )
        drafts[card_type] = card.id
    await db.commit()
    return locals()


async def _risk(client: httpx.AsyncClient) -> dict[str, dict[str, Any]]:
    response = await client.get("/api/dashboard/risk")
    assert response.status_code == 200, response.text
    return {p["name"]: p for p in response.json()["processes"]}


async def _approve(client: httpx.AsyncClient, card_id: Any) -> None:
    response = await client.post(f"/api/cards/{card_id}/approve", json={"review_seconds": 30})
    assert response.status_code == 200, response.text


async def test_risk_map_and_its_change_after_approval(
    client: httpx.AsyncClient, world: dict[str, Any]
) -> None:
    """M4 acceptance: the process risk changes after the expert approves cards."""
    w = world
    await login(client, w["manager"])
    response = await client.get("/api/dashboard/risk")
    body = response.json()
    assert body["org_unit_name"] == w["unit"].name and body["high_threshold"] == 0.35
    names = [p["name"] for p in body["processes"]]
    assert names == ["Отчёт о движении контингента", "Оформление пересдач"]  # highest risk first

    before = await _risk(client)
    report = before["Отчёт о движении контингента"]
    # The leaving expert does not count; the successor is only learning.
    assert report["holders"] == [] and report["coverage"] == 0
    assert report["days_left"] == 21 and report["level"] == "high"
    assert report["risk"] == pytest.approx(1.0 * 1.0 * 1.0 * 0.7, abs=1e-3)
    retakes = before["Оформление пересдач"]
    assert [h["full_name"] for h in retakes["holders"]] == [w["colleague"].full_name]
    assert retakes["risk"] == pytest.approx(2 / 3 * 0.6 * 0.7, abs=1e-3) and retakes["level"] == "medium"

    await login(client, w["expert"])
    await _approve(client, w["drafts"]["procedure"])
    await login(client, w["manager"])
    after_one = (await _risk(client))["Отчёт о движении контингента"]
    assert after_one["coverage"] == pytest.approx(4 / 11, abs=1e-3)
    assert after_one["risk"] < report["risk"] and after_one["level"] == "high"
    cells = {a["key"]: a["status"] for a in after_one["aspects"]}
    assert cells["steps"] == "covered" and cells["exceptions"] == "missing"

    await login(client, w["expert"])
    await _approve(client, w["drafts"]["rule"])
    await login(client, w["manager"])
    after_two = (await _risk(client))["Отчёт о движении контингента"]
    assert after_two["coverage"] == pytest.approx(7 / 11, abs=1e-3)
    assert after_two["level"] == "medium"


async def test_risk_map_is_for_the_unit_manager(client: httpx.AsyncClient, world: dict[str, Any]) -> None:
    w = world
    await login(client, w["other_manager"])
    assert (
        await client.get("/api/dashboard/risk", params={"org_unit_id": str(w["unit"].id)})
    ).status_code == 403
    await login(client, w["expert"])
    assert (await client.get("/api/dashboard/risk")).status_code == 403


async def test_handover_progress(client: httpx.AsyncClient, world: dict[str, Any]) -> None:
    w = world
    await login(client, w["expert"])
    await _approve(client, w["drafts"]["procedure"])
    progress = (await client.get(f"/api/handovers/{w['handover'].id}/progress")).json()
    assert progress["days_left"] == 21
    assert progress["interview_sessions"] == 1 and progress["interview_minutes"] == 10
    assert (
        progress["cards_draft"] == 1 and progress["cards_approved"] == 1 and progress["cards_rejected"] == 0
    )
    assert progress["open_gaps"] == 0 and progress["recordings"] == 0
    assert {p["name"] for p in progress["processes"]} == {
        "Отчёт о движении контингента",
        "Оформление пересдач",
    }

    await login(client, w["successor"])
    assert (await client.get(f"/api/handovers/{w['handover'].id}/progress")).status_code == 403


async def test_metrics_and_csv(client: httpx.AsyncClient, world: dict[str, Any]) -> None:
    w = world
    await login(client, w["expert"])
    await _approve(client, w["drafts"]["procedure"])
    await _approve(client, w["drafts"]["rule"])

    await login(client, w["manager"])
    metrics = (await client.get("/api/dashboard/metrics")).json()
    assert metrics["cards_approved"] == 2 and metrics["cards_approved_edited"] == 0
    assert metrics["review_minutes"] == 1  # 2 × 30 s
    assert metrics["questions"] == 0 and metrics["answered_share"] is None
    assert metrics["key_processes_coverage"] == pytest.approx(7 / 11, abs=1e-3)

    one = (await client.get("/api/dashboard/metrics", params={"handover_id": str(w["handover"].id)})).json()
    assert one["cards_approved"] == 2
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    later = (await client.get("/api/dashboard/metrics", params={"from": tomorrow})).json()
    assert later["cards_approved"] == 0

    csv = await client.get("/api/dashboard/metrics.csv")
    assert csv.status_code == 200 and csv.headers["content-type"].startswith("text/csv")
    text = csv.content.decode("utf-8")
    assert text.startswith("﻿Показатель;Значение")
    assert "Подтверждено карточек;2" in text

    await login(client, w["expert"])
    assert (await client.get("/api/dashboard/metrics")).status_code == 403
    await login(client, w["other_manager"])
    params = {"handover_id": str(w["handover"].id)}
    assert (await client.get("/api/dashboard/metrics", params=params)).status_code == 403


async def test_audit_log(client: httpx.AsyncClient, db: AsyncSession, world: dict[str, Any]) -> None:
    w = world
    await login(client, w["expert"])
    await _approve(client, w["drafts"]["procedure"])

    await login(client, w["manager"])
    entries = (await client.get("/api/audit", params={"entity": "card"})).json()
    assert [(e["action"], e["user_name"]) for e in entries] == [("card.approved", w["expert"].full_name)]
    one = (
        await client.get("/api/audit", params={"entity": "card", "entity_id": str(w["drafts"]["rule"])})
    ).json()
    assert one == []

    await login(client, w["other_manager"])  # actions of another unit's employees are not shown
    assert (await client.get("/api/audit", params={"entity": "card"})).json() == []
    await login(client, w["expert"])
    assert (await client.get("/api/audit")).status_code == 403


async def test_watching_a_video_is_audited_once(
    client: httpx.AsyncClient, db: AsyncSession, world: dict[str, Any]
) -> None:
    w = world
    video = await make_asset(db, AssetKind.VIDEO, w["expert"].id, w["handover"].id)
    await db.commit()
    await login(client, w["successor"])
    for _ in range(3):  # the player asks for ranges again and again
        assert (
            await client.get(f"/api/assets/{video.id}", headers={"Range": "bytes=0-1"})
        ).status_code == 206
    count = await db.scalar(
        select(func.count()).select_from(AuditLog).where(AuditLog.action == "recording.viewed")
    )
    assert count == 1
