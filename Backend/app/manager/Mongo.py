import os
import secrets
from time import sleep

import bcrypt
from bson import ObjectId
from pymongo import MongoClient
from datetime import datetime
from typing import Optional, Any
from app.models.distributors import Distributor, Model
import logging
from dotenv import load_dotenv
from app.services.auth.auth_utils import create_refresh_token
logger = logging.getLogger(__name__)

class Mongo:
    # Conexión compartida
    _client: Optional[MongoClient] = None
    _db: Optional[Any] = None

    @classmethod
    def get_instance(cls):
        if cls._client is None:
            load_dotenv()

            mongo_uri = os.getenv('MONGODB_URI')
            if not mongo_uri:
                raise ValueError("MONGODB_URI environment variable not set")

            try:
                cls._client = MongoClient(
                    mongo_uri,
                    serverSelectionTimeoutMS=5000,
                    connectTimeoutMS=5000,
                    socketTimeoutMS=10000,
                )
                if cls._client is None:
                    raise ConnectionError("Failed to create MongoDB client")
                db_name = os.getenv('MONGODB_DB_NAME')
                cls._db = cls._client[db_name]
            except Exception as e:
                logger.error(f"MongoDB connection error: {e}")
                raise ConnectionError(f"Could not connect to MongoDB: {e}")

            # Configurar índices una sola vez
            cls._db.users.create_index("username", unique=True)
        return cls._db

    def __init__(self):
        """Inicializa el acceso a MongoDB Atlas"""
        self.db = self.get_instance()
        if self.db is None:
            raise ConnectionError("Failed to initialize MongoDB connection")
    def connect_distributors(self):
        if self.db is None:
            self.db = self.get_instance()
            if self.db is None:
                raise ConnectionError("Could not connect to MongoDB database")
        collection = self.db['distributors']
        return collection

    def connect_users(self):
        if self.db is None:
            self.db = self.get_instance()
            if self.db is None:
                raise ConnectionError("Could not connect to MongoDB database")
        collection = self.db['users']
        return collection

    def connect_models(self):
        if self.db is None:
            self.db = self.get_instance()
            if self.db is None:
                raise ConnectionError("Could not connect to MongoDB database")
        collection = self.db['models']
        return collection
    # USUARIOS

    def insert_distributor(self, distributor: Distributor):
        collection = self.connect_distributors()
        collection.insert_one(distributor.dict(by_alias=True))

    def get_all_distributors(self):
        collection = self.connect_distributors()
        distributors = list(collection.find())
        # Convert ObjectId to string for each document
        for distributor in distributors:
            distributor['_id'] = str(distributor['_id'])
        return distributors

    def get_distributor(self, distributor_id: str):
        collection = self.connect_distributors()
        distributor = collection.find_one({"_id": ObjectId(distributor_id)})
        if distributor:
            return Distributor(**distributor)
        return None

    def insert_model(self, model: Model):
        collection = self.connect_models()
        collection.insert_one(model.dict(by_alias=True))

    def get_distributor_with_models(self, distributor_id: str):
        distributor_collection = self.connect_distributors()
        models_collection = self.connect_models()

        try:
            distributor_object_id = ObjectId(distributor_id)
        except Exception:
            return None
        result = []
        distributor = distributor_collection.find_one({"_id": distributor_object_id})
        if not distributor:
            return None

        distributor['_id'] = str(distributor['_id'])
        distributor = Distributor(**distributor)

        models = list(models_collection.find({"distributor_id": distributor_object_id}))
        for model in models:
            model['_id'] = str(model['_id'])
            model['distributor_id'] = str(model['distributor_id'])

        models = [Model(**model) for model in models]
        distributor.models = models
        result.append(distributor)

        return result

    def get_all_distributors_with_models(self):
        distributors_collection = self.connect_distributors()
        models_collection = self.connect_models()

        all_distributors_with_models = []

        for distributor_doc in distributors_collection.find():
            distributor = Distributor(**distributor_doc)
            models = list(models_collection.find({"distributor_id": distributor.id}))
            models = [Model(**model) for model in models]

            # Assign models to the distributor object
            distributor.models = models
            all_distributors_with_models.append(distributor)
        return all_distributors_with_models

    def connect_conversations(self):
        """Conecta a la colección de conversaciones"""
        if self.db is None:
            self.db = self.get_instance()
            if self.db is None:
                raise ConnectionError("Could not connect to MongoDB database")
        collection = self.db['conversations']
        return collection

    def manage_refresh_tokens(self, username: str) -> tuple[str, bool]:
        """
        Gestiona los refresh tokens de un usuario de manera inteligente.
        Retorna: (token, is_new_token)
        - Busca un token válido existente
        - Si no encuentra, crea uno nuevo
        - Limpia tokens antiguos o revocados
        """
        # Buscar tokens válidos existentes
        collection_user = self.connect_users()
        user = collection_user.find_one(
            {"username": username},
            {"refresh_tokens": 1}
        )

        now = datetime.now()
        valid_token = None

        if user and "refresh_tokens" in user:
            for token_data in user["refresh_tokens"]:
                if token_data.get("is_revoked"):
                    continue

                try:
                    # Verificar si el token no es muy antiguo (> 30 días)
                    created_at = token_data.get("created_at", now)
                    if (now - created_at).days <= 30:
                        valid_token = token_data["token"]
                        # Actualizar último uso
                        collection_user.update_one(
                            {"username": username, "refresh_tokens.token": valid_token},
                            {"$set": {"refresh_tokens.$.last_used": now}}
                        )
                        break
                except:
                    continue

        if valid_token:
            return valid_token, False

        # Si no hay token válido, crear uno nuevo
        new_token = create_refresh_token(data={"sub": username})
        token_data = {
            "token": new_token,
            "session_id": secrets.token_hex(16),
            "created_at": now,
            "last_used": now,
            "is_revoked": False,
            "revoked_at": None
        }

        # Limpiar tokens antiguos y guardar el nuevo
        self._cleanup_old_sessions(username, max_sessions=5)
        collection_user.update_one(
            {"username": username},
            {
                "$push": {
                    "refresh_tokens": {
                        "$each": [token_data],
                        "$sort": {"last_used": -1}
                    }
                },
                "$set": {"last_login": now}
            }
        )

        return new_token, True

    def _cleanup_old_sessions(self, username: str, max_sessions: int):
        """Limpia sesiones antiguas si se excede el límite máximo"""
        collection_user = self.connect_users()
        user = collection_user.find_one(
            {"username": username},
            {"refresh_tokens": 1}
        )

        if not user or "refresh_tokens" not in user:
            return

        tokens = user.get("refresh_tokens", [])
        active_tokens = [t for t in tokens if not t.get("is_revoked", False)]

        if len(active_tokens) >= max_sessions:
            # Mantener solo las sesiones más recientes
            tokens_to_keep_ids = [t["session_id"] for t in sorted(
                active_tokens,
                key=lambda x: x.get("last_used", x.get("created_at")),
                reverse=True
            )[:max_sessions - 1]]

            # Marcar como revocadas las sesiones más antiguas
            collection_user.update_one(
                {"username": username},
                {
                    "$set": {
                        "refresh_tokens.$[elem].is_revoked": True,
                        "refresh_tokens.$[elem].revoked_at": datetime.now()
                    }
                },
                array_filters=[{
                    "elem.session_id": {"$nin": tokens_to_keep_ids},
                    "elem.is_revoked": False
                }]
            )

    def revoke_all_refresh_tokens(self, username: str) -> bool:
        """Revoca todos los refresh tokens activos de un usuario"""
        collection_user = self.connect_users()
        result = collection_user.update_one(
            {"username": username},
            {
                "$set": {
                    "refresh_tokens.$[elem].is_revoked": True,
                    "refresh_tokens.$[elem].revoked_at": datetime.now()
                }
            },
            array_filters=[{"elem.is_revoked": False}]
        )
        return result.modified_count > 0

    def close_connection(self):
        if self._client is not None:
            self._client.close()