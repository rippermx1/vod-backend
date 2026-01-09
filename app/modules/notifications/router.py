from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core import deps
from app.modules.auth import models as auth_models
from app.modules.notifications import schemas, service
from app.modules.notifications.broadcaster import broadcaster
from fastapi.responses import StreamingResponse
import asyncio
import json

router = APIRouter()

@router.get("/", response_model=List[schemas.NotificationRead])
async def list_notifications(
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    List current user's notifications.
    """
    return await service.list_my_notifications(db, current_user.id)

@router.post("/{id}/read", response_model=schemas.NotificationRead)
async def mark_read(
    id: str,
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Mark a notification as read.
    """
    # Parse UUID? Pydantic handles validation if we pass to service or use UUID type in path
    from uuid import UUID
    try:
        uuid_id = UUID(id)
    except ValueError:
       raise HTTPException(status_code=400, detail="Invalid ID")

    notification = await service.mark_as_read(db, uuid_id, current_user.id)
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    return notification

@router.get("/stream")
async def stream_notifications(
    current_user: auth_models.User = Depends(deps.get_current_active_user)
):
    """
    SSE Endpoint for real-time notifications.
    """
    async def event_generator():
        queue = await broadcaster.connect(current_user.id)
        try:
            while True:
                # Wait for message or keep-alive
                try:
                    # Timeout to send keep-alive comment every 15s to prevent timeouts
                    message = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {json.dumps(message)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        except asyncio.CancelledError:
            await broadcaster.disconnect(current_user.id, queue)
            # break (generator exit)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
