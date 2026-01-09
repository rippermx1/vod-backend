from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from fastapi import UploadFile, HTTPException
from uuid import UUID
import uuid
from datetime import datetime

from app.modules.cms import models, schemas
from app.core.storage import storage
from app.modules.auth.models import User
from app.modules.plans.service import has_feature, get_active_plans, get_creator_subscription, get_plan_limit
from app.core.db import SessionLocal
from app.core.db import SessionLocal
import asyncio
from app.modules.delivery.b2_service import get_b2_service
import os

async def create_upload_intent(db: AsyncSession, user: User, intent: schemas.MediaUploadIntent):
    # 1. Check Plan Limits
    limit_gb = await get_plan_limit(db, user.id, "max_storage_gb")
    # ... (Reuse existing logic or refactor) ...
    if limit_gb != -1:
        limit_bytes = limit_gb * 1024 * 1024 * 1024
        result = await db.execute(select(func.sum(models.Media.size_bytes)).where(models.Media.creator_id == user.id))
        current_usage = result.scalars().first() or 0
        if current_usage + intent.size_bytes > limit_bytes:
             raise HTTPException(status_code=403, detail="Storage limit exceeded")

    # 2. Get B2 Upload URL
    b2 = get_b2_service()
    try:
        upload_url, auth_token = b2.get_upload_url()
    except Exception as e:
        print(f"B2 Error: {e}")
        # Build local mock if B2 creds missing for dev (User asked for B2, but fallback is nice)
        # Actually USER asked strictly for B2. Raise error if fails.
        raise HTTPException(status_code=500, detail="Failed to initiate upload provider")

    # 3. Create Pending Media Record
    # Generate B2 Storage Key with folder structure
    # Pattern: creators/{user_id}/{category}/{uuid}/{filename}
    file_uuid = uuid.uuid4()
    
    # Sanitize filename to avoid B2 encoding issues (e.g. commas)
    # We replace spaces with underscores and remove non-safe chars
    import re
    safe_filename = re.sub(r'[^a-zA-Z0-9_\-\.]', '', intent.filename.replace(' ', '_'))
    if not safe_filename:
        safe_filename = "unnamed_file"

    # Determine category
    folder = intent.category
    if not folder:
        if "video" in intent.mime_type:
            folder = "videos"
        elif "image" in intent.mime_type:
            folder = "images"
        else:
            folder = "misc"
            
    storage_key = f"creators/{user.id}/{folder}/{file_uuid}/{safe_filename}"
    print(f"[DEBUG] Upload Intent Key: {storage_key} | Folder: {folder}")
    
    media = models.Media(
        creator_id=user.id,
        media_type=models.MediaType.VIDEO if "video" in intent.mime_type else models.MediaType.IMAGE,
        file_path=storage_key,
        filename=intent.filename, # Keep original filename for display
        content_type=intent.mime_type,
        size_bytes=intent.size_bytes,
        processing_status=models.ProcessingStatus.PENDING
    )
    db.add(media)
    await db.commit()
    await db.refresh(media)
    
    return schemas.MediaUploadResponse(
        media_asset_id=media.id,
        upload_url=upload_url,
        auth_token=auth_token,
        storage_key=storage_key
    )

async def complete_upload(db: AsyncSession, user: User, media_id: UUID, complete: schemas.MediaComplete):
    media = await db.get(models.Media, media_id)
    if not media or media.creator_id != user.id:
        raise HTTPException(status_code=404, detail="Media not found")
        
    # Mark ready only if image or non-transcode type
    # If video, keep PENDING so worker can pick it up (or router triggers it)
    if media.media_type == models.MediaType.IMAGE:
        media.processing_status = models.ProcessingStatus.READY
    else:
        # Video stays pending/processing until worker finishes
        # We might set it to PENDING explicitly to be safe
        media.processing_status = models.ProcessingStatus.PENDING
        
    await db.commit()
    return media

