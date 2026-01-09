import uuid
from sqlalchemy import Column, String, Boolean, DateTime, func, Enum, Float
from sqlalchemy.dialects.postgresql import UUID
from app.core.db import Base
import enum

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    CREATOR = "creator"
    CONSUMER = "consumer"

class KYCStatus(str, enum.Enum):
    NONE = "none" # For consumers
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    role = Column(Enum(UserRole), default=UserRole.CONSUMER, nullable=False)
    is_active = Column(Boolean, default=True)
    
    # Profile
    bio = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    
    # Creator specific (can be moved to profile later if needed)
    kyc_status = Column(Enum(KYCStatus), default=KYCStatus.NONE, nullable=False)
    
    # Creator Specific
    monthly_price = Column(Float, default=9.99, nullable=False)
    subscription_enabled = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class UserLike(Base):
    __tablename__ = "user_likes"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False) # The person who likes
    creator_id = Column(UUID(as_uuid=True), nullable=False) # The creator being liked
    created_at = Column(DateTime(timezone=True), server_default=func.now())
