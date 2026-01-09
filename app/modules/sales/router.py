
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.db import get_db
from core import deps
from modules.auth import models as auth_models
from modules.cms import models as cms_models
from modules.sales import models as sales_models
from pydantic import BaseModel
import uuid
from datetime import datetime

router = APIRouter()

class PurchaseRequest(BaseModel):
    tx_hash: str

class PurchaseResponse(BaseModel):
    id: uuid.UUID
    status: str
    amount: float

@router.post("/content/{content_id}/purchase", response_model=PurchaseResponse)
async def purchase_content(
    content_id: uuid.UUID,
    payload: PurchaseRequest,
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    # 1. Fetch Content
    content = await db.get(cms_models.Content, content_id)
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
        
    if content.is_free:
        raise HTTPException(status_code=400, detail="Content is free, no purchase needed")
        
    # 2. Check if already purchased
    existing = await db.execute(
        select(sales_models.ContentPurchase)
        .where(
            sales_models.ContentPurchase.user_id == current_user.id,
            sales_models.ContentPurchase.content_id == content_id,
            sales_models.ContentPurchase.status == sales_models.PurchaseStatus.COMPLETED
        )
    )
    if existing.scalars().first():
         raise HTTPException(status_code=400, detail="Already purchased")

    # 3. Create Purchase Record
    # MOCK: Auto-complete for now since it's manual proof
    status = sales_models.PurchaseStatus.COMPLETED 
    
    purchase = sales_models.ContentPurchase(
        user_id=current_user.id,
        content_id=content_id,
        amount=content.price or 0.0,
        tx_hash=payload.tx_hash,
        status=status,
        completed_at=datetime.utcnow() if status == sales_models.PurchaseStatus.COMPLETED else None
    )
    db.add(purchase)
    await db.commit()
    await db.refresh(purchase)
    
    return purchase

@router.get("/content/{content_id}/check_access")
async def check_access(
    content_id: uuid.UUID,
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    # Check purchase
    result = await db.execute(
        select(sales_models.ContentPurchase)
        .where(
            sales_models.ContentPurchase.user_id == current_user.id,
            sales_models.ContentPurchase.content_id == content_id,
            sales_models.ContentPurchase.status == sales_models.PurchaseStatus.COMPLETED
        )
    )
    purchase = result.scalars().first()
    return {"access":purchase is not None}
