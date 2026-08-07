from datetime import datetime, timedelta, timezone
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext
from pwdlib import PasswordHash

from app.core.config import settings

# bcrypt : algorithme de hachage lent et salé, résistant au brute-force.
# _pwd = CryptContext(schemes=["bcrypt"], deprecated="auto"
_pwd = PasswordHash.recommended()

def hash_password(plain: str) -> str:
    return _pwd.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd.verify(plain, hashed)


def create_access_token(*, user_id: UUID, role: str) -> str:
    """Génère un JWT signé encodant l'id et le rôle de l'utilisateur."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": str(user_id),      # subject = id utilisateur
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Vérifie la signature et l'expiration. Retourne le payload ou None si invalide."""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None