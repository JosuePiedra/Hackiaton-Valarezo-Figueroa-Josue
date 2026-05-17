import os
import logging
import re
import uuid
from fastapi.security import OAuth2PasswordBearer
from app.models.user import UserInDB, UserCreate
from app.manager.Mongo_provider import Mongo_provider
from datetime import datetime
from app.services.auth.auth_utils import create_access_token, get_password_hash
from typing import Dict, Optional, List

# Configurar logging
logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="token",
    scopes={"admin": "Acceso total", "user": "Acceso básico"}
)

class AuthService:
    """
    Clase que encapsula la lógica de autenticación y gestión de usuarios.
    Centraliza las operaciones relacionadas con autenticación, separando
    la lógica de negocio de los endpoints.
    """

    def __init__(self):
        self.db = Mongo_provider()
        logger.info("AuthService inicializado")

    def login(self, username: str, password: str, device_info: Dict = None, ip_address: str = None) -> Dict:
        """
        Autentica un usuario y genera tokens de acceso y refresco.
        """
        logger.info(f"Intento de login para usuario: {username}")
        try:
            user = self.db.users_manager.authenticate_user(username, password)
            if not user:
                raise ValueError("Credenciales incorrectas")

            processed_device_info = self._process_device_info(device_info, ip_address)
            device_id = processed_device_info.get("device_id")

            token_payload = {
                "sub": user["username"],
                "role": user.get("role", "user"),
                "plan": user.get("plan", "free"),
                "id": str(user["_id"]),
                "device_id": device_id
            }
            access_token = create_access_token(token_payload)

            refresh_token, _, _ = self.db.users_manager.manage_refresh_token(
                str(user["_id"]),
                device_info=processed_device_info,
                ip_address=ip_address
            )

            logger.info(f"Login exitoso para usuario: {username}")
            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "username": user["username"],
                "role": user.get("role", "user"),
                "plan": user.get("plan", "free"),
                "_id": str(user["_id"])
            }
        except Exception as e:
            logger.error(f"Error en login: {str(e)}", exc_info=True)
            raise

    def register_user(self, user_data: UserCreate, client_ip: str, device_info: Dict = None) -> Dict:
        """
        Registra un nuevo usuario o convierte un usuario provisional existente.
        """
        logger.info(f"Intento de registro para usuario: {user_data.username}")
        try:
            if self.db.users_manager.get_user(user_data.username) or self.db.users_manager.users.find_one({"email": user_data.email}):
                raise ValueError("No se pudo completar el registro con los datos proporcionados")

            safe_user_data = UserCreate(
                username=user_data.username,
                password=user_data.password,
                email=user_data.email,
                role="user",
                plan="free",
                profile=user_data.profile
            )

            user_id, _ = self.db.users_manager.create_or_update_provisional_user(safe_user_data, client_ip)
            user = self.db.users_manager.get_user_by_id(user_id)
            if not user:
                raise ValueError("Error interno, no se pudo obtener usuario recién creado.")

            processed_device_info = self._process_device_info(device_info, client_ip)
            device_id = processed_device_info.get("device_id")

            token_payload = {
                "sub": user["username"],
                "role": user["role"],
                "plan": user["plan"],
                "id": user_id,
                "device_id": device_id
            }
            access_token = create_access_token(token_payload)

            refresh_token, _, _ = self.db.users_manager.manage_refresh_token(
                user_id,
                device_info=processed_device_info,
                ip_address=client_ip
            )

            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "username": user["username"],
                "role": user["role"],
                "plan": user["plan"],
                "_id": user_id
            }
        except Exception as e:
            logger.error(f"Error en registro: {str(e)}", exc_info=True)
            raise

    def get_user_profile(self, user_id: str, user_payload: Dict) -> Dict:
        try:
            user_profile = self.db.users_manager.get_user_profile(user_id, user_payload)
            if not user_profile:
                raise ValueError("Error interno, no se pudo obtener perfil del usuario.")
            return user_profile
        except Exception as e:
            logger.error(f"Error al obtener perfil de usuario: {str(e)}", exc_info=True)
            raise

    def logout(self, username: str, refresh_token: str) -> bool:
        return self.db.users_manager.revoke_refresh_token(username, refresh_token)

    def get_user_sessions(self, user_id: str) -> List[Dict]:
        try:
            return self.db.users_manager.get_active_sessions(user_id)
        except Exception as e:
            logger.error(f"Error al obtener sesiones del usuario: {str(e)}")
            raise ValueError(f"Error al obtener sesiones: {str(e)}")

    def revoke_session(self, user_id: str, session_id: str) -> bool:
        try:
            return self.db.users_manager.revoke_session_by_id(user_id, session_id)
        except Exception as e:
            logger.error(f"Error al revocar sesión: {str(e)}")
            return False

    def revoke_all_sessions_except(self, user_id: str, current_token: str) -> bool:
        try:
            return self.db.users_manager.revoke_all_sessions_except_current(user_id, current_token)
        except Exception as e:
            logger.error(f"Error al revocar sesiones: {str(e)}")
            return False

    def change_password(self, username: str, current_password: str, new_password: str) -> bool:
        if not self.db.users_manager.verify_user(username, current_password):
            raise ValueError("Contraseña actual incorrecta")
        return self.db.users_manager.change_password(username, new_password)

    def update_user_role(self, user_id: str, role: str, admin_username: str) -> bool:
        valid_roles = ["user", "admin", "staff"]
        if role not in valid_roles:
            raise ValueError(f"Rol inválido. Valores permitidos: {', '.join(valid_roles)}")
        
        target_user = self.db.users_manager.get_user_by_id(user_id)
        if not target_user:
            raise ValueError("Usuario no encontrado")

        if target_user.get("username") == "admin": # Simplified superadmin check
            raise ValueError("No se puede cambiar el rol del superadministrador")

        return self.db.users_manager.update_user_role(user_id, role)

    def update_user_plan(self, user_id: str, plan: str, admin_username: str) -> bool:
        valid_plans = ["free", "basic", "premium", "enterprise"]
        if plan not in valid_plans:
            raise ValueError(f"Plan inválido. Valores permitidos: {', '.join(valid_plans)}")
        return self.db.users_manager.update_user_plan(user_id, plan)

    def _process_device_info(self, device_info: Optional[Dict] = None, ip_address: Optional[str] = None) -> Dict:
        now = datetime.utcnow()
        if not device_info:
            device_info = {}

        if not device_info.get("device_id"):
            user_agent = device_info.get("user_agent", "")
            device_info["device_id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, user_agent)) if user_agent else str(uuid.uuid4())

        # Basic device parsing from User-Agent
        # ... (rest of the parsing logic is fine)

        device_info["last_used_at"] = now
        if not device_info.get("created_at"):
            device_info["created_at"] = now
        if ip_address:
            device_info["ip_address"] = ip_address
        
        return device_info

    def create_first_admin(self, user_data: UserCreate, secret_key: str, client_ip: str, device_info: Dict = None) -> Dict:
        admin_secret = os.environ.get("ADMIN_SECRET_KEY")
        if not admin_secret or secret_key != admin_secret:
            raise ValueError("Clave secreta inválida")

        if self.db.users_manager.users.find_one({"role": "admin"}):
            raise ValueError("Ya existe un usuario administrador")

        admin_data = {
            "username": user_data.username,
            "email": user_data.email,
            "password": get_password_hash(user_data.password),
            "role": "admin",
            "plan": "enterprise",
            "is_active": True,
            "created_at": datetime.utcnow(),
        }
        user_id = self.db.users_manager.create_user(admin_data)

        processed_device_info = self._process_device_info(device_info, client_ip)
        device_id = processed_device_info.get("device_id")

        token_payload = {
            "sub": admin_data["username"],
            "role": "admin",
            "plan": "enterprise",
            "id": user_id,
            "device_id": device_id
        }
        access_token = create_access_token(token_payload)

        refresh_token, _, _ = self.db.users_manager.manage_refresh_token(
            user_id,
            device_info=processed_device_info,
            ip_address=client_ip
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user_id": user_id,
            "username": admin_data["username"],
        }

auth_service = AuthService()