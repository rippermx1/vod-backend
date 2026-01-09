from datetime import datetime
from uuid import UUID
from pydantic import BaseModel
from typing import Optional
from app.modules.subscriptions.models import ConsumerSubscriptionStatus

class SubscriptionCreate(BaseModel):
    pass 

class SubscriptionProof(BaseModel):
    tx_hash: str

class SubscriptionRead(BaseModel):
    id: UUID
    consumer_id: UUID
    creator_id: UUID
    status: ConsumerSubscriptionStatus
    proof_tx_hash: Optional[str]
    current_period_end: datetime
    created_at: datetime
    consumer_email: Optional[str] = None
    creator_email: Optional[str] = None
    new_posts_count: int = 0
    monthly_price: Optional[float] = 0.0
    creator_name: Optional[str] = None
    creator_avatar_url: Optional[str] = None
    
    class Config:
        from_attributes = True
