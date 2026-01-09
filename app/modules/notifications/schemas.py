from datetime import datetime
from uuid import UUID
from pydantic import BaseModel
from typing import Optional

class NotificationRead(BaseModel):
    id: UUID
    title: str
    message: str
    is_read: bool
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
