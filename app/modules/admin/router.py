from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_db
from core import deps
from modules.auth import models as auth_models
from modules.auth import schemas as auth_schemas # Added for UserRead response model
from modules.admin import schemas, service
from typing import Any, Dict

router = APIRouter()

@router.get("/stats", response_model=schemas.AdminStats)
async def get_admin_stats(
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Get system-wide statistics for Admin Dashboard.
    """
    if current_user.role != auth_models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin only")
        
    return await service.get_stats(db)

@router.get("/users", response_model=list[auth_schemas.UserRead])
async def get_all_users(
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Get all users (Admin only).
    """
    if current_user.role != auth_models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin only")
        
    return await service.get_all_users(db)

@router.patch("/users/{user_id}/status", response_model=auth_schemas.UserRead)
async def update_user_status(
    user_id: str,
    is_active: bool, # Query param for simplicity
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Ban/Unban a user.
    """
    if current_user.role != auth_models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin only")
    
    import uuid
    try:
        u_id = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID")

    user = await service.update_user_status(db, u_id, is_active, current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    return user

from modules.plans import schemas as plan_schemas

@router.get("/plans", response_model=list[plan_schemas.PlanRead])
async def get_admin_plans(
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    if current_user.role != auth_models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin only")
    return await service.get_all_plans(db)

@router.post("/plans", response_model=plan_schemas.PlanRead)
async def create_plan(
    plan_in: plan_schemas.PlanCreate,
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    if current_user.role != auth_models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin only")
    return await service.create_plan(db, plan_in)

@router.put("/plans/{plan_id}", response_model=plan_schemas.PlanRead)
async def update_plan(
    plan_id: str,
    plan_in: plan_schemas.PlanCreate, # Re-using create schema for full update
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    if current_user.role != auth_models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin only")
    import uuid
    try:
        p_uid = uuid.UUID(plan_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid UUID")
        
    plan = await service.update_plan(db, p_uid, plan_in)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan

@router.get("/audit-logs", response_model=list[schemas.AuditLogRead])
async def get_audit_logs(
    limit: int = 50,
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    if current_user.role != auth_models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin only")
    return await service.get_audit_logs(db, limit)

@router.get("/users/{user_id}", response_model=schemas.UserDetail)
async def get_user_detail(
    user_id: str,
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    if current_user.role != auth_models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin only")
        
    import uuid
    try:
        u_uid = uuid.UUID(user_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid UUID")
        
    user = await service.get_user_details(db, u_uid)
    if not user:
         raise HTTPException(status_code=404, detail="User not found")
    return user

@router.put("/users/{user_id}", response_model=auth_schemas.UserRead)
async def update_user(
    user_id: str,
    user_in: schemas.UserUpdateAdmin,
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    if current_user.role != auth_models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin only")
        
    import uuid
    try:
        u_uid = uuid.UUID(user_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid UUID")
        
    user = await service.update_user(db, u_uid, user_in, current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.put("/users/{user_id}/plan", response_model=auth_schemas.UserRead)
async def update_user_plan_endpoint(
    user_id: str,
    payload: Dict[str, Any], # Expect {"plan_id": "uuid"}
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Forcefully update a user's plan (Admin only).
    """
    if current_user.role != auth_models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin only")
        
    import uuid
    try:
        u_uid = uuid.UUID(user_id)
        p_uid = uuid.UUID(payload.get("plan_id")) if payload.get("plan_id") else None
    except:
        raise HTTPException(status_code=400, detail="Invalid UUID")
        
    user = await service.update_user_plan(db, u_uid, p_uid, current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.get("/settings", response_model=list[schemas.SystemSettingRead])
async def get_settings(
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    if current_user.role != auth_models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin only")
    return await service.get_system_settings(db)

@router.put("/settings/{key}", response_model=schemas.SystemSettingRead)
async def update_setting(
    key: str,
    setting_in: schemas.SystemSettingUpdate,
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    if current_user.role != auth_models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin only")
        
    updated = await service.update_system_setting(db, key, setting_in.value, setting_in.description)
    
    # Audit
    await service.create_audit_log(
        db,
        action="admin.setting.update",
        user_id=current_user.id,
        target_type="setting",
        target_id=key,
        metadata={"value": setting_in.value}
    )
    
    return updated
