import uuid
from sqlalchemy import Column, DateTime, ForeignKey, Enum, func, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum
from app.core.db import Base

class ConsumerSubscriptionStatus(str, enum.Enum):
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PENDING_REVIEW = "PENDING_REVIEW"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"

class ConsumerSubscription(Base):
    __tablename__ = "consumer_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    consumer_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    status = Column(Enum(ConsumerSubscriptionStatus), default=ConsumerSubscriptionStatus.PENDING_PAYMENT, nullable=False)
    proof_tx_hash = Column(String, nullable=True)
    
    current_period_start = Column(DateTime(timezone=True), server_default=func.now())
    current_period_end = Column(DateTime(timezone=True), nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships can be added if needed, e.g. backref from User
    # But usually lazy loading or dedicated query is fine.
