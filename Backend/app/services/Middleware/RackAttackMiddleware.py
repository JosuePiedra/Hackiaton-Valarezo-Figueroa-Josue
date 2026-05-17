from datetime import datetime, timedelta
import logging
from cachetools import TTLCache
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.manager.Mongo_provider import Mongo_provider
from app.services.TimeTracker import TimeTracker

logger = logging.getLogger(__name__)

class RackAttackMiddleware(BaseHTTPMiddleware):
    """
    Middleware para prevención de ataques y control de tasas de solicitudes,
    inspirado en Rack Attack.
    """
    
    def __init__(self, app):
        super().__init__(app)
        self.db = Mongo_provider()
        
        # Cache para almacenar intentos fallidos (TTL 1 hora)
        self.failed_attempts = TTLCache(maxsize=10000, ttl=3600)
        
        # Cache para IPs bloqueadas (TTL 24 horas)
        self.blocked_ips = TTLCache(maxsize=1000, ttl=86400)
        
        # Cache para conteo de solicitudes por IP (TTL 1 minuto)
        self.request_counts = TTLCache(maxsize=10000, ttl=60)
        
        # Configuración de límites
        self.max_requests_per_minute = 60  # Solicitudes permitidas por minuto por IP
        self.max_failed_attempts = 5  # Intentos fallidos permitidos antes de bloqueo
        self.block_duration = timedelta(hours=240)  # Duración del bloqueo
        
        # Rutas excluidas del rate limiting
        self.excluded_paths = {
            "/docs",
            "/redoc",
            "/openapi.json",
            "/api/v1/auth/login",
            "/api/v1/auth/register"
        }
        
        logger.info("RackAttackMiddleware inicializado")

    def get_client_ip(self, request: Request) -> str:
        """Obtiene la IP real del cliente considerando proxies."""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        return request.client.host

    def is_ip_blocked(self, ip: str) -> bool:
        """Verifica si una IP está bloqueada."""
        return ip in self.blocked_ips

    def record_failed_attempt(self, ip: str) -> None:
        """Registra un intento fallido y bloquea la IP si excede el límite."""
        current_attempts = self.failed_attempts.get(ip, 0) + 1
        self.failed_attempts[ip] = current_attempts
        
        if current_attempts >= self.max_failed_attempts:
            self.block_ip(ip)
            logger.warning(f"IP {ip} bloqueada por múltiples intentos fallidos")

    def block_ip(self, ip: str) -> None:
        """Bloquea una IP por el período configurado."""
        self.blocked_ips[ip] = datetime.utcnow()
        
        # Registrar el bloqueo en la base de datos
        try:
            self.db.users_manager.record_ip_block({
                "ip": ip,
                "blocked_at": datetime.utcnow(),
                "reason": "Múltiples intentos fallidos",
                "duration": str(self.block_duration)
            })
        except Exception as e:
            logger.error(f"Error al registrar bloqueo de IP en BD: {e}")

    def check_rate_limit(self, ip: str) -> bool:
        """Verifica si una IP ha excedido el límite de solicitudes."""
        current_count = self.request_counts.get(ip, 0) + 1
        self.request_counts[ip] = current_count
        return current_count <= self.max_requests_per_minute

    async def dispatch(self, request: Request, call_next):
        """Procesa la solicitud aplicando las reglas de seguridad."""
        timer = TimeTracker("rack_attack_middleware")
        path = request.url.path
        
        try:
            # Verificar si la ruta está excluida
            if path in self.excluded_paths:
                return await call_next(request)
            
            # Obtener IP del cliente
            client_ip = self.get_client_ip(request)
            
            # Verificar si la IP está bloqueada
            if self.is_ip_blocked(client_ip):
                logger.warning(f"Intento de acceso desde IP bloqueada: {client_ip}")
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": "Tu IP ha sido bloqueada por múltiples intentos fallidos"
                    }
                )
            
            # Verificar rate limit
            if not self.check_rate_limit(client_ip):
                logger.warning(f"Rate limit excedido para IP: {client_ip}")
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": f"Demasiadas solicitudes. Máximo {self.max_requests_per_minute} por minuto."
                    }
                )
            
            # Procesar la solicitud
            response = await call_next(request)
            
            # Si la respuesta indica un error de autenticación, registrar intento fallido
            if response.status_code in (401, 403):
                self.record_failed_attempt(client_ip)
            
            timer.finish()
            return response
            
        except Exception as e:
            logger.error(f"Error en RackAttackMiddleware: {str(e)}", exc_info=True)
            timer.finish()
            return JSONResponse(
                status_code=500,
                content={"detail": "Error interno del servidor"}
            )