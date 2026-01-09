from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import UploadFile, HTTPException
from modules.compliance import models, schemas
from modules.auth import models as auth_models
from modules.compliance import models, schemas
from modules.auth import models as auth_models
from uuid import UUID
from uuid import UUID

async def submit_kyc(
    db: AsyncSession,
    user: auth_models.User,
    document: UploadFile,
    selfie: UploadFile
) -> models.KYCSubmission:
    # 1. Check existing
    result = await db.execute(select(models.KYCSubmission).where(models.KYCSubmission.user_id == user.id))
    existing = result.scalars().first()
    if existing and existing.status == models.KYCStatus.VERIFIED:
        raise HTTPException(status_code=400, detail="Already verified")
    
    # 2. Upload Files to B2 (kyc folder)
    from modules.delivery.b2_service import get_b2_service
    b2 = get_b2_service()
    
    # Read files (Standard KYC images are small enough for memory)
    doc_bytes = await document.read()
    selfie_bytes = await selfie.read()
    
    # Generate Paths
    # creators/{user_id}/kyc/document_{uuid}.extension
    doc_ext = document.filename.split('.')[-1] if '.' in document.filename else "jpg"
    selfie_ext = selfie.filename.split('.')[-1] if '.' in selfie.filename else "jpg"
    
    # Use UUID for randomness
    from uuid import uuid4
    doc_key = f"creators/{user.id}/kyc/doc_{uuid4()}.{doc_ext}"
    selfie_key = f"creators/{user.id}/kyc/selfie_{uuid4()}.{selfie_ext}"
    
    # Upload
    # If using Mock, this returns local path. If B2, returns key (which we use for get_download_url).
    # Since we want to store the "key" (file_path) in DB for generating signed URLs later.
    b2.upload_file(doc_bytes, doc_key)
    b2.upload_file(selfie_bytes, selfie_key)
    
    # 3. Create or Update Submission
    if existing:
        existing.document_url = doc_key # Storing KEY now
        existing.selfie_url = selfie_key
        existing.status = models.KYCStatus.PENDING
        existing.admin_notes = None
        db.add(existing)
        submission = existing
    else:
        submission = models.KYCSubmission(
            user_id=user.id,
            document_url=doc_key,
            selfie_url=selfie_key,
            status=models.KYCStatus.PENDING
        )
        db.add(submission)
    
    # Update User Status
    if hasattr(user, "kyc_status"):
         user.kyc_status = auth_models.KYCStatus.PENDING
         db.add(user)

    await db.commit()
    await db.refresh(submission)
    return submission

async def review_kyc(
    db: AsyncSession,
    submission_id: UUID,
    admin_id: UUID,
    action: str,
    notes: str
) -> models.KYCSubmission:
    submission = await db.get(models.KYCSubmission, submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
        
    if action == "approve":
        submission.status = models.KYCStatus.VERIFIED
        # Update User
        user = await db.get(auth_models.User, submission.user_id)
        if user:
            user.kyc_status = auth_models.KYCStatus.VERIFIED
            db.add(user)
    elif action == "reject":
        submission.status = models.KYCStatus.REJECTED
        user = await db.get(auth_models.User, submission.user_id)
        if user:
            user.kyc_status = auth_models.KYCStatus.REJECTED
            db.add(user)
    else:
        raise HTTPException(status_code=400, detail="Invalid action")
        
    submission.reviewed_by = admin_id
    submission.admin_notes = notes
    
    # Audit Log
    from modules.admin import service as admin_service
    await admin_service.create_audit_log(
        db,
        action=f"kyc.review.{action}",
        user_id=admin_id,
        target_type="kyc_submission",
        target_id=str(submission.id),
        metadata={"user_being_reviewed": str(submission.user_id), "notes": notes}
    )
    
    # Notification
    from modules.notifications import service as notification_service
    await notification_service.create_notification(
        db,
        user_id=submission.user_id,
        title=f"KYC {action.capitalize()}ed",
        message=f"Your KYC submission has been {action}ed. Notes: {notes}",
        resource_type="kyc_submission",
        resource_id=str(submission.id)
    )

    await db.commit()
    await db.refresh(submission)
    return submission

async def list_pending_kyc(db: AsyncSession):
    stmt = (
        select(models.KYCSubmission, auth_models.User.email)
        .join(auth_models.User, models.KYCSubmission.user_id == auth_models.User.id)
        .where(models.KYCSubmission.status == models.KYCStatus.PENDING)
    )
    result = await db.execute(stmt)
    rows = result.all()
    
    # Map to schema compatible format
    response = []
    for kyc, email in rows:
        # Pydantic v2 from_attributes might not handle the extra field on the model object itself easily if we just pass the model.
        # So we construct a dict or object. 
        # Easier to copy properties.
        kyc_dict = {
            "id": kyc.id,
            "user_id": kyc.user_id,
            "user_email": email,
            "document_url": kyc.document_url,
            "selfie_url": kyc.selfie_url,
            "status": kyc.status,
            "admin_notes": kyc.admin_notes,
            "created_at": kyc.created_at
        }
        response.append(kyc_dict)
    return response
