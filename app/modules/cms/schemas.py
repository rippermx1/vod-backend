from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from uuid import UUID
from modules.cms.models import ContentStatus, MediaType, ProcessingStatus

class MediaBase(BaseModel):
    media_type: MediaType
    filename: str

class MediaRead(MediaBase):
    id: UUID
    creator_id: UUID
    public_url: str # Computed alias for API
    processing_status: ProcessingStatus
    is_public_preview: bool = False
    size_bytes: int
    created_at: datetime
    
    # We will compute public_url in response or use file_path if it's a URL
    class Config:
        from_attributes = True

class MediaPreviewUpdate(BaseModel):
    is_public_preview: bool

class MediaListResponse(BaseModel):
    items: List[MediaRead]
    total: int
    page: int
    size: int
    pages: int

class ContentCreate(BaseModel):
    title: str
    description: Optional[str] = None
    is_free: bool = False
    price: Optional[float] = 0.0
    published_at: Optional[datetime] = None
    tags: List[str] = []
    category: Optional[str] = None
    cover_image_url: Optional[str] = None

class ContentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    is_free: Optional[bool] = None
    price: Optional[float] = None
    status: Optional[ContentStatus] = None
    published_at: Optional[datetime] = None
    tags: Optional[List[str]] = None
    category: Optional[str] = None
    cover_image_url: Optional[str] = None

class ContentRead(BaseModel):
    id: UUID
    title: str
    description: Optional[str]
    status: ContentStatus
    is_free: bool
    price: Optional[float]
    created_at: datetime
    published_at: Optional[datetime]
    tags: Optional[List[str]] = []
    category: Optional[str] = None
    cover_image_url: Optional[str] = None
    media_items: List[MediaRead] = []

    class Config:
        from_attributes = True

class SubscriberStats(BaseModel):
    id: UUID
    full_name: Optional[str]
    email: str
    joined_at: datetime

class DashboardStats(BaseModel):
    total_subscribers: int
    active_content: int
    est_earnings: float
    views: int
    recent_subscribers: List[SubscriberStats] = []
    recent_content: List[ContentRead] = []


class MediaUploadIntent(BaseModel):
    filename: str
    size_bytes: int
    mime_type: str
    category: Optional[str] = None # e.g. "videos", "images", "avatars", "kyc"

class MediaUploadResponse(BaseModel):
    media_asset_id: UUID
    upload_url: str
    auth_token: str
    storage_key: str

class MediaComplete(BaseModel):
    status: str # "uploaded", "failed", etc.

class StorageUsage(BaseModel):
    used_bytes: int
    limit_bytes: int
    used_gb: float
    limit_gb: float
    percent_used: float
