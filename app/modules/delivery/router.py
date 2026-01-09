from datetime import timedelta, datetime
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from jose import jwt

from app.core.db import get_db
from app.core import deps
from app.core.config import settings
from app.modules.auth import models as auth_models
from app.modules.delivery import schemas
from app.modules.cms import models as cms_models
from app.modules.subscriptions import service as sub_service

router = APIRouter()

def create_playback_token(user_id: str, media_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=5) # Short lived
    to_encode = {
        "exp": expire,
        "sub": str(user_id),
        "media_id": str(media_id),
        "scope": "playback"
    }
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

@router.post("/token", response_model=schemas.PlaybackTokenResponse)
async def generate_playback_token(
    request: schemas.PlaybackTokenRequest,
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    # 1. Get Media
    media = await db.get(cms_models.Media, request.media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    # 2. Check Entitlements
    is_entitled = False
    
    # Creator always entitled
    if media.creator_id == current_user.id:
        is_entitled = True
    elif media.is_public_preview:
        is_entitled = True
    else:
        # Check if media is attached to any content that is PUBLIC or if user is SUBSCRIBED
        # Complex check: Media -> Content. 
        # Ideally Entitlement is against CONTENT, not MEDIA. 
        # But for streaming, we request media.
        # Let's check Subscription to Creator for MVP.
        # If user is subscribed to creator, they have access to all media of that creator (MVP rule).
        has_access = await sub_service.check_subscription_access(db, current_user.id, media.creator_id)
        if has_access:
            is_entitled = True
        else:
            # Check if media belongs to PUBLIC content?
            # Media.content_id might be null if just uploaded.
            # If attached:
            # If attached:
            if media.content_id:
                content = await db.get(cms_models.Content, media.content_id)
                if content:
                    # Check Purchase Entitlement
                    from sqlalchemy import select
                    from app.modules.sales import models as sales_models
                    
                    purchase_query = select(sales_models.ContentPurchase).where(
                        sales_models.ContentPurchase.user_id == current_user.id,
                        sales_models.ContentPurchase.content_id == content.id,
                        sales_models.ContentPurchase.status == sales_models.PurchaseStatus.COMPLETED
                    )
                    purchase = await db.execute(purchase_query)
                    if purchase.scalars().first():
                         is_entitled = True
                         
                    # Check if free
                    if not is_entitled and content.is_free:
                         # MVP: Free content is accessible if published
                         pass

    if not is_entitled:
        # Final Strict Check: 
        # If user is NOT subscribed, reject for MVP strictness (unless we implement "Guest Public Access" logic which is tricky safely).
        # Wait, Public posts (Search/Explore) allow guests? 
        # `07` says "GET /creators/{slug}/posts (solo public for guest)".
        # So guests need playback too.
        # If Content.is_free == True, allow.
        
        if media.content_id:
             content = await db.get(cms_models.Content, media.content_id)
             if content and content.status == cms_models.ContentStatus.PUBLISHED and content.is_free:
                 is_entitled = True

    if not is_entitled:
        raise HTTPException(status_code=403, detail="Not entitled to view this media")

    # 3. Generate Token
    token = create_playback_token(current_user.id, media.id)
    
    return {
        "token": token,
        "media_id": media.id,
        "expires_in_seconds": 300
    }

from fastapi.responses import FileResponse

@router.get("/secure/{media_id}")
async def get_secure_media(
    media_id: str,
    token: str,
    noredirect: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """
    Stream media content securely using a playback token.
    """
    # 1. Verify Token
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        token_sub = payload.get("sub")
        token_media_id = payload.get("media_id")
        token_scope = payload.get("scope")
        
        if token_scope != "playback":
            raise HTTPException(status_code=403, detail="Invalid token scope")
            
        if token_media_id != media_id:
             raise HTTPException(status_code=403, detail="Token mismatch for this media")
             
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=403, detail="Token expired")
    except jwt.JWTError:
        raise HTTPException(status_code=403, detail="Invalid token")

    # 2. Get Media Record
    media = await db.get(cms_models.Media, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    # 3. Stream File (Redirect to B2/Mock URL)
    from app.modules.delivery.b2_service import get_b2_service
    from fastapi.responses import RedirectResponse
    
    b2 = get_b2_service()
    
    # Path Reconstruction Logic for Legacy/Malformed Keys
    # Expected: creators/{user_id}/{folder}/{uuid}/{filename} (5 parts)
    # Found: creators/{user_id}/{uuid}/{filename} (4 parts) - Missing folder
    
    raw_path = media.file_path
    parts = raw_path.split("/")
    
    if len(parts) == 4 and parts[0] == "creators":
        # Missing category folder, inject it
        folder = "misc"
        if media.media_type == cms_models.MediaType.VIDEO:
            folder = "videos"
        elif media.media_type == cms_models.MediaType.IMAGE:
            folder = "images"
            
        # Reconstruct: creators/uid + /folder + /uuid/filename
        # parts[0]/parts[1] + /folder + /parts[2]/parts[3]
        fixed_path = f"{parts[0]}/{parts[1]}/{folder}/{parts[2]}/{parts[3]}"
        print(f"[DEBUG] Fixed Path: {fixed_path} (was {raw_path})")
        raw_path = fixed_path
    
    download_url = b2.get_download_url(raw_path)
    
    if not download_url:
        raise HTTPException(status_code=404, detail="Content unavailable")

    # If it's a local file path (not B2), fallback? 
    # Current DB stores "creators/..." or "/static/..."
    # If B2 Mock, it returns "http://localhost:8000/static/uploads/creators/..."
    # If B2 Prod, it returns "https://..."
    
    print(f"[DEBUG] Redirecting to: {download_url}")
    
    if noredirect:
        return {"url": download_url}

    return RedirectResponse(url=download_url)

@router.get("/cover/{content_id}")
async def get_content_cover(
    content_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Redirects to the content cover image (signed B2 URL or local).
    """
    content = await db.get(cms_models.Content, content_id)
    if not content or not content.cover_image_url:
         # Fallback default cover
         from fastapi.responses import RedirectResponse
         return RedirectResponse(url="/static/img/default-cover.jpg") 

    cover_url = content.cover_image_url
    
    # B2 Signing
    if not cover_url.startswith("http") and not cover_url.startswith("/"):
         from app.modules.delivery.b2_service import get_b2_service
         b2 = get_b2_service()
         signed_url = b2.get_download_url(cover_url)
         if signed_url:
             from fastapi.responses import RedirectResponse
             return RedirectResponse(url=signed_url)
    
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=cover_url)
