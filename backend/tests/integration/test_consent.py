import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import UserRole
from tests.factories import login, make_handover, make_org_unit, make_user


async def test_consent_gates_the_interview(client: httpx.AsyncClient, db: AsyncSession) -> None:
    unit = await make_org_unit(db)
    manager = await make_user(db, UserRole.MANAGER, org_unit=unit)
    expert = await make_user(db, UserRole.EXPERT, org_unit=unit)
    handover = await make_handover(db, org_unit=unit, manager=manager, expert=expert)
    await db.commit()
    await login(client, expert)

    text = (await client.get("/api/consents/current-text")).json()
    assert text["version"] == "1" and "Кто видит" in text["text"] and len(text["hash"]) == 64
    assert "{{" not in text["text"]

    denied = await client.post("/api/interviews", json={"handover_id": str(handover.id)})
    assert denied.status_code == 403
    assert denied.json() == {
        "detail": "Сначала примите согласие на запись и обработку рабочих бесед",
        "code": "consent_required",
    }
    assert (await client.get("/api/consents/my", params={"handover_id": str(handover.id)})).json() is None

    accepted = await client.post("/api/consents", json={"handover_id": str(handover.id)})
    assert accepted.status_code == 201
    again = await client.post("/api/consents", json={"handover_id": str(handover.id)})
    assert again.json()["id"] == accepted.json()["id"]  # idempotent

    assert (await client.post("/api/interviews", json={"handover_id": str(handover.id)})).status_code == 201

    revoked = await client.post(f"/api/consents/{accepted.json()['id']}/revoke")
    assert revoked.json()["revoked_at"] is not None
    assert (await client.post("/api/interviews", json={"handover_id": str(handover.id)})).status_code == 403


async def test_only_the_expert_gives_consent(client: httpx.AsyncClient, db: AsyncSession) -> None:
    unit = await make_org_unit(db)
    manager = await make_user(db, UserRole.MANAGER, org_unit=unit)
    successor = await make_user(db, UserRole.SUCCESSOR, org_unit=unit)
    handover = await make_handover(db, org_unit=unit, manager=manager, successor=successor)
    await db.commit()
    for user in (manager, successor):
        await login(client, user)
        assert (await client.post("/api/consents", json={"handover_id": str(handover.id)})).status_code == 403
