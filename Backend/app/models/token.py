from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict
from datetime import datetime

class TokenData(BaseModel):
    username: str
    role: str
    usage_limits: List[dict]
    exp: Optional[int] = None
    device_id: Optional[str] = None

class Token(BaseModel):
    user_id: str
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    username: str
    role: str
    plan: str
    usage_limits: Optional[List[dict]] = None
    device_info: Optional[Dict] = None

class RefreshToken(BaseModel):
    refresh_token: str

class DeviceInfo(BaseModel):
    device_id: str
    device_type: str
    device_name: Optional[str] = None
    os: Optional[str] = None
    browser: Optional[str] = None
    ip_address: Optional[str] = None
    location: Optional[Dict] = None
    last_used_at: datetime
    created_at: datetime

class SessionInfo(BaseModel):
    id: str
    device_info: DeviceInfo
    is_current: Optional[bool] = False

class ResponseSessionInfo(BaseModel):
    data: List[SessionInfo]
    current_session: Optional[SessionInfo] = None
    message: Optional[str] = None
    status: Optional[int] = None
    error: Optional[str] = None