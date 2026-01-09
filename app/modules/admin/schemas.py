from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional, Dict, Any

class AdminStats(BaseModel):
    total_users: int
    total_creators: int
    total_consumers: int
    pending_kyc: int
    pending_payments: int
    revenue_total_usdt: float

class AuditLogRead(BaseModel):
    id: UUID
    user_id: Optional[UUID]
    action: str
    target_type: Optional[str]
    target_id: Optional[str]
    ip_address: Optional[str]
    created_at: datetime
    metadata_json: Optional[Dict[str, Any]]

    class Config:
        from_attributes = True

class SystemSettingRead(BaseModel):
    key: str
    value: str
    description: Optional[str]

class SystemSettingUpdate(BaseModel):
    value: str
    description: Optional[str] = None

from app.modules.auth.schemas import UserRead

class UserUpdateAdmin(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None # 'admin', 'creator', 'consumer'
    is_active: Optional[bool] = None
    bio: Optional[str] = None
    plan_id: Optional[UUID] = None

class UserDetail(UserRead):
    plan_id: Optional[UUID] = None # Added for manual Plan Override
    # Extended Stats
    created_content_count: int = 0
    active_subscriptions_count: int = 0
    subscribers_count: int = 0
    total_spent_usdt: float = 0.0
    
    # Recent Activity
    recent_logs: list[AuditLogRead] = []
