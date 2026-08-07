from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import constraint_name
from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.core.pagination import paginate
from app.models.payment_request import PaymentRequest
from app.models.purchase_order import PurchaseOrder
from app.models.supplier import Supplier
from app.repositories.payment_request import PaymentRequestRepository
from app.schemas.payment_request import (
    PaymentRequestCreate,
    PaymentRequestUpdate,
)

_MAX_RETRIES = 5


def serialize(pr: PaymentRequest) -> dict:
    return {
        "id": pr.id,
        "request_number": pr.request_number,
        "title": pr.title,
        "amount": pr.amount,
        "request_date": pr.request_date,
        "link": pr.link,
        "odoo_reference": pr.odoo_reference,
        "priority": pr.priority,
        "status": pr.status,
        "supplier": {"id": pr.supplier.id, "name": pr.supplier.name},
        "notes": pr.notes,
        "paid_at": pr.paid_at,
        "created_at": pr.created_at,
    }


class PaymentRequestService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = PaymentRequestRepository(session)

    async def get_or_404(self, request_id: UUID) -> PaymentRequest:
        pr = await self.repo.get_detail(request_id)
        if pr is None:
            raise NotFoundError(f"Demande de paiement {request_id} introuvable.")
        return pr

    async def get_detail(self, request_id: UUID) -> dict:
        return serialize(await self.get_or_404(request_id))

    async def list_payments(self, *, search, status, priority, supplier_id, start_date, end_date, page, limit):
        stmt = self.repo.filtered_stmt(
            search=search, status=status, priority=priority,
            supplier_id=supplier_id, start_date=start_date, end_date=end_date,
        ).order_by(PaymentRequest.request_date.desc(), PaymentRequest.request_number.desc())
        items, total = await paginate(self.session, stmt, page=page, limit=limit)
        return [serialize(pr) for pr in items], total

    async def create(self, data: PaymentRequestCreate) -> dict:
        await self._ensure_supplier(data.supplier_id)
        pr = PaymentRequest(
            title=data.title.strip(),
            amount=data.amount,
            request_date=data.request_date,
            link=(data.link or None),
            odoo_reference=(data.odoo_reference or None),
            priority=data.priority,
            supplier_id=data.supplier_id,
            notes=data.notes,
        )
        return await self._persist_new(pr)


    async def update(self, request_id: UUID, data: PaymentRequestUpdate) -> dict:
        pr = await self.get_or_404(request_id)
        if pr.status == "paid":
            raise BusinessRuleError("Une demande déjà payée ne peut plus être modifiée.")
        fields = data.model_dump(exclude_unset=True)
        if fields.get("title") is not None:
            pr.title = fields["title"].strip()
        if fields.get("amount") is not None:
            pr.amount = fields["amount"]
        if fields.get("request_date") is not None:
            pr.request_date = fields["request_date"]
        if "link" in fields:
            pr.link = fields["link"] or None
        if "odoo_reference" in fields:
            pr.odoo_reference = fields["odoo_reference"] or None
        if fields.get("priority") is not None:
            pr.priority = fields["priority"]
        if "notes" in fields:
            pr.notes = fields["notes"]
        await self.session.commit()
        await self.session.refresh(pr)
        return serialize(pr)

    async def mark_paid(self, request_id: UUID) -> dict:
        pr = await self.get_or_404(request_id)
        if pr.status == "paid":
            raise BusinessRuleError("Cette demande est déjà marquée comme payée.")
        pr.status = "paid"
        pr.paid_at = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(pr)
        return serialize(pr)

    async def mark_unpaid(self, request_id: UUID) -> dict:
        pr = await self.get_or_404(request_id)
        pr.status = "to_pay"
        pr.paid_at = None
        await self.session.commit()
        await self.session.refresh(pr)
        return serialize(pr)

    async def delete(self, request_id: UUID) -> None:
        pr = await self.get_or_404(request_id)
        await self.repo.delete(pr)
        await self.session.commit()

    # --- internes ---
    async def _persist_new(self, pr: PaymentRequest) -> dict:
        last_exc = None
        for _ in range(_MAX_RETRIES):
            pr.request_number = await self._next_number(pr.request_date.year)
            self.session.add(pr)
            try:
                await self.session.commit()
            except IntegrityError as exc:
                await self.session.rollback()
                if constraint_name(exc) == "uq_payment_requests_number":
                    last_exc = exc
                    continue
                raise
            else:
                await self.session.refresh(pr)
                return serialize(await self.get_or_404(pr.id))
        raise ConflictError("Impossible de générer un numéro de demande unique.") from last_exc

    async def _next_number(self, year: int) -> str:
        prefix = f"DP-{year}-"
        seq = cast(func.split_part(PaymentRequest.request_number, "-", 3), Integer)
        last = await self.session.scalar(
            select(func.coalesce(func.max(seq), 0)).where(
                PaymentRequest.request_number.like(f"{prefix}%")
            )
        )
        return f"{prefix}{(last or 0) + 1:03d}"

    async def _ensure_supplier(self, supplier_id: UUID) -> None:
        if await self.session.scalar(select(Supplier.id).where(Supplier.id == supplier_id)) is None:
            raise NotFoundError(f"Fournisseur {supplier_id} introuvable.")
