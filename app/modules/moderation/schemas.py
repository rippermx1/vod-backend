from datetime import datetime
from uuid import UUID
from pydantic import BaseModel
from typing import Optional
from modules.moderation.models import ReportStatus

class ReportCreate(BaseModel):
    content_id: UUID
    reason: str
    description: Optional[str] = None

class ReportResolve(BaseModel):
    action: str # "block", "dismiss"
    notes: Optional[str] = None

class ReportRead(BaseModel):
    id: UUID
    reporter_id: UUID
    content_id: UUID
    reason: str
    description: Optional[str]
    status: ReportStatus
    created_at: datetime

    class Config:
        from_attributes = True
