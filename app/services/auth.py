from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.security import create_access_token, verify_password
from app.models.user import User
from app.repositories.user import UserRepository


class AuthError(AppException):
    """401 — identifiants invalides ou compte désactivé."""
    status_code = 401


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = UserRepository(session)

    async def authenticate(self, username: str, password: str) -> str:
        user = await self.repo.get_by_username(username.strip())
        # Message volontairement identique dans tous les cas d'échec :
        # ne pas révéler si c'est l'utilisateur ou le mot de passe qui est faux.
        if user is None or not verify_password(password, user.password_hash):
            raise AuthError("Identifiant ou mot de passe incorrect.")
        if not user.is_active:
            raise AuthError("Ce compte est désactivé.")
        return create_access_token(user_id=user.id, role=user.role)

    async def get_user(self, user_id: UUID) -> User | None:
        return await self.repo.get_by_id(user_id)