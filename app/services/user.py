from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import constraint_name
from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.core.pagination import paginate
from app.core.security import hash_password
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.user import UserCreate, UserUpdate


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = UserRepository(session)

    async def get_or_404(self, user_id: UUID) -> User:
        user = await self.repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError(f"Utilisateur {user_id} introuvable.")
        return user

    async def list_users(self, *, search, role, is_active, page, limit):
        stmt = select(User)
        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(
                User.username.ilike(like) | User.full_name.ilike(like)
            )
        if role:
            stmt = stmt.where(User.role == role)
        if is_active is not None:
            stmt = stmt.where(User.is_active == is_active)
        stmt = stmt.order_by(User.username)
        items, total = await paginate(self.session, stmt, page=page, limit=limit)
        return items, total

    async def create(self, data: UserCreate) -> User:
        user = User(
            username=data.username.strip(),
            full_name=data.full_name,
            password_hash=hash_password(data.password),
            role=data.role,
            is_active=True,
        )
        self.session.add(user)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if constraint_name(exc) in {"uq_users_username", "ix_users_username"}:
                raise ConflictError(f"L'identifiant « {data.username} » est déjà pris.") from exc
            raise
        await self.session.refresh(user)
        return user

    async def update(self, user_id: UUID, data: UserUpdate, *, acting_admin_id: UUID) -> User:
        user = await self.get_or_404(user_id)
        fields = data.model_dump(exclude_unset=True)
        # Garde-fou : un admin ne peut pas se rétrograder lui-même
        # (sinon risque de se retrouver sans aucun admin).
        if (
            user.id == acting_admin_id
            and fields.get("role") == "magazinier"
            and user.role == "admin"
        ):
            raise BusinessRuleError("Vous ne pouvez pas retirer votre propre rôle admin.")
        if "full_name" in fields:
            user.full_name = fields["full_name"]
        if fields.get("role") is not None:
            await self._guard_last_admin(user, new_role=fields["role"])
            user.role = fields["role"]
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def reset_password(self, user_id: UUID, new_password: str) -> None:
        user = await self.get_or_404(user_id)
        user.password_hash = hash_password(new_password)
        await self.session.commit()

    async def set_active(self, user_id: UUID, active: bool, *, acting_admin_id: UUID) -> User:
        user = await self.get_or_404(user_id)
        if user.id == acting_admin_id and not active:
            raise BusinessRuleError("Vous ne pouvez pas désactiver votre propre compte.")
        if not active:
            await self._guard_last_admin(user, new_role=None)  # désactiver = perdre un admin
        user.is_active = active
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def delete(self, user_id: UUID, *, acting_admin_id: UUID) -> None:
        user = await self.get_or_404(user_id)
        if user.id == acting_admin_id:
            raise BusinessRuleError("Vous ne pouvez pas supprimer votre propre compte.")
        await self._guard_last_admin(user, new_role=None)
        await self.session.delete(user)
        await self.session.commit()

    async def _guard_last_admin(self, user: User, *, new_role: str | None) -> None:
        """Empêche de supprimer/rétrograder/désactiver le DERNIER admin actif.
        new_role=None signifie suppression ou désactivation."""
        if user.role != "admin":
            return
        if new_role == "admin":
            return  # reste admin, aucun risque
        active_admins = await self.session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == "admin", User.is_active.is_(True))
        )
        if active_admins is not None and active_admins <= 1:
            raise BusinessRuleError(
                "Impossible : il doit rester au moins un administrateur actif."
            )