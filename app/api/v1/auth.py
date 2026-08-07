from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import SessionDep
from app.api.auth_deps import CurrentUserDep
from app.schemas.auth import CurrentUser, Token
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token)
async def login(
    session: SessionDep,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
):
    """Login OAuth2 standard : champs 'username' et 'password' en form-data.
    Compatible avec le bouton Authorize de Swagger."""
    token = await AuthService(session).authenticate(form.username, form.password)
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me", response_model=CurrentUser)
async def me(user: CurrentUserDep):
    """Retourne l'utilisateur connecté (utile au frontend au démarrage)."""
    return user