from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from datetime import datetime, timedelta

from core.db import get_db
from core import deps
from modules.auth import models as auth_models
from modules.subscriptions import schemas, service, models

router = APIRouter()

@router.get("/me", response_model=List[schemas.SubscriptionRead])
async def list_my_subscriptions(
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    from sqlalchemy import select, func, and_
    from modules.auth.models import User
    from modules.cms.models import Content, ContentStatus
    
    # Subquery for new posts (last 3 days)
    three_days_ago = datetime.utcnow() - timedelta(days=3)
    
    # We want to count posts per creator.
    # We can do this with a scalar subquery in the main select
    new_posts_subquery = (
        select(func.count(Content.id))
        .where(
            Content.creator_id == models.ConsumerSubscription.creator_id,
            Content.status == ContentStatus.PUBLISHED,
            Content.published_at >= three_days_ago
        )
        .scalar_subquery()
    )
    
    result = await db.execute(
        select(
            models.ConsumerSubscription, 
            User.email.label("creator_email"),
            User.monthly_price.label("monthly_price"),
            new_posts_subquery.label("new_posts_count"),
            User.full_name.label("creator_name"),
            User.avatar_url.label("creator_avatar_url")
        )
        .join(User, models.ConsumerSubscription.creator_id == User.id)
        .where(models.ConsumerSubscription.consumer_id == current_user.id)
    )
    
    rows = result.all()
    response = []
    for sub, email, price, count, name, avatar in rows:
        sub_dict = {
            "id": sub.id,
            "consumer_id": sub.consumer_id,
            "creator_id": sub.creator_id,
            "status": sub.status,
            "proof_tx_hash": sub.proof_tx_hash,
            "current_period_end": sub.current_period_end,
            "created_at": sub.created_at,
            "creator_email": email,
            "monthly_price": price or 0.0,
            "new_posts_count": count or 0,
            "creator_name": name or "Unknown Creator",
            "creator_avatar_url": avatar
        }
        response.append(sub_dict)
    return response

@router.get("/requests", response_model=List[schemas.SubscriptionRead])
async def list_subscription_requests(
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """For Creators to see pending requests"""
    if current_user.role != auth_models.UserRole.CREATOR:
         raise HTTPException(status_code=403, detail="Only creators")
         
    from sqlalchemy import select
    result = await db.execute(
        select(models.ConsumerSubscription)
        .where(
            models.ConsumerSubscription.creator_id == current_user.id,
            models.ConsumerSubscription.status == models.ConsumerSubscriptionStatus.PENDING_REVIEW
        )
    )
    return result.scalars().all()

@router.get("/subscribers", response_model=List[schemas.SubscriptionRead])
async def list_my_subscribers(
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """For Creators to see all subscribers"""
    if current_user.role != auth_models.UserRole.CREATOR:
         raise HTTPException(status_code=403, detail="Only creators")
         
    from sqlalchemy import select
    from modules.auth.models import User
    
    # improved query with join to get email
    stmt = (
        select(models.ConsumerSubscription, User.email.label("consumer_email"))
        .join(User, models.ConsumerSubscription.consumer_id == User.id)
        .where(models.ConsumerSubscription.creator_id == current_user.id)
        .order_by(models.ConsumerSubscription.created_at.desc())
    )
    
    result = await db.execute(stmt)
    
    # Map result (Tuple[ConsumerSubscription, str]) to Schema
    # Since we are returning a list of Pydantic models, we need to manually map or update the objects
    rows = result.all()
    
    response = []
    for sub, email in rows:
        # Pydantic's from_attributes handles the DB model fields, we inject email manually or use a dict
        sub_dict = {
            "id": sub.id,
            "consumer_id": sub.consumer_id,
            "creator_id": sub.creator_id,
            "status": sub.status,
            "proof_tx_hash": sub.proof_tx_hash,
            "current_period_end": sub.current_period_end,
            "created_at": sub.created_at,
            "consumer_email": email
        }
        response.append(sub_dict)
        
    return response

@router.post("/{creator_id}", response_model=schemas.SubscriptionRead)
async def subscribe_to_creator(
    creator_id: UUID,
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    if current_user.id == creator_id:
        raise HTTPException(status_code=400, detail="Cannot subscribe to yourself")
    
    # Check existing
    from sqlalchemy import select
    result = await db.execute(
        select(models.ConsumerSubscription)
        .where(
            models.ConsumerSubscription.consumer_id == current_user.id,
            models.ConsumerSubscription.creator_id == creator_id
        )
    )
    existing = result.scalars().first()
    if existing:
        return existing
        
    # Create new PENDING_PAYMENT
    # MVP end date? Set to now or null?
    # Let's set it to now, extended only on activation.
    sub = models.ConsumerSubscription(
        consumer_id=current_user.id,
        creator_id=creator_id,
        status=models.ConsumerSubscriptionStatus.PENDING_PAYMENT,
        current_period_end=datetime.utcnow()
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    await db.refresh(sub)
    return sub

@router.get("/{sub_id}", response_model=schemas.SubscriptionRead)
async def get_subscription(
    sub_id: UUID,
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Get subscription details"""
    sub = await db.get(models.ConsumerSubscription, sub_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
        
    if sub.consumer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your subscription")
        
    return sub

@router.post("/{sub_id}/proof", response_model=schemas.SubscriptionRead)
async def submit_proof(
    sub_id: UUID,
    proof_in: schemas.SubscriptionProof,
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    sub = await db.get(models.ConsumerSubscription, sub_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    if sub.consumer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your subscription")
        
    sub.proof_tx_hash = proof_in.tx_hash
    sub.status = models.ConsumerSubscriptionStatus.PENDING_REVIEW
    await db.commit()
    await db.refresh(sub)
    return sub

@router.post("/{sub_id}/approve", response_model=schemas.SubscriptionRead)
async def approve_subscription(
    sub_id: UUID,
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    sub = await db.get(models.ConsumerSubscription, sub_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    if sub.creator_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the creator can approve this subscription")
        
    # Activate
    sub.status = models.ConsumerSubscriptionStatus.ACTIVE
    sub.current_period_end = datetime.utcnow() + timedelta(days=30)
    await db.commit()
    await db.refresh(sub)
    return sub

@router.post("/{sub_id}/reject", response_model=schemas.SubscriptionRead)
async def reject_subscription(
    sub_id: UUID,
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    sub = await db.get(models.ConsumerSubscription, sub_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    if sub.creator_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the creator can reject this subscription")
        
    # Reject
    sub.status = models.ConsumerSubscriptionStatus.REJECTED
    # Optional: Reset proof? Keep it for audit.
    await db.commit()
    await db.refresh(sub)
    return sub

@router.get("/check/{creator_id}", response_model=bool)
async def check_access(
    creator_id: UUID,
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    return await service.check_subscription_access(db, current_user.id, creator_id)

@router.post("/{sub_id}/simulate-payment", response_model=schemas.SubscriptionRead)
async def simulate_payment(
    sub_id: UUID,
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Mock payment for local testing"""
    sub = await db.get(models.ConsumerSubscription, sub_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    if sub.consumer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your subscription")
        
    # Auto-activate
    sub.status = models.ConsumerSubscriptionStatus.ACTIVE
    sub.current_period_end = datetime.utcnow() + timedelta(days=30)
    await db.commit()
    await db.refresh(sub)
    return sub






