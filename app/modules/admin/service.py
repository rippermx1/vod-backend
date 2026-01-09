from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from modules.auth import models as auth_models
from modules.compliance import models as kyc_models
from modules.plans import models as plan_models
from modules.admin.models import AuditLog
from uuid import UUID
from typing import Optional, Dict, Any

async def create_audit_log(
    db: AsyncSession,
    action: str,
    user_id: Optional[UUID] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None
):
    log = AuditLog(
        user_id=user_id,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id else None,
        metadata_json=metadata,
        ip_address=ip_address
    )
    db.add(log)
    # We commit here to ensure log is saved even if main transaction might fail later, 
    # BUT typically we want it part of the same transaction if it's "action X occurred".
    # For now, we assume the caller handles commit or we assume it's part of the flow.
    # Actually, async session requires explicit commit.
    # If we want it to be part of the main Unit of Work, we just add it.
    # If we want it to persist even if the operation fails (e.g. "failed login"), we commit immediately.
    # For now, just add. Caller usually commits.
    # Wait, if we use this for "side effects", we might want to commit.
    # Let's commit to be safe it persists.
    await db.commit() 

async def get_stats(db: AsyncSession) -> dict:
    # Users
    users_res = await db.execute(
        select(auth_models.User.role, func.count(auth_models.User.id)).group_by(auth_models.User.role)
    )
    user_counts = {row[0]: row[1] for row in users_res.all()}
    
    total_creators = user_counts.get(auth_models.UserRole.CREATOR, 0)
    total_consumers = user_counts.get(auth_models.UserRole.CONSUMER, 0)
    total_users = sum(user_counts.values())
    
    # KYC
    kyc_res = await db.execute(
        select(func.count(kyc_models.KYCSubmission.id))
        .where(kyc_models.KYCSubmission.status == kyc_models.KYCStatus.PENDING)
    )
    pending_kyc = kyc_res.scalar() or 0
    
    # Payments (SaasPayment)
    payments_res = await db.execute(
        select(func.count(plan_models.SaasPayment.id))
        .where(plan_models.SaasPayment.status == plan_models.PaymentStatus.PENDING)
    )
    pending_payments = payments_res.scalar() or 0

    # Revenue (Confirmed Payments)
    revenue_res = await db.execute(
        select(func.sum(plan_models.SaasPayment.amount_usdt))
        .where(plan_models.SaasPayment.status == plan_models.PaymentStatus.CONFIRMED)
    )
    revenue_total_usdt = revenue_res.scalar() or 0.0
    
    return {
        "total_users": total_users,
        "total_creators": total_creators,
        "total_consumers": total_consumers,
        "pending_kyc": pending_kyc,
        "pending_payments": pending_payments,
        "revenue_total_usdt": float(revenue_total_usdt)
    }

async def get_all_users(db: AsyncSession):
    result = await db.execute(
        select(auth_models.User)
        .order_by(auth_models.User.created_at.desc())
    )
    return result.scalars().all()

async def update_user_status(db: AsyncSession, user_id: UUID, is_active: bool, current_admin_id: UUID) -> auth_models.User:
    result = await db.execute(select(auth_models.User).where(auth_models.User.id == user_id))
    user = result.scalars().first()
    
    if not user:
        return None
        
    old_status = user.is_active
    user.is_active = is_active
    db.add(user)
    
    # Audit Log
    await create_audit_log(
        db,
        action="admin.user.ban" if not is_active else "admin.user.unban",
        user_id=current_admin_id,
        target_type="user",
        target_id=str(user.id),
        metadata={"old_status": old_status, "new_status": is_active}
    )
    
    await db.commit()
    await db.refresh(user)
    return user

async def update_user(db: AsyncSession, user_id: UUID, user_in: Any, current_admin_id: UUID) -> auth_models.User:
    result = await db.execute(select(auth_models.User).where(auth_models.User.id == user_id))
    user = result.scalars().first()
    
    if not user:
        return None
        
    update_data = user_in.model_dump(exclude_unset=True)
    
    # Track changes for audit
    changes = {}
    
    for field, value in update_data.items():
        if hasattr(user, field):
            old_val = getattr(user, field)
            if old_val != value:
                setattr(user, field, value)
                changes[field] = {"old": str(old_val), "new": str(value)}
                
    if changes:
        db.add(user)
        # Audit Log
        await create_audit_log(
            db,
            action="admin.user.update",
            user_id=current_admin_id,
            target_type="user",
            target_id=str(user.id),
            metadata={"changes": changes}
        )
        await db.commit()
        await db.refresh(user)
        
    return user

