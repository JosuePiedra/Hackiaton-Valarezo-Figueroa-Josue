from datetime import datetime, timedelta
import logging
from typing import Dict, Tuple
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
import time
from cachetools import TTLCache
import os
from dotenv import load_dotenv

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from fastapi import Request

from app.models.rate_limit import RateLimitPlan, EndpointLimit
from app.manager.Mongo_provider import Mongo_provider

# Cargar variables de entorno
load_dotenv()

logger = logging.getLogger(__name__)

class RateLimitMiddlewareProvider(BaseHTTPMiddleware):
    """Middleware para controlar límites de tasa de solicitudes por usuario y plan."""
    EXCLUDED_PATHS = os.getenv(
        "RATE_LIMIT_EXCLUDED_PATHS",
        "/docs,/redoc,/openapi.json,/api/v1/auth,/api/v1/auth_apple/apple"
    ).split(",")

    DEFAULT_LIMITS = {
        "requests_per_minute": int(os.getenv("RATE_LIMIT_PER_MINUTE", "20")),
        "requests_per_hour": int(os.getenv("RATE_LIMIT_PER_HOUR", "100")),
        "requests_per_day": int(os.getenv("RATE_LIMIT_PER_DAY", "1000")),
        "requests_per_month": int(os.getenv("RATE_LIMIT_PER_MONTH", "10000"))
    }

    TIME_INTERVALS = {
        "minute": ("used_minute", "last_reset_minute", 60),
        "hour": ("used_hour", "last_reset_hour", 3600),
        "day": ("used_today", "last_reset_day", 86400),
        "month": ("used_this_month", "last_reset_month", 2592000)
    }

    COLLECTIONS_PER_PLAN = {
        "free": int(os.getenv("RATE_LIMIT_COLLECTIONS_FREE", "3")),
        "basic": int(os.getenv("RATE_LIMIT_COLLECTIONS_BASIC", "10")),
        "pro": int(os.getenv("RATE_LIMIT_COLLECTIONS_PRO", "20")),
        "enterprise": int(os.getenv("RATE_LIMIT_COLLECTIONS_ENTERPRISE", "100")),
    }
    def __init__(self, app):
        super().__init__(app)
        logger.info("Inicializando RateLimitMiddleware")

        # Cache para límites de planes (TTL configurable desde env)
        plan_cache_ttl = int(os.getenv("RATE_LIMIT_PLAN_CACHE_TTL", "300"))
        plan_cache_size = int(os.getenv("RATE_LIMIT_PLAN_CACHE_SIZE", "100"))
        self.plan_limits_cache = TTLCache(maxsize=plan_cache_size, ttl=plan_cache_ttl)

        # Cache para documentos de uso
        usage_cache_ttl = int(os.getenv("RATE_LIMIT_USAGE_CACHE_TTL", "60"))
        usage_cache_size = int(os.getenv("RATE_LIMIT_USAGE_CACHE_SIZE", "1000"))
        self.usage_cache = TTLCache(maxsize=usage_cache_size, ttl=usage_cache_ttl)

        # ThreadPool para operaciones asíncronas
        workers = int(os.getenv("RATE_LIMIT_THREAD_WORKERS", "3"))
        self._executor = ThreadPoolExecutor(max_workers=workers)

        self.rate_limits = {}
        self.db = Mongo_provider()
        self._load_rate_limits()

        # Configuración para tareas en segundo plano
        self.refresh_interval = int(os.getenv("RATE_LIMIT_REFRESH_INTERVAL", "300"))
        self.cleanup_interval = int(os.getenv("RATE_LIMIT_CLEANUP_INTERVAL", "3600"))

        # Iniciar tareas en segundo plano
        self._start_background_tasks()

    def _start_background_tasks(self):
        """Inicia las tareas periódicas en segundo plano"""
        def refresh_limits_task():
            while True:
                try:
                    self._load_rate_limits()
                    time.sleep(self.refresh_interval)  # Actualizar límites según configuración
                except Exception as e:
                    logger.error(f"Error en actualización de límites: {e}")
                    time.sleep(60)

        def cleanup_task():
            while True:
                try:
                    self._cleanup_expired_records()
                    time.sleep(self.cleanup_interval)  # Limpiar registros según configuración
                except Exception as e:
                    logger.error(f"Error en limpieza de registros: {e}")
                    time.sleep(300)

        # Iniciar tareas solo si están habilitadas
        if os.getenv("RATE_LIMIT_ENABLE_REFRESH", "true").lower() == "true":
            Thread(target=refresh_limits_task, daemon=True).start()

        if os.getenv("RATE_LIMIT_ENABLE_CLEANUP", "true").lower() == "true":
            Thread(target=cleanup_task, daemon=True).start()

    def _cleanup_expired_records(self):
        """Limpia registros de uso expirados en segundo plano"""
        try:
            now = datetime.utcnow()
            result = self.db.rate_limit_manager.cleanup_expired_usage_records(now)
            logger.info(f"Limpiados {result} registros de uso expirados")
        except Exception as e:
            logger.error(f"Error en limpieza de registros: {e}")

    def _load_rate_limits(self) -> None:
        """Carga la configuración de límites desde la base de datos."""
        logger.debug("Cargando límites de tasa")

        try:
            self.rate_limits = self.db.rate_limit_manager.load_rate_limits()

            if not self.rate_limits:
                self._setup_default_plan()

            # Limpiar cache de límites al recargar
            self.plan_limits_cache.clear()
            logger.debug(f"Límites de tasa cargados correctamente")
        except Exception as e:
            logger.error(f"Error al cargar configuración de rate limits: {e}")
            raise

    def _setup_default_plan(self) -> None:
        """Configura el plan gratuito por defecto cuando no existen planes en la BD."""
        default_plan_name = os.getenv("RATE_LIMIT_DEFAULT_PLAN", "free")
        default_plan_description = os.getenv("RATE_LIMIT_DEFAULT_PLAN_DESC", "Plan gratuito por defecto")

        default_plan = RateLimitPlan(
            plan_name=default_plan_name,
            description=default_plan_description,
            default_limits=EndpointLimit(**self.DEFAULT_LIMITS),
            endpoint_limits={}
        )

        if self.db.rate_limit_manager.create_default_plan(default_plan):
            self.rate_limits[default_plan_name] = {
                "default_limits": default_plan.default_limits.dict(),
                "endpoint_limits": {}
            }
            logger.info(f"Plan por defecto '{default_plan_name}' creado correctamente")
        else:
            logger.error("Error al crear plan por defecto")
            raise RuntimeError("No se pudo crear el plan por defecto")

    def get_endpoint_limits(self, plan_name: str, endpoint: str) -> dict:
        """Obtiene los límites específicos para un endpoint o los límites por defecto del plan."""
        # Intentar obtener del cache primero
        cache_key = f"{plan_name}:{endpoint}"
        cached_limits = self.plan_limits_cache.get(cache_key)
        if cached_limits:
            return cached_limits

        # Si no está en cache, obtener de la BD
        plan_limits, found = self.db.rate_limit_manager.get_plan_limits(plan_name, endpoint)
        default_plan = os.getenv("RATE_LIMIT_DEFAULT_PLAN", "free")
        if not found:
            plan_limits, _ = self.db.rate_limit_manager.get_plan_limits(default_plan, endpoint)

        # Guardar en cache
        self.plan_limits_cache[cache_key] = plan_limits
        return plan_limits

    def _update_usage_async(self, user_id: str, endpoint: str, usage_doc: Dict):
        """Actualiza el uso en la base de datos de forma asíncrona"""
        def update_task():
            try:
                self.db.rate_limit_manager.update_usage_record(user_id, endpoint, usage_doc)
            except Exception as e:
                logger.error(f"Error al actualizar uso async para {user_id}: {e}")

        self._executor.submit(update_task)

    async def check_collection_limit(self, user_id: str, plan_name: str) -> Tuple[bool, Dict]:
        """Verifica si se han excedido los límites de colecciones para un usuario según su plan."""
        try:
            # Obtener el número máximo de colecciones permitidas para el plan
            max_collections = self.COLLECTIONS_PER_PLAN.get(plan_name, self.COLLECTIONS_PER_PLAN["free"])

            # Obtener el número actual de colecciones del usuario
            current_collection_count = self.db.users_manager.get_user_collection_count(user_id)

            # Verificar si se ha excedido el límite
            if current_collection_count >= max_collections:
                logger.warning(f"Límite de colecciones excedido para usuario: {user_id} con plan: {plan_name}")
                return False, {
                    "error_type": "collection_limit_reached",
                    "message": f"Has alcanzado el límite de {max_collections} colecciones para tu plan {plan_name}",
                    "current_count": current_collection_count,
                    "max_allowed": max_collections,
                    "plan": plan_name
                }

            return True, {}

        except Exception as e:
            logger.error(f"Error verificando límite de colecciones: {e}")
            return False, {"detail": "Error interno verificando límites de colecciones"}

    async def check_rate_limit(self, user_id: str, endpoint: str, plan_name: str) -> Tuple[bool, Dict]:
        """Verifica si se han excedido los límites de uso."""
        now = datetime.utcnow()

        try:
            # Intentar obtener del cache primero
            cache_key = f"{user_id}:{endpoint}"
            usage_doc = self.usage_cache.get(cache_key)

            if not usage_doc:
                # Si no está en cache, obtener de la BD
                usage_doc = await self._get_usage_document(user_id, endpoint, now)
                self.usage_cache[cache_key] = usage_doc

            # Obtener límites aplicables (ya usa cache internamente)
            limits = self.get_endpoint_limits(plan_name, endpoint)

            # Verificar cada intervalo de tiempo
            updated_usage, is_allowed, error_details = self._check_time_intervals(usage_doc, limits, now)

            # Si no está permitido, devolver el error
            if not is_allowed:
                return False, error_details

            # Actualizar el uso en cache
            self.usage_cache[cache_key] = updated_usage
            # Actualizar en BD de forma asíncrona
            self._update_usage_async(user_id, endpoint, updated_usage)

            return True, {}

        except Exception as e:
            logger.error(f"Error verificando rate limit: {e}")
            return False, {"detail": "Error interno verificando límites de uso"}

    async def _get_usage_document(self, user_id: str, endpoint: str, now: datetime) -> Dict:
        """Obtiene el documento de uso o crea uno nuevo si no existe."""
        usage_doc = self.db.rate_limit_manager.get_usage_record(user_id, endpoint)

        if not usage_doc:
            usage_doc = {
                "user_id": user_id,
                "endpoint": endpoint,
                "used_minute": 0,
                "used_hour": 0,
                "used_today": 0,
                "used_this_month": 0,
                "last_reset_minute": now,
                "last_reset_hour": now,
                "last_reset_day": now,
                "last_reset_month": now
            }
            if not self.db.rate_limit_manager.create_usage_record(user_id, endpoint, usage_doc):
                logger.error(f"Error creando registro de uso para {user_id} en {endpoint}")
                raise RuntimeError("Error creando registro de uso")

        return usage_doc

    def _check_time_intervals(self, usage_doc: Dict, limits: Dict, now: datetime) -> Tuple[Dict, bool, Dict]:
        """Verifica todos los intervalos de tiempo y actualiza el uso."""
        updated_usage = usage_doc.copy()

        try:
            # Verificar cada intervalo de tiempo
            for interval, (usage_field, reset_field, duration) in self.TIME_INTERVALS.items():
                limit_key = f"requests_per_{interval}"
                limit = limits.get(limit_key, self.DEFAULT_LIMITS.get(limit_key))

                last_reset = usage_doc[reset_field]
                if isinstance(last_reset, str):
                    last_reset = datetime.fromisoformat(last_reset.replace('Z', '+00:00'))

                # Resetear si el intervalo expiró
                if (now - last_reset).total_seconds() > duration:
                    updated_usage[usage_field] = 0
                    updated_usage[reset_field] = now
                elif usage_doc[usage_field] >= limit:
                    reset_at = last_reset + timedelta(seconds=duration)
                    logger.warning(f"Límite excedido ({interval}) para usuario: {usage_doc['user_id']}")
                    return updated_usage, False, {
                        "detail": f"Límite excedido ({interval}). Por favor, espere hasta {reset_at.isoformat()}",
                        "limit": limit,
                        "current": usage_doc[usage_field],
                        "reset_at": reset_at.isoformat(),
                        "interval": interval
                    }

            # Si pasa todas las verificaciones, incrementar el uso
            for usage_field, _, _ in self.TIME_INTERVALS.values():
                updated_usage[usage_field] = updated_usage[usage_field] + 1

            return updated_usage, True, {}

        except Exception as e:
            logger.error(f"Error en verificación de intervalos: {e}")
            raise

    async def dispatch(self, request: Request, call_next):
        """Procesa la solicitud y aplica límites de tasa según el plan del usuario."""
        endpoint = request.url.path

        try:
            # Verificar si la ruta está excluida de los límites
            if any(endpoint.startswith(path) for path in self.EXCLUDED_PATHS):
                return await call_next(request)

            # Obtener información del usuario del JWT middleware
            user_info = getattr(request.state, "user", {})
            user_id = user_info.get("id")
            if not user_id:
                logger.warning("No se encontró ID de usuario en la solicitud")
                return JSONResponse(
                    status_code=401,
                    content={
                        "status": 401,
                        "message": "Unauthorized",
                        "data":None
                    }
                )

            default_plan = os.getenv("RATE_LIMIT_DEFAULT_PLAN", "free")
            plan_name = user_info.get("plan", default_plan)
            logger.debug(f"Verificando límites para usuario {user_id} con plan {plan_name} en {endpoint}")

            # Verificar límites de colecciones para endpoints específicos
            if endpoint == "/api/v1/questionary/upload_user_documents" and request.method == "POST":
                collection_allowed, collection_error = await self.check_collection_limit(user_id, plan_name)
                if not collection_allowed:
                    logger.warning(
                        f"Límite de colecciones excedido para usuario {user_id}. "
                        f"Plan: {plan_name}. Detalles: {collection_error}"
                    )
                    return JSONResponse(
                        status_code=403,
                        content={
                            "status": 403,
                            "message": "Collection limit exceeded",
                            **collection_error
                        }
                    )

            # Verificar límites de uso
            allowed, error_details = await self.check_rate_limit(user_id, endpoint, plan_name)

            if not allowed:
                logger.warning(
                    f"Límite excedido para usuario {user_id} en {endpoint}. "
                    f"Plan: {plan_name}. Detalles: {error_details}"
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "status": 429,
                        "message": "Rate limit exceeded",
                        **error_details
                    }
                )

            # Continuar con la solicitud
            response = await call_next(request)
            return response

        except Exception as e:
            logger.error(f"Error en rate limit middleware: {str(e)}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": 500,
                    "message": "Error interno al verificar límites de uso"
                }
            )
