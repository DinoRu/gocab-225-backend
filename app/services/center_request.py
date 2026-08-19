from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.db import constraint_name
from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.core.pagination import paginate
from app.models.center_request import CenterRequest, CenterRequestItem

_MAX_RETRIES = 5


def serialize(req: CenterRequest) -> dict:
    items = [
        {
            "id": it.id,
            "part_id": it.part_id,
            "designation": it.designation,
            "quantity": it.quantity,
            "note": it.note,
            "prepared": it.prepared,
            "from_catalog": it.part_id is not None,
        }
        for it in sorted(req.items, key=lambda x: x.designation)
    ]
    prepared_count = sum(1 for it in req.items if it.prepared)
    return {
        "id": req.id,
        "request_number": req.request_number,
        "vehicle_brand": req.vehicle_brand,
        "vehicle_model": req.vehicle_model,
        "plate_number": req.plate_number,
        "request_date": req.request_date,
        "status": req.status,
        "notes": req.notes,
        "created_by": req.created_by,
        "created_by_name": (req.creator.full_name or req.creator.username) if req.creator else None,
        "items": items,
        "prepared_count": prepared_count,
        "total_items": len(req.items),
        "created_at": req.created_at,
    }


class CenterRequestService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _get(self, request_id: UUID) -> CenterRequest | None:
        return await self.session.scalar(
            select(CenterRequest)
            .where(CenterRequest.id == request_id)
            .options(selectinload(CenterRequest.items), selectinload(CenterRequest.creator))
        )

    async def get_or_404(self, request_id: UUID) -> CenterRequest:
        req = await self._get(request_id)
        if req is None:
            raise NotFoundError(f"Demande {request_id} introuvable.")
        return req

    async def get_detail(self, request_id: UUID) -> dict:
        return serialize(await self.get_or_404(request_id))

    async def list_requests(self, *, status, mine_only, user_id, page, limit):
        stmt = (
            select(CenterRequest)
            .options(selectinload(CenterRequest.items), selectinload(CenterRequest.creator))
            .order_by(CenterRequest.request_date.desc(), CenterRequest.request_number.desc())
        )
        if status:
            stmt = stmt.where(CenterRequest.status == status)
        if mine_only and user_id:
            stmt = stmt.where(CenterRequest.created_by == user_id)
        items, total = await paginate(self.session, stmt, page=page, limit=limit)
        return [serialize(r) for r in items], total

    async def create(self, data, *, user_id: UUID) -> dict:
        last_exc = None
        for _ in range(_MAX_RETRIES):
            number = await self._next_number(data.request_date.year)
            req = CenterRequest(
                request_number=number,
                vehicle_brand=data.vehicle_brand.strip(),
                vehicle_model=data.vehicle_model.strip(),
                plate_number=(data.plate_number or "").strip() or None,
                request_date=data.request_date,
                status="nouvelle",
                notes=data.notes,
                created_by=user_id,
                items=[
                    CenterRequestItem(
                        part_id=i.part_id,
                        designation=i.designation.strip(),
                        quantity=i.quantity,
                        note=(i.note or "").strip() or None,
                    )
                    for i in data.items
                ],
            )
            self.session.add(req)
            try:
                await self.session.commit()
            except IntegrityError as exc:
                await self.session.rollback()
                if constraint_name(exc) == "uq_center_requests_number":
                    last_exc = exc
                    continue
                raise
            else:
                return await self.get_detail(req.id)
        raise ConflictError("Impossible de générer un numéro de demande unique.") from last_exc

    async def update(self, request_id: UUID, data, *, user_id: UUID, is_admin: bool) -> dict:
        req = await self.get_or_404(request_id)
        # Le centre ne modifie que ses demandes encore 'nouvelle' ; l'admin peut toujours.
        if not is_admin:
            if req.created_by != user_id:
                raise BusinessRuleError("Vous ne pouvez modifier que vos propres demandes.")
            if req.status != "nouvelle":
                raise BusinessRuleError("Cette demande est déjà en préparation et ne peut plus être modifiée.")
        fields = data.model_dump(exclude_unset=True)
        for f in ("vehicle_brand", "vehicle_model", "plate_number", "request_date", "notes"):
            if f in fields and fields[f] is not None:
                setattr(req, f, fields[f])
        if data.items is not None:
            req.items.clear()
            await self.session.flush()
            for i in data.items:
                req.items.append(CenterRequestItem(
                    part_id=i.part_id, designation=i.designation.strip(),
                    quantity=i.quantity, note=(i.note or "").strip() or None,
                ))
        await self.session.commit()
        return await self.get_detail(request_id)

    async def toggle_item(self, request_id: UUID, item_id: UUID, prepared: bool) -> dict:
        req = await self.get_or_404(request_id)
        item = next((it for it in req.items if it.id == item_id), None)
        if item is None:
            raise NotFoundError(f"Ligne {item_id} introuvable dans cette demande.")
        item.prepared = prepared
        await self.session.commit()
        return await self.get_detail(request_id)

    async def set_status(self, request_id: UUID, new_status: str) -> dict:
        req = await self.get_or_404(request_id)
        if new_status not in ("nouvelle", "preparee", "envoyee"):
            raise BusinessRuleError("Statut invalide.")
        req.status = new_status
        if new_status == "preparee":
            req.prepared_at = datetime.utcnow()
        elif new_status == "envoyee":
            req.sent_at = datetime.utcnow()
        await self.session.commit()
        return await self.get_detail(request_id)

    async def delete(self, request_id: UUID, *, user_id: UUID, is_admin: bool) -> None:
        req = await self.get_or_404(request_id)
        if not is_admin and (req.created_by != user_id or req.status != "nouvelle"):
            raise BusinessRuleError("Vous ne pouvez supprimer que vos demandes non encore traitées.")
        await self.session.delete(req)
        await self.session.commit()

    async def _next_number(self, year: int) -> str:
        prefix = f"DEM-{year}-"
        seq = cast(func.split_part(CenterRequest.request_number, "-", 3), Integer)
        last = await self.session.scalar(
            select(func.coalesce(func.max(seq), 0)).where(
                CenterRequest.request_number.like(f"{prefix}%")
            )
        )
        return f"{prefix}{(last or 0) + 1:03d}"

    async def preparation_list(self) -> dict:
        """Liste consolidée des pièces à rassembler (demandes nouvelles + préparées).
        Regroupe par part_id (catalogue) ou par désignation normalisée (libre)."""
        reqs = (await self.session.scalars(
            select(CenterRequest)
            .where(CenterRequest.status.in_(["nouvelle", "preparee"]))
            .options(selectinload(CenterRequest.items))
            .order_by(CenterRequest.request_date.asc())
        )).all()

        # clé de regroupement → agrégat
        groups: dict[str, dict] = {}
        for req in reqs:
            vehicle = f"{req.vehicle_brand} {req.vehicle_model}"
            for it in req.items:
                if it.part_id is not None:
                    key = f"cat:{it.part_id}"
                    from_catalog = True
                else:
                    key = f"free:{' '.join(it.designation.lower().split())}"
                    from_catalog = False

                if key not in groups:
                    groups[key] = {
                        "designation": it.designation,
                        "from_catalog": from_catalog,
                        "total_quantity": 0,
                        "sources": [],
                    }
                groups[key]["total_quantity"] += it.quantity
                groups[key]["sources"].append({
                    "request_number": req.request_number,
                    "vehicle": vehicle,
                    "plate_number": req.plate_number,
                    "quantity": it.quantity,
                    "note": it.note,
                })

        # tri : catalogue d'abord, puis alphabétique
        items = sorted(
            groups.values(),
            key=lambda g: (not g["from_catalog"], g["designation"].lower()),
        )

        return {
            "generated_at": datetime.utcnow(),
            "request_count": len(reqs),
            "distinct_parts": len(items),
            "items": items,
        }