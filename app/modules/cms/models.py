import uuid
from sqlalchemy import Column, String, Boolean, Integer, Float, DateTime, func, Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
from core.db import Base
import enum

class ContentStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"
    BLOCKED = "blocked"

class MediaType(str, enum.Enum):
    VIDEO = "video"
    IMAGE = "image"
    DOCUMENT = "document"

class ProcessingStatus(str, enum.Enum):
    PENDING = "pending"
    # PROCESSING = "processing" (DB issues, using PENDING)
    READY = "ready"
    FAILED = "failed"

class Content(Base):
    __tablename__ = "cms_content"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(Enum(ContentStatus), default=ContentStatus.DRAFT, nullable=False)
    
    is_free = Column(Boolean, default=False, nullable=False) # False = Requires Subscription
    is_free = Column(Boolean, default=False, nullable=False) # False = Requires Subscription
    price = Column(Float, nullable=True, default=0.0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    published_at = Column(DateTime(timezone=True), nullable=True)
    
    tags = Column(ARRAY(String), default=[], nullable=True)
    category = Column(String, nullable=True)
    cover_image_url = Column(String, nullable=True)
    
    # Relationships
    media_items = relationship("Media", back_populates="content", cascade="all, delete-orphan")

class Media(Base):
    __tablename__ = "cms_media"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    content_id = Column(UUID(as_uuid=True), ForeignKey("cms_content.id"), nullable=True) # Nullable until attached to post
    
    media_type = Column(Enum(MediaType), nullable=False)
    file_path = Column(String, nullable=False) # Local path or S3 Key
    filename = Column(String, nullable=False)
    content_type = Column(String, nullable=False) # Mime Type
    size_bytes = Column(Integer, nullable=False)
    
    processing_status = Column(Enum(ProcessingStatus), default=ProcessingStatus.PENDING, nullable=False)
    is_public_preview = Column(Boolean, default=False, nullable=False) # True = content is visible even if parent post is locked
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    content = relationship("Content", back_populates="media_items")

    @property
    def public_url(self):
        if self.file_path.startswith("/static"):
            return f"http://localhost:8000{self.file_path}"
        if self.file_path.startswith("http"):
            return self.file_path
        # Assume B2 path if not static and not http
        from core.config import settings
        
        # If user provides a full public CDN URL (e.g. Cloudflare), use that
        if settings.B2_PUBLIC_URL:
             # Logic: B2_PUBLIC_URL might be "https://cdn.com" -> result "https://cdn.com/path/to/file"
             # If B2_PUBLIC_URL already has bucket name logic, great.
             # Typically it is just the domain.
             return f"{settings.B2_PUBLIC_URL}/{self.file_path}"
             
        # Friendly URL Fallback
        return f"{settings.B2_ENDPOINT}/file/{settings.B2_BUCKET_NAME}/{self.file_path}"
