from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.db import constraint_name
from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.core.pagination import paginate
from app.models.sales import (
    SalesClient, SalesOrder, SalesOrderItem,
    SalesPayment, SalesPaymentAllocation,
)
from app.services._sales_balance import allocated_by_order
from app.core.tax import ttc_amount

_MAX_RETRIES = 5


def _sale_total_ht(so: SalesOrder) -> Decimal:
    return sum((it.sale_price * it.quantity for it in so.items), Decimal("0"))

def _sale_total_ttc(so: SalesOrder) -> Decimal:
    return ttc_amount(_sale_total_ht(so))


class SalesPaymentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---------- lecture ----------
    def _serialize(self, p: SalesPayment, sale_numbers: dict[UUID, str]) -> dict:
        return {
            "id": p.id,
            "payment_number": p.payment_number,
            "client_id": p.client_id,
            "client_name": p.client.name,
            "payment_date": p.payment_date,
            "amount": p.amount,
            "method": p.method,
            "notes": p.notes,
            "allocations": [
                {
                    "sales_order_id": a.sales_order_id,
                    "sale_number": sale_numbers.get(a.sales_order_id, "—"),
                    "amount": a.amount,
                }
                for a in p.allocations
            ],
            "created_at": p.created_at,
        }

    async def _payment_detail(self, p: SalesPayment) -> dict:
        order_ids = [a.sales_order_id for a in p.allocations]
        numbers = {}
        if order_ids:
            rows = await self.session.execute(
                select(SalesOrder.id, SalesOrder.sale_number).where(SalesOrder.id.in_(order_ids))
            )
            numbers = {oid: num for oid, num in rows.all()}
        return self._serialize(p, numbers)

    async def get_or_404(self, payment_id: UUID) -> SalesPayment:
        p = await self.session.scalar(
            select(SalesPayment)
            .where(SalesPayment.id == payment_id)
            .options(selectinload(SalesPayment.allocations), selectinload(SalesPayment.client))
        )
        if p is None:
            raise NotFoundError(f"Paiement {payment_id} introuvable.")
        return p

    async def list_payments(self, *, client_id, start_date, end_date, page, limit):
        stmt = (
            select(SalesPayment)
            .options(selectinload(SalesPayment.allocations), selectinload(SalesPayment.client))
            .order_by(SalesPayment.payment_date.desc(), SalesPayment.payment_number.desc())
        )
        if client_id:
            stmt = stmt.where(SalesPayment.client_id == client_id)
        if start_date is not None:
            stmt = stmt.where(SalesPayment.payment_date >= start_date)
        if end_date is not None:
            stmt = stmt.where(SalesPayment.payment_date <= end_date)
        items, total = await paginate(self.session, stmt, page=page, limit=limit)
        out = [await self._payment_detail(p) for p in items]
        return out, total

    # ---------- création avec imputation automatique ----------
    async def create(self, data) -> dict:
        client = await self.session.get(SalesClient, data.client_id)
        if client is None:
            raise NotFoundError(f"Client {data.client_id} introuvable.")

        # Ventes du client, chronologiques, avec leurs lignes (pour le total).
        sales = (await self.session.scalars(
            select(SalesOrder)
            .where(SalesOrder.client_id == data.client_id)
            .options(selectinload(SalesOrder.items))
            .order_by(SalesOrder.sale_date.asc(), SalesOrder.sale_number.asc())
        )).all()

        allocated = await allocated_by_order(self.session, [s.id for s in sales])

        # Reste dû par vente, dans l'ordre.
        remaining_by_sale = []
        total_due = Decimal("0")
        for s in sales:
            rem = _sale_total_ttc(s) - allocated.get(s.id, Decimal("0"))
            if rem > 0:
                remaining_by_sale.append((s, rem))
                total_due += rem

        amount = Decimal(data.amount)
        if total_due == 0:
            raise BusinessRuleError("Ce client n'a aucune vente impayée.")
        if amount > total_due:
            raise BusinessRuleError(
                f"Le montant ({amount}) dépasse le total dû par le client ({total_due})."
            )

        # Imputation : on remplit les ventes de la plus ancienne à la plus récente.
        allocations: list[tuple[UUID, Decimal]] = []
        left = amount
        for s, rem in remaining_by_sale:
            if left <= 0:
                break
            take = min(left, rem)
            allocations.append((s.id, take))
            left -= take

        last_exc = None
        for _ in range(_MAX_RETRIES):
            number = await self._next_number(data.payment_date.year)
            payment = SalesPayment(
                payment_number=number,
                client_id=data.client_id,
                payment_date=data.payment_date,
                amount=amount,
                method=data.method,
                notes=data.notes,
                allocations=[
                    SalesPaymentAllocation(sales_order_id=oid, amount=amt)
                    for oid, amt in allocations
                ],
            )
            self.session.add(payment)
            try:
                await self.session.commit()
            except IntegrityError as exc:
                await self.session.rollback()
                if constraint_name(exc) == "uq_sales_payments_number":
                    last_exc = exc
                    continue
                raise
            else:
                await self.session.refresh(payment)
                full = await self.get_or_404(payment.id)
                return await self._payment_detail(full)
        raise ConflictError("Impossible de générer un numéro de paiement unique.") from last_exc

    async def delete(self, payment_id: UUID) -> None:
        p = await self.get_or_404(payment_id)
        await self.session.delete(p)   # cascade → allocations supprimées → ventes libérées
        await self.session.commit()

    async def _next_number(self, year: int) -> str:
        prefix = f"PAY-{year}-"
        seq = cast(func.split_part(SalesPayment.payment_number, "-", 3), Integer)
        last = await self.session.scalar(
            select(func.coalesce(func.max(seq), 0)).where(
                SalesPayment.payment_number.like(f"{prefix}%")
            )
        )
        return f"{prefix}{(last or 0) + 1:03d}"

    # ---------- grand livre ----------
    async def client_ledger(self, client_id: UUID) -> dict:
        client = await self.session.get(SalesClient, client_id)
        if client is None:
            raise NotFoundError(f"Client {client_id} introuvable.")

        sales = (await self.session.scalars(
            select(SalesOrder)
            .where(SalesOrder.client_id == client_id)
            .options(selectinload(SalesOrder.items))
            .order_by(SalesOrder.sale_date.asc(), SalesOrder.sale_number.asc())
        )).all()
        payments = (await self.session.scalars(
            select(SalesPayment)
            .where(SalesPayment.client_id == client_id)
            .order_by(SalesPayment.payment_date.asc(), SalesPayment.payment_number.asc())
        )).all()

        allocated = await allocated_by_order(self.session, [s.id for s in sales])

        total_sold = Decimal("0")
        unpaid = []
        for s in sales:
            tot = _sale_total_ttc(s)
            paid = allocated.get(s.id, Decimal("0"))
            rem = tot - paid
            total_sold += tot
            if rem > 0:
                unpaid.append({
                    "id": s.id, "sale_number": s.sale_number, "sale_date": s.sale_date,
                    "total_sale": tot, "paid": paid, "remaining": rem,
                })

        total_paid = sum((p.amount for p in payments), Decimal("0"))

        # Relevé chronologique : ventes (débit) + paiements (crédit), solde courant.
        events = []
        for s in sales:
            events.append((s.sale_date, 0, "sale", s.sale_number, _sale_total_ttc(s), None))
        for p in payments:
            events.append((p.payment_date, 1, "payment", p.payment_number, None, p.amount))
        # tri par date puis ventes avant paiements le même jour (ordre 0/1)
        events.sort(key=lambda e: (e[0], e[1], e[3]))

        entries = []
        balance = Decimal("0")
        for ev_date, _o, kind, ref, debit, credit in events:
            if debit is not None:
                balance += debit
            if credit is not None:
                balance -= credit
            entries.append({
                "date": ev_date, "kind": kind, "ref": ref,
                "debit": debit, "credit": credit, "running_balance": balance,
            })

        return {
            "client_id": client.id,
            "client_name": client.name,
            "total_sold": total_sold,
            "total_paid": total_paid,
            "balance": total_sold - total_paid,
            "unpaid_sales": unpaid,
            "entries": entries,
        }