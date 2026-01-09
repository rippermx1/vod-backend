from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from modules.plans import models, schemas
from uuid import UUID
from datetime import datetime, timedelta

async def get_active_plans(db: AsyncSession):
    # Eager load features and limits
    result = await db.execute(
        select(models.SaasPlan)
        .where(models.SaasPlan.is_active == True)
        .options(selectinload(models.SaasPlan.features), selectinload(models.SaasPlan.limits))
    )
    return result.scalars().all()

async def create_payment_request(db: AsyncSession, creator_id: UUID, payment_in: schemas.PaymentCreate):
    payment = models.SaasPayment(
        creator_id=creator_id,
        plan_id=payment_in.plan_id,
        amount_usdt=payment_in.amount_usdt,
        tx_hash=payment_in.tx_hash,
        status=models.PaymentStatus.PENDING
    )
    db.add(payment)
    await db.commit()
    await db.refresh(payment)
    return payment

async def get_creator_subscription(db: AsyncSession, creator_id: UUID):
    # Eager load plan AND its deep relations
    result = await db.execute(
        select(models.CreatorSubscription)
        .where(models.CreatorSubscription.creator_id == creator_id)
        .options(
            selectinload(models.CreatorSubscription.plan)
            .selectinload(models.SaasPlan.features),
            selectinload(models.CreatorSubscription.plan)
            .selectinload(models.SaasPlan.limits)
        )
    )
    return result.scalars().first()

async def confirm_payment_and_subscribe(db: AsyncSession, payment_id: str, admin_id: UUID):
    # Get payment
    result = await db.execute(select(models.SaasPayment).where(models.SaasPayment.id == payment_id))
    payment = result.scalars().first()
    if not payment or payment.status != models.PaymentStatus.PENDING:
        return None
    
    # Update Payment
    payment.status = models.PaymentStatus.CONFIRMED
    payment.reviewed_by = admin_id
    
    # Audit Log
    from modules.admin import service as admin_service
    await admin_service.create_audit_log(
        db,
        action="payment.confirm",
        user_id=admin_id,
        target_type="saas_payment",
        target_id=str(payment.id),
        metadata={"amount": float(payment.amount_usdt), "creator_id": str(payment.creator_id)}
    )

    # Notification
    from modules.notifications import service as notification_service
    await notification_service.create_notification(
        db,
        user_id=payment.creator_id,
        title="Payment Confirmed",
        message=f"Your payment of ${payment.amount_usdt} USDT has been confirmed.",
        resource_type="saas_payment",
        resource_id=str(payment.id)
    )
    
    # Get Plan
    plan_result = await db.execute(select(models.SaasPlan).where(models.SaasPlan.id == payment.plan_id))
    plan = plan_result.scalars().first()
    
    # Upsert Subscription
    # Check existing
    sub_result = await db.execute(select(models.CreatorSubscription).where(models.CreatorSubscription.creator_id == payment.creator_id))
    sub = sub_result.scalars().first()
    
    if sub:
        sub.plan_id = plan.id
        sub.status = models.SubscriptionStatus.ACTIVE
        sub.expires_at = datetime.utcnow() + timedelta(days=plan.period_days)
    else:
        sub = models.CreatorSubscription(
            creator_id=payment.creator_id,
            plan_id=plan.id,
            status=models.SubscriptionStatus.ACTIVE,
            expires_at=datetime.utcnow() + timedelta(days=plan.period_days)
        )
        db.add(sub)
    
    await db.commit()
    await db.refresh(sub)
    # Eager load plan for return
    # Manual reload to ensure relationship is populated
    return await get_creator_subscription(db, payment.creator_id)

async def has_feature(db: AsyncSession, creator_id: UUID, feature_key: str) -> bool:
    sub = await get_creator_subscription(db, creator_id)
    if not sub or sub.status != models.SubscriptionStatus.ACTIVE:
        return False
    
    # Check Plan Features
    # Since get_creator_subscription eagerly loads features via chained selectinload
    for feature in sub.plan.features:
        if feature.feature_key == feature_key:
            return feature.is_enabled
    
    return False # Default to False if not specified

async def get_plan_limit(db: AsyncSession, creator_id: UUID, limit_key: str) -> int:
    """Returns limit value. -1 for unlimited, 0 for none."""
    sub = await get_creator_subscription(db, creator_id)
    if not sub or sub.status != models.SubscriptionStatus.ACTIVE:
        return 0
    
    for limit in sub.plan.limits:
        if limit.limit_key == limit_key:
            return limit.limit_value
            
    return 0 # Default 0 if not specified

async def list_pending_payments(db: AsyncSession):
    from modules.auth import models as auth_models
    stmt = (
        select(models.SaasPayment, auth_models.User.email)
        .join(auth_models.User, models.SaasPayment.creator_id == auth_models.User.id)
        .where(models.SaasPayment.status == models.PaymentStatus.PENDING)
    )
    result = await db.execute(stmt)
    rows = result.all()
    
    response = []
    for payment, email in rows:
        p_dict = {
            "id": payment.id,
            "creator_id": payment.creator_id,
            "creator_email": email,
            "plan_id": payment.plan_id,
            "status": payment.status,
            "tx_hash": payment.tx_hash,
            "amount_usdt": payment.amount_usdt,
            "created_at": payment.created_at
        }
        response.append(p_dict)
    return response
    return response

from fastapi import HTTPException, Depends
from core import deps
from modules.auth import models as auth_models

async def require_active_saas_plan(
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(deps.get_db)
) -> auth_models.User:
    """
    Dependency to ensure the current creator has an ACTIVE SaaS subscription.
    """
    if current_user.role != auth_models.UserRole.CREATOR:
        raise HTTPException(status_code=403, detail="Role must be CREATOR")

    sub = await get_creator_subscription(db, current_user.id)
    if not sub:
        raise HTTPException(status_code=403, detail="SaaS Plan required to perform this action.")
    
    if sub.status != models.SubscriptionStatus.ACTIVE:
        # Check expiry grace logic here if needed, for now Strict MVP
        if sub.expires_at and sub.expires_at < datetime.utcnow():
             raise HTTPException(status_code=403, detail="SaaS Plan expired. Please renew.")
        if sub.status != models.SubscriptionStatus.ACTIVE:
             raise HTTPException(status_code=403, detail="SaaS Plan not active.")

    return current_user

async def assign_free_trial(db: AsyncSession, creator_id: UUID) -> bool:
    """
    Assigns a 14-day free trial of the 'Basic' (or first available) plan to the creator.
    """
    # 1. Try to find a specific TRIAL plan, or fall back to any plan (usually Basic)
    result = await db.execute(select(models.SaasPlan).where(models.SaasPlan.code == "TRIAL"))
    plan = result.scalars().first()
    
    if not plan:
        # Fallback: Find cheapest plan
        result = await db.execute(select(models.SaasPlan).order_by(models.SaasPlan.price_usdt.asc()))
        plan = result.scalars().first()
        
    if not plan:
        return False # No plans seeded?
        
    # 2. Create Active Subscription (Trial)
    sub = models.CreatorSubscription(
        creator_id=creator_id,
        plan_id=plan.id,
        status=models.SubscriptionStatus.ACTIVE,
        expires_at=datetime.utcnow() + timedelta(days=14) # 14 Day Trial
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return True
