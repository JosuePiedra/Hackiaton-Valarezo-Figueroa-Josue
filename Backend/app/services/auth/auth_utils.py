import logging
import os
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, Request, status
from fastapi import HTTPException
from bson import ObjectId
from jose import jwt, JWTError

from app.models.token import TokenData
from passlib.context import CryptContext
from dotenv import load_dotenv

from app.models.user import UserInDB
logger = logging.getLogger(__name__)

load_dotenv()
# Configuración de seguridad
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-default")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 3000000))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 3000))

def _serialize_datetime(obj):
    """Serializa recursivamente objetos datetime en una estructura de datos"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {key: _serialize_datetime(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [_serialize_datetime(item) for item in obj]
    return obj

def create_jwt_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Crea un token JWT"""
    # Serializar todos los objetos datetime en la estructura
    to_encode = _serialize_datetime(data)

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)

    # Add expiration time
    to_encode["exp"] = expire.timestamp()  # Use timestamp instead of datetime object

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_access_token(data: dict) -> str:
    """Crea un token de acceso"""
    return create_jwt_token(
        data,
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

def create_refresh_token(data: dict) -> str:
    """Crea un token de actualización"""
    return create_jwt_token(
        data,
        timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    )

def verify_token(token: str) -> Optional[TokenData]:
    """Verifica un token JWT"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
        token_data = TokenData(
            username=username,
            role=payload.get("role", "user"),
            usage_limits=payload.get("usage_limits", []),
            exp=payload.get("exp")
        )
        return token_data
    except JWTError:
        return None

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica si la contraseña coincide con el hash"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Genera un hash de la contraseña"""
    return pwd_context.hash(password)


async def get_current_user(
        request: Request,
) -> UserInDB:
    """
    Obtiene el usuario actual usando el payload validado por el middleware.
    El token se mantiene como parámetro por compatibilidad con FastAPI.
    """
    from app.manager.Mongo_provider import Mongo_provider

    db = Mongo_provider()
    logger.debug("Iniciando get_current_user")

    if not hasattr(request.state, 'user'):
        logger.error("No se encontró user en request.state")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No se encontró información del usuario"
        )

    # El middleware ya validó el token y guardó el payload
    payload = request.state.user
    logger.debug(f"Payload del usuario: {payload}")

    # El middleware ya verificó que el usuario existe y está activo
    try:
        logger.debug(f"Obteniendo usuario de la base de datos: {payload.get('sub')}")
        user_data = db.users_manager.get_user(payload.get("sub"))
        if user_data is None:
            logger.error(f"Usuario no encontrado en DB: {payload.get('sub')}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuario no encontrado"
            )

        # Convertir ObjectId a string para que Pydantic pueda procesarlo
        if "_id" in user_data and isinstance(user_data["_id"], ObjectId):
            user_data["_id"] = str(user_data["_id"])

        # Garantizar que los refresh_tokens sean objetos válidos
        if "refresh_tokens" in user_data and isinstance(user_data["refresh_tokens"], list):
            refresh_tokens = []
            for token in user_data["refresh_tokens"]:
                if isinstance(token, dict):
                    # Convertir cualquier ObjectId en los tokens también
                    if "_id" in token and isinstance(token["_id"], ObjectId):
                        token["_id"] = str(token["_id"])
                    refresh_tokens.append(token)
            user_data["refresh_tokens"] = refresh_tokens

        logger.debug("Usuario encontrado y validado correctamente")
        logger.debug(f"Datos de usuario procesados: {user_data}")

        return UserInDB(**user_data)
    except Exception as e:
        logger.error(f"Error al obtener usuario: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener usuario: {str(e)}"
        )
