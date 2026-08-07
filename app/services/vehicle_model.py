from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.db import constraint_name
from app.core.exceptions import ConflictError, NotFoundError
from app.core.pagination import paginate
from app.models.vehicle_brand import VehicleBrand
from app.models.vehicle_model import VehicleModel
from app.repositories.vehicle_model import VehicleModelRepository
from app.schemas.vehicle_model import VehicleModelCreate, VehicleModelUpdate


class VehicleModelService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = VehicleModelRepository(session)

    async def get_or_404(self, model_id: UUID) -> VehicleModel:
        model = await self.repo.get(model_id)
        if model is None:
            raise NotFoundError(f"Modèle {model_id} introuvable.")
        return model

    async def get_with_brand(self, model_id: UUID) -> VehicleModel:
        stmt = (
            select(VehicleModel)
            .where(VehicleModel.id == model_id)
            .options(selectinload(VehicleModel.brand))
        )
        model = await self.session.scalar(stmt)
        if model is None:
            raise NotFoundError(f"Modèle {model_id} introuvable.")
        return model

    async def list(
        self, *, brand_id: UUID | None, search: str | None, page: int, limit: int
    ) -> tuple[list, int]:
        stmt = select(VehicleModel)
        if brand_id is not None:
            stmt = stmt.where(VehicleModel.brand_id == brand_id)
        if search:
            stmt = stmt.where(VehicleModel.name.ilike(f"%{search.strip()}%"))
        stmt = stmt.order_by(VehicleModel.name)
        return await paginate(self.session, stmt, page=page, limit=limit)

    async def create(self, data: VehicleModelCreate) -> VehicleModel:
        await self._ensure_brand_exists(data.brand_id)
        model = self.repo.add(
            VehicleModel(brand_id=data.brand_id, name=data.name.strip())
        )
        await self._commit(model_name=data.name.strip())
        await self.session.refresh(model)
        return model

    async def update(self, model_id: UUID, data: VehicleModelUpdate) -> VehicleModel:
        model = await self.get_or_404(model_id)
        if data.name is not None:
            model.name = data.name.strip()
        await self._commit(model_name=model.name)
        await self.session.refresh(model)
        return model

    async def delete(self, model_id: UUID) -> None:
        model = await self.get_or_404(model_id)
        await self.repo.delete(model)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError(
                "Impossible de supprimer ce modèle : des pièces y sont rattachées."
            ) from exc

    # --- internes ---

    async def _ensure_brand_exists(self, brand_id: UUID) -> None:
        exists = await self.session.scalar(
            select(VehicleBrand.id).where(VehicleBrand.id == brand_id)
        )
        if exists is None:
            raise NotFoundError(f"Marque {brand_id} introuvable.")

    async def _commit(self, *, model_name: str) -> None:
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            cn = constraint_name(exc)
            if cn == "uq_vehicle_models_brand_name":
                raise ConflictError(
                    f"Le modèle « {model_name} » existe déjà pour cette marque."
                ) from exc
            # Race : la marque a disparu entre le check et l'insert (FK auto-nommée *_brand_id_fkey)
            if cn and cn.endswith("brand_id_fkey"):
                raise NotFoundError("Marque introuvable.") from exc
            raise