async def get_creator_stats(db: AsyncSession, user_id: UUID):
    # 1. Total Subscribers
    # Import inside to avoid circular deps if any
    from app.modules.subscriptions import models as sub_models
    
    sub_query = select(func.count(sub_models.ConsumerSubscription.consumer_id)).where(
        sub_models.ConsumerSubscription.creator_id == user_id,
        sub_models.ConsumerSubscription.status == sub_models.ConsumerSubscriptionStatus.ACTIVE
    )
    sub_count = (await db.execute(sub_query)).scalar() or 0
    
    # 2. Active Content
    content_query = select(func.count(models.Content.id)).where(
        models.Content.creator_id == user_id,
        models.Content.status == models.ContentStatus.PUBLISHED
    )
    content_count = (await db.execute(content_query)).scalar() or 0
    
    # 3. Est. Earnings (Mock: Subs * Price). Price is on User model.
    user_query = select(User).where(User.id == user_id)
    user = (await db.execute(user_query)).scalars().first()
    price = user.monthly_price if user else 0
    earnings = sub_count * price
    
    return {
        "total_subscribers": sub_count,
        "active_content": content_count,
        "est_earnings": earnings,
        "views": 0 # Mock
    }

    async with SessionLocal() as db:
        media = await db.get(models.Media, media_id)
        if media:
            media.processing_status = models.ProcessingStatus.READY
            # logic to create HLS files would go here
            await db.commit()

async def get_storage_usage(db: AsyncSession, user_id: UUID) -> schemas.StorageUsage:
    # 1. Get Limit
    limit_gb = await get_plan_limit(db, user_id, "max_storage_gb")
    
    # 2. Get Usage
    result = await db.execute(
        select(func.sum(models.Media.size_bytes)).where(models.Media.creator_id == user_id)
    )
    used_bytes = result.scalars().first() or 0
    
    # 3. Calculate
    if limit_gb == -1:
        limit_bytes = -1
        percent = 0
    else:
        limit_bytes = limit_gb * 1024 * 1024 * 1024
        percent = (used_bytes / limit_bytes * 100) if limit_bytes > 0 else 100
        
    return schemas.StorageUsage(
        used_bytes=used_bytes,
        limit_bytes=limit_bytes,
        used_gb=round(used_bytes / (1024**3), 2),
        limit_gb=limit_gb,
        percent_used=round(percent, 1)
    )

async def upload_media(db: AsyncSession, user: User, file: UploadFile, media_type: models.MediaType):
    # 1. Get Plan Limit
    limit_gb = await get_plan_limit(db, user.id, "max_storage_gb")
    
    if limit_gb > 0: # If 0 or -1 (unlimited logic depends on implementation, usually -1 is unlimited)
        # Assuming -1 is unlimited, 0 is no storage (or fallback default). 
        # Model comment says "-1 for unlimited".
        # If limit_gb is -1, skip check.
        pass
    
    if limit_gb != -1:
        limit_bytes = limit_gb * 1024 * 1024 * 1024
        
        # 2. Calculate Current Usage
        result = await db.execute(
            select(func.sum(models.Media.size_bytes)).where(models.Media.creator_id == user.id)
        )
        current_usage = result.scalars().first() or 0
        
        # Estimate new file size? UploadFile doesn't always have size before read.
        # But we can check after read or rely on Content-Length header (unreliable).
        # For MVP, since we save to disk first (in storage.save_upload), we could check AFTER save but BEFORE DB commit.
        # However, saving effectively uses storage.
        # Ideally we check roughly before.
        
        # Proper way: Check current_usage >= limit_bytes.
        if current_usage >= limit_bytes:
             raise HTTPException(status_code=403, detail=f"Storage limit of {limit_gb}GB exceeded. Upgrade your plan.")

    # Save to storage
    stored = await storage.save_upload(file, str(user.id))
    
    # Create DB Record
    media = models.Media(
        creator_id=user.id,
        media_type=media_type,
        file_path=stored["url"], # Storing web-path for now as MVP
        filename=stored["filename"],
        content_type=file.content_type,
        size_bytes=stored["size"],
        processing_status=models.ProcessingStatus.PENDING # Starts Pending, Background Task makes Ready
    )
    db.add(media)
    await db.commit()
    await db.refresh(media)
    return media

