from typing import Optional
from pydantic import BaseModel, EmailStr
from modules.auth.models import UserRole, KYCStatus
from uuid import UUID

class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    role: UserRole = UserRole.CONSUMER

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    monthly_price: Optional[float] = None
    subscription_enabled: Optional[bool] = None

class UserRead(UserBase):
    id: UUID
    is_active: bool
    kyc_status: KYCStatus
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    monthly_price: Optional[float] = 9.99
    subscription_enabled: bool = True
    
    class Config:
        from_attributes = True

class CreatorProfileResponse(UserRead):
    is_subscribed: bool = False
    likes_count: int = 0
    is_liked: bool = False

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    id: Optional[str] = None
