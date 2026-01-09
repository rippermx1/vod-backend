from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from uuid import UUID
from modules.plans.models import SubscriptionStatus, PaymentStatus

class PlanFeatureBase(BaseModel):
    feature_key: str
    is_enabled: bool

class PlanLimitBase(BaseModel):
    limit_key: str
    limit_value: int

class PlanBase(BaseModel):
    code: str
    name: str
    price_usdt: float
    period_days: int
    is_active: bool = True

class PlanCreate(PlanBase):
    features: List[PlanFeatureBase] = []
    limits: List[PlanLimitBase] = []

class PlanRead(PlanBase):
    id: UUID
    features: List[PlanFeatureBase]
    limits: List[PlanLimitBase]
    
    class Config:
        from_attributes = True

class PaymentCreate(BaseModel):
    plan_id: UUID
    tx_hash: str
    amount_usdt: float

class PaymentRead(BaseModel):
    id: UUID
    creator_id: UUID
    creator_email: Optional[str] = None
    plan_id: UUID
    status: PaymentStatus
    tx_hash: str
    amount_usdt: float
    created_at: datetime

    class Config:
        from_attributes = True

class SubscriptionRead(BaseModel):
    id: UUID
    plan: PlanRead
    status: SubscriptionStatus
    expires_at: Optional[datetime]

    class Config:
        from_attributes = True

class PaymentMethodCreate(BaseModel):
    payment_type: str
    details: dict

class PaymentMethodRead(BaseModel):
    id: UUID
    payment_type: str
    details: dict
    is_active: bool

    class Config:
        from_attributes = True
