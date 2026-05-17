import logging
import json
import re
from typing import Optional, Dict, Any, Tuple
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from app.manager.UserManager import UserManager
from app.services.Middleware.RateLimitMiddlewareProvider import RateLimitMiddlewareProvider

logger = logging.getLogger(__name__)

class SupabaseAccessMiddleware(BaseHTTPMiddleware):
    """
    Middleware para controlar el acceso a recursos de Supabase.
    
    Este middleware verifica:
    1. Que el usuario esté autenticado para cualquier operación con Supabase
    2. Que un usuario no exceda el límite de colecciones permitido según su plan
    3. Que el usuario solo pueda acceder a recursos (tablas/colecciones) que le pertenecen
    """
    
    def __init__(self, app):
        super().__init__(app)
        self.user_manager = UserManager()
        # Usar las constantes de límites definidas en RateLimitMiddlewareProvider
        self.collections_per_plan = RateLimitMiddlewareProvider.COLLECTIONS_PER_PLAN
        
        # Patrones para detectar rutas que acceden a recursos de Supabase
        self.supabase_path_patterns = [
            r"/api/v1/supabase/",
            r"/supabase/",
            r"/api/v1/questionary/upload_user_documents",
            r"/api/v1/questionary/delete_collection/.*",
            r"/api/v1/questionary/.*collection.*",
            r"/api/v1/questionary/collection_status/.*",
            r"/api/v1/questionary/document_status/.*",
            r"/api/v1/vector_store/.*",
            r"/api/v1/.*vector.*"
        ]
        
        # Patrones de colección para extraer el nombre de la colección de diferentes partes de la URL
        self.collection_name_pattern = re.compile(r'collection_([0-9a-f]+)_[0-9a-f]+')
        
        # Patrón para extraer IDs de colecciones de las rutas
        self.collection_id_pattern = re.compile(r'/delete_collection/([a-zA-Z0-9\-_]+)')
    
    async def _extract_resource_name(self, request: Request) -> Optional[str]:
        """
        Extrae el nombre del recurso (tabla/colección) de la solicitud.
        Optimizado para mejorar la detección de recursos y rendimiento.
        """
        path = request.url.path
        
        # 1. Verificar si es una ruta de delete_collection y extraer el ID directamente
        if "/delete_collection/" in path:
            match = self.collection_id_pattern.search(path)
            if match:
                collection_id = match.group(1)
                logger.debug(f"ID de colección extraído de delete_collection: {collection_id}")
                return collection_id
        
        # 2. Buscar en query params (rápido y común)
        param_keys = ["collection_name", "table_name", "collection", "table", "vector_store_name", "collection_id", "id"]
        for param_name in param_keys:
            if param_name in request.query_params:
                value = request.query_params.get(param_name)
                if value:
                    logger.debug(f"Resource extraído de query param '{param_name}': {value}")
                    return value
        
        # 3. Buscar en path params basado en patrones comunes
        path_parts = path.split("/")
        resource_indicators = ["tables", "collections", "collection", "table", "vector_store"]
        
        # 3.0 Manejo especial para rutas de collection_status y document_status
        if "collection_status" in path_parts:
            collection_status_index = path_parts.index("collection_status")
            if collection_status_index < len(path_parts) - 1:
                next_part = path_parts[collection_status_index + 1]
                if next_part:
                    logger.debug(f"Resource extraído después de collection_status: {next_part}")
                    return next_part
        
        if "document_status" in path_parts:
            document_status_index = path_parts.index("document_status")
            if document_status_index < len(path_parts) - 1:
                next_part = path_parts[document_status_index + 1]
                if next_part:
                    logger.debug(f"Resource extraído después de document_status: {next_part}")
                    return next_part
        
        for i, part in enumerate(path_parts):
            # 3.1 Si la parte actual es un indicador de recurso y hay una parte siguiente
            if i < len(path_parts) - 1 and part in resource_indicators:
                next_part = path_parts[i+1]
                if next_part and next_part not in resource_indicators:
                    logger.debug(f"Resource extraído de path param después de '{part}': {next_part}")
                    return next_part
            
            # 3.2 Si la parte actual parece una colección directamente
            if part.startswith("collection_"):
                logger.debug(f"Resource extraído directamente del path: {part}")
                return part
        
        # 4. Verificación en el body para métodos que permiten body
        # Limitamos esto a métodos que normalmente tienen body
        if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
            try:
                body_bytes = await request.body()
                if body_bytes:
                    # 4.1 Intentar parsear como JSON
                    try:
                        body = json.loads(body_bytes)
                        if isinstance(body, dict):
                            # Buscar en múltiples claves posibles
                            for key in param_keys:
                                if key in body and body[key]:
                                    value = body[key]
                                    logger.debug(f"Resource extraído del body JSON en campo '{key}': {value}")
                                    return value
                    except json.JSONDecodeError:
                        # 4.2 Si no es JSON válido, buscar patrones en el texto
                        body_text = body_bytes.decode('utf-8', errors='ignore')
                        # Buscar patrones de colección
                        match = self.collection_name_pattern.search(body_text)
                        if match:
                            value = match.group(0)
                            logger.debug(f"Resource extraído del body raw mediante regex: {value}")
                            return value
            except Exception as e:
                logger.debug(f"Error procesando body para extraer resource: {str(e)}")
        
        # 5. Si todo lo anterior falla, intentar con el patrón en la URL completa
        url_str = str(request.url)
        match = self.collection_name_pattern.search(url_str)
        if match:
            value = match.group(0)
            logger.debug(f"Resource extraído mediante regex en URL completa: {value}")
            return value
        
        # No se encontró recurso
        logger.debug(f"No se pudo extraer un resource name para la ruta: {path}")
        logger.debug(f"Partes del path analizadas: {path_parts}")
        return None
        
    async def _check_collection_limit(self, user_id: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Verifica si el usuario ha excedido su límite de colecciones según su plan.
        """
        try:
            # Obtener el plan del usuario
            user = self.user_manager.get_user_by_id(user_id)
            if not user:
                return False, {
                    "status": 403,
                    "message": "Usuario no encontrado",
                    "data": {
                        "error_type": "user_not_found",
                        "detail": "Usuario no encontrado en la base de datos"
                    }

                }
                
            plan_name = user.get("plan", "free")
            max_collections = self.collections_per_plan.get(plan_name, self.collections_per_plan["free"])
            
            # Obtener el número de colecciones actuales
            current_count = self.user_manager.get_user_collection_count(user_id)
            
            # Verificar límite
            if current_count >= max_collections:
                logger.warning(f"Límite de colecciones excedido para usuario: {user_id} con plan: {plan_name}")
                return False, {
                    "status": 403,
                    "message": "Límite de colecciones alcanzado",
                    "data": {
                        "error_type": "collection_limit_reached",
                        "detail": f"Has alcanzado el límite de {max_collections} colecciones para tu plan {plan_name}",
                        "current_count": current_count,
                        "max_allowed": max_collections,
                        "plan": plan_name
                    }
                }
                
            return True, None
        except Exception as e:
            logger.error(f"Error verificando límite de colecciones: {str(e)}")
            return False, {
                "status": 500,
                "message": "Error interno verificando límites",
                "data": {
                    "error_type": "internal_error",
                    "detail": str(e)
                }
            }
    
    async def _verify_resource_ownership(self, user_id: str, resource_name: str, method: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Verifica si el usuario es propietario del recurso solicitado.
        Optimizado para minimizar consultas a la base de datos y mejorar la detección de propiedad.
        """
        try:
            # Obtener usuario una sola vez para todos los chequeos (reducir consultas a BD)
            user = self.user_manager.get_user_by_id(user_id)
            if not user or "collections" not in user:
                logger.warning(f"Usuario {user_id} no encontrado o no tiene colecciones")
                return False, {
                    "status": 403,
                    "message": "Acceso denegado",
                    "data": {
                        "error_type": "access_denied",
                        "detail": "No tienes permisos para este recurso"
                    }
                }
            
            # Si no hay resource_name, no podemos verificar
            if not resource_name:
                return False, {
                    "status": 400,
                    "message": "Identificador de recurso no especificado",
                    "data": {
                        "error_type": "invalid_resource",
                        "detail": "No se ha especificado un identificador de recurso válido"
                    }
                }
            
            collections = user.get("collections", [])
            collection_found = False
            
            # Caso 1: Verificar por patrón de nombre collection_{user_id}_{uuid}
            if resource_name.startswith("collection_"):
                match = self.collection_name_pattern.match(resource_name)
                if match:
                    collection_user_id = match.group(1)
                    if collection_user_id == user_id:
                        logger.debug(f"Acceso verificado por patrón de nombre: {resource_name} pertenece a {user_id}")
                        return True, None
            
            # Caso 2: Verificar en todas las propiedades relevantes de las colecciones
            for collection in collections:
                # Lista de campos donde buscar coincidencia
                check_fields = [
                    ("collection_id", str),
                    ("_id", str),
                    ("name", None),
                    ("id", str)
                ]
                
                for field_name, convert_func in check_fields:
                    if field_name in collection:
                        field_value = collection[field_name]
                        if convert_func:
                            field_value = convert_func(field_value)
                            
                        if field_value == resource_name:
                            logger.info(f"Colección {resource_name} encontrada en campo '{field_name}' para usuario {user_id}")
                            collection_found = True
                            break
                
                if collection_found:
                    break
            
            # Caso 3: Verificación adicional con métodos del UserManager (en caso de estructuras antiguas)
            if not collection_found:
                # Intentar con los métodos de verificación
                if self.user_manager.verify_collection_ownership(user_id, resource_name):
                    logger.info(f"Colección {resource_name} verificada usando verify_collection_ownership")
                    collection_found = True
                elif "table" in resource_name and self.user_manager.verify_table_ownership(user_id, resource_name):
                    logger.info(f"Tabla {resource_name} verificada usando verify_table_ownership")
                    collection_found = True
            
            # Respuesta según resultado de verificación
            if not collection_found:
                # Añadir logs de depuración para facilitar diagnóstico
                logger.debug(f"Colección no encontrada. IDs disponibles: {[c.get('collection_id', c.get('_id', 'desconocido')) for c in collections]}")
                logger.debug(f"Nombres disponibles: {[c.get('name', 'desconocido') for c in collections]}")
                
                action = "consultar" if method == "GET" else "modificar" if method in ["POST", "PUT", "PATCH"] else "eliminar"
                logger.warning(f"Acceso denegado: usuario={user_id}, recurso={resource_name}, método={method}")
                
                return False, {
                    "status": 403,
                    "message": "Acceso denegado",
                    "data": {
                        "error_type": "access_denied",
                        "detail": f"No tienes permisos para {action} este recurso",
                        "resource": resource_name,
                        "method": method,
                        "resource_type": "collection" if resource_name.startswith("collection_") else "table"
                    }
                }
            
            logger.info(f"Propiedad verificada: usuario={user_id} es propietario de {resource_name}")
            return True, None
            
        except Exception as e:
            logger.error(f"Error verificando propiedad del recurso: {str(e)}", exc_info=True)
            return False, {
                "status": 500,
                "message": "Error interno verificando permisos",
                "data": {
                    "error_type": "internal_error",
                    "detail": str(e)
                }
            }
    
    def _is_creation_endpoint(self, request: Request) -> bool:
        """Determina si el endpoint es para creación de recursos"""
        # Verificar patrones comunes para endpoints de creación
        creation_patterns = [
            "/tables", "/collections", "/create_table", "/create_collection",
            "/upload_user_documents", "/add_collection", "/vector_store/create"
        ]
        
        # Verificar si es un método POST y la ruta contiene alguno de los patrones
        return (request.method == "POST" and any(
            pattern in request.url.path for pattern in creation_patterns
        ))
    
    def _is_supabase_path(self, path: str) -> bool:
        """
        Determina si la ruta es una operación que involucra recursos de Supabase.
        
        Args:
            path: Ruta de la solicitud
        
        Returns:
            bool: True si es una ruta de Supabase, False en caso contrario
        """
        # Verificar todos los patrones definidos
        return any(re.search(pattern, path) for pattern in self.supabase_path_patterns)
    
    async def dispatch(self, request: Request, call_next):
        """
        Procesa la solicitud verificando permisos de acceso a recursos de Supabase.
        """
        # Verificar si es un endpoint que requiere verificación
        if not self._is_supabase_path(request.url.path):
            # Si no requiere verificación, continuar normalmente
            return await call_next(request)
            
        try:
            # 1. Verificar autenticación del usuario
            user_id = request.state.user.get("id") if hasattr(request.state, "user") else None
            if not user_id:
                logger.warning(f"Acceso no autenticado a ruta protegida: {request.url.path}")
                return JSONResponse(
                    status_code=401,
                    content={
                        "status": "error",
                        "message": "Autenticación requerida",
                        "data": {
                            "error_type": "authentication_required",
                            "detail": "Debes iniciar sesión para acceder a este recurso"
                        }
                    }
                )
            
            # 2. Extraer nombre del recurso (tabla/colección)
            resource_name = await self._extract_resource_name(request)
            logger.debug(f"Recurso extraído: {resource_name}, Ruta: {request.url.path}")
            
            # 3. Verificar si es un endpoint de creación
            if self._is_creation_endpoint(request):
                # Verificar límite de colecciones
                is_allowed, error_details = await self._check_collection_limit(user_id)
                if not is_allowed:
                    return JSONResponse(status_code=403, content=error_details)
            
            # 4. Para endpoints con recursos específicos, verificar propiedad
            if resource_name or "/delete_collection/" in request.url.path:
                # Si es una ruta de eliminación de colección pero resource_name es None, proporcionar un error específico
                if not resource_name and "/delete_collection/" in request.url.path:
                    logger.warning(f"Intento de eliminar colección sin ID válido: {request.url.path}")
                    return JSONResponse(
                        status_code=400,
                        content={
                            "status": "error",
                            "message": "ID de colección no especificado o no válido",
                            "data": {
                                "error_type": "invalid_collection_id",
                                "detail": "ID de colección no especificado o no válido"
                            }
                        }
                    )
                
                # Verificar propiedad del recurso
                is_owner, error_details = await self._verify_resource_ownership(
                    user_id, resource_name, request.method
                )
                if not is_owner:
                    return JSONResponse(status_code=403, content=error_details)
            
            # 5. Guardar información útil en el estado de la solicitud
            request.state.resource_owner_id = user_id
            if resource_name:
                request.state.resource_name = resource_name
            
            logger.info(f"Acceso permitido: usuario={user_id}, recurso={resource_name or 'N/A'}, método={request.method}, ruta={request.url.path}")
            
            # Continuar con el procesamiento normal
            return await call_next(request)
            
        except Exception as e:
            logger.error(f"Error verificando permisos: {str(e)}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": "Error interno verificando permisos",
                    "data": {
                        "error_type": "internal_error",
                        "detail": str(e)
                    }
                }
            )