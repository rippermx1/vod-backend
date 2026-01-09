from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_db
from core import deps
from modules.auth import models as auth_models
from modules.moderation import schemas, service

router = APIRouter()

@router.post("/reports", response_model=schemas.ReportRead)
async def submit_report(
    report_in: schemas.ReportCreate,
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    return await service.create_report(db, current_user.id, report_in)

@router.get("/reports", response_model=List[schemas.ReportRead])
async def list_reports(
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    if current_user.role != auth_models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin only")
    return await service.list_pending_reports(db)

@router.post("/reports/{id}/resolve", response_model=schemas.ReportRead)
async def resolve_report(
    id: str,
    resolve_in: schemas.ReportResolve,
    current_user: auth_models.User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    if current_user.role != auth_models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin only")
        
    from uuid import UUID
    return await service.resolve_report(db, UUID(id), current_user.id, resolve_in)
