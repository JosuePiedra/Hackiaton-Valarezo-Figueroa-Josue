from typing import Dict, Optional, Tuple, Any
import time
import logging
from langchain_chroma import Chroma
logger = logging.getLogger(__name__)
class VectorStorePool:
    """Pool de colecciones de vector stores para reutilización"""
    
    # Singleton pattern
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def __init__(self, max_idle_time=600):  # 10 minutos por defecto
        # Evitar reinicialización
        if VectorStorePool._instance is not None:
            return
            
        self.collections = {}  # {collection_name: (collection_instance, last_used_timestamp)}
        self.max_idle_time = max_idle_time
        logger.info(f"VectorStorePool inicializado con tiempo máximo de inactividad: {max_idle_time}s")
        
        VectorStorePool._instance = self
    
    def get_collection(self, collection_name: str) -> Optional[Chroma]:
        """Obtiene una colección del pool o la carga si no existe"""
        # Verificar si ya existe en el pool y no está expirada
        current_time = time.time()
        if collection_name in self.collections:
            collection, last_used = self.collections[collection_name]
            if current_time - last_used <= self.max_idle_time:
                # Actualizar timestamp y devolver colección existente
                self.collections[collection_name] = (collection, current_time)
                logger.debug(f"Vector store reutilizado del pool: {collection_name}")
                return collection
        
        # Si no existe o está expirada, cargar desde ChromaDB
        from app.services.Chroma import load_collection
        collection = load_collection(collection_name)
        
        if collection:
            # Almacenar en el pool con timestamp actual
            self.collections[collection_name] = (collection, current_time)
            logger.debug(f"Vector store cargado y añadido al pool: {collection_name}")
            
        return collection
    
    def clean_expired(self):
        """Limpia las colecciones expiradas del pool"""
        current_time = time.time()
        expired_keys = [
            key for key, (_, last_used) in self.collections.items()
            if current_time - last_used > self.max_idle_time
        ]
        
        for key in expired_keys:
            del self.collections[key]
            
        if expired_keys:
            logger.info(f"Limpiadas {len(expired_keys)} colecciones expiradas del pool")

# Instancia global para fácil acceso
vector_store_pool = VectorStorePool.get_instance()