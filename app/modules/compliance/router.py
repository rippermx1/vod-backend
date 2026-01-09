from typing import Any, List
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from core.db import get_db
from core import deps
from modules.auth import models as auth_models
from modules.compliance import schemas, service

router = APIRouter()

@router.post("/kyc", response_model=schemas.KYCRead)
async def submit_kyc_docs(
    document: UploadFile = File(...),
    selfie: UploadFile = File(...),
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    if current_user.role != auth_models.UserRole.CREATOR:
        raise HTTPException(status_code=403, detail="Only creators need KYC")
        
    return await service.submit_kyc(db, current_user, document, selfie)

@router.get("/kyc/pending", response_model=List[schemas.KYCRead])
async def list_pending(
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    if current_user.role != auth_models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin only")
        
    return await service.list_pending_kyc(db)

@router.post("/kyc/{id}/review", response_model=schemas.KYCRead)
async def review_submission(
    id: UUID,
    review_in: schemas.KYCReview,
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    if current_user.role != auth_models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin only")
        
    return await service.review_kyc(db, id, current_user.id, review_in.action, review_in.notes)
