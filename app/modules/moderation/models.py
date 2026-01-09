import uuid
import enum
from sqlalchemy import Column, String, Enum, ForeignKey, Text, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from core.db import Base

class ReportStatus(str, enum.Enum):
    PENDING = "pending"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"

class Report(Base):
    __tablename__ = "moderation_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reporter_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    content_id = Column(UUID(as_uuid=True), ForeignKey("cms_content.id"), nullable=False)
    
    reason = Column(String, nullable=False) # e.g. "spam", "inappropriate"
    description = Column(Text, nullable=True)
    
    status = Column(Enum(ReportStatus), default=ReportStatus.PENDING, nullable=False)
    admin_notes = Column(Text, nullable=True)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
