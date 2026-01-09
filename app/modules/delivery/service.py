from datetime import datetime, timedelta
from typing import Optional
from jose import jwt, JWTError
from core.config import settings
from uuid import UUID
from fastapi import HTTPException, status

# Reusing app secret for now, ideally separate
ALGORITHM = "HS256"

def create_playback_token(user_id: UUID, media_id: UUID) -> str:
    """
    Generates a short-lived token for accessing a specific media file.
    """
    expire = datetime.utcnow() + timedelta(minutes=60) # 1 hour validity
    to_encode = {
        "sub": str(user_id),
        "media_id": str(media_id),
        "exp": expire,
        "type": "playback"
    }
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def validate_playback_token(token: str, media_id: str) -> bool:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        token_type = payload.get("type")
        token_media_id = payload.get("media_id")
        
        if token_type != "playback":
            return False
        
        if token_media_id != media_id:
            return False
            
        return True
    except JWTError:
        return False
