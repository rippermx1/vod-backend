from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks
import aiofiles
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, List
import os
from core.db import get_db
from core import deps
from modules.auth import models as auth_models
from modules.cms import schemas, service, models
cms_models = models # Alias for compatibility with new code
from modules.plans import service as plans_service # Import for enforcement
from modules.subscriptions import models as sub_models
from modules.worker.runner import worker
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

router = APIRouter()

@router.get("/dashboard/stats", response_model=schemas.DashboardStats)
async def get_dashboard_stats(
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    if current_user.role != auth_models.UserRole.CREATOR:
        raise HTTPException(status_code=403, detail="Only creators access stats")
        
    # Count Subscribers
    subscriber_count = (await db.execute(
        select(func.count(sub_models.ConsumerSubscription.id))
        .where(
            sub_models.ConsumerSubscription.creator_id == current_user.id,
            sub_models.ConsumerSubscription.status == sub_models.ConsumerSubscriptionStatus.ACTIVE
        )
    )).scalar() or 0
    
    # Calculate Revenue
    revenue = subscriber_count * current_user.monthly_price
    
    # Count Content
    content_count = (await db.execute(
        select(func.count(models.Content.id))
        .where(
            models.Content.creator_id == current_user.id,
            models.Content.status == models.ContentStatus.PUBLISHED
        )
    )).scalar() or 0

    # Recent Subscribers (Last 5)
    recent_subs_res = await db.execute(
        select(auth_models.User.id, auth_models.User.full_name, auth_models.User.email, sub_models.ConsumerSubscription.created_at.label("joined_at"))
        .join(sub_models.ConsumerSubscription, sub_models.ConsumerSubscription.consumer_id == auth_models.User.id)
        .where(
            sub_models.ConsumerSubscription.creator_id == current_user.id,
            sub_models.ConsumerSubscription.status == sub_models.ConsumerSubscriptionStatus.ACTIVE
        )
        .order_by(sub_models.ConsumerSubscription.created_at.desc())
        .limit(5)
    )
    recent_subscribers = []
    for row in recent_subs_res:
         recent_subscribers.append({
             "id": row.id,
             "full_name": row.full_name or "Anonymous",
             "email": row.email,
             "joined_at": row.joined_at
         })

    # Recent Content (Last 5)
    recent_content_res = await db.execute(
        select(models.Content)
        .where(models.Content.creator_id == current_user.id)
        .options(selectinload(models.Content.media_items)) # Fix MissingGreenlet
        .order_by(models.Content.created_at.desc())
        .limit(5)
    )
    recent_content = recent_content_res.scalars().all()
    
    return {
        "total_subscribers": subscriber_count,
        "active_content": content_count,
        "est_earnings": revenue,
        "views": 100, # Mock
        "recent_subscribers": recent_subscribers,
        "recent_content": recent_content
    }

@router.get("/storage-usage", response_model=schemas.StorageUsage)
async def get_storage_usage(
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    if current_user.role != auth_models.UserRole.CREATOR:
        raise HTTPException(status_code=403, detail="Only creators")
    return await service.get_storage_usage(db, current_user.id)

@router.post("/upload", response_model=schemas.MediaRead)
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    media_type: models.MediaType = Form(...),
    current_user: auth_models.User = Depends(plans_service.require_active_saas_plan), # Strict Enforcement
    db: AsyncSession = Depends(get_db)
) -> Any:
    # Check if Creator (Redundant if dependency checks, but keep for type safety)
    if current_user.role != auth_models.UserRole.CREATOR:
         raise HTTPException(status_code=403, detail="Only creators can upload content")
         
    # Validate Content Type
    if media_type == models.MediaType.IMAGE:
        if not file.content_type.startswith("image/"):
             raise HTTPException(status_code=400, detail="Invalid file type. Expected image.")
    elif media_type == models.MediaType.VIDEO:
        if not file.content_type.startswith("video/"):
             raise HTTPException(status_code=400, detail="Invalid file type. Expected video.")
         
    # Call Service
    media = await service.upload_media(db, current_user, file, media_type)
    
    # Trigger Background Transcoding
    # background_tasks.add_task(transcoding_service.process_media, db, media.id)
    await worker.enqueue_job("transcode_media", media_id=media.id)
    return media

@router.post("/posts", response_model=schemas.ContentRead)
async def create_post(
    post_in: schemas.ContentCreate,
    current_user: auth_models.User = Depends(plans_service.require_active_saas_plan), # Strict Enforcement
    db: AsyncSession = Depends(get_db)
) -> Any:
    if current_user.role != auth_models.UserRole.CREATOR:
         raise HTTPException(status_code=403, detail="Only creators can create posts")
    
    content = await service.create_content(db, current_user, post_in)
    return content

from uuid import UUID

@router.put("/posts/{content_id}", response_model=schemas.ContentRead)
async def update_post(
    content_id: UUID,
    post_in: schemas.ContentUpdate,
    current_user: auth_models.User = Depends(plans_service.require_active_saas_plan),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Update post details or status (e.g. Publish).
    """
    content = await service.update_content(db, current_user, content_id, post_in)
    if not content:
        raise HTTPException(status_code=404, detail="Content not found or access denied")
    return content

@router.delete("/posts/{content_id}", status_code=204)
async def delete_post(
    content_id: UUID,
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> None:
    """
    Soft delete content.
    """
    success = await service.delete_content(db, current_user, content_id)
    if not success:
        raise HTTPException(status_code=404, detail="Content not found or access denied")
    return None

@router.get("/media", response_model=schemas.MediaListResponse)
async def list_my_media(
    page: int = 1,
    size: int = 20,
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    List creator's uploaded media (Paginated).
    """
    if current_user.role != auth_models.UserRole.CREATOR:
        # Return empty structure
        return {"items": [], "total": 0, "page": page, "size": size, "pages": 0}
        
    return await service.list_creator_media_paginated(db, current_user.id, page, size)

@router.post("/media/upload-intent", response_model=schemas.MediaUploadResponse)
async def upload_intent(
    intent: schemas.MediaUploadIntent,
    current_user: auth_models.User = Depends(plans_service.require_active_saas_plan),
    db: AsyncSession = Depends(get_db)
) -> Any:
    # Strictly for Creators
    if current_user.role != auth_models.UserRole.CREATOR:
         raise HTTPException(status_code=403, detail="Only creators can upload content")
         
    # Validate MIME Type
    if not (intent.mime_type.startswith("image/") or intent.mime_type.startswith("video/")):
        raise HTTPException(status_code=400, detail="Invalid MIME type. Only images and videos are allowed.")
    
    return await service.create_upload_intent(db, current_user, intent)

@router.patch("/media/{media_id}/complete", response_model=schemas.MediaRead)
async def complete_upload(
    media_id: UUID,
    complete: schemas.MediaComplete,
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    media = await service.complete_upload(db, current_user, media_id, complete)
    
    # If video, trigger transcoding
    if media.media_type == models.MediaType.VIDEO:
        await worker.enqueue_job("transcode_media", media_id=media.id)
        
    return media

@router.delete("/media/{media_id}", status_code=204)
async def delete_media(
    media_id: UUID,
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> None:
    """
    Delete uploaded media.
    """
    success = await service.delete_media(db, current_user, media_id)
    if not success:
        raise HTTPException(status_code=404, detail="Media not found or access denied")
    return None

@router.put("/media/{media_id}/preview", response_model=schemas.MediaRead)
async def set_media_preview(
    media_id: UUID,
    status_update: schemas.MediaPreviewUpdate,
    current_user: auth_models.User = Depends(plans_service.require_active_saas_plan),
    db: AsyncSession = Depends(get_db)
):
    """
    Toggle is_public_preview flag for media.
    """
    return await service.update_media_preview(db, current_user, media_id, status_update.is_public_preview)

@router.post("/posts/{content_id}/attach/{media_id}", response_model=schemas.ContentRead)
async def attach_media(
    content_id: UUID,
    media_id: UUID,
    current_user: auth_models.User = Depends(plans_service.require_active_saas_plan), # Strict Enforcement
    db: AsyncSession = Depends(get_db)
) -> Any:
    # Service handles ownership check through simple db.get match, but safer strictly here
    # We pass UUIDs
    content = await service.attach_media_to_content(db, current_user, content_id, media_id)
    return content

@router.delete("/posts/{content_id}/media/{media_id}", status_code=204)
async def detach_media(
    content_id: UUID,
    media_id: UUID,
    current_user: auth_models.User = Depends(plans_service.require_active_saas_plan),
    db: AsyncSession = Depends(get_db)
) -> None:
    """
    Detach media from a post (does not delete the media file).
    """
    success = await service.detach_media_from_content(db, current_user, content_id, media_id)
    if not success:
        raise HTTPException(status_code=404, detail="Content/Media not found or not associated")
    return None

@router.get("/posts", response_model=List[schemas.ContentRead])
async def list_my_posts(
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
     if current_user.role == auth_models.UserRole.CREATOR:
         return await service.list_creator_content(db, current_user.id)
     else:
         # For consumers, list public or accessible?
         # For now, Creator only endpoint implies "My Posts"
         return []

@router.get("/posts/{content_id}", response_model=schemas.ContentRead)
async def get_post(
    content_id: UUID,
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    # Allow creator to see their own, or consumer to see published?
    # Logic in service needed.
    content = await service.get_content_details(db, current_user, content_id)
    if not content:
         raise HTTPException(status_code=404, detail="Content not found")
    return content

@router.get("/creator/{creator_id}/posts", response_model=List[schemas.ContentRead])
async def list_creator_posts_public(
    creator_id: UUID,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    List published posts for a specific creator.
    """
    return await service.list_creator_public_posts(db, creator_id)

@router.get("/feed", response_model=List[schemas.ContentRead])
async def list_feed(
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    List content from creators the user is subscribed to (ACTIVE status).
    """
    return await service.list_consumer_feed(db, current_user.id)
    
from fastapi import Request
import os
import aiofiles

@router.post("/b2-mock-upload")
async def b2_mock_upload(request: Request):
    """
    Simulates B2 Upload Endpoint.
    Expects binary body and 'X-Bz-File-Name' header.
    """
    file_name_encoded = request.headers.get("X-Bz-File-Name")
    if not file_name_encoded:
        raise HTTPException(status_code=400, detail="Missing X-Bz-File-Name header")
        
    # Decode the filename (frontend sends it url-encoded)
    from urllib.parse import unquote
    file_name = unquote(file_name_encoded)
    
    # Local Storage Path (e.g., /tmp/b2_mock)
    # Ensure directory exists
    mock_base = "static/uploads"
    os.makedirs(mock_base, exist_ok=True)
    
    # We strip 'creators/' to simplify local struct or keep it
    # file_name is like "creators/uuid/uuid/video.mp4"
    safe_path = os.path.join(mock_base, file_name)
    os.makedirs(os.path.dirname(safe_path), exist_ok=True)
    
    # Stream write
    async with aiofiles.open(safe_path, 'wb') as out_file:
        async for chunk in request.stream():
            await out_file.write(chunk)
            
    return {"fileId": "mock-file-id", "fileName": file_name, "contentSha1": "mock-sha1"}

@router.get("/media/{media_id}/preview")
async def get_media_preview(
    media_id: str,
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns a short-lived signed URL for the media thumbnail/preview.
    """
    media = await db.get(cms_models.Media, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
        
    # Check ownership (Creator only for CMS)
    if media.creator_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    # Determine Path
    start_path = media.file_path
    target_path = start_path
    
    print(f"[Preview] Processing media {media.id} ({media.media_type}) - Path: {start_path}")
    
    if media.media_type == cms_models.MediaType.VIDEO:
        # Resolve to poster.jpg if it exists/is expected
        if start_path.endswith("index.m3u8"):
            # processed
            parent = start_path.rsplit("/", 2)[0]
            target_path = f"{parent}/poster.jpg"
        else:
            # legacy/raw
            parent = os.path.dirname(start_path)
            target_path = f"{parent}/poster.jpg"
            
    print(f"[Preview] Target Path: {target_path}")
            
    # Get Signed URL
    from modules.delivery.b2_service import get_b2_service
    from fastapi.responses import RedirectResponse
    
    b2 = get_b2_service()
    
    # Try to get URL
    url = b2.get_download_url(target_path)
    print(f"[Preview] Generated URL: {url}")
    
    if not url:
        # Fallback to file path if image
        if media.media_type == cms_models.MediaType.IMAGE:
             # Just try signing the exact path
             url = b2.get_download_url(media.file_path)
             if not url:
                 print("[Preview] Failed to generate URL.")
                 raise HTTPException(status_code=404, detail="Preview unavailable")
        else:
             print("[Preview] Failed to generate URL.")
             raise HTTPException(status_code=404, detail="Preview unavailable")
             
    return RedirectResponse(url=url)
