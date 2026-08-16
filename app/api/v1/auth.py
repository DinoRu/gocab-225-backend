from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import SessionDep
from app.api.auth_deps import CurrentUserDep
from app.schemas.auth import CurrentUser, Token, RefreshInput
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token)
async def login(
    session: SessionDep,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
):
    access, refresh = await AuthService(session).authenticate(form.username, form.password)
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}


@router.post("/refresh", response_model=Token)
async def refresh(session: SessionDep, payload: RefreshInput):
    access, new_refresh = await AuthService(session).refresh(payload.refresh_token)
    return {"access_token": access, "refresh_token": new_refresh, "token_type": "bearer"}


@router.post("/logout", status_code=204)
async def logout(session: SessionDep, payload: RefreshInput):
    await AuthService(session).logout(payload.refresh_token)


@router.get("/me", response_model=CurrentUser)
async def me(user: CurrentUserDep):
    """Retourne l'utilisateur connecté (utile au frontend au démarrage)."""
    return user