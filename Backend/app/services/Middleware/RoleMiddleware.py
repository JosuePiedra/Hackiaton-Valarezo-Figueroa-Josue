from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import logging

logger = logging.getLogger(__name__)

class RoleMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.role_permissions = {
            "admin": {
                "allowed_paths": ["*"],
            },
            "staff": {
                "allowed_paths": ["*"]
            },
            "user": {
                "allowed_paths": [
                    "/api/v1/user/profile",
                    "/api/v1/chat-agent-MAD",
                    "/api/v1/chat/message/update-calification",
                    "api/v1/chat/history/all/conversations",
                    "api/v1/chat/message/edit",
                    "api/v1/chat/history/{session_id}",
                    "/api/v1/auth/auth/google"
                ]
            }
        }
        logger.info("RoleMiddleware inicializado")

    def is_path_allowed(self, role: str, path: str) -> bool:
        """Verifica si un path está permitido para un rol específico"""
        if role not in self.role_permissions:
            return False

        permissions = self.role_permissions[role]
        allowed_paths = permissions["allowed_paths"]

        # Si el rol tiene acceso a todo
        if "*" in allowed_paths:
            return True

        # Verificar si el path coincide con alguno de los permitidos
        return any(path.startswith(allowed_path) for allowed_path in allowed_paths)

    async def dispatch(self, request: Request, call_next):
        # Ignorar rutas públicas
        if request.url.path.startswith(("/docs", "/redoc", "/openapi.json", "/api/v1/auth")):
            return await call_next(request)

        try:
            # Obtener información del usuario del estado de la request
            user_data = getattr(request.state, "user", None)
            if not user_data:
                logger.warning(f"No se encontró información del usuario para: {request.url.path}")
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Se requiere autenticación"}
                )
            # Obtener el rol del usuario
            role = user_data.get("role", "user")
            path = request.url.path

            # Verificar permisos
            if not self.is_path_allowed(role, path):
                logger.warning(f"Acceso denegado para rol {role} en path {path}")
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": "No tienes permiso para acceder a este recurso",
                        "role": role,
                        "path": path
                    }
                )

            logger.info(f"Acceso permitido para rol {role} en path {path}")
            return await call_next(request)

        except Exception as e:
            logger.error(f"Error en RoleMiddleware: {str(e)}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={"detail": "Error interno del servidor al verificar permisos"}
            )