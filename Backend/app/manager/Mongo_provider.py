import os
import logging
from abc import ABC

from pymongo import MongoClient
from dotenv import load_dotenv

from app.manager.ConversationManager import ConversationManager
from app.manager.ModelPoolManager import ModelPoolManager
from app.manager.RateLimitManager import RateLimitManager
from app.manager.TimeTrackerManager import TimeTrackerManager
from app.manager.UserManager import UserManager


class Mongo_provider(ABC):
    _instance = None
    _client = None
    _db = None

    def __new__(cls):
        """Asegura que solo exista una instancia de Mongo"""
        if cls._instance is None:
            cls._instance = super(Mongo_provider, cls).__new__(cls)
            cls._instance._initialize_connection()
        return cls._instance

    @classmethod
    def _initialize_connection(self):
        """Inicializa la conexión a MongoDB Atlas"""
        if Mongo_provider._client is None:
            load_dotenv()
            logging.getLogger("pymongo").setLevel(logging.WARNING)

            mongo_uri = os.getenv('MONGODB_URI')
            if not mongo_uri:
                raise ValueError("MONGODB_URI environment variable not set")

            Mongo_provider._client = MongoClient(mongo_uri)
            db_name = os.getenv('MONGODB_DB_NAME')
            Mongo_provider._db = Mongo_provider._client[db_name]

            # Configurar índices
            if self.__class__ is Mongo_provider:
                self._setup_indexes()

        self.db = Mongo_provider._db
        self.users_manager = UserManager()
        self.conversation_manager = ConversationManager()
        self.time_tracker_manager = TimeTrackerManager()
        self.rate_limit_manager = RateLimitManager()
        self.models_pool_manager = ModelPoolManager()


    def _setup_indexes(self):
        """Configura todos los índices necesarios para la base de datos"""
        # Índice para usuarios
        Mongo_provider._db.users.create_index("username", unique=True)
    @classmethod
    def close_connection(cls):
        """Cierra la conexión compartida (debe usarse con precaución)"""
        if cls._client:
            cls._client.close()
            cls._client = None
            cls._db = None
            cls._instance = None

    # Métodos de conexión a colecciones
    def connect_distributors(self):
        collection = self.db['distributors']
        return collection

    def connect_users(self):
        collection = self.db['users']
        return collection

    def connect_models(self):
        collection = self.db['models']
        return collection

    def connect_conversations(self):
        collection = self.db['conversations']
        return collection

    def connect_prompts(self):
        collection = self.db['prompts']
        return collection