async def update_user_plan(db: AsyncSession, user_id: UUID, plan_id: Optional[UUID], current_admin_id: UUID) -> auth_models.User:
    result = await db.execute(select(auth_models.User).where(auth_models.User.id == user_id))
    user = result.scalars().first()
    
    if not user:
        return None
    
    # Needs to update CreatorSubscription, not user.plan_id
    from modules.plans import models as plan_models
    
    # Find existing active or recent subscription
    # Logic: "Admin Override" implies forcing the current active plan.
    # We should search for an active subscription. If none, create one.
    sub_res = await db.execute(
        select(plan_models.CreatorSubscription)
        .where(plan_models.CreatorSubscription.creator_id == user_id)
    )
    # Just take the first one or the active one?
    # Creator should only have one active.
    subs = sub_res.scalars().all()
    
    active_sub = next((s for s in subs if s.status == plan_models.SubscriptionStatus.ACTIVE), None)
    target_sub = active_sub if active_sub else (subs[0] if subs else None)
    
    old_plan = target_sub.plan_id if target_sub else None
    
    if plan_id:
        if target_sub:
            target_sub.plan_id = plan_id
            target_sub.status = plan_models.SubscriptionStatus.ACTIVE # Force active if admin sets it
            db.add(target_sub)
        else:
            # Create new
            new_sub = plan_models.CreatorSubscription(
                creator_id=user_id,
                plan_id=plan_id,
                status=plan_models.SubscriptionStatus.ACTIVE
            )
            db.add(new_sub)
    elif target_sub:
        # If plan_id is None, maybe we want to cancel?
        # For now, let's assume removing plan means setting status to cancelled or expired
         target_sub.status = plan_models.SubscriptionStatus.CANCELLED
         db.add(target_sub)
    
    await create_audit_log(
        db,
        action="admin.user.plan_update",
        user_id=current_admin_id,
        target_type="user",
        target_id=str(user.id),
        metadata={"old_plan": str(old_plan), "new_plan": str(plan_id)}
    )
    
    await db.commit()
    await db.refresh(user)
    return user

async def get_all_plans(db: AsyncSession):
    # Admin wants to see even inactive plans? Probably yes.
    result = await db.execute(select(plan_models.SaasPlan).order_by(plan_models.SaasPlan.price_usdt.asc()))
    plans = result.scalars().all()
    # Eager load features/limits? SQLModel defaults? SQLAlchemy needs active join or lazy load.
    # The response model PlanRead expects features/limits.
    # We should use `options(selectinload(SaasPlan.features))`
    
    # Re-query with eager loading properly
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(plan_models.SaasPlan)
        .options(selectinload(plan_models.SaasPlan.features), selectinload(plan_models.SaasPlan.limits))
        .order_by(plan_models.SaasPlan.price_usdt.asc())
    )
    return result.scalars().all()

async def create_plan(db: AsyncSession, plan_in: Any) -> plan_models.SaasPlan:
    # plan_in is PlanCreate schema
    db_plan = plan_models.SaasPlan(
        code=plan_in.code,
        name=plan_in.name,
        price_usdt=plan_in.price_usdt,
        period_days=plan_in.period_days,
        is_active=plan_in.is_active
    )
    db.add(db_plan)
    await db.commit()
    await db.refresh(db_plan)
    
    # Add features
    for feat in plan_in.features:
        db_feat = plan_models.SaasPlanFeature(
            plan_id=db_plan.id,
            feature_key=feat.feature_key,
            is_enabled=feat.is_enabled
        )
        db.add(db_feat)
        
    # Add limits
    for lim in plan_in.limits:
        db_lim = plan_models.SaasPlanLimit(
            plan_id=db_plan.id,
            limit_key=lim.limit_key,
            limit_value=lim.limit_value
        )
        db.add(db_lim)
        
    await db.commit()
    
    # Reload with relations
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(plan_models.SaasPlan)
        .where(plan_models.SaasPlan.id == db_plan.id)
        .options(selectinload(plan_models.SaasPlan.features), selectinload(plan_models.SaasPlan.limits))
    )
    return result.scalars().first()