async def create_content(db: AsyncSession, user: User, content_in: schemas.ContentCreate):
    # KYC Check for Premium Content
    if not content_in.is_free:
         # We need to check exact enum value. 
         # Enum is defined in auth/models.py but imported as User.
         # Ideally we compare string or import Enum.
         # 'verified' is the value.
         if str(user.kyc_status) != "verified":
             raise HTTPException(status_code=403, detail="KYC verification required for subscribers-only content")

    content = models.Content(
        creator_id=user.id,
        title=content_in.title,
        description=content_in.description,
        is_free=content_in.is_free,
        status=models.ContentStatus.DRAFT,
        published_at=content_in.published_at,
        tags=content_in.tags,
        category=content_in.category,
        cover_image_url=content_in.cover_image_url
    )
    db.add(content)
    await db.commit()
    # Eager load for return
    result = await db.execute(
        select(models.Content)
        .where(models.Content.id == content.id)
        .options(selectinload(models.Content.media_items))
    )
    return result.scalars().first()

    return result.scalars().first()

async def get_content_details(db: AsyncSession, user: User, content_id: UUID):
    result = await db.execute(
        select(models.Content)
        .where(models.Content.id == content_id)
        .options(selectinload(models.Content.media_items))
    )
    content = result.scalars().first()
    if not content:
        return None
        
    # Access Control
    if user.role == "creator":
        if content.creator_id != user.id:
            return None
    
    # If consumer, must be PUBLISHED (and maybe check subscription if not free?)
    # For now, strict ownership for creator editing.
    if user.role != "creator" and content.status != models.ContentStatus.PUBLISHED:
         return None
         
    return content

async def update_content(db: AsyncSession, user: User, content_id: UUID, content_in: schemas.ContentUpdate):
    result = await db.execute(select(models.Content).where(models.Content.id == content_id))
    content = result.scalars().first()
    
    if not content:
        return None
    if content.creator_id != user.id:
        return None
        
    # Update fields
    # Update fields
    update_data = content_in.dict(exclude_unset=True)
    for field, value in update_data.items():
        if field == 'status': 
            continue # Handle status specifically below
        if hasattr(content, field):
            setattr(content, field, value)

    if content_in.status is not None:
        # If publishing, check KYC again? Or basics?
        if content_in.status == models.ContentStatus.PUBLISHED:
            # Set published_at if not set AND not provided in this update (if it was provided, allowed to be None or Date)
            # If explicit None was sent, published_at is now None (from loop above).
            # We only default to NOW if it's currently None AND the user didn't explicitly providing a date (Wait, if they passed None, they WANT it None? No, if Published must have date?)
            # Logic: If status is Published, we MUST have a published_at. 
            # If user sent None (publish immediately) or didn't send it, we default to NOW relative to backend?
            # Actually, "Publish Immediately" means "Set to NOW".
            # "Scheduled" means "Set to Future".
            # If I send status=PUBLISHED and published_at=None, I expect it to be NOW?
            # OR, does frontend send published_at=None to mean "Immediate"?
            
            # Frontend logic:
            # If "Publish Immediately": sends status=published, published_at=null.
            # Backend: If published_at is None, set to utcnow().
            
            # If I send status=published, published_at=FUTURE_DATE.
            # Backend: Sets it to future date.
            
            # So:
            # 1. Apply all updates (including published_at=None from frontend).
            # 2. If status becomes PUBLISHED check published_at.
            # 3. If published_at is None, set to utcnow().
            
            pass 
        content.status = content_in.status

    # Post-update check for Published consistency
    if content.status == models.ContentStatus.PUBLISHED:
        if not content.published_at:
             content.published_at = datetime.utcnow()
        
    await db.commit()
    await db.refresh(content)
    
    # Reload for response
    result = await db.execute(
        select(models.Content)
        .where(models.Content.id == content.id)
        .options(selectinload(models.Content.media_items))
    )
    return result.scalars().first()

async def delete_content(db: AsyncSession, user: User, content_id: UUID):
    content = await db.get(models.Content, content_id)
    if not content:
        return False
    if content.creator_id != user.id:
        return False
        
    # Soft Delete (Archive)
    content.status = models.ContentStatus.ARCHIVED
    await db.commit()
    return True



