from datetime import date
from uuid import UUID

from sqlalchemy import select, func, cast, Integer
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import constraint_name
from app.core.exceptions import ConflictError, NotFoundError
from app.core.pagination import paginate
from app.models.part import Part
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_item import PurchaseOrderItem
from app.models.supplier import Supplier
from app.models.vehicle_model import VehicleModel
from app.repositories.part import PartRepository
from app.schemas.part import PartCreate, PartUpdate


def serialize_part(part: Part) -> dict:
    models = [
        {"id": m.id, "name": m.name, "brand_id": m.brand_id, "brand_name": m.brand.name}
        for m in part.vehicle_models
    ]
    return {
        "id": part.id,
        "reference": part.reference,
        "designation": part.designation,
        "category": part.category,
        "vehicle_models": models,
        "is_universal": len(models) == 0,
        "created_at": part.created_at,
        "updated_at": part.updated_at,
    }


class PartService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = PartRepository(session)

    async def get_or_404(self, part_id: UUID) -> Part:
        part = await self.repo.get_with_relations(part_id)
        if part is None:
            raise NotFoundError(f"Pièce {part_id} introuvable.")
        return part

    async def get_detail(self, part_id: UUID) -> dict:
        return serialize_part(await self.get_or_404(part_id))

    async def list_parts(self, *, search, brand_id, vehicle_model_id, universal, page, limit):
        stmt = self.repo.search_stmt(
            search=search, brand_id=brand_id,
            vehicle_model_id=vehicle_model_id, universal=universal,
        )
        items, total = await paginate(self.session, stmt, page=page, limit=limit)
        return [serialize_part(p) for p in items], total

    async def create(self, data: PartCreate) -> dict:
        models = await self._resolve_models(data.vehicle_model_ids)
        ref = (data.reference or "").strip()

        for _ in range(5):
            if not ref:
                ref = await self.next_reference()
            part = Part(
                reference=ref,
                designation=data.designation.strip(),
                category=(data.category.strip() or None) if data.category else None,
            )
            part.vehicle_models = models
            self.session.add(part)
            try:
                await self.session.commit()
            except IntegrityError as exc:
                await self.session.rollback()
                if constraint_name(exc) in {"uq_parts_reference", "ix_parts_reference"}:
                    # collision : si la réf venait de l'auto-génération, on regénère ;
                    # si elle était saisie manuellement, c'est une vraie erreur.
                    if not (data.reference or "").strip():
                        ref = ""   # vide → regénère au tour suivant
                        continue
                    raise ConflictError(f"La référence « {ref} » existe déjà.") from exc
                raise
            await self.session.refresh(part)
            part = await self.repo.get_with_relations(part.id)
            return serialize_part(part)

        raise ConflictError("Impossible de générer une référence unique.")

    async def update(self, part_id: UUID, data: PartUpdate) -> dict:
        part = await self.get_or_404(part_id)
        fields = data.model_dump(exclude_unset=True)

        if fields.get("reference") is not None:
            part.reference = fields["reference"].strip()
        if fields.get("designation") is not None:
            part.designation = fields["designation"].strip()
        if "category" in fields:
            v = fields["category"]
            part.category = (v.strip() or None) if v else None
        if "vehicle_model_ids" in fields and fields["vehicle_model_ids"] is not None:
            part.vehicle_models = await self._resolve_models(fields["vehicle_model_ids"])

        await self._commit(reference=part.reference)
        await self.session.refresh(part)
        return serialize_part(part)

    async def delete(self, part_id: UUID) -> None:
        part = await self.get_or_404(part_id)
        await self.repo.delete(part)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError(
                "Impossible de supprimer cette pièce : elle figure dans des commandes."
            ) from exc

    async def order_history(self, part_id, *, start_date, end_date, supplier_id) -> list[dict]:
        await self.get_or_404(part_id)
        stmt = (
            select(
                PurchaseOrder.order_date,
                PurchaseOrder.order_number,
                Supplier.name.label("supplier_name"),
                PurchaseOrderItem.quantity,
                PurchaseOrderItem.unit_price,
            )
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderItem.purchase_order_id)
            .join(Supplier, Supplier.id == PurchaseOrder.supplier_id)
            .where(PurchaseOrderItem.part_id == part_id)
            .order_by(PurchaseOrder.order_date.desc(), PurchaseOrder.order_number.desc())
        )
        if start_date is not None:
            stmt = stmt.where(PurchaseOrder.order_date >= start_date)
        if end_date is not None:
            stmt = stmt.where(PurchaseOrder.order_date <= end_date)
        if supplier_id is not None:
            stmt = stmt.where(PurchaseOrder.supplier_id == supplier_id)

        rows = (await self.session.execute(stmt)).all()
        return [
            {
                "order_date": r.order_date,
                "order_number": r.order_number,
                "supplier_name": r.supplier_name,
                "quantity": r.quantity,
                "unit_price": r.unit_price,
                "line_total": r.unit_price * r.quantity if r.unit_price is not None else None,
            }
            for r in rows
        ]

    async def _resolve_models(self, ids: list[UUID]) -> list[VehicleModel]:
        if not ids:
            return []
        unique = list(dict.fromkeys(ids))
        models = list(
            await self.session.scalars(select(VehicleModel).where(VehicleModel.id.in_(unique)))
        )
        missing = set(unique) - {m.id for m in models}
        if missing:
            raise NotFoundError(f"Modèle(s) introuvable(s) : {', '.join(str(m) for m in missing)}")
        return models

    async def _commit(self, *, reference: str) -> None:
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if constraint_name(exc) in {"uq_parts_reference", "ix_parts_reference"}:
                raise ConflictError(f"La référence « {reference} » existe déjà.") from exc
            raise
        
    async def next_reference(self) -> str:
        """Prochaine référence auto : PCE-0001, PCE-0002… (ignore les réf d'un autre format)."""
        prefix = "PCE-"
        seq = cast(func.split_part(Part.reference, "-", 2), Integer)
        last = await self.session.scalar(
            select(func.coalesce(func.max(seq), 0)).where(
                Part.reference.op("~")(r'^PCE-\d+$')
            )
        )
        return f"{prefix}{(last or 0) + 1:04d}"
    
    def _classify_error(self, exc: Exception) -> tuple[str, str]:
        """Traduit une exception en (type, message) pour le rapport bulk."""
        from app.core.exceptions import ConflictError, NotFoundError, BusinessRuleError
        if isinstance(exc, ConflictError):
            return "conflict", str(exc)
        if isinstance(exc, NotFoundError):
            return "not_found", str(exc)
        if isinstance(exc, BusinessRuleError):
            return "business_rule", str(exc)
        return "error", str(exc)

    async def _bulk_references(self, count: int, manual_refs: set[str]) -> list[str]:
        """Génère `count` références PCE-nnnn en série, en évitant les réf manuelles du lot."""
        seq = cast(func.split_part(Part.reference, "-", 2), Integer)
        last = await self.session.scalar(
            select(func.coalesce(func.max(seq), 0)).where(
                Part.reference.op("~")(r'^PCE-\d+$')
            )
        )
        n = (last or 0) + 1
        manual_lower = {r.lower() for r in manual_refs}
        refs = []
        while len(refs) < count:
            candidate = f"PCE-{n:04d}"
            n += 1
            if candidate.lower() in manual_lower:
                continue
            refs.append(candidate)
        return refs

    async def bulk_create(self, atomic: bool, items: list) -> dict:
        # Références manuelles saisies dans le lot (pour éviter collision avec l'auto)
        manual_refs = {
            (it.reference or "").strip()
            for it in items
            if (it.reference or "").strip()
        }
        # Nombre d'items sans référence → à auto-générer
        auto_count = sum(1 for it in items if not (it.reference or "").strip())
        auto_refs = await self._bulk_references(auto_count, manual_refs) if auto_count else []
        auto_iter = iter(auto_refs)

        # Attribution des références (manuelle ou auto) à chaque item, dans l'ordre
        resolved_refs: list[str] = []
        for it in items:
            ref = (it.reference or "").strip()
            resolved_refs.append(ref if ref else next(auto_iter))

        succeeded = []
        failed = []

        if atomic:
            # Tout dans une transaction : au premier échec, rollback total.
            try:
                for idx, (it, ref) in enumerate(zip(items, resolved_refs)):
                    models = await self._resolve_models(it.vehicle_model_ids)
                    part = Part(
                        reference=ref,
                        designation=it.designation.strip(),
                        category=(it.category.strip() or None) if it.category else None,
                    )
                    part.vehicle_models = models
                    self.session.add(part)
                    await self.session.flush()   # détecte les conflits sans commit
                await self.session.commit()
                # recharger pour la sérialisation
                for it, ref in zip(items, resolved_refs):
                    pass  # les parts sont déjà en session
                # on récupère les parts créés (ordre préservé)
                created = await self._fetch_by_refs(resolved_refs)
                succeeded = [self._serialize_bulk(p) for p in created]
                return self._envelope(len(items), succeeded, failed, atomic=True, committed=True)
            except IntegrityError as exc:
                await self.session.rollback()
                etype, emsg = ("conflict", "Référence en doublon.") \
                    if constraint_name(exc) in {"uq_parts_reference", "ix_parts_reference"} \
                    else ("error", "Erreur d'intégrité.")
                # en atomique, tout échoue : on reporte l'erreur globale sur la 1re ligne
                failed = [{"index": 0, "input": items[0], "error": {"type": etype, "message": emsg}}]
                return self._envelope(len(items), [], failed, atomic=True, committed=False)
            except Exception as exc:
                await self.session.rollback()
                etype, emsg = self._classify_error(exc)
                failed = [{"index": 0, "input": items[0], "error": {"type": etype, "message": emsg}}]
                return self._envelope(len(items), [], failed, atomic=True, committed=False)

        # --- Mode partiel : chaque pièce indépendante ---
        for idx, (it, ref) in enumerate(zip(items, resolved_refs)):
            try:
                models = await self._resolve_models(it.vehicle_model_ids)
                part = Part(
                    reference=ref,
                    designation=it.designation.strip(),
                    category=(it.category.strip() or None) if it.category else None,
                )
                part.vehicle_models = models
                self.session.add(part)
                await self.session.commit()
                await self.session.refresh(part)
                part = await self.repo.get_with_relations(part.id)
                succeeded.append(self._serialize_bulk(part))
            except IntegrityError as exc:
                await self.session.rollback()
                etype, emsg = ("conflict", f"La référence « {ref} » existe déjà.") \
                    if constraint_name(exc) in {"uq_parts_reference", "ix_parts_reference"} \
                    else ("error", "Erreur d'intégrité.")
                failed.append({"index": idx, "input": it, "error": {"type": etype, "message": emsg}})
            except Exception as exc:
                await self.session.rollback()
                etype, emsg = self._classify_error(exc)
                failed.append({"index": idx, "input": it, "error": {"type": etype, "message": emsg}})

        return self._envelope(len(items), succeeded, failed, atomic=False, committed=len(succeeded) > 0)

    def _serialize_bulk(self, part: Part) -> dict:
        return {
            "id": part.id,
            "reference": part.reference,
            "designation": part.designation,
            "category": part.category,
            "is_universal": len(part.vehicle_models) == 0,
        }

    async def _fetch_by_refs(self, refs: list[str]) -> list[Part]:
        rows = await self.session.scalars(
            select(Part).where(Part.reference.in_(refs))
        )
        by_ref = {p.reference: p for p in rows}
        return [by_ref[r] for r in refs if r in by_ref]

    def _envelope(self, total, succeeded, failed, *, atomic, committed) -> dict:
        return {
            "summary": {
                "total": total,
                "succeeded": len(succeeded),
                "failed": len(failed),
                "atomic": atomic,
                "committed": committed,
            },
            "succeeded": succeeded,
            "failed": failed,
        }