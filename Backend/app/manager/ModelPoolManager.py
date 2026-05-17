import logging
import os
import psutil # type: ignore
from datetime import datetime
from typing import Dict, Optional, Any
from pymongo.errors import PyMongoError
from pymongo import ASCENDING, DESCENDING

from app.manager.Mongo import Mongo

logger = logging.getLogger(__name__)

class ModelPoolManager(Mongo):
    """
    Clase que maneja todas las operaciones relacionadas con el pool de modelos,
    centralizando la lógica de acceso a la base de datos MongoDB.
    """

    def __init__(self):
        """Inicializa el gestor del pool de modelos con una conexión a MongoDB."""
        logger.info("Iniciando inicialización de ModelPoolManager")
        try:
            super().__init__()
            logger.info("Conexión base inicializada")

            if self.db is None:
                logger.error("La base de datos no está disponible después de la inicialización")
                raise RuntimeError("Database connection not available")

            logger.info("Conectando a colecciones...")
            # Verificar existencia de colecciones
            collections = self.db.list_collection_names()

            # Verificar y obtener models_status
            if 'models_status' not in collections:
                logger.info("Creando colección models_status")
                self.db.create_collection('models_status')
            self.models_status = self.db['models_status']

            # Verificar y obtener models_metrics
            if 'models_metrics' not in collections:
                logger.info("Creando colección models_metrics")
                self.db.create_collection('models_metrics')
            self.models_metrics = self.db['models_metrics']

            # Verificar y obtener cache_stats
            if 'cache_stats' not in collections:
                logger.info("Creando colección cache_stats")
                self.db.create_collection('cache_stats')
            self.cache_stats = self.db['cache_stats']

            logger.info("Configurando índices...")
            self._setup_indexes()
            logger.info("ModelPoolManager inicializado correctamente")
        except Exception as e:
            logger.error(f"Error durante la inicialización de ModelPoolManager: {str(e)}")
            logger.exception("Detalles del error:")
            raise

    def connect_models_status(self):
        """Conecta a la colección models_status"""
        try:
            if self.db is None:
                logger.error("No hay conexión a MongoDB")
                return None
            return self.db['models_status']
        except Exception as e:
            logger.error(f"Error al conectar con models_status: {e}")
            return None

    def connect_models_metrics(self):
        """Conecta a la colección models_metrics"""
        try:
            if self.db is None:
                logger.error("No hay conexión a MongoDB")
                return None
            return self.db['models_metrics']
        except Exception as e:
            logger.error(f"Error al conectar con models_metrics: {e}")
            return None

    def connect_cache_stats(self):
        """Conecta a la colección cache_stats"""
        try:
            if self.db is None:
                logger.error("No hay conexión a MongoDB")
                return None
            return self.db['cache_stats']
        except Exception as e:
            logger.error(f"Error al conectar con cache_stats: {e}")
            return None

    def _setup_indexes(self):
        """Configura índices en las colecciones para optimizar consultas."""
        try:
            # Índices para models_status
            self.models_status.create_index([
                ("model_key", ASCENDING),
                ("type", ASCENDING)
            ], unique=True)
            self.models_status.create_index([("last_used", DESCENDING)])

            # Índices para models_metrics
            self.models_metrics.create_index([
                ("model_key", ASCENDING),
                ("date", DESCENDING)
            ])

            # Índices para cache_stats
            self.cache_stats.create_index([
                ("cache_type", ASCENDING),
                ("date", DESCENDING)
            ])
        except PyMongoError as e:
            logger.error(f"Error al configurar índices en MongoDB: {e}")

    def update_model_status(
            self,
            model_key: str,
            model_type: str,
            model: Any,
            last_used: float
    ) -> bool:
        """
        Actualiza o crea el estado de un modelo en la base de datos.
        Retorna True si la operación fue exitosa, False en caso contrario.
        """
        try:
            if not hasattr(self, 'models_status') or self.models_status is None:
                self.models_status = self.connect_models_status()
                if self.models_status is None:
                    return False

            self.models_status.update_one(
                {
                    "model_key": model_key,
                    "type": model_type
                },
                {
                    "$set": {
                        "last_used": last_used,
                        "updated_at": datetime.utcnow()
                    }
                },
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error actualizando estado del modelo {model_key}: {e}")
            return False

    def get_model_status(
            self,
            model_key: str,
            model_type: str
    ) -> Optional[Dict]:
        """
        Obtiene el estado actual de un modelo.
        """
        logger.info(f"Iniciando get_model_status: model_key={model_key}, type={model_type}")
        try:
            logger.info("Verificando conexión a MongoDB...")
            if self.db is None:
                logger.error("No hay conexión a MongoDB")
                return None

            # Asegurar que tenemos acceso a la colección models_status
            if not hasattr(self, 'models_status') or self.models_status is None:
                logger.info("Reconectando a la colección models_status...")
                self.models_status = self.connect_models_status()
                if self.models_status is None:
                    logger.error("No se pudo conectar a la colección models_status")
                    return None

            logger.info("Ejecutando find_one en MongoDB...")
            result = self.models_status.find_one({
                "model_key": model_key,
                "type": model_type
            })

            logger.info(f"Resultado de MongoDB: {result}")

            if result:
                # Convertir ObjectId a string y asegurar que sea un dict
                result["_id"] = str(result["_id"])
                logger.info(f"Retornando resultado procesado: {dict(result)}")
                return dict(result)

            logger.info("No se encontró el modelo en la BD")
            return None
        except Exception as e:
            logger.error(f"Error obteniendo estado del modelo {model_key}: {e}")
            logger.exception("Detalles del error:")
            return None

    def update_cache_stats(
            self,
            cache_type: str,
            is_hit: bool
    ) -> float:
        """
        Actualiza las estadísticas de caché y retorna el hit rate actual.
        """
        try:
            if not hasattr(self, 'cache_stats') or self.cache_stats is None:
                self.cache_stats = self.connect_cache_stats()
                if self.cache_stats is None:
                    return 0.0

            today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            # Actualizar estadísticas
            result = self.cache_stats.find_one_and_update(
                {
                    "cache_type": cache_type,
                    "date": today
                },
                {
                    "$inc": {
                        "total": 1,
                        "hits": 1 if is_hit else 0
                    }
                },
                upsert=True,
                return_document=True
            )

            # Calcular hit rate
            if result:
                return (result["hits"] / result["total"]) * 100
            return 0
        except Exception as e:
            logger.error(f"Error actualizando estadísticas de caché: {e}")
            return 0

    def update_model_metrics(
            self,
            model_key: str,
            initialization_time: float,
            memory_usage: float = None
    ) -> bool:
        """
        Registra métricas de rendimiento del modelo.

        Args:
            model_key: Clave única del modelo
            initialization_time: Tiempo de inicialización en segundos
            memory_usage: Uso de memoria en MB. Si es None o 0, se intentará medir automáticamente.
        
        Returns:
            bool: True si la operación fue exitosa, False en caso contrario
        """
        try:
            if not hasattr(self, 'models_metrics') or self.models_metrics is None:
                self.models_metrics = self.connect_models_metrics()
                if self.models_metrics is None:
                    return False

            # Si no se proporciona un valor válido de uso de memoria, medimos automáticamente
            if memory_usage is None or memory_usage <= 0:
                try:
                    # Intentar medir el uso de memoria del proceso actual
                    process = psutil.Process(os.getpid())
                    memory_info = process.memory_info()
                    # Convertir bytes a MB para una mejor legibilidad
                    memory_usage = memory_info.rss / (1024 * 1024)
                    logger.debug(f"Uso de memoria medido para {model_key}: {memory_usage:.2f} MB")
                except Exception as mem_error:
                    logger.warning(f"No se pudo medir el uso de memoria: {mem_error}")
                    # Usar un valor por defecto si no se puede medir
                    memory_usage = 0

            # Si el tiempo de inicialización es 0, intentar obtener un valor más realista
            if initialization_time <= 0:
                # Si tenemos métricas anteriores, podemos usar el promedio
                previous_metrics = self.models_metrics.find({"model_key": model_key}).limit(5)
                times = [doc["initialization_time"] for doc in previous_metrics if doc["initialization_time"] > 0]
                if times:
                    initialization_time = sum(times) / len(times)
                    logger.debug(f"Usando tiempo de inicialización promedio para {model_key}: {initialization_time:.3f}s")
                else:
                    # Si no hay datos previos, usar un valor estimado conservador
                    initialization_time = 0.5  # Medio segundo como valor por defecto

            # Insertar métricas en la base de datos
            self.models_metrics.insert_one({
                "model_key": model_key,
                "initialization_time": initialization_time,
                "memory_usage": memory_usage,
                "date": datetime.utcnow(),
                "process_id": os.getpid()
            })

            logger.info(f"Métricas registradas para {model_key}: "
                        f"tiempo_init={initialization_time:.3f}s, "
                        f"memoria={memory_usage:.2f}MB")

            # Actualizar métricas agregadas para análisis de tendencias
            self.models_metrics.update_one(
                {"model_key": "aggregate_stats"},
                {
                    "$inc": {
                        "total_initializations": 1,
                        "sum_init_time": initialization_time,
                        "sum_memory": memory_usage
                    },
                    "$set": {
                        "last_updated": datetime.utcnow()
                    }
                },
                upsert=True
            )
            return True

        except Exception as e:
            logger.error(f"Error registrando métricas del modelo {model_key}: {e}")
            logger.exception("Detalles completos del error:")
            return False

    def clean_expired_models(self, max_idle_time: float) -> list:
        """
        Elimina los registros de modelos expirados y retorna las claves eliminadas.
        """
        try:
            if not hasattr(self, 'models_status') or self.models_status is None:
                self.models_status = self.connect_models_status()
                if self.models_status is None:
                    return []

            current_time = datetime.utcnow().timestamp()
            result = self.models_status.find({
                "last_used": {"$lt": current_time - max_idle_time}
            })

            expired_keys = []
            for doc in result:
                self.models_status.delete_one({"_id": doc["_id"]})
                expired_keys.append(doc["model_key"])

            return expired_keys
        except Exception as e:
            logger.error(f"Error limpiando modelos expirados: {e}")
            return []

    def get_model_statistics(self) -> Dict:
        """
        Obtiene estadísticas generales del pool de modelos.
        """
        try:
            if not hasattr(self, 'models_status') or self.models_status is None:
                self.models_status = self.connect_models_status()
            if not hasattr(self, 'models_metrics') or self.models_metrics is None:
                self.models_metrics = self.connect_models_metrics()
            if not hasattr(self, 'cache_stats') or self.cache_stats is None:
                self.cache_stats = self.connect_cache_stats()

            # Si alguna colección no está disponible, retornar diccionario vacío
            if None in [self.models_status, self.models_metrics, self.cache_stats]:
                logger.error("No se pudo conectar a todas las colecciones necesarias")
                return {}

            stats = {
                "total_models": self.models_status.count_documents({}),
                "simple_models": self.models_status.count_documents({"type": "simple"}),
                "multi_agent_models": self.models_status.count_documents({"type": "multi_agent"}),
                "average_initialization_time": 0,
                "cache_hit_rate": 0
            }

            # Calcular tiempo promedio de inicialización
            pipeline = [
                {"$group": {
                    "_id": None,
                    "avg_init_time": {"$avg": "$initialization_time"}
                }}
            ]
            result = list(self.models_metrics.aggregate(pipeline))
            if result:
                stats["average_initialization_time"] = result[0]["avg_init_time"]

            # Calcular hit rate general
            pipeline = [
                {"$group": {
                    "_id": "$cache_type",
                    "total_hits": {"$sum": "$hits"},
                    "total_requests": {"$sum": "$total"}
                }}
            ]
            result = list(self.cache_stats.aggregate(pipeline))
            total_hits = sum(r["total_hits"] for r in result)
            total_requests = sum(r["total_requests"] for r in result)
            if total_requests > 0:
                stats["cache_hit_rate"] = (total_hits / total_requests) * 100

            return stats
        except Exception as e:
            logger.error(f"Error obteniendo estadísticas del pool: {e}")
            return {}