async def attach_media_to_content(db: AsyncSession, user: User, content_id: UUID, media_id: UUID):
    # Verify ownership
    content = await db.get(models.Content, content_id)
    if not content or content.creator_id != user.id:
        raise HTTPException(status_code=404, detail="Content not found")
        
    media = await db.get(models.Media, media_id)
    if not media or media.creator_id != user.id:
        raise HTTPException(status_code=404, detail="Media not found")
        
    media.content_id = content.id
    await db.commit()
    
    # Eager load for return
    result = await db.execute(
        select(models.Content)
        .where(models.Content.id == content.id)
        .options(selectinload(models.Content.media_items))
    )
    return result.scalars().first()

async def detach_media_from_content(db: AsyncSession, user: User, content_id: UUID, media_id: UUID):
    # Verify ownership
    content = await db.get(models.Content, content_id)
    if not content or content.creator_id != user.id:
        return False
        
    media = await db.get(models.Media, media_id)
    if not media or media.content_id != content.id:
        return False
        
    media.content_id = None
    await db.commit()
    return True

async def list_creator_content(db: AsyncSession, user_id: UUID):
    result = await db.execute(
        select(models.Content)
        .where(models.Content.creator_id == user_id)
        .options(selectinload(models.Content.media_items))
        .order_by(models.Content.created_at.desc())
    )
    return result.scalars().all()

async def list_public_content(db: AsyncSession):
    # Only published AND released
    result = await db.execute(
        select(models.Content)
        .where(
            models.Content.status == models.ContentStatus.PUBLISHED,
            models.Content.published_at <= datetime.utcnow()
        )
        .options(selectinload(models.Content.media_items))
        .order_by(models.Content.published_at.desc())
    )
    return result.scalars().all()

async def list_creator_public_posts(db: AsyncSession, creator_id: UUID):
    result = await db.execute(
        select(models.Content)
        .where(
            models.Content.creator_id == creator_id,
            models.Content.status == models.ContentStatus.PUBLISHED,
            models.Content.published_at <= datetime.utcnow()
        )
        .options(selectinload(models.Content.media_items))
        .order_by(models.Content.created_at.desc())
    )
    return result.scalars().all()

    return result.scalars().all()

async def list_consumer_feed(db: AsyncSession, consumer_id: UUID):
    from app.modules.subscriptions import models as sub_models
    result = await db.execute(
        select(models.Content)
        .join(sub_models.ConsumerSubscription, models.Content.creator_id == sub_models.ConsumerSubscription.creator_id)
        .where(
            sub_models.ConsumerSubscription.consumer_id == consumer_id,
            sub_models.ConsumerSubscription.status == sub_models.ConsumerSubscriptionStatus.ACTIVE,
            models.Content.status == models.ContentStatus.PUBLISHED,
            models.Content.published_at <= datetime.utcnow()
        )
        .options(selectinload(models.Content.media_items))
        .order_by(models.Content.published_at.desc())
    )
    return result.scalars().all()

async def list_creator_media_paginated(db: AsyncSession, user_id: UUID, page: int, size: int) -> dict:
    offset = (page - 1) * size
    
    # Total Count
    count_query = select(func.count(models.Media.id)).where(models.Media.creator_id == user_id)
    total = (await db.execute(count_query)).scalar() or 0
    
    # Items
    query = select(models.Media).where(models.Media.creator_id == user_id)\
        .order_by(models.Media.created_at.desc())\
        .offset(offset).limit(size)
    items = (await db.execute(query)).scalars().all()
    
    import math
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": math.ceil(total / size) if size > 0 else 0
    }

async def delete_media(db: AsyncSession, user: User, media_id: UUID) -> bool:
    media = await db.get(models.Media, media_id)
    if not media:
        return False
    if media.creator_id != user.id:
        return False
        
    await db.delete(media)
    await db.commit()
    return True

async def update_media_preview(db: AsyncSession, user: User, media_id: UUID, is_public_preview: bool):
    media = await db.get(models.Media, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    if media.creator_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    media.is_public_preview = is_public_preview
    await db.commit()
    await db.refresh(media)
    return media
