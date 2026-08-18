from datetime import date
from decimal import Decimal
from uuid import UUID

from dateutil.relativedelta import relativedelta
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sales import (
    SalesClient, SalesOrder, SalesOrderItem, SalesPayment, SalesPaymentAllocation,
)
from app.core.tax import vat_amount, ttc_amount




class SalesDashboardService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _window(months: int) -> tuple[date, date]:
        today = date.today()
        return today - relativedelta(months=months), today

    async def build(self, *, months: int) -> dict:
        start, end = self._window(months)

        # --- CA, dépenses (achats), bénéfice : sur les ventes de la période ---
        # On agrège les lignes des ventes dont la date est dans la fenêtre.
        line_totals = await self.session.execute(
            select(
                func.coalesce(func.sum(SalesOrderItem.sale_price * SalesOrderItem.quantity), 0),
                func.coalesce(func.sum(SalesOrderItem.purchase_price * SalesOrderItem.quantity), 0),
            )
            .select_from(SalesOrderItem)
            .join(SalesOrder, SalesOrder.id == SalesOrderItem.sales_order_id)
            .where(SalesOrder.sale_date >= start, SalesOrder.sale_date <= end)
        )
        ca, depenses = line_totals.one()
        ca = Decimal(ca)
        # après avoir calculé ca (total HT de la période) :
        tva_collectee = vat_amount(ca)
        depenses = Decimal(depenses)
        benefice = ca - depenses

        # --- Créances : total dû par TOUS les clients (indépendant de la période) ---
        # somme des ventes - somme des imputations, sur tout l'historique.
        total_sold_all = await self.session.scalar(
            select(func.coalesce(func.sum(SalesOrderItem.sale_price * SalesOrderItem.quantity), 0))
        )
        total_paid_all = await self.session.scalar(
            select(func.coalesce(func.sum(SalesPaymentAllocation.amount), 0))
        )
        total_sold_ht = Decimal(total_sold_all)
        total_sold_ttc = ttc_amount(total_sold_ht)
        creances = total_sold_ttc - Decimal(total_paid_all)

        # --- CA + bénéfice par mois (fenêtre) ---
        month_col = func.to_char(SalesOrder.sale_date, "YYYY-MM")
        monthly = await self.session.execute(
            select(
                month_col.label("month"),
                func.coalesce(func.sum(SalesOrderItem.sale_price * SalesOrderItem.quantity), 0),
                func.coalesce(func.sum(
                    (SalesOrderItem.sale_price - SalesOrderItem.purchase_price) * SalesOrderItem.quantity
                ), 0),
            )
            .select_from(SalesOrderItem)
            .join(SalesOrder, SalesOrder.id == SalesOrderItem.sales_order_id)
            .where(SalesOrder.sale_date >= start, SalesOrder.sale_date <= end)
            .group_by(month_col)
            .order_by(month_col)
        )
        by_month = [
            {"month": m, "ca": Decimal(c), "benefice": Decimal(b)}
            for m, c, b in monthly.all()
        ]

        # --- Top clients par CA (fenêtre) ---
        top = await self.session.execute(
            select(
                SalesClient.id,
                SalesClient.name,
                func.coalesce(func.sum(SalesOrderItem.sale_price * SalesOrderItem.quantity), 0).label("ca"),
            )
            .select_from(SalesOrderItem)
            .join(SalesOrder, SalesOrder.id == SalesOrderItem.sales_order_id)
            .join(SalesClient, SalesClient.id == SalesOrder.client_id)
            .where(SalesOrder.sale_date >= start, SalesOrder.sale_date <= end)
            .group_by(SalesClient.id, SalesClient.name)
            .order_by(func.sum(SalesOrderItem.sale_price * SalesOrderItem.quantity).desc())
            .limit(6)
        )
        top_clients = [
            {
                "client_id": cid,
                "name": name,
                "ca": ttc_amount(Decimal(ca_)),   # ← TTC (HT × 1,18)
            }
            for cid, name, ca_ in top.all()
        ]

        return {
            "period": {"start_date": start, "end_date": end},
            "ca": ca,
            "tva_collectee": tva_collectee, 
            "depenses": depenses,
            "benefice": benefice,
            "creances": creances,
            "by_month": by_month,
            "top_clients": top_clients,
        }