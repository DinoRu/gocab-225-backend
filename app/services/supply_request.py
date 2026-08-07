from datetime import date
from uuid import UUID

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import constraint_name
from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.core.pagination import paginate
from app.models.part import Part
from app.models.purchase_request import PurchaseRequest
from app.models.supplier import Supplier
from app.models.supply_request import SupplyRequest, SupplyRequestItem
from app.repositories.supply_request import SupplyRequestRepository
from app.schemas.supply_request import SupplyRequestCreate, SupplyRequestUpdate

_MAX_RETRIES = 5


async def _linked_bcs(session: AsyncSession, sr_id: UUID) -> list[dict]:
    """Les bons de commande issus de ce besoin (traçabilité de l'éclatement)."""
    rows = (
        await session.execute(
            select(
                PurchaseRequest.id,
                PurchaseRequest.bc_number,
                PurchaseRequest.status,
                Supplier.name.label("supplier_name"),
            )
            .join(Supplier, Supplier.id == PurchaseRequest.supplier_id, isouter=True)
            .where(PurchaseRequest.supply_request_id == sr_id)
            .order_by(PurchaseRequest.bc_number)
        )
    ).all()
    return [
        {"id": r.id, "bc_number": r.bc_number, "supplier_name": r.supplier_name, "status": r.status}
        for r in rows
    ]


def _serialize(sr: SupplyRequest, linked: list[dict]) -> dict:
    items = sorted(
        (
            {
                "id": it.id,
                "part_id": it.part_id,
                "reference": it.part.reference,
                "designation": it.part.designation,
                "quantity": it.quantity,
            }
            for it in sr.items
        ),
        key=lambda x: x["reference"],
    )
    return {
        "id": sr.id,
        "sr_number": sr.sr_number,
        "request_date": sr.request_date,
        "status": sr.status,
        "notes": sr.notes,
        "created_by": sr.created_by,
        "created_by_name": sr.creator.full_name or sr.creator.username if sr.creator else None,
        "items": items,
        "linked_bcs": linked,
        "created_at": sr.created_at,
    }


class SupplyRequestService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = SupplyRequestRepository(session)

    async def get_or_404(self, request_id: UUID) -> SupplyRequest:
        sr = await self.repo.get_detail(request_id)
        if sr is None:
            raise NotFoundError(f"Besoin {request_id} introuvable.")
        return sr

    async def get_detail(self, request_id: UUID) -> dict:
        sr = await self.get_or_404(request_id)
        linked = await _linked_bcs(self.session, sr.id)
        return _serialize(sr, linked)

    async def list_requests(self, *, search, status, created_by, start_date, end_date, page, limit):
        stmt = self.repo.list_stmt(
            search=search, status=status, created_by=created_by,
            start_date=start_date, end_date=end_date,
        )
        items, total = await paginate(self.session, stmt, page=page, limit=limit)
        # Les bons liés sont chargés par besoin (peu de besoins par page, coût négligeable).
        out = []
        for sr in items:
            linked = await _linked_bcs(self.session, sr.id)
            out.append(_serialize(sr, linked))
        return out, total

    async def create(self, data: SupplyRequestCreate, *, created_by: UUID) -> dict:
        await self._ensure_parts([i.part_id for i in data.items])
        last_exc = None
        for _ in range(_MAX_RETRIES):
            number = await self._next_number(data.request_date.year)
            sr = SupplyRequest(
                sr_number=number,
                request_date=data.request_date,
                notes=data.notes,
                status="open",
                created_by=created_by,
                items=[
                    SupplyRequestItem(part_id=i.part_id, quantity=i.quantity)
                    for i in data.items
                ],
            )
            self.session.add(sr)
            try:
                await self.session.commit()
            except IntegrityError as exc:
                await self.session.rollback()
                if constraint_name(exc) == "uq_supply_requests_number":
                    last_exc = exc
                    continue
                self._translate(exc)
                raise
            else:
                return await self.get_detail(sr.id)
        raise ConflictError("Impossible de générer un numéro de besoin unique.") from last_exc

    async def update(self, request_id: UUID, data: SupplyRequestUpdate) -> dict:
        sr = await self.repo.get_with_items(request_id)
        if sr is None:
            raise NotFoundError(f"Besoin {request_id} introuvable.")
        if sr.status == "fulfilled":
            raise BusinessRuleError("Un besoin traité ne peut plus être modifié.")
        fields = data.model_dump(exclude_unset=True)
        if fields.get("request_date") is not None:
            sr.request_date = fields["request_date"]
        if "notes" in fields:
            sr.notes = fields["notes"]
        if data.items is not None:
            await self._ensure_parts([i.part_id for i in data.items])
            sr.items.clear()
            await self.session.flush()
            for i in data.items:
                sr.items.append(SupplyRequestItem(part_id=i.part_id, quantity=i.quantity))
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            self._translate(exc)
            raise
        return await self.get_detail(request_id)

    async def mark_fulfilled(self, request_id: UUID) -> dict:
        sr = await self.get_or_404(request_id)
        sr.status = "fulfilled"
        await self.session.commit()
        return await self.get_detail(request_id)

    async def reopen(self, request_id: UUID) -> dict:
        sr = await self.get_or_404(request_id)
        # Si des bons existent déjà, on revient à "en cours", sinon "ouvert".
        linked = await _linked_bcs(self.session, sr.id)
        sr.status = "in_progress" if linked else "open"
        await self.session.commit()
        return await self.get_detail(request_id)

    async def delete(self, request_id: UUID) -> None:
        sr = await self.repo.get_with_items(request_id)
        if sr is None:
            raise NotFoundError(f"Besoin {request_id} introuvable.")
        await self.session.delete(sr)
        await self.session.commit()

    async def mark_in_progress_if_open(self, request_id: UUID) -> None:
        """Appelé quand un bon est créé depuis ce besoin : open → in_progress."""
        sr = await self.session.get(SupplyRequest, request_id)
        if sr is not None and sr.status == "open":
            sr.status = "in_progress"
            await self.session.commit()

    # --- internes ---
    async def _next_number(self, year: int) -> str:
        prefix = f"BA-{year}-"
        seq = cast(func.split_part(SupplyRequest.sr_number, "-", 3), Integer)
        last = await self.session.scalar(
            select(func.coalesce(func.max(seq), 0)).where(
                SupplyRequest.sr_number.like(f"{prefix}%")
            )
        )
        return f"{prefix}{(last or 0) + 1:03d}"

    async def _ensure_parts(self, part_ids: list[UUID]) -> None:
        unique = set(part_ids)
        found = set(await self.session.scalars(select(Part.id).where(Part.id.in_(unique))))
        missing = unique - found
        if missing:
            raise NotFoundError(f"Pièce(s) introuvable(s) : {', '.join(str(m) for m in missing)}")

    def _translate(self, exc: IntegrityError) -> None:
        cn = constraint_name(exc)
        if cn == "uq_sr_item_request_part":
            raise ConflictError("Une même pièce ne peut apparaître qu'une fois.") from exc
        if cn == "ck_sr_item_quantity_positive":
            raise BusinessRuleError("La quantité doit être supérieure à zéro.") from exc
        if cn and cn.endswith("part_id_fkey"):
            raise NotFoundError("Pièce introuvable.") from exc