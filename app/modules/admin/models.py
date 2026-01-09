from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
import uuid

from app.core.db import Base

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True) # Nullable for system actions or failed logins where user unknown (though usually we log known users)
    
    action = Column(String, nullable=False) # e.g. "auth.login", "kyc.review", "payment.confirm"
    target_type = Column(String, nullable=True) # e.g. "user", "kyc_submission", "payment"
    target_id = Column(String, nullable=True) # UUID as string
    
    metadata_json = Column(JSONB, nullable=True) # Extra details
    ip_address = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class SystemSetting(Base):
    __tablename__ = "admin_settings"
    
    key = Column(String, primary_key=True)
    value = Column(String, nullable=False) # Store as string, cast as needed
    description = Column(String, nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
