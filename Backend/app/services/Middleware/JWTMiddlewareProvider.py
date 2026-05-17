import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class JWTAuthMiddlewareProvider(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        # Solo estas rutas pasan; cualquier otra es rechazada.
        self.public_paths = [
            "/api/v1/insurance/asdfhnjoasidjasidailosdiajsdqweqnwadsnjkdaushcasjkdaso/upload",
            "/api/v1/insurance/dnjfasndashdqweojgkpsdjfmmknsabdkodfpoiucxzcasdqwm/chat",
            # "/docs",
            # "/redoc",
            # "/openapi.json",
        ]
        logger.info("JWTAuthMiddleware inicializado")

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if any(path.startswith(public) for public in self.public_paths):
            return await call_next(request)

        logger.warning(f"Acceso denegado a ruta no pública: {path}")
        return JSONResponse(
            status_code=401,
            content={
                "status": 401,
                "message": "Ruta no autorizada",
                "data": None,
            },
        )
