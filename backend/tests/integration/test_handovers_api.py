from datetime import date

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import UserRole
from app.modules.org.models import HolderLevel, ProcessHolder
from tests.factories import login, make_handover, make_org_unit, make_process, make_user


async def test_manager_creates_handover_and_holders_are_set(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    unit = await make_org_unit(db)
    manager = await make_user(db, UserRole.MANAGER, org_unit=unit)
    expert = await make_user(db, UserRole.EXPERT, org_unit=unit)
    successor = await make_user(db, UserRole.SUCCESSOR, org_unit=unit)
    report = await make_process(db, unit, "Отчёт о движении контингента", criticality=3)
    db.add(ProcessHolder(process_id=report.id, user_id=successor.id, level=HolderLevel.KNOWS))
    await db.commit()
    await login(client, manager)

    response = await client.post(
        "/api/handovers",
        json={
            "expert_id": str(expert.id),
            "successor_id": str(successor.id),
            "reason": "retirement",
            "deadline": "2026-11-07",
            "process_ids": [str(report.id)],
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "active" and body["my_role"] == "manager"
    assert [p["name"] for p in body["processes"]] == ["Отчёт о движении контингента"]
    assert [e["id"] for e in body["experts"]] == [str(expert.id)]

    holders = dict((await db.execute(select(ProcessHolder.user_id, ProcessHolder.level))).all())
    assert holders[expert.id] is HolderLevel.OWNER
    assert holders[successor.id] is HolderLevel.KNOWS  # a stronger level is not downgraded to «learning»


async def test_processes_must_belong_to_the_unit(client: httpx.AsyncClient, db: AsyncSession) -> None:
    unit, other = await make_org_unit(db), await make_org_unit(db)
    manager = await make_user(db, UserRole.MANAGER, org_unit=unit)
    expert = await make_user(db, UserRole.EXPERT, org_unit=unit)
    foreign = await make_process(db, other, "Чужой процесс")
    await db.commit()
    await login(client, manager)
    response = await client.post(
        "/api/handovers",
        json={"expert_id": str(expert.id), "reason": "leave", "process_ids": [str(foreign.id)]},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "bad_processes"


async def test_list_shows_only_visible_handovers(client: httpx.AsyncClient, db: AsyncSession) -> None:
    unit, other = await make_org_unit(db), await make_org_unit(db)
    manager = await make_user(db, UserRole.MANAGER, org_unit=unit)
    other_manager = await make_user(db, UserRole.MANAGER, org_unit=other)
    expert = await make_user(db, UserRole.EXPERT, org_unit=unit)
    successor = await make_user(db, UserRole.SUCCESSOR, org_unit=unit)
    mine = await make_handover(db, org_unit=unit, manager=manager, expert=expert, successor=successor)
    await make_handover(
        db, org_unit=other, manager=other_manager, expert=await make_user(db, UserRole.EXPERT)
    )
    await db.commit()

    for user, role in ((manager, "manager"), (expert, "expert"), (successor, "successor")):
        await login(client, user)
        listed = (await client.get("/api/handovers")).json()
        assert [(h["id"], h["my_role"]) for h in listed] == [(str(mine.id), role)]

    await login(client, other_manager)
    assert (await client.get(f"/api/handovers/{mine.id}")).status_code == 403


async def test_manager_updates_handover(client: httpx.AsyncClient, db: AsyncSession) -> None:
    unit = await make_org_unit(db)
    manager = await make_user(db, UserRole.MANAGER, org_unit=unit)
    expert = await make_user(db, UserRole.EXPERT, org_unit=unit)
    successor = await make_user(db, UserRole.SUCCESSOR, org_unit=unit)
    handover = await make_handover(db, org_unit=unit, manager=manager, expert=expert)
    process = await make_process(db, unit, "Оформление пересдач")
    await db.commit()
    await login(client, manager)

    response = await client.patch(
        f"/api/handovers/{handover.id}",
        json={"deadline": "2026-11-20", "successor_id": str(successor.id), "process_ids": [str(process.id)]},
    )
    body = response.json()
    assert body["deadline"] == date(2026, 11, 20).isoformat()
    assert [s["id"] for s in body["successors"]] == [str(successor.id)]
    assert [p["id"] for p in body["processes"]] == [str(process.id)]

    await login(client, expert)
    assert (
        await client.patch(f"/api/handovers/{handover.id}", json={"status": "completed"})
    ).status_code == 403


async def test_processes_crud_and_directory(client: httpx.AsyncClient, db: AsyncSession) -> None:
    unit, other = await make_org_unit(db), await make_org_unit(db)
    manager = await make_user(db, UserRole.MANAGER, org_unit=unit)
    expert = await make_user(db, UserRole.EXPERT, org_unit=unit)
    await make_user(db, UserRole.EXPERT, org_unit=other)
    await db.commit()
    await login(client, manager)

    created = await client.post("/api/processes", json={"name": "Справки студентам", "criticality": 1})
    assert created.status_code == 201
    process_id = created.json()["id"]
    await client.patch(f"/api/processes/{process_id}", json={"criticality": 3, "frequency": "daily"})
    with_holder = await client.post(
        f"/api/processes/{process_id}/holders", json={"user_id": str(expert.id), "level": "owner"}
    )
    assert with_holder.json()["holders"][0]["full_name"] == expert.full_name
    listed = (await client.get("/api/processes")).json()
    assert [(p["name"], p["criticality"], p["frequency"]) for p in listed] == [
        ("Справки студентам", 3, "daily")
    ]
    removed = await client.delete(f"/api/processes/{process_id}/holders/{expert.id}")
    assert removed.json()["holders"] == []

    experts = (await client.get("/api/users", params={"role": "expert"})).json()
    assert [u["id"] for u in experts] == [str(expert.id)]  # only the manager's unit

    assert (await client.get("/api/processes", params={"org_unit_id": str(other.id)})).status_code == 403
    await login(client, expert)
    assert (await client.post("/api/processes", json={"name": "x"})).status_code == 403
