from datetime import datetime
from typing import List, Optional
from bson import ObjectId
from pydantic import BaseModel, Field, EmailStr, validator

class UserUpdate(BaseModel):
    email: str | None = None
    role: str | None = None

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class RefreshToken(BaseModel):
    """Modelo para los tokens de refresco"""
    token: str
    session_id: str
    created_at: datetime
    last_used: datetime
    is_revoked: bool = False
    revoked_at: Optional[datetime] = None

class UserSession(BaseModel):
    """Modelo para las sesiones de usuario"""
    token: str
    created_at: datetime | None

class UserStats(BaseModel):
    endpoints: dict
    total_daily_usage: int
    total_monthly_usage: int

class UserAuth(BaseModel):
    username: str
    password: str

class UserCreate(BaseModel):
    username: str
    password: str
    email: EmailStr
    role: str = "user"
    plan: str = "free"
    profile: dict = {}

class UserInDB(BaseModel):
    """Modelo para usuarios en la base de datos"""
    id: Optional[str] = Field(None, alias="_id")
    username: str
    email: EmailStr
    is_active: bool = True
    role: str = "user"
    plan: str = "free"  # Plan del usuario (free, basic, pro, etc.)
    origin_type: str = "registered"  # "registered" | "provisional"
    created_at: datetime = datetime.now()
    last_login: Optional[datetime] = None
    origin_ip: Optional[str] = None
    profile: dict = {}

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            ObjectId: str
        }

    @validator('origin_type')
    def validate_origin_type(cls, v):
        """Valida que origin_type sea uno de los valores permitidos"""
        if v not in ["registered", "provisional"]:
            raise ValueError('origin_type debe ser "registered" o "provisional"')
        return v

class UpdateProfileUser(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    profile: dict
