import logging
from datetime import datetime, timedelta
import secrets
import hashlib
import uuid
from typing import Dict, Optional, List, Tuple
from bson import ObjectId
from pymongo.errors import PyMongoError, DuplicateKeyError
from pymongo import ASCENDING
from app.models.user import UpdateProfileUser, UserCreate
from app.manager.Mongo import Mongo
from app.services.auth.auth_utils import get_password_hash, verify_password
logger = logging.getLogger(__name__)
MOCK_ADMIN_ID = ObjectId('000000000000000000000001')
MOCK_USER1_ID = ObjectId('000000000000000000000002')
MOCK_USER2_ID = ObjectId('000000000000000000000003')
HARDCODED_USERS = {'admin': {'_id': MOCK_ADMIN_ID, 'username': 'admin', 'email': 'admin@test.com', 'role': 'admin', 'plan': 'enterprise', 'is_active': True, 'password': 'hashed_password_placeholder'}, 'user1': {'_id': MOCK_USER1_ID, 'username': 'user1', 'email': 'user1@test.com', 'role': 'user', 'plan': 'free', 'is_active': True, 'password': 'hashed_password_placeholder'}, 'user2': {'_id': MOCK_USER2_ID, 'username': 'user2', 'email': 'user2@test.com', 'role': 'user', 'plan': 'free', 'is_active': True, 'password': 'hashed_password_placeholder'}}

