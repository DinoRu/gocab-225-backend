from datetime import date
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import Integer, cast, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.db import constraint_name
from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.core.pagination import paginate
from app.models.inventory import InventoryCount, InventoryCountItem
from app.models.inventory_audit import InventoryAuditLog
from app.models.part import Part
from app.repositories.inventory import InventoryRepository
from app.schemas.inventory import InventoryCountCreate, InventoryCountEdit, InventoryCountUpdate

_MAX_RETRIES = 5


class InventoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = InventoryRepository(session)

    # ---------- lecture ----------
    async def get_or_404(self, count_id: UUID) -> InventoryCount:
        count = await self.repo.get_detail(count_id)
        if count is None:
            raise NotFoundError(f"Comptage {count_id} introuvable.")
        return count

    async def get_detail(self, count_id: UUID) -> dict:
        count = await self.get_or_404(count_id)
        return await self._serialize(count)

    async def list_counts(self, *, search, start_date, end_date, page, limit):
        stmt = self.repo.list_stmt(search=search, start_date=start_date, end_date=end_date)
        items, total = await paginate(self.session, stmt, page=page, limit=limit)
        return [await self._serialize(c) for c in items], total

    async def part_history(self, part_id: UUID) -> list[dict]:
        await self._ensure_part(part_id)
        history = await self.repo.part_history(part_id)
        out: list[dict] = []
        prev_qty: int | None = None
        prev_date: date | None = None
        for item in history:
            cdate = item.count.count_date
            entries = 0
            outflow = None
            anomaly = False
            if prev_qty is not None and prev_date is not None:
                entries = await self.repo.entries_between(
                    part_id, after_date=prev_date, up_to_date=cdate
                )
                outflow = prev_qty + entries - item.counted_quantity
                anomaly = outflow < 0
            out.append({
                "count_number": item.count.count_number,
                "count_date": cdate,
                "counted_quantity": item.counted_quantity,
                "previous_quantity": prev_qty,
                "entries_between": entries,
                "outflow": outflow,
                "anomaly": anomaly,
            })
            prev_qty = item.counted_quantity
            prev_date = cdate
        return out

    # ---------- écriture -------------------------------------
    async def create(self, data: InventoryCountCreate) -> dict:
        await self._ensure_parts([i.part_id for i in data.items])
        last_exc = None
        for _ in range(_MAX_RETRIES):
            number = await self._next_number(data.count_date.year)
            count = InventoryCount(
                count_number=number,
                count_date=data.count_date,
                notes=data.notes,
                items=[
                    InventoryCountItem(part_id=i.part_id, counted_quantity=i.counted_quantity)
                    for i in data.items
                ],
            )
            self.session.add(count)
            try:
                await self.session.commit()
            except IntegrityError as exc:
                await self.session.rollback()
                cn = constraint_name(exc)
                if cn == "uq_inventory_counts_number":
                    last_exc = exc
                    continue
                self._translate(exc)
                raise
            else:
                return await self.get_detail(count.id)
        raise ConflictError("Impossible de générer un numéro de comptage unique.") from last_exc

    # async def update(self, count_id: UUID, data: InventoryCountUpdate) -> dict:
    #     count = await self.repo.get_with_items(count_id)
    #     if count is None:
    #         raise NotFoundError(f"Comptage {count_id} introuvable.")
    #     fields = data.model_dump(exclude_unset=True)
    #     if fields.get("count_date") is not None:
    #         count.count_date = fields["count_date"]
    #     if "notes" in fields:
    #         count.notes = fields["notes"]
    #     if data.items is not None:
    #         await self._ensure_parts([i.part_id for i in data.items])
    #         count.items.clear()
    #         await self.session.flush()
    #         for i in data.items:
    #             count.items.append(
    #                 InventoryCountItem(part_id=i.part_id, counted_quantity=i.counted_quantity)
    #             )
    #     try:
    #         await self.session.commit()
    #     except IntegrityError as exc:
    #         await self.session.rollback()
    #         self._translate(exc)
    #         raise
    #     return await self.get_detail(count_id)

    async def delete(self, count_id: UUID) -> None:
        count = await self.repo.get_with_items(count_id)
        if count is None:
            raise NotFoundError(f"Comptage {count_id} introuvable.")
        await self.session.delete(count)
        await self.session.commit()

    # ---------- calcul ----------
    async def _serialize(self, count: InventoryCount) -> dict:
        items_out = []
        for item in count.items:
            prev = await self.repo.previous_count_item(
                item.part_id, before_date=count.count_date, exclude_count_id=count.id
            )
            if prev is None:
                # Premier comptage de cette pièce : sert de base, pas de calcul.
                items_out.append({
                    "id": item.id,
                    "part_id": item.part_id,
                    "reference": item.part.reference,
                    "designation": item.part.designation,
                    "counted_quantity": item.counted_quantity,
                    "previous_quantity": None,
                    "previous_count_date": None,
                    "entries_between": 0,
                    "outflow": None,
                    "anomaly": False,
                })
                continue
            prev_qty, prev_date = prev
            entries = await self.repo.entries_between(
                item.part_id, after_date=prev_date, up_to_date=count.count_date
            )
            outflow = prev_qty + entries - item.counted_quantity
            items_out.append({
                "id": item.id,
                "part_id": item.part_id,
                "reference": item.part.reference,
                "designation": item.part.designation,
                "counted_quantity": item.counted_quantity,
                "previous_quantity": prev_qty,
                "previous_count_date": prev_date,
                "entries_between": entries,
                "outflow": outflow,
                "anomaly": outflow < 0,
            })
        # tri par référence pour un affichage stable
        items_out.sort(key=lambda x: x["reference"])
        return {
            "id": count.id,
            "count_number": count.count_number,
            "count_date": count.count_date,
            "notes": count.notes,
            "items": items_out,
            "created_at": count.created_at,
        }

    # ---------- internes ----------
    async def _next_number(self, year: int) -> str:
        prefix = f"INV-{year}-"
        seq = cast(func.split_part(InventoryCount.count_number, "-", 3), Integer)
        last = await self.session.scalar(
            select(func.coalesce(func.max(seq), 0)).where(
                InventoryCount.count_number.like(f"{prefix}%")
            )
        )
        return f"{prefix}{(last or 0) + 1:03d}"

    async def _ensure_part(self, part_id: UUID) -> None:
        if await self.session.scalar(select(Part.id).where(Part.id == part_id)) is None:
            raise NotFoundError(f"Pièce {part_id} introuvable.")

    async def _ensure_parts(self, part_ids: list[UUID]) -> None:
        unique = set(part_ids)
        found = set(await self.session.scalars(select(Part.id).where(Part.id.in_(unique))))
        missing = unique - found
        if missing:
            raise NotFoundError(f"Pièce(s) introuvable(s) : {', '.join(str(m) for m in missing)}")

    def _translate(self, exc: IntegrityError) -> None:
        cn = constraint_name(exc)
        if cn == "uq_count_item_count_part":
            raise ConflictError("Une même pièce ne peut apparaître qu'une fois dans le comptage.") from exc
        if cn == "ck_count_item_qty_nonneg":
            raise BusinessRuleError("La quantité comptée ne peut pas être négative.") from exc
        if cn and cn.endswith("part_id_fkey"):
            raise NotFoundError("Pièce introuvable.") from exc
        
    
    async def _get_with_items(self, count_id: UUID) -> InventoryCount | None:
        return await self.session.scalar(
            select(InventoryCount)
            .where(InventoryCount.id == count_id)
            .options(selectinload(InventoryCount.items).selectinload(InventoryCountItem.part))
        )

    async def _posterior_counts(self, count: InventoryCount, extra_part_ids=()) -> list[dict]:
        """Comptages postérieurs qui dépendent d'une pièce touchée (donc seront recalculés)."""
        part_ids = {it.part_id for it in count.items} | set(extra_part_ids)
        if not part_ids:
            return []
        rows = await self.session.execute(
            select(InventoryCount.id, InventoryCount.count_number, InventoryCount.count_date)
            .join(InventoryCountItem, InventoryCountItem.inventory_count_id == InventoryCount.id)
            .where(
                InventoryCountItem.part_id.in_(part_ids),
                InventoryCount.count_date > count.count_date,
            )
            .distinct()
            .order_by(InventoryCount.count_date)
        )
        return [
            {"id": r.id, "count_number": r.count_number, "count_date": r.count_date}
            for r in rows.all()
        ]

    async def edit_impact(self, count_id: UUID) -> dict:
        count = await self._get_with_items(count_id)
        if count is None:
            raise NotFoundError(f"Comptage {count_id} introuvable.")
        posterior = await self._posterior_counts(count)
        is_leaf = len(posterior) == 0
        return {"is_leaf": is_leaf, "editable_by_magazinier": is_leaf, "posterior": posterior}

    async def update_count(
        self, count_id: UUID, data: InventoryCountEdit, *, user_id: UUID, username: str, role: str
    ) -> dict:
        count = await self._get_with_items(count_id)
        if count is None:
            raise NotFoundError(f"Comptage {count_id} introuvable.")

        new_by_part = {i.part_id: i for i in data.items}
        await self._ensure_parts(list(new_by_part.keys()))
        old_by_part = {it.part_id: it for it in count.items}

        # Parties touchées = anciennes ∪ nouvelles → détermine la dépendance postérieure
        added_ids = [pid for pid in new_by_part if pid not in old_by_part]
        posterior = await self._posterior_counts(count, extra_part_ids=added_ids)

        # RÈGLE D'ACCÈS : feuille → admin + magazinier ; non-feuille → admin seul
        if role != "admin" and posterior:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Ce comptage a des comptages postérieurs qui en dépendent : "
                       "seul un administrateur peut le corriger.",
            )

        # Références pour les messages d'audit
        ref_map = {it.part_id: it.part.reference for it in count.items}
        missing_refs = [pid for pid in new_by_part if pid not in ref_map]
        if missing_refs:
            rows = await self.session.execute(
                select(Part.id, Part.reference).where(Part.id.in_(missing_refs))
            )
            for pid, ref in rows.all():
                ref_map[pid] = ref

        changes: list[str] = []

        # Modifications & ajouts
        for pid, new_line in new_by_part.items():
            ref = ref_map.get(pid, str(pid))
            old = old_by_part.get(pid)
            if old is None:
                count.items.append(InventoryCountItem(
                    part_id=pid, counted_quantity=new_line.counted_quantity,
                ))
                changes.append(f"＋ Ajout ligne « {ref} » (compté {new_line.counted_quantity})")
            elif old.counted_quantity != new_line.counted_quantity:
                changes.append(
                    f"Ligne « {ref} » : compté {old.counted_quantity} → {new_line.counted_quantity}"
                )
                old.counted_quantity = new_line.counted_quantity

        # Suppressions
        for pid, old in list(old_by_part.items()):
            if pid not in new_by_part:
                ref = ref_map.get(pid, str(pid))
                changes.append(f"－ Suppression ligne « {ref} »")
                count.items.remove(old)
                await self.session.delete(old)

        if data.notes is not None and data.notes != count.notes:
            count.notes = data.notes

        if changes:
            self.session.add(InventoryAuditLog(
                inventory_count_id=count.id, user_id=user_id, username=username, changes=changes,
            ))

        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("Modification impossible (contrainte violée).") from exc

        return await self.get_detail(count_id)   # ← ta méthode de lecture recalculée

    async def list_audit(self, count_id: UUID) -> list[InventoryAuditLog]:
        rows = await self.session.scalars(
            select(InventoryAuditLog)
            .where(InventoryAuditLog.inventory_count_id == count_id)
            .order_by(InventoryAuditLog.created_at.desc())
        )
        return list(rows)