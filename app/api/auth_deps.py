
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.api.deps import SessionDep
from app.core.security import decode_access_token
from app.models.user import User
from app.services.auth import AuthService

# tokenUrl = l'endpoint de login (pour la doc Swagger et le bouton "Authorize").
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

_CREDENTIALS_EXC = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Non authentifié.",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    session: SessionDep,
    token: Annotated[str, Depends(oauth2_scheme)],
) -> User:
    payload = decode_access_token(token)
    if payload is None:
        raise _CREDENTIALS_EXC
    sub = payload.get("sub")
    if sub is None:
        raise _CREDENTIALS_EXC
    try:
        user_id = UUID(sub)
    except (ValueError, TypeError):
        raise _CREDENTIALS_EXC

    user = await AuthService(session).get_user(user_id)
    if user is None or not user.is_active:
        raise _CREDENTIALS_EXC
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


def require_role(*allowed_roles: str):
    """Fabrique une dépendance qui n'autorise que certains rôles.
    Usage : dependencies=[Depends(require_role("admin"))]
       ou  : user: Annotated[User, Depends(require_role("admin", "magazinier"))]
    """
    async def _guard(user: CurrentUserDep) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous n'avez pas les droits pour cette action.",
            )
        return user
    return _guard


# Raccourcis prêts à l'emploi pour la tranche 2.
AdminOnly = Annotated[User, Depends(require_role("admin"))]
AnyUser = Annotated[User, Depends(require_role("admin", "magazinier"))]