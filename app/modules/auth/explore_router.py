from typing import Any, List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.db import get_db
from app.core import deps
from app.modules.auth import models, schemas

router = APIRouter()

@router.get("/", response_model=List[schemas.CreatorProfileResponse])
async def list_creators(
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Public endpoint to list all active creators.
    """
    from sqlalchemy import func
    
    # We need to fetch likes count for each creator
    # Simplest way is a subquery or loading dynamically
    
    # Subquery for count
    likes_subquery = (
        select(func.count(models.UserLike.id))
        .where(models.UserLike.creator_id == models.User.id)
        .scalar_subquery()
    )
    
    result = await db.execute(
        select(models.User, likes_subquery.label("likes_count"))
        .where(
            models.User.role == models.UserRole.CREATOR,
            models.User.is_active == True
        )
    )
    
    rows = result.all()
    response = []
    
    # If we had a current user, we could check is_liked too, but this endpoint is public/optional auth
    # For now let's just return counts. 
    # NOTE: To support "is_liked" efficiently we need the user. 
    # Let's add optional user dependency if we want "is_liked" in the list.
    
    for user, likes in rows:
        # Map to schema
        profile = schemas.CreatorProfileResponse.from_orm(user)
        profile.likes_count = likes or 0
        response.append(profile)
        
    return response

from uuid import UUID
from fastapi import HTTPException
from app.modules.auth import models

@router.get("/{user_id}", response_model=schemas.CreatorProfileResponse)
async def get_creator_profile(
    user_id: UUID,
    current_user: models.User | None = Depends(deps.get_current_user_optional),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Get public profile of a creator.
    """
    user = await db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Creator not found")
        
    response = schemas.CreatorProfileResponse.from_orm(user)
    
    if current_user:
        # Check subscription
        from app.modules.subscriptions import service as sub_service
        is_subscribed = await sub_service.check_subscription_access(db, current_user.id, user_id)
        response.is_subscribed = is_subscribed
        
    return response

@router.post("/{user_id}/like", response_model=bool)
async def like_creator(
    user_id: UUID,
    current_user: models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    # Check if self
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot like yourself")
        
    # Check if creator exists (optional but good)
    creator = await db.get(models.User, user_id)
    if not creator:
        raise HTTPException(status_code=404, detail="Creator not found")

    # Check existence
    result = await db.execute(
        select(models.UserLike)
        .where(
            models.UserLike.user_id == current_user.id,
            models.UserLike.creator_id == user_id
        )
    )
    existing = result.scalars().first()
    if existing:
        return True # Already liked
        
    new_like = models.UserLike(user_id=current_user.id, creator_id=user_id)
    db.add(new_like)
    await db.commit()
    return True

@router.delete("/{user_id}/like", response_model=bool)
async def unlike_creator(
    user_id: UUID,
    current_user: models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    result = await db.execute(
        select(models.UserLike)
        .where(
            models.UserLike.user_id == current_user.id,
            models.UserLike.creator_id == user_id
        )
    )
    existing = result.scalars().first()
    if existing:
        await db.delete(existing)
        await db.commit()
        
    return True

@router.get("/{user_id}/avatar")
async def get_creator_avatar(
    user_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Redirects to the creator's avatar (signed B2 URL or local).
    """
    user = await db.get(models.User, user_id)
    if not user or not user.avatar_url:
         # Redirect to default avatar or return 404
         # Better: Redirect to a static placeholder
         from fastapi.responses import RedirectResponse
         return RedirectResponse(url="/static/img/default-avatar.png") # adjust path as needed

    avatar_url = user.avatar_url
    
    # If it's a B2 path (no protocol), sign it
    if not avatar_url.startswith("http") and not avatar_url.startswith("/"):
         from app.modules.delivery.b2_service import get_b2_service
         b2 = get_b2_service()
         signed_url = b2.get_download_url(avatar_url)
         if signed_url:
             from fastapi.responses import RedirectResponse
             return RedirectResponse(url=signed_url)
    
    # If it's local (starts with /) or external (http), redirect directly or serve?
    # If mock local: /static/uploads/...
    from fastapi.responses import RedirectResponse
    # Ensure full URL for local if needed, or relative redirect works?
    # RedirectResponse works with relative.
    
    # Fix for local mock having full URL stored sometimes?
    # ProfileCMS stores: `http://localhost:8000/static/uploads/...` for mock.
    # B2 stores: `creators/...`
    
    if avatar_url.startswith("http"):
         return RedirectResponse(url=avatar_url)
         
    if avatar_url.startswith("/"):
         return RedirectResponse(url=avatar_url)

    # Fallback
    return RedirectResponse(url="/static/img/default-avatar.png")
