from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime, timedelta

from modules.subscriptions import models, schemas
from modules.auth.models import User

async def subscribe_to_creator(db: AsyncSession, consumer_id: UUID, creator_id: UUID) -> models.ConsumerSubscription:
    # Check if already subscribed
    result = await db.execute(
        select(models.ConsumerSubscription)
        .where(
            models.ConsumerSubscription.consumer_id == consumer_id,
            models.ConsumerSubscription.creator_id == creator_id
        )
    )
    existing = result.scalars().first()
    
    # MVP: 30 days trial/period
    next_period_end = datetime.utcnow() + timedelta(days=30)
    
    if existing:
        existing.status = models.ConsumerSubscriptionStatus.ACTIVE
        existing.current_period_end = next_period_end # Extend
        # Return updated
        await db.commit()
        await db.refresh(existing)
        return existing
        
    # Create new
    sub = models.ConsumerSubscription(
        consumer_id=consumer_id,
        creator_id=creator_id,
        status=models.ConsumerSubscriptionStatus.ACTIVE,
        current_period_end=next_period_end
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return sub

from datetime import timezone

async def check_subscription_access(db: AsyncSession, consumer_id: UUID, creator_id: UUID) -> bool:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(models.ConsumerSubscription)
        .where(
            models.ConsumerSubscription.consumer_id == consumer_id,
            models.ConsumerSubscription.creator_id == creator_id,
            models.ConsumerSubscription.status == models.ConsumerSubscriptionStatus.ACTIVE,
            models.ConsumerSubscription.current_period_end > now
        )
    )
    sub = result.scalars().first()
    return sub is not None
