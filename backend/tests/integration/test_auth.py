import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AUTH_COOKIE
from app.modules.audit.models import AuditLog
from app.modules.identity.models import UserRole
from tests.factories import PASSWORD, make_org_unit, make_user


async def login(client: httpx.AsyncClient, email: str, password: str = PASSWORD) -> httpx.Response:
    return await client.post("/api/auth/login", json={"email": email, "password": password})


async def test_login_sets_httponly_cookie_and_me_works(client: httpx.AsyncClient, db: AsyncSession) -> None:
    user = await make_user(db, UserRole.EXPERT, email="expert@test.local")
    await db.commit()

    response = await login(client, " Expert@Test.local ")  # email is normalized
    assert response.status_code == 200
    assert response.json()["id"] == str(user.id)
    set_cookie = response.headers["set-cookie"].lower()
    assert f"{AUTH_COOKIE}=" in set_cookie and "httponly" in set_cookie and "samesite=lax" in set_cookie

    me = await client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "expert@test.local"


async def test_wrong_password_gives_russian_error(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await make_user(db, UserRole.EXPERT, email="expert@test.local")
    await db.commit()
    response = await login(client, "expert@test.local", "wrong-password")
    assert response.status_code == 401
    assert response.json() == {"detail": "Неверный email или пароль", "code": "invalid_credentials"}


async def test_unknown_email_gives_same_error(client: httpx.AsyncClient) -> None:
    response = await login(client, "nobody@test.local")
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"


async def test_inactive_user_cannot_log_in(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await make_user(db, UserRole.EXPERT, email="gone@test.local", is_active=False)
    await db.commit()
    assert (await login(client, "gone@test.local")).status_code == 401


async def test_me_without_cookie_is_401(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "Войдите в систему"


async def test_logout_clears_cookie(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await make_user(db, UserRole.EXPERT, email="expert@test.local")
    await db.commit()
    await login(client, "expert@test.local")
    assert (await client.post("/api/auth/logout")).status_code == 204
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_deactivated_user_loses_access_with_valid_cookie(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    user = await make_user(db, UserRole.EXPERT, email="expert@test.local")
    await db.commit()
    await login(client, "expert@test.local")
    user.is_active = False
    await db.commit()
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_login_is_audited(client: httpx.AsyncClient, db: AsyncSession) -> None:
    user = await make_user(db, UserRole.EXPERT, email="expert@test.local")
    await db.commit()
    await login(client, "expert@test.local")
    await login(client, "expert@test.local", "wrong-password")
    actions = (await db.execute(select(AuditLog.action, AuditLog.entity_id).order_by(AuditLog.at))).all()
    assert [a for a, _ in actions] == ["auth.login", "auth.login_failed"]
    assert all(entity_id == user.id for _, entity_id in actions)


async def test_admin_manages_users(client: httpx.AsyncClient, db: AsyncSession) -> None:
    unit = await make_org_unit(db)
    await make_user(db, UserRole.ADMIN, email="admin@test.local")
    await db.commit()
    await login(client, "admin@test.local")

    created = await client.post(
        "/api/admin/users",
        json={
            "email": "New@Test.local",
            "full_name": "Новый сотрудник",
            "role": "successor",
            "password": "secret-pass",
            "org_unit_id": str(unit.id),
        },
    )
    assert created.status_code == 201
    assert created.json()["email"] == "new@test.local"

    duplicate = await client.post(
        "/api/admin/users",
        json={"email": "new@test.local", "full_name": "x", "role": "expert", "password": "secret-pass"},
    )
    assert duplicate.status_code == 409

    user_id = created.json()["id"]
    patched = await client.patch(f"/api/admin/users/{user_id}", json={"is_active": False})
    assert patched.json()["is_active"] is False
    assert len((await client.get("/api/admin/users")).json()) == 2


async def test_non_admin_cannot_manage_users(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await make_user(db, UserRole.MANAGER, email="manager@test.local")
    await db.commit()
    await login(client, "manager@test.local")
    response = await client.get("/api/admin/users")
    assert response.status_code == 403
    assert response.json()["detail"] == "Недостаточно прав"


async def test_admin_creates_org_unit(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await make_user(db, UserRole.ADMIN, email="admin@test.local")
    await db.commit()
    await login(client, "admin@test.local")
    assert (await client.post("/api/admin/org-units", json={"name": "Деканат"})).status_code == 201
    assert (await client.post("/api/admin/org-units", json={"name": "Деканат"})).status_code == 409
    assert [u["name"] for u in (await client.get("/api/admin/org-units")).json()] == ["Деканат"]
