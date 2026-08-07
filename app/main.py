from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.exceptions import register_exception_handlers

# Les routers seront ajoutés étape par étape (marques, modèles, etc.)
from app.api.router.router import api_router


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
        docs_url="/docs",
    )
    
    origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
    print(f"DEBUG CORS origins chargées : {origins!r}") 
    app.add_middleware(
        CORSMiddleware,
        allow_origins= origins or ["http://localhost:3000"],  # + l'URL de prod
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    @app.get("/health", tags=["health"])
    async def health():
        return {"status": "ok"}

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    return app


app = create_app()