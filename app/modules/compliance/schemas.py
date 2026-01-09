from datetime import datetime
from uuid import UUID
from pydantic import BaseModel
from typing import Optional
from app.modules.compliance.models import KYCStatus

class KYCSubmit(BaseModel):
    pass # Uploads are handled via Form/File, no JSON body initially

class KYCRead(BaseModel):
    id: UUID
    user_id: UUID
    user_email: Optional[str] = None
    document_url: str
    selfie_url: str
    status: KYCStatus
    admin_notes: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True

class KYCReview(BaseModel):
    action: str # "approve" or "reject"
    notes: Optional[str] = None
