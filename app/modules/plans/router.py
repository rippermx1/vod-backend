from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from core.db import get_db
from core import deps
from modules.auth import models as auth_models
from modules.plans import schemas, service

router = APIRouter()

@router.get("/", response_model=List[schemas.PlanRead])
async def list_plans(
    db: AsyncSession = Depends(get_db)
) -> Any:
    # return await service.get_active_plans(db)
    # Service returns scalars, simple return implies validation by pydantic which might need relationships loaded.
    # To be safe, we might need explicit conversion or eager loading.
    # For MVP, assuming service handles query correctly.
    plans = await service.get_active_plans(db)
    return plans

@router.post("/pay", response_model=schemas.PaymentRead)
async def submit_payment(
    payment_in: schemas.PaymentCreate,
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    if current_user.role != auth_models.UserRole.CREATOR:
        raise HTTPException(status_code=403, detail="Only creators can subscribe to plans")
        
    payment = await service.create_payment_request(db, current_user.id, payment_in)
    return payment

@router.get("/me/subscription", response_model=Optional[schemas.SubscriptionRead])
async def get_my_subscription(
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    sub = await service.get_creator_subscription(db, current_user.id)
    return sub

@router.post("/payments/{payment_id}/confirm", response_model=schemas.SubscriptionRead)
async def confirm_payment(
    payment_id: str,
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    if current_user.role != auth_models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    # Logic moved to service for cleanliness
    sub = await service.confirm_payment_and_subscribe(db, payment_id, current_user.id)
    if not sub:
        raise HTTPException(status_code=404, detail="Payment not found or already processed")
    return sub

@router.post("/me/payment-methods", response_model=schemas.PaymentMethodRead)
async def create_payment_method(
    method_in: schemas.PaymentMethodCreate,
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    if current_user.role != auth_models.UserRole.CREATOR:
        raise HTTPException(status_code=403, detail="Only creators can set payment methods")
    
    # Deactivate old ones? For MVP just add one or update existing?
    # Let's simple add new one
    from modules.plans import models
    method = models.CreatorPaymentMethod(
        creator_id=current_user.id,
        payment_type=method_in.payment_type,
        details=method_in.details,
        is_active=True
    )
    db.add(method)
    await db.commit()
    await db.refresh(method)
    return method

@router.get("/payment-methods/{creator_id}", response_model=List[schemas.PaymentMethodRead])
async def get_creator_payment_methods(
    creator_id: str,
    db: AsyncSession = Depends(get_db)
) -> Any:
    from sqlalchemy import select
    from modules.plans import models
    result = await db.execute(
        select(models.CreatorPaymentMethod)
        .where(models.CreatorPaymentMethod.creator_id == creator_id, models.CreatorPaymentMethod.is_active == True)
    )
    return result.scalars().all()

@router.get("/payments", response_model=List[schemas.PaymentRead])
async def list_payments(
    status: schemas.PaymentStatus = schemas.PaymentStatus.PENDING,
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    if current_user.role != auth_models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin only")
    
    if status == schemas.PaymentStatus.PENDING:
        return await service.list_pending_payments(db)
    
    return [] # Placeholder for other statuses
