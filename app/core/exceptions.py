from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppException(Exception):
    status_code: int = 400
    detail: str = "Erreur applicative"

    def __init__(self, detail: str | None = None):
        if detail is not None:
            self.detail = detail
        super().__init__(self.detail)


class NotFoundError(AppException):
    status_code = 404
    detail = "Ressource introuvable"


class ConflictError(AppException):
    """Violation d'unicité, doublon, etc."""
    status_code = 409
    detail = "Conflit"


class BusinessRuleError(AppException):
    """Règle métier violée (quantité <= 0, pièce dupliquée, dates incohérentes...)."""
    status_code = 422
    detail = "Règle métier non respectée"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def _handle_app_exception(request: Request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )