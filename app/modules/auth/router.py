from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.db import get_db
from core import security
from core import deps
from modules.auth import schemas, models

router = APIRouter()

@router.post("/register", response_model=schemas.UserRead)
async def register_user(
    user_in: schemas.UserCreate,
    db: AsyncSession = Depends(get_db)
) -> Any:
    # Check if user exists
    try:
        result = await db.execute(select(models.User).where(models.User.email == user_in.email))
        existing_user = result.scalars().first()
        if existing_user:
            raise HTTPException(
                status_code=400,
                detail="The user with this email already exists in the system",
            )
        
        user = models.User(
            email=user_in.email,
            hashed_password=security.get_password_hash(user_in.password),
            full_name=user_in.full_name,
            role=user_in.role
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        # Free Trial for Creators
        if user.role == models.UserRole.CREATOR:
            from modules.plans import service as plans_service
            # We don't await this blocking response? No, it's critical.
            # But suppress error so registration doesn't fail if plan system is down
            try:
                await plans_service.assign_free_trial(db, user.id)
            except Exception as e:
                print(f"Failed to assign trial: {e}")

        return user
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise e

@router.post("/reset-password")
async def reset_password_mock(
    email: str, # Form or Body
):
    """
    Mock password reset.
    """
    # Just return success
    return {"message": "If this email exists, a reset link has been sent."}

@router.post("/login", response_model=schemas.Token)
async def login_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
) -> Any:
    result = await db.execute(select(models.User).where(models.User.email == form_data.username))
    user = result.scalars().first()
    
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
        
    # Audit Log
    from modules.admin import service as admin_service
    await admin_service.create_audit_log(
        db, 
        action="auth.login", 
        user_id=user.id,
        ip_address=None # Need Request object to get IP, skipping for MVP/schema limit
    )

    access_token = security.create_access_token(subject=user.id)
    return {
        "access_token": access_token, 
        "token_type": "bearer"
    }

@router.get("/me", response_model=schemas.UserRead)
async def read_users_me(
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    return current_user

@router.put("/me", response_model=schemas.UserRead)
async def update_user_me(
    user_in: schemas.UserUpdate,
    current_user: models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    # Update allowed fields
    if user_in.full_name is not None:
        current_user.full_name = user_in.full_name
    if user_in.bio is not None:
        current_user.bio = user_in.bio
    if user_in.avatar_url is not None:
        current_user.avatar_url = user_in.avatar_url
    if user_in.monthly_price is not None:
        current_user.monthly_price = user_in.monthly_price
    if user_in.subscription_enabled is not None:
        current_user.subscription_enabled = user_in.subscription_enabled
        
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    return current_user
