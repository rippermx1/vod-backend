from pydantic import BaseModel
from uuid import UUID

class PlaybackTokenRequest(BaseModel):
    media_id: UUID

class PlaybackTokenResponse(BaseModel):
    token: str
    media_id: UUID
    expires_in_seconds: int
