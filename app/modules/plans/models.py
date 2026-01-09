import uuid
from sqlalchemy import Column, String, Boolean, Integer, DateTime, func, Enum, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.db import Base
import enum

class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"
    EXPIRED = "expired"

class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"

class SaasPlan(Base):
    __tablename__ = "saas_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String, unique=True, index=True, nullable=False) # e.g. 'free', 'pro'
    name = Column(String, nullable=False)
    price_usdt = Column(Numeric(10, 2), nullable=False)
    period_days = Column(Integer, default=30, nullable=False)
    is_active = Column(Boolean, default=True)
    
    features = relationship("SaasPlanFeature", back_populates="plan", cascade="all, delete-orphan")
    limits = relationship("SaasPlanLimit", back_populates="plan", cascade="all, delete-orphan")

class SaasPlanFeature(Base):
    __tablename__ = "saas_plan_features"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("saas_plans.id"), nullable=False)
    feature_key = Column(String, nullable=False) # e.g. 'custom_domain'
    is_enabled = Column(Boolean, default=True)
    
    plan = relationship("SaasPlan", back_populates="features")

class SaasPlanLimit(Base):
    __tablename__ = "saas_plan_limits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("saas_plans.id"), nullable=False)
    limit_key = Column(String, nullable=False) # e.g. 'max_storage_gb'
    limit_value = Column(Integer, nullable=False) # -1 for unlimited
    
    plan = relationship("SaasPlan", back_populates="limits")

class CreatorSubscription(Base):
    __tablename__ = "creator_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True) # One active sub per creator ideally
    plan_id = Column(UUID(as_uuid=True), ForeignKey("saas_plans.id"), nullable=False)
    
    status = Column(Enum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    plan = relationship("SaasPlan")

class SaasPayment(Base):
    __tablename__ = "saas_payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("saas_plans.id"), nullable=False)
    
    amount_usdt = Column(Numeric(10, 2), nullable=False)
    tx_hash = Column(String, nullable=False) # Blockchain TX
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False)
    
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class CreatorPaymentMethod(Base):
    __tablename__ = "creator_payment_methods"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    payment_type = Column(String, default="USDT_TRC20", nullable=False)
    details = Column(String, nullable=False) # e.g. Wallet Address
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
