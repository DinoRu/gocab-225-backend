from __future__ import annotations

from datetime import date
from decimal import Decimal

from httpx import AsyncClient


class ApiFactory:
    """Fabrique d'entités via l'API réelle (parcourt tout le stack HTTP→service→DB).
    Utilisée par les tests pour éliminer la duplication des helpers de setup."""

    def __init__(self, client: AsyncClient) -> None:
        self.client = client

    async def brand(self, name: str) -> str:
        resp = await self.client.post("/api/v1/vehicle-brands", json={"name": name})
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    async def model(self, brand_id: str, name: str) -> str:
        resp = await self.client.post(
            "/api/v1/vehicle-models", json={"brand_id": brand_id, "name": name}
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    async def part(
        self, model_id: str, reference: str, designation: str, **extra
    ) -> str:
        resp = await self.client.post(
            "/api/v1/parts",
            json={
                "reference": reference,
                "designation": designation,
                "vehicle_model_id": model_id,
                **extra,
            },
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    async def supplier(self, name: str, **extra) -> str:
        resp = await self.client.post(
            "/api/v1/suppliers", json={"name": name, **extra}
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    async def order(
        self,
        supplier_id: str,
        order_date: str | date,
        lines: list[tuple[str, int, Decimal | None]],
        **extra,
    ) -> dict:
        """lines : liste de (part_id, quantity, unit_price|None)."""
        payload = {
            "supplier_id": supplier_id,
            "order_date": order_date if isinstance(order_date, str) else order_date.isoformat(),
            "items": [
                {
                    "part_id": pid,
                    "quantity": qty,
                    **({"unit_price": str(price)} if price is not None else {}),
                }
                for pid, qty, price in lines
            ],
            **extra,
        }
        resp = await self.client.post("/api/v1/purchase-orders", json=payload)
        assert resp.status_code == 201, resp.text
        return resp.json()