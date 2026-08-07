from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import constraint_name
from app.core.exceptions import ConflictError, NotFoundError
from app.core.pagination import paginate
from app.models.vehicle_brand import VehicleBrand
from app.models.vehicle_model import VehicleModel
from app.repositories.vehicle_brand import VehicleBrandRepository
from app.schemas.vehicle_brand import VehicleBrandCreate, VehicleBrandUpdate


class VehicleBrandService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = VehicleBrandRepository(session)

    async def get_or_404(self, brand_id: UUID) -> VehicleBrand:
        brand = await self.repo.get(brand_id)
        if brand is None:
            raise NotFoundError(f"Marque {brand_id} introuvable.")
        return brand

    async def list_brands(self, *, search: str | None, page: int, limit: int) -> tuple[list, int]:
        stmt = select(VehicleBrand)
        if search:
            stmt = stmt.where(VehicleBrand.name.ilike(f"%{search.strip()}%"))
        stmt = stmt.order_by(VehicleBrand.name)
        return await paginate(self.session, stmt, page=page, limit=limit)

    async def create(self, data: VehicleBrandCreate) -> VehicleBrand:
        brand = self.repo.add(VehicleBrand(name=data.name.strip()))
        await self._commit_unique(brand.name)
        await self.session.refresh(brand)
        return brand

    async def update(self, brand_id: UUID, data: VehicleBrandUpdate) -> VehicleBrand:
        brand = await self.get_or_404(brand_id)
        if data.name is not None:
            brand.name = data.name.strip()
        await self._commit_unique(brand.name)
        await self.session.refresh(brand)
        return brand

    async def delete(self, brand_id: UUID) -> None:
        brand = await self.get_or_404(brand_id)
        await self.repo.delete(brand)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError(
                "Impossible de supprimer cette marque : des modèles ou pièces y sont rattachés."
            ) from exc

    async def list_models(self, brand_id: UUID) -> list[VehicleModel]:
        await self.get_or_404(brand_id)
        stmt = (
            select(VehicleModel)
            .where(VehicleModel.brand_id == brand_id)
            .order_by(VehicleModel.name)
        )
        return list(await self.session.scalars(stmt))

    async def _commit_unique(self, name: str) -> None:
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if constraint_name(exc) in {"uq_vehicle_brands_name", "ix_vehicle_brands_name"}:
                raise ConflictError(f"La marque « {name} » existe déjà.") from exc
            raise