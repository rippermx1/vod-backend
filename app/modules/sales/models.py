
import uuid
from sqlalchemy import Column, String, Float, DateTime, func, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
from core.db import Base
import enum

class PurchaseStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"

class ContentPurchase(Base):
    __tablename__ = "sales_content_purchases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    content_id = Column(UUID(as_uuid=True), ForeignKey("cms_content.id"), nullable=False)
    
    amount = Column(Float, nullable=False)
    currency = Column(String, default="USD")
    
    tx_hash = Column(String, nullable=True) # Manual payment proof
    status = Column(Enum(PurchaseStatus), default=PurchaseStatus.PENDING, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
