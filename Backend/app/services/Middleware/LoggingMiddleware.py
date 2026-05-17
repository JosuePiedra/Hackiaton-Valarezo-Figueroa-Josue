import time
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
logger = logging.getLogger(__name__) # Logger para este módulo

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        # Obtener datos de usuario si está disponible
        user = getattr(request.state, "user", {})
        username = user.get("sub", "anónimo")

        # Log de entrada
        logger.info(
            f"[REQUEST] {request.method} {request.url.path} - Usuario: {username}"
        )

        # Procesar la solicitud
        response = await call_next(request)

        # Calcular tiempo de proceso
        process_time = time.time() - start_time

        # Log de salida
        logger.info(
            f"[RESPONSE] {request.method} {request.url.path} - "
            f"Status: {response.status_code} - "
            f"Tiempo: {process_time:.4f}s - "
            f"Usuario: {username}"
        )

        # Añadir headers de procesamiento
        response.headers["X-Process-Time"] = str(process_time)

        return response