from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import constraint_name
from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.core.pagination import paginate
from app.models.part import Part
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_request import PurchaseRequest, PurchaseRequestItem
from app.models.supplier import Supplier
from app.repositories.purchase_request import PurchaseRequestRepository
from app.schemas.purchase_request import PurchaseRequestCreate, PurchaseRequestItemCreate, PurchaseRequestUpdate

_MAX_RETRIES = 5
_STATUS_FLOW = {"draft": "sent", "sent": "received"}


def serialize(pr: PurchaseRequest) -> dict:
    items = []
    total = Decimal("0")
    has_price = False
    for it in pr.items:
        line_total = None
        if it.unit_price is not None:
            line_total = it.unit_price * it.quantity
            total += line_total
            has_price = True
        items.append({
            "id": it.id,
            "part_id": it.part_id,
            "reference": it.part.reference,
            "designation": it.part.designation,
            "quantity": it.quantity,
            "unit_price": it.unit_price,
            "line_total": line_total,
        })
    items.sort(key=lambda x: x["reference"])
    return {
        "id": pr.id,
        "bc_number": pr.bc_number,
        "supplier": {"id": pr.supplier.id, "name": pr.supplier.name},
        "request_date": pr.request_date,
        "expected_date": pr.expected_date,
        "status": pr.status,
        "purchase_order_id": pr.purchase_order_id,
        "order_number": None,   # rempli par le service si lié (voir get_detail)
        "notes": pr.notes,
        "items": items,
        "total_amount": total if has_price else None,
        "sent_at": pr.sent_at,
        "received_at": pr.received_at,
        "created_at": pr.created_at,
    }


