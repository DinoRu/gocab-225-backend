import pytest


async def _login(client, username, password):
    r = await client.post("/api/v1/auth/login", data={"username": username, "password": password})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
async def admin_h(client):
    from app.core.security import hash_password
    from app.models.user import User
    from tests.conftest import TestSession
    async with TestSession() as s:
        s.add(User(username="admin1", password_hash=hash_password("password123"), role="admin", is_active=True))
        await s.commit()
    return await _login(client, "admin1", "password123")


@pytest.fixture
async def mag_h(client, admin_h):
    await client.post("/api/v1/users", headers=admin_h,
                      json={"username": "mag1", "password": "password123", "role": "magazinier"})
    return await _login(client, "mag1", "password123")


async def _parts(client, admin_h):
    b = (await client.post("/api/v1/vehicle-brands", headers=admin_h, json={"name": "Chery"})).json()["id"]
    m = (await client.post("/api/v1/vehicle-models", headers=admin_h, json={"brand_id": b, "name": "Tiggo2"})).json()["id"]
    air = (await client.post("/api/v1/parts", headers=admin_h, json={
        "reference": "AIR-1", "designation": "Filtre à air", "vehicle_model_ids": [m]})).json()["id"]
    bat = (await client.post("/api/v1/parts", headers=admin_h, json={
        "reference": "BAT-1", "designation": "Batterie 60Ah", "vehicle_model_ids": [m]})).json()["id"]
    return air, bat


async def _create_need(client, headers, items, date_="2026-03-01"):
    return await client.post("/api/v1/supply-requests", headers=headers, json={
        "request_date": date_,
        "items": [{"part_id": p, "quantity": q} for p, q in items],
    })


# --- création & numérotation ---

async def test_magazinier_creates_need(client, admin_h, mag_h):
    air, _ = await _parts(client, admin_h)
    resp = await _create_need(client, mag_h, [(air, 20)])
    assert resp.status_code == 201
    body = resp.json()
    assert body["sr_number"] == "BA-2026-001"
    assert body["status"] == "open"
    assert body["created_by_name"] == "mag1"


# --- visibilité : le magazinier ne voit que ses besoins ---

async def test_magazinier_sees_only_own(client, admin_h, mag_h):
    air, _ = await _parts(client, admin_h)
    await _create_need(client, admin_h, [(air, 5)])     # besoin de l'admin
    await _create_need(client, mag_h, [(air, 20)])      # besoin du magazinier

    mag_list = (await client.get("/api/v1/supply-requests", headers=mag_h)).json()
    assert mag_list["total"] == 1                        # ne voit que le sien

    admin_list = (await client.get("/api/v1/supply-requests", headers=admin_h)).json()
    assert admin_list["total"] == 2                      # admin voit tout


async def test_magazinier_cannot_open_others_need(client, admin_h, mag_h):
    air, _ = await _parts(client, admin_h)
    admin_need = (await _create_need(client, admin_h, [(air, 5)])).json()
    resp = await client.get(f"/api/v1/supply-requests/{admin_need['id']}", headers=mag_h)
    assert resp.status_code == 404                       # 404, pas 403 (on ne révèle pas l'existence)


# --- transformation en bon + éclatement ---

async def test_create_bc_from_need_sets_in_progress(client, admin_h, mag_h):
    air, bat = await _parts(client, admin_h)
    need = (await _create_need(client, mag_h, [(air, 20), (bat, 10)])).json()
    sup = (await client.post("/api/v1/suppliers", headers=admin_h, json={"name": "SEP-CI"})).json()["id"]

    # L'admin crée un bon depuis le besoin
    bc = await client.post("/api/v1/purchase-requests/from-supply", headers=admin_h, json={
        "supply_request_id": need["id"], "supplier_id": sup, "request_date": "2026-03-05",
    })
    assert bc.status_code == 201
    assert bc.json()["supply_request_id"] == need["id"]

    # Le besoin est passé "en cours" automatiquement
    refreshed = (await client.get(f"/api/v1/supply-requests/{need['id']}", headers=admin_h)).json()
    assert refreshed["status"] == "in_progress"
    assert len(refreshed["linked_bcs"]) == 1


async def test_need_split_into_multiple_bcs(client, admin_h, mag_h):
    """Éclatement : un besoin → deux bons chez deux fournisseurs."""
    air, bat = await _parts(client, admin_h)
    need = (await _create_need(client, mag_h, [(air, 20), (bat, 10)])).json()
    sup1 = (await client.post("/api/v1/suppliers", headers=admin_h, json={"name": "SEP-CI"})).json()["id"]
    sup2 = (await client.post("/api/v1/suppliers", headers=admin_h, json={"name": "AutrePro"})).json()["id"]

    # Bon 1 : les filtres chez SEP-CI
    await client.post("/api/v1/purchase-requests/from-supply", headers=admin_h, json={
        "supply_request_id": need["id"], "supplier_id": sup1, "request_date": "2026-03-05",
        "items": [{"part_id": air, "quantity": 20}],
    })
    # Bon 2 : les batteries ailleurs
    await client.post("/api/v1/purchase-requests/from-supply", headers=admin_h, json={
        "supply_request_id": need["id"], "supplier_id": sup2, "request_date": "2026-03-05",
        "items": [{"part_id": bat, "quantity": 10}],
    })

    refreshed = (await client.get(f"/api/v1/supply-requests/{need['id']}", headers=admin_h)).json()
    assert len(refreshed["linked_bcs"]) == 2             # deux bons tracés sur le besoin


async def test_only_admin_creates_bc_from_need(client, admin_h, mag_h):
    air, _ = await _parts(client, admin_h)
    need = (await _create_need(client, mag_h, [(air, 20)])).json()
    sup = (await client.post("/api/v1/suppliers", headers=admin_h, json={"name": "SEP-CI"})).json()["id"]
    # Le magazinier tente de créer un bon → interdit
    resp = await client.post("/api/v1/purchase-requests/from-supply", headers=mag_h, json={
        "supply_request_id": need["id"], "supplier_id": sup, "request_date": "2026-03-05",
    })
    assert resp.status_code == 403


# --- statut ---

async def test_mark_fulfilled_is_admin_only(client, admin_h, mag_h):
    air, _ = await _parts(client, admin_h)
    need = (await _create_need(client, mag_h, [(air, 20)])).json()
    # magazinier ne peut pas
    assert (await client.post(f"/api/v1/supply-requests/{need['id']}/mark-fulfilled", headers=mag_h)).status_code == 403
    # admin peut
    done = await client.post(f"/api/v1/supply-requests/{need['id']}/mark-fulfilled", headers=admin_h)
    assert done.json()["status"] == "fulfilled"


async def test_duplicate_part_422(client, admin_h, mag_h):
    air, _ = await _parts(client, admin_h)
    resp = await _create_need(client, mag_h, [(air, 5), (air, 10)])
    assert resp.status_code == 422


async def test_export(client, admin_h, mag_h):
    from io import BytesIO
    import openpyxl
    air, _ = await _parts(client, admin_h)
    await _create_need(client, mag_h, [(air, 20)])
    resp = await client.get("/api/v1/supply-requests/export", headers=mag_h)
    assert resp.status_code == 200
    ws = openpyxl.load_workbook(BytesIO(resp.content)).active
    assert "Besoins" in ws["A1"].value