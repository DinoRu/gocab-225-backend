from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppException
from app.core.security import (
    create_access_token, verify_password,
    generate_refresh_token, hash_refresh_token,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.repositories.user import UserRepository
from app.repositories.refresh_token import RefreshTokenRepository


class AuthError(AppException):
    status_code = 401


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.tokens = RefreshTokenRepository(session)

    async def _issue_refresh(self, user_id: UUID) -> str:
        raw = generate_refresh_token()
        rt = RefreshToken(
            user_id=user_id,
            token_hash=hash_refresh_token(raw),
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
        self.session.add(rt)
        await self.session.flush()
        return raw

    async def authenticate(self, username: str, password: str) -> tuple[str, str]:
        user = await self.users.get_by_username(username.strip())
        if user is None or not verify_password(password, user.password_hash):
            raise AuthError("Identifiant ou mot de passe incorrect.")
        if not user.is_active:
            raise AuthError("Ce compte est désactivé.")
        access = create_access_token(user_id=user.id, role=user.role)
        refresh = await self._issue_refresh(user.id)
        await self.session.commit()
        return access, refresh

    async def refresh(self, raw_token: str) -> tuple[str, str]:
        row = await self.tokens.get_by_hash(hash_refresh_token(raw_token))
        if row is None:
            raise AuthError("Session invalide. Veuillez vous reconnecter.")

        # Réutilisation d'un token déjà consommé → vol suspecté → on coupe tout.
        if row.revoked:
            await self.tokens.revoke_all_for_user(row.user_id)
            await self.session.commit()
            raise AuthError("Session compromise. Veuillez vous reconnecter.")

        if row.expires_at < datetime.now(timezone.utc):
            raise AuthError("Session expirée. Veuillez vous reconnecter.")

        user = await self.users.get_by_id(row.user_id)
        if user is None or not user.is_active:
            raise AuthError("Compte indisponible.")

        # Rotation : on révoque l'ancien, on émet un nouveau couple.
        row.revoked = True
        new_refresh = await self._issue_refresh(user.id)
        # trace de filiation (facultatif mais utile au diagnostic)
        latest = await self.tokens.get_by_hash(hash_refresh_token(new_refresh))
        if latest is not None:
            row.replaced_by_id = latest.id

        access = create_access_token(user_id=user.id, role=user.role)
        await self.session.commit()
        return access, new_refresh

    async def logout(self, raw_token: str) -> None:
        row = await self.tokens.get_by_hash(hash_refresh_token(raw_token))
        if row is not None and not row.revoked:
            row.revoked = True
            await self.session.commit()

    async def get_user(self, user_id: UUID) -> User | None:
        return await self.users.get_by_id(user_id)