class PurchaseRequestService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = PurchaseRequestRepository(session)

    async def get_or_404(self, request_id: UUID) -> PurchaseRequest:
        pr = await self.repo.get_detail(request_id)
        if pr is None:
            raise NotFoundError(f"Bon de commande {request_id} introuvable.")
        return pr

    async def get_detail(self, request_id: UUID) -> dict:
        pr = await self.get_or_404(request_id)
        data = serialize(pr)
        if pr.purchase_order_id:
            order_number = await self.session.scalar(
                select(PurchaseOrder.order_number).where(PurchaseOrder.id == pr.purchase_order_id)
            )
            data["order_number"] = order_number
        return data

    async def list_purchases(self, *, search, status, supplier_id, start_date, end_date, page, limit):
        stmt = self.repo.list_stmt(
            search=search, status=status, supplier_id=supplier_id,
            start_date=start_date, end_date=end_date,
        )
        items, total = await paginate(self.session, stmt, page=page, limit=limit)
        return [serialize(pr) for pr in items], total

    async def create(self, data: PurchaseRequestCreate) -> dict:
        await self._ensure_supplier(data.supplier_id)
        await self._ensure_parts([i.part_id for i in data.items])
        last_exc = None
        for _ in range(_MAX_RETRIES):
            number = await self._next_number(data.request_date.year)
            pr = PurchaseRequest(
                bc_number=number,
                supplier_id=data.supplier_id,
                request_date=data.request_date,
                expected_date=data.expected_date,
                notes=data.notes,
                status="draft",
                items=[
                    PurchaseRequestItem(part_id=i.part_id, quantity=i.quantity, unit_price=i.unit_price)
                    for i in data.items
                ],
            )
            self.session.add(pr)
            try:
                await self.session.commit()
            except IntegrityError as exc:
                await self.session.rollback()
                cn = constraint_name(exc)
                if cn == "uq_purchase_requests_number":
                    last_exc = exc
                    continue
                self._translate(exc)
                raise
            else:
                return await self.get_detail(pr.id)
        raise ConflictError("Impossible de générer un numéro de bon unique.") from last_exc
    
    
    async def create_from_supply(self, data, *, service_supply) -> dict:
        """Crée un bon à partir d'un besoin. Pré-remplit les lignes si non fournies,
        lie le bon au besoin, et fait passer le besoin en 'in_progress'."""
        from app.models.supply_request import SupplyRequest, SupplyRequestItem
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        sr = await self.session.scalar(
            select(SupplyRequest)
            .where(SupplyRequest.id == data.supply_request_id)
            .options(selectinload(SupplyRequest.items))
        )
        if sr is None:
            raise NotFoundError(f"Besoin {data.supply_request_id} introuvable.")

        await self._ensure_supplier(data.supplier_id)

        # Lignes : celles fournies (ajustées) ou reprise intégrale du besoin sans prix.
        if data.items is not None:
            lines = data.items
        else:
            lines = [
                PurchaseRequestItemCreate(part_id=i.part_id, quantity=i.quantity, unit_price=None)
                for i in sr.items
            ]
        await self._ensure_parts([l.part_id for l in lines])

        last_exc = None
        for _ in range(_MAX_RETRIES):
            number = await self._next_number(data.request_date.year)
            pr = PurchaseRequest(
                bc_number=number,
                supplier_id=data.supplier_id,
                request_date=data.request_date,
                expected_date=data.expected_date,
                notes=data.notes,
                status="draft",
                supply_request_id=sr.id,        # ← le lien de traçabilité
                items=[
                    PurchaseRequestItem(part_id=l.part_id, quantity=l.quantity, unit_price=l.unit_price)
                    for l in lines
                ],
            )
            self.session.add(pr)
            try:
                await self.session.commit()
            except IntegrityError as exc:
                await self.session.rollback()
                if constraint_name(exc) == "uq_purchase_requests_number":
                    last_exc = exc
                    continue
                self._translate(exc)
                raise
            else:
                # Le besoin passe en "en cours" (s'il était encore ouvert).
                await service_supply.mark_in_progress_if_open(sr.id)
                return await self.get_detail(pr.id)
        raise ConflictError("Impossible de générer un numéro de bon unique.") from last_exc

    async def update(self, request_id: UUID, data: PurchaseRequestUpdate) -> dict:
        pr = await self.repo.get_with_items(request_id)
        if pr is None:
            raise NotFoundError(f"Bon de commande {request_id} introuvable.")
        if pr.status == "received":
            raise BusinessRuleError("Un bon déjà réceptionné ne peut plus être modifié.")

        fields = data.model_dump(exclude_unset=True)
        if fields.get("supplier_id") is not None:
            await self._ensure_supplier(fields["supplier_id"])
            pr.supplier_id = fields["supplier_id"]
        if fields.get("request_date") is not None:
            pr.request_date = fields["request_date"]
        if "expected_date" in fields:
            pr.expected_date = fields["expected_date"]
        if "notes" in fields:
            pr.notes = fields["notes"]
        if data.items is not None:
            await self._ensure_parts([i.part_id for i in data.items])
            pr.items.clear()
            await self.session.flush()
            for i in data.items:
                pr.items.append(
                    PurchaseRequestItem(part_id=i.part_id, quantity=i.quantity, unit_price=i.unit_price)
                )
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            self._translate(exc)
            raise
        return await self.get_detail(request_id)

    async def mark_sent(self, request_id: UUID) -> dict:
        pr = await self.get_or_404(request_id)
        if pr.status != "draft":
            raise BusinessRuleError("Seul un bon en brouillon peut être marqué « envoyé ».")
        pr.status = "sent"
        pr.sent_at = datetime.utcnow()
        await self.session.commit()
        return await self.get_detail(request_id)

    async def mark_received(self, request_id: UUID, *, purchase_order_id: UUID | None) -> dict:
        pr = await self.get_or_404(request_id)
        if pr.status not in ("sent", "draft"):
            raise BusinessRuleError("Ce bon est déjà réceptionné.")
        if purchase_order_id is not None:
            if await self.session.scalar(
                select(PurchaseOrder.id).where(PurchaseOrder.id == purchase_order_id)
            ) is None:
                raise NotFoundError(f"Commande {purchase_order_id} introuvable.")
            pr.purchase_order_id = purchase_order_id
        pr.status = "received"
        pr.received_at = datetime.utcnow()
        await self.session.commit()
        return await self.get_detail(request_id)

    async def reopen(self, request_id: UUID) -> dict:
        """Repasse un bon en brouillon (annule envoi/réception)."""
        pr = await self.get_or_404(request_id)
        pr.status = "draft"
        pr.sent_at = None
        pr.received_at = None
        pr.purchase_order_id = None
        await self.session.commit()
        return await self.get_detail(request_id)

    async def delete(self, request_id: UUID) -> None:
        pr = await self.repo.get_with_items(request_id)
        if pr is None:
            raise NotFoundError(f"Bon de commande {request_id} introuvable.")
        await self.session.delete(pr)
        await self.session.commit()

    # --- internes ---
    async def _next_number(self, year: int) -> str:
        prefix = f"BC-{year}-"
        seq = cast(func.split_part(PurchaseRequest.bc_number, "-", 3), Integer)
        last = await self.session.scalar(
            select(func.coalesce(func.max(seq), 0)).where(
                PurchaseRequest.bc_number.like(f"{prefix}%")
            )
        )
        return f"{prefix}{(last or 0) + 1:03d}"

    async def _ensure_supplier(self, supplier_id: UUID) -> None:
        if await self.session.scalar(select(Supplier.id).where(Supplier.id == supplier_id)) is None:
            raise NotFoundError(f"Fournisseur {supplier_id} introuvable.")

    async def _ensure_parts(self, part_ids: list[UUID]) -> None:
        unique = set(part_ids)
        found = set(await self.session.scalars(select(Part.id).where(Part.id.in_(unique))))
        missing = unique - found
        if missing:
            raise NotFoundError(f"Pièce(s) introuvable(s) : {', '.join(str(m) for m in missing)}")

    def _translate(self, exc: IntegrityError) -> None:
        cn = constraint_name(exc)
        if cn == "uq_pr_item_request_part":
            raise ConflictError("Une même pièce ne peut apparaître qu'une fois dans le bon.") from exc
        if cn == "ck_pr_item_quantity_positive":
            raise BusinessRuleError("La quantité doit être supérieure à zéro.") from exc
        if cn and cn.endswith("part_id_fkey"):
            raise NotFoundError("Pièce introuvable.") from exc
        if cn and cn.endswith("supplier_id_fkey"):
            raise NotFoundError("Fournisseur introuvable.") from exc