class UserManager(Mongo):
    """
    Clase que maneja todas las operaciones relacionadas con usuarios y autenticación,
    centralizando la lógica de acceso a la base de datos MongoDB.
    """

    def __init__(self):
        """
        Inicializa el gestor de usuarios con una conexión a MongoDB.
        """
        super().__init__()
        self.users = self.db['users']
        self.refresh_tokens = self.db['refresh_tokens']
        self._setup_indexes()

    def _setup_indexes(self):
        """Configura índices en las colecciones para optimizar consultas."""
        try:
            self.users.create_index([('username', ASCENDING)], unique=True)
            self.refresh_tokens.create_index([('token', ASCENDING)], unique=True)
            self.refresh_tokens.create_index([('username', ASCENDING)])
            self.refresh_tokens.create_index([('expires_at', ASCENDING)], expireAfterSeconds=0)
        except PyMongoError as e:
            logger.error(f'Error al configurar índices en MongoDB: {e}')

    def authenticate_user(self, username: str, password: str) -> Optional[Dict]:
        """Autentica un usuario verificando sus credenciales."""
        try:
            if username in HARDCODED_USERS:
                return dict(HARDCODED_USERS[username])
            user = self.users.find_one({'username': username})
            if not user or not verify_password(password, user.get('password')):
                return None
            if user.get('origin_type') == 'provisional':
                self._update_provisional_user_tracking(user)
            return user
        except Exception as e:
            logger.error(f'Error en autenticación: {str(e)}')
            return None

    def create_user(self, user_data: Dict) -> Optional[str]:
        """
        Crea un nuevo usuario en la base de datos.
        Args:
            user_data: Diccionario con los datos del usuario a crear.
        Returns:
            str: El ID del usuario creado, o None si hay error.
        """
        try:
            result = self.users.insert_one(user_data)
            return str(result.inserted_id)
        except DuplicateKeyError:
            logger.warning(f"Intento de crear usuario con datos duplicados: {user_data.get('username')}, {user_data.get('email')}")
            raise ValueError('Username o email ya existe')
        except Exception as e:
            logger.error(f'Error creando usuario: {str(e)}')
            return None

    def get_user_profile(self, user_id: str, user) -> Dict:
        try:
            return dict(user)
        except Exception as e:
            logger.error(f'Error al obtener perfil: {str(e)}')
            raise

    def manage_refresh_token(self, user_id: str, device_info: Dict=None, ip_address: str=None) -> Tuple[str, bool, str]:
        """
        Gestiona los refresh tokens de un usuario de manera inteligente.
        Retorna: (token, is_new_token, device_id)
        - Busca un token válido existente para el dispositivo
        - Si no encuentra, crea uno nuevo
        - Limpia tokens antiguos o revocados
        - Limita el número de sesiones activas según el plan del usuario

        Args:
            user_id: ID del usuario
            device_info: Información del dispositivo
            ip_address: Dirección IP del cliente

        Returns:
            Tuple[str, bool, str]: (token, is_new_token, device_id)
        """
        try:
            device_id = device_info.get('device_id') if device_info and 'device_id' in device_info else self._generate_device_id()
            existing_token = None
            if device_id:
                existing_token = self.refresh_tokens.find_one({'user_id': user_id, 'device_info.device_id': device_id, 'expires_at': {'$gt': datetime.utcnow()}})
            if not existing_token:
                existing_token = self.refresh_tokens.find_one({'user_id': user_id, 'expires_at': {'$gt': datetime.utcnow()}})
            if existing_token and existing_token.get('is_provisional', False):
                self.refresh_tokens.update_one({'_id': existing_token['_id']}, {'$set': {'is_provisional': False, 'last_used_at': datetime.utcnow()}})
            if existing_token:
                self.refresh_tokens.update_one({'_id': existing_token['_id']}, {'$set': {'last_used_at': datetime.utcnow()}})
                token_device_id = (existing_token.get('device_info') or {}).get('device_id', device_id)
                return (existing_token['token'], False, token_device_id)
            token = secrets.token_urlsafe(32)
            expires_at = datetime.utcnow() + timedelta(days=30)
            now = datetime.utcnow()
            if not device_info:
                device_info = {'device_id': device_id, 'device_type': 'unknown', 'device_name': 'Unknown Device', 'os': 'unknown', 'browser': 'unknown'}
            else:
                device_info['device_id'] = device_id
            if ip_address:
                device_info['ip_address'] = ip_address
                device_info['location'] = self._get_location_from_ip(ip_address)
            self.refresh_tokens.insert_one({'token': token, 'user_id': user_id, 'expires_at': expires_at, 'is_provisional': False, 'device_info': device_info, 'last_used_at': now, 'created_at': now})
            return (token, True, device_id)
        except Exception as e:
            logger.error(f'Error gestionando refresh token: {str(e)}')
            raise

    def verify_refresh_token(self, username: str, token: str) -> bool:
        """Verifica si un refresh token es válido."""
        try:
            token_doc = self.refresh_tokens.find_one({'username': username, 'token': token, 'expires_at': {'$gt': datetime.utcnow()}})
            return bool(token_doc)
        except Exception as e:
            logger.error(f'Error verificando refresh token: {str(e)}')
            return False

    def revoke_refresh_token(self, username: str, token: str) -> bool:
        """Revoca un refresh token."""
        try:
            result = self.refresh_tokens.delete_one({'username': username, 'token': token})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f'Error revocando refresh token: {str(e)}')
            return False

    def update_user_profile(self, username: str, update_data: Dict) -> bool:
        """Actualiza el perfil del usuario."""
        try:
            result = self.users.update_one({'username': username}, {'$set': update_data})
            return result.modified_count > 0
        except Exception as e:
            logger.error(f'Error actualizando perfil: {str(e)}')
            return False

    def update_user_by_id(self, user_id: str, updates: Dict) -> bool:
        """
        Actualiza un documento de usuario por su ID con un set de operaciones.
        Args:
            user_id: ID del usuario a actualizar
            updates: Diccionario con las operaciones de actualización de MongoDB (e.g., {"$set": {...}})
        Returns:
            bool: True si la actualización fue exitosa, False en caso contrario
        """
        try:
            result = self.users.update_one({'_id': ObjectId(user_id)}, updates)
            return result.modified_count > 0
        except Exception as e:
            logger.error(f'Error actualizando usuario por ID {user_id}: {str(e)}')
            return False

    def update_user_profile_by_id(self, user_id: str, profile_update: UpdateProfileUser) -> bool:
        """
        Actualiza el perfil del usuario usando su ID.
        Args:
            user_id: ID del usuario
            profile_update: Objeto UpdateProfileUser con los datos del perfil a actualizar
        Returns:
            bool: True si la actualización fue exitosa, False en caso contrario
        """
        try:
            if not profile_update.profile.update:
                return True
            result = self.users.update_one({'_id': ObjectId(user_id)}, {'$set': {'profile': profile_update.profile}})
            return result.modified_count > 0
        except Exception as e:
            logger.error(f'Error actualizando perfil por ID: {str(e)}')
            return False

    def verify_user(self, username: str, password: str) -> bool:
        """Verifica las credenciales del usuario."""
        try:
            if username in HARDCODED_USERS:
                return True
            user = self.users.find_one({'username': username})
            if not user:
                return False
            return verify_password(password, user['password'])
        except Exception as e:
            logger.error(f'Error verificando usuario: {str(e)}')
            return False

    def change_password(self, username: str, new_password: str) -> bool:
        """Cambia la contraseña del usuario."""
        try:
            hashed_password = get_password_hash(new_password)
            result = self.users.update_one({'username': username}, {'$set': {'password': hashed_password}})
            return result.modified_count > 0
        except Exception as e:
            logger.error(f'Error cambiando contraseña: {str(e)}')
            return False

    def get_user(self, username: str) -> Optional[Dict]:
        """Obtiene la información de un usuario."""
        try:
            if username in HARDCODED_USERS:
                return dict(HARDCODED_USERS[username])
            return self.users.find_one({'username': username})
        except Exception as e:
            logger.error(f'Error obteniendo usuario: {str(e)}')
            return None

    def get_user_by_id(self, user_id: str) -> Optional[Dict]:
        """Obtiene la información de un usuario por su ID."""
        try:
            for user in HARDCODED_USERS.values():
                if str(user['_id']) == str(user_id):
                    return dict(user)
            return self.users.find_one({'_id': ObjectId(user_id)})
        except Exception as e:
            logger.error(f'Error obteniendo usuario por ID: {str(e)}')
            return None

    def is_user_active(self, username: str) -> bool:
        """Determina si un usuario está activo."""
        try:
            if username in HARDCODED_USERS:
                return HARDCODED_USERS[username].get('is_active', False)
            user = self.users.find_one({'username': username})
            return user.get('is_active', False)
        except Exception as e:
            logger.error(f'Error verificando usuario activo: {str(e)}')
            return False

    def update_user_role(self, user_id: str, role: str) -> bool:
        """
        Actualiza el rol de un usuario.

        Args:
            user_id: ID del usuario
            role: Nuevo rol a asignar

        Returns:
            bool: True si se actualiza con éxito, False si hay error
        """
        try:
            valid_roles = ['user', 'admin', 'staff']
            if role not in valid_roles:
                logger.warning(f'Intento de asignar rol inválido: {role}')
                return False
            result = self.users.update_one({'_id': ObjectId(user_id)}, {'$set': {'role': role}})
            if result.modified_count == 0:
                logger.warning(f'No se modificó el rol para el usuario: {user_id}')
                return False
            logger.info(f'Rol actualizado para usuario {user_id}: {role}')
            return True
        except Exception as e:
            logger.error(f'Error al actualizar rol de usuario {user_id}: {str(e)}')
            return False

    def update_user_plan(self, user_id: str, plan: str) -> bool:
        """
        Actualiza el plan de suscripción de un usuario.

        Args:
            user_id: ID del usuario
            plan: Nuevo plan a asignar

        Returns:
            bool: True si se actualiza con éxito, False si hay error
        """
        try:
            valid_plans = ['free', 'basic', 'premium', 'enterprise']
            if plan not in valid_plans:
                logger.warning(f'Intento de asignar plan inválido: {plan}')
                return False
            result = self.users.update_one({'_id': ObjectId(user_id)}, {'$set': {'plan': plan}})
            if result.modified_count == 0:
                logger.warning(f'No se modificó el plan para el usuario: {user_id}')
                return False
            logger.info(f'Plan actualizado para usuario {user_id}: {plan}')
            return True
        except Exception as e:
            logger.error(f'Error al actualizar plan de usuario {user_id}: {str(e)}')
            return False

    def _generate_device_id(self) -> str:
        """
        Genera un ID único para un dispositivo.

        Returns:
            str: ID único para el dispositivo
        """
        return str(uuid.uuid4())

    def _get_location_from_ip(self, ip_address: str) -> Dict:
        """
        Obtiene información de ubicación aproximada basada en IP.
        Esta es una implementación básica. En producción, se podría usar
        un servicio como MaxMind GeoIP o similar.

        Args:
            ip_address: Dirección IP del cliente

        Returns:
            Dict: Información de ubicación
        """
        return {'country': 'unknown', 'city': 'unknown', 'region': 'unknown'}

    def get_active_sessions(self, user_id: str) -> List[Dict]:
        """
        Obtiene todas las sesiones activas del usuario.

        Args:
            user_id: ID del usuario

        Returns:
            List[Dict]: Lista de sesiones activas
        """
        try:
            sessions = list(self.refresh_tokens.find({'user_id': user_id, 'expires_at': {'$gt': datetime.utcnow()}}))
            formatted_sessions = []
            for session in sessions:
                if 'device_info' not in session:
                    session['device_info'] = {'device_id': self._generate_device_id(), 'device_type': 'unknown', 'device_name': 'Unknown Device', 'os': 'unknown', 'browser': 'unknown', 'last_used_at': session.get('last_used_at', datetime.utcnow()), 'created_at': session.get('created_at', datetime.utcnow())}
                if 'last_used_at' not in session['device_info']:
                    session['device_info']['last_used_at'] = session.get('last_used_at', datetime.utcnow())
                if 'created_at' not in session['device_info']:
                    session['device_info']['created_at'] = session.get('created_at', datetime.utcnow())
                if 'created_at' not in session:
                    session['created_at'] = session.get('last_used_at', datetime.utcnow())
                formatted_session = {'id': str(session['_id']), 'device_info': session['device_info']}
                formatted_sessions.append(formatted_session)
            return formatted_sessions
        except Exception as e:
            logger.error(f'Error obteniendo sesiones activas: {str(e)}')
            return []

    def revoke_session_by_id(self, user_id: str, session_id: str) -> bool:
        """
        Revoca una sesión específica por su ID.

        Args:
            user_id: ID del usuario
            session_id: ID de la sesión a revocar

        Returns:
            bool: True si se revocó correctamente, False en caso contrario
        """
        try:
            result = self.refresh_tokens.delete_one({'_id': ObjectId(session_id), 'user_id': user_id})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f'Error revocando sesión: {str(e)}')
            return False

    def revoke_all_sessions_except_current(self, user_id: str, current_token: str) -> bool:
        """
        Revoca todas las sesiones excepto la actual.

        Args:
            user_id: ID del usuario
            current_token: Token actual que no debe ser revocado

        Returns:
            bool: True si se revocaron correctamente, False en caso contrario
        """
        try:
            current_session = self.refresh_tokens.find_one({'user_id': user_id, 'token': current_token})
            if not current_session:
                return False
            result = self.refresh_tokens.delete_many({'user_id': user_id, '_id': {'$ne': current_session['_id']}})
            return result.deleted_count >= 0
        except Exception as e:
            logger.error(f'Error revocando sesiones: {str(e)}')
            return False

    def get_user_by_provider_uid(self, provider: str, provider_uid: str):
        field = f'{provider}_provider.uid'
        return self.users.find_one({field: provider_uid})

    def get_user_email(self, email: str):
        return self.users.find_one({'email': email})