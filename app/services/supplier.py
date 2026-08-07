from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import constraint_name
from app.core.exceptions import ConflictError, NotFoundError
from app.core.pagination import paginate
from app.models.supplier import Supplier
from app.repositories.supplier import SupplierRepository
from app.schemas.supplier import SupplierCreate, SupplierUpdate


class SupplierService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = SupplierRepository(session)

    async def get_or_404(self, supplier_id: UUID) -> Supplier:
        supplier = await self.repo.get(supplier_id)
        if supplier is None:
            raise NotFoundError(f"Fournisseur {supplier_id} introuvable.")
        return supplier

    async def list(
        self, *, search: str | None, page: int, limit: int
    ) -> tuple[list, int]:
        stmt = select(Supplier)
        if search:
            stmt = stmt.where(Supplier.name.ilike(f"%{search.strip()}%"))
        stmt = stmt.order_by(Supplier.name)
        return await paginate(self.session, stmt, page=page, limit=limit)

    async def create(self, data: SupplierCreate) -> Supplier:
        supplier = self.repo.add(
            Supplier(
                name=data.name.strip(),
                phone=(data.phone.strip() or None) if data.phone else None,
                email=data.email,  # déjà normalisé/validé par le schéma
            )
        )
        await self._commit(name=data.name.strip())
        await self.session.refresh(supplier)
        return supplier

    async def update(self, supplier_id: UUID, data: SupplierUpdate) -> Supplier:
        supplier = await self.get_or_404(supplier_id)
        fields = data.model_dump(exclude_unset=True)

        if "name" in fields and fields["name"] is not None:
            supplier.name = fields["name"].strip()
        if "phone" in fields:
            value = fields["phone"]
            supplier.phone = value.strip() or None if value else None
        if "email" in fields:
            supplier.email = fields["email"]  # None efface, sinon déjà normalisé

        await self._commit(name=supplier.name)
        await self.session.refresh(supplier)
        return supplier

    async def delete(self, supplier_id: UUID) -> None:
        supplier = await self.get_or_404(supplier_id)
        await self.repo.delete(supplier)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError(
                "Impossible de supprimer ce fournisseur : des commandes lui sont rattachées."
            ) from exc

    async def _commit(self, *, name: str) -> None:
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if constraint_name(exc) in {"uq_suppliers_name", "ix_suppliers_name"}:
                raise ConflictError(f"Le fournisseur « {name} » existe déjà.") from exc
            raise