async def update_plan(db: AsyncSession, plan_id: UUID, plan_in: Any) -> plan_models.SaasPlan:
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(plan_models.SaasPlan)
        .where(plan_models.SaasPlan.id == plan_id)
        .options(selectinload(plan_models.SaasPlan.features), selectinload(plan_models.SaasPlan.limits))
    )
    db_plan = result.scalars().first()
    if not db_plan:
        return None
        
    # Update base fields
    if plan_in.name is not None: db_plan.name = plan_in.name
    if plan_in.price_usdt is not None: db_plan.price_usdt = plan_in.price_usdt
    if plan_in.is_active is not None: db_plan.is_active = plan_in.is_active
    # Code is usually immutable for logic but for admin maybe editable if handled carefully.
    
    # Re-create features/limits (simplest) or update?
    # For MVP, clear and re-add is easiest but destructive of IDs. 
    # Let's assume frontend sends full list.
    
    # Clear existing
    for f in db_plan.features:
        await db.delete(f)
    for l in db_plan.limits:
        await db.delete(l)
        
    # Add new
    from modules.plans import models as pm
    for feat in plan_in.features:
        db.add(pm.SaasPlanFeature(plan_id=db_plan.id, feature_key=feat.feature_key, is_enabled=feat.is_enabled))
    for lim in plan_in.limits:
        db.add(pm.SaasPlanLimit(plan_id=db_plan.id, limit_key=lim.limit_key, limit_value=lim.limit_value))
        
    await db.commit()
    await db.refresh(db_plan)
    return db_plan

async def get_audit_logs(db: AsyncSession, limit: int = 50):
    result = await db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit))
    return result.scalars().all()

from modules.admin.models import SystemSetting

async def get_system_settings(db: AsyncSession):
    result = await db.execute(select(SystemSetting))
    return result.scalars().all()

async def update_system_setting(db: AsyncSession, key: str, value: str, description: str = None) -> SystemSetting:
    result = await db.execute(select(SystemSetting).where(SystemSetting.key == key))
    setting = result.scalars().first()
    
    if not setting:
        setting = SystemSetting(key=key, value=value, description=description)
        db.add(setting)
    else:
        setting.value = value
        if description:
            setting.description = description
            
    await db.commit()
    await db.refresh(setting)
    return setting

async def get_maintenance_mode(db: AsyncSession) -> bool:
    # Use cached or direct query
    # For MVP direct query is fine
    result = await db.execute(select(SystemSetting).where(SystemSetting.key == "maintenance_mode"))
    setting = result.scalars().first()
    if setting and setting.value.lower() == "true":
        return True
    return False

async def get_user_details(db: AsyncSession, user_id: UUID) -> Any:
    # 1. Get User
    result = await db.execute(select(auth_models.User).where(auth_models.User.id == user_id))
    user = result.scalars().first()
    if not user:
        return None
        
    # 2. Get Stats (Mocked or Real queries)
    # For MVP we can do simple queries or just return 0s if relationships aren't eager loaded
    
    # Content Count
    from modules.cms.models import Content
    c_res = await db.execute(select(func.count(Content.id)).where(Content.creator_id == user_id))
    content_count = c_res.scalar() or 0
    
    # Active Subscriptions (As Consumer)
    from modules.subscriptions.models import ConsumerSubscription, ConsumerSubscriptionStatus
    s_res = await db.execute(select(func.count(ConsumerSubscription.id)).where(
        (ConsumerSubscription.consumer_id == user_id) & 
        (ConsumerSubscription.status == ConsumerSubscriptionStatus.ACTIVE)
    ))
    subs_count = s_res.scalar() or 0
    
    # Recent Logs
    l_res = await db.execute(
        select(AuditLog)
        .where((AuditLog.user_id == user_id) | (AuditLog.target_id == str(user_id)))
        .order_by(AuditLog.created_at.desc())
        .limit(5)
    )
    logs = l_res.scalars().all()
    
    # [NEW] Get Current Plan ID
    from modules.plans import models as plan_models
    sub_res = await db.execute(
        select(plan_models.CreatorSubscription)
        .where(plan_models.CreatorSubscription.creator_id == user_id)
        .order_by(plan_models.CreatorSubscription.created_at.desc()) # Get latest
    )
    latest_sub = sub_res.scalars().first()
    current_plan_id = latest_sub.plan_id if latest_sub and latest_sub.status == plan_models.SubscriptionStatus.ACTIVE else None
    
    return {
        **user.__dict__,
        "created_content_count": content_count,
        "active_subscriptions_count": subs_count,
        "subscribers_count": 0, # TODO: Query if creator
        "total_spent_usdt": 0.0, # TODO: Sum payments
        "recent_logs": logs,
        "plan_id": current_plan_id
    }
