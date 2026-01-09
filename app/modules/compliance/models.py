import uuid
import enum
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, func
from sqlalchemy.dialects.postgresql import UUID
from core.db import Base

class KYCStatus(str, enum.Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"

class KYCSubmission(Base):
    __tablename__ = "kyc_submissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True) # One pending/active submission per user?
    
    document_url = Column(String, nullable=False)
    selfie_url = Column(String, nullable=False)
    
    status = Column(Enum(KYCStatus), default=KYCStatus.PENDING, nullable=False)
    admin_notes = Column(String, nullable=True)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
