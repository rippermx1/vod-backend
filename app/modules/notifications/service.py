from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.modules.notifications import models, schemas
from uuid import UUID
from typing import Optional

async def create_notification(
    db: AsyncSession,
    user_id: UUID,
    title: str,
    message: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None
) -> models.Notification:
    notification = models.Notification(
        user_id=user_id,
        title=title,
        message=message,
        resource_type=resource_type,
        resource_id=resource_id,
        is_read=False
    )
    db.add(notification)
    # We await commit here to ensure notification persists immediately if called as side-effect
    await db.commit()
    
    # Real-time Broadcast
    try:
        from app.modules.notifications.broadcaster import broadcaster
        payload = {
            "id": str(notification.id),
            "title": notification.title,
            "message": notification.message,
            "resource_type": notification.resource_type,
            "resource_id": notification.resource_id,
            "created_at": notification.created_at.isoformat() if notification.created_at else None
        }
        await broadcaster.broadcast(user_id, payload)
    except Exception as e:
        print(f"Broadcast error: {e}")

    return notification

async def list_my_notifications(db: AsyncSession, user_id: UUID):
    result = await db.execute(
        select(models.Notification)
        .where(models.Notification.user_id == user_id)
        .order_by(models.Notification.created_at.desc())
    )
    return result.scalars().all()

async def mark_as_read(db: AsyncSession, notification_id: UUID, user_id: UUID):
    result = await db.execute(
        select(models.Notification)
        .where(models.Notification.id == notification_id, models.Notification.user_id == user_id)
    )
    notification = result.scalars().first()
    if notification:
        notification.is_read = True
        await db.commit()
        await db.refresh(notification)
    return notification
