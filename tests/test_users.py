import pytest


async def _login(client, username, password):
    resp = await client.post("/api/v1/auth/login",
                             data={"username": username, "password": password})
    return resp.json()["access_token"]


async def _auth(client, token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def admin_token(client):
    # Crée un admin de départ directement en base (ou via ton seed de test).
    from app.core.security import hash_password
    from app.models.user import User
    from tests.conftest import TestSession  # adapte à ta fixture de session

    async with TestSession() as s:
        s.add(User(username="admin1", password_hash=hash_password("password123"),
                   role="admin", is_active=True))
        await s.commit()
    return await _login(client, "admin1", "password123")


async def test_create_magazinier(client, admin_token):
    h = await _auth(client, admin_token)
    resp = await client.post("/api/v1/users", headers=h, json={
        "username": "mag1", "password": "motdepasse1", "full_name": "Kouassi", "role": "magazinier",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["username"] == "mag1"
    assert body["role"] == "magazinier"
    assert "password" not in body and "password_hash" not in body   # jamais exposé


async def test_duplicate_username_409(client, admin_token):
    h = await _auth(client, admin_token)
    await client.post("/api/v1/users", headers=h, json={
        "username": "mag2", "password": "motdepasse1"})
    resp = await client.post("/api/v1/users", headers=h, json={
        "username": "mag2", "password": "autre123"})
    assert resp.status_code == 409


async def test_short_password_422(client, admin_token):
    h = await _auth(client, admin_token)
    resp = await client.post("/api/v1/users", headers=h, json={
        "username": "mag3", "password": "court"})
    assert resp.status_code == 422


async def test_magazinier_cannot_access_users(client, admin_token):
    h = await _auth(client, admin_token)
    await client.post("/api/v1/users", headers=h, json={
        "username": "mag4", "password": "motdepasse1", "role": "magazinier"})
    mag_token = await _login(client, "mag4", "motdepasse1")
    mh = await _auth(client, mag_token)
    resp = await client.get("/api/v1/users", headers=mh)
    assert resp.status_code == 403          # magazinier interdit ici


async def test_new_magazinier_can_login(client, admin_token):
    h = await _auth(client, admin_token)
    await client.post("/api/v1/users", headers=h, json={
        "username": "mag5", "password": "motdepasse1"})
    resp = await client.post("/api/v1/auth/login",
                             data={"username": "mag5", "password": "motdepasse1"})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


async def test_deactivate_blocks_login(client, admin_token):
    h = await _auth(client, admin_token)
    u = (await client.post("/api/v1/users", headers=h, json={
        "username": "mag6", "password": "motdepasse1"})).json()
    await client.post(f"/api/v1/users/{u['id']}/deactivate", headers=h)
    resp = await client.post("/api/v1/auth/login",
                             data={"username": "mag6", "password": "motdepasse1"})
    assert resp.status_code == 401          # compte désactivé, login refusé


async def test_reset_password(client, admin_token):
    h = await _auth(client, admin_token)
    u = (await client.post("/api/v1/users", headers=h, json={
        "username": "mag7", "password": "motdepasse1"})).json()
    await client.post(f"/api/v1/users/{u['id']}/reset-password", headers=h,
                      json={"new_password": "nouveaupass1"})
    # ancien refusé, nouveau accepté
    assert (await client.post("/api/v1/auth/login",
            data={"username": "mag7", "password": "motdepasse1"})).status_code == 401
    assert (await client.post("/api/v1/auth/login",
            data={"username": "mag7", "password": "nouveaupass1"})).status_code == 200


async def test_cannot_delete_self(client, admin_token):
    h = await _auth(client, admin_token)
    me = (await client.get("/api/v1/auth/me", headers=h)).json()
    resp = await client.delete(f"/api/v1/users/{me['id']}", headers=h)
    assert resp.status_code == 422          # garde-fou "pas soi-même"


async def test_cannot_remove_last_admin(client, admin_token):
    h = await _auth(client, admin_token)
    me = (await client.get("/api/v1/auth/me", headers=h)).json()
    # tenter de se rétrograder → bloqué (dernier admin + soi-même)
    resp = await client.patch(f"/api/v1/users/{me['id']}", headers=h,
                              json={"role": "magazinier"})
    assert resp.status_code == 422