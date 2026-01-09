from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from modules.moderation import models, schemas
from modules.cms import models as cms_models
from modules.admin import service as admin_service
from modules.notifications import service as notification_service
from uuid import UUID
from fastapi import HTTPException

async def create_report(
    db: AsyncSession,
    reporter_id: UUID,
    report_in: schemas.ReportCreate
) -> models.Report:
    report = models.Report(
        reporter_id=reporter_id,
        content_id=report_in.content_id,
        reason=report_in.reason,
        description=report_in.description,
        status=models.ReportStatus.PENDING
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return report

async def list_pending_reports(db: AsyncSession):
    result = await db.execute(select(models.Report).where(models.Report.status == models.ReportStatus.PENDING))
    return result.scalars().all()

async def resolve_report(
    db: AsyncSession,
    report_id: UUID,
    admin_id: UUID,
    resolve_in: schemas.ReportResolve
):
    report = await db.get(models.Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
        
    content = await db.get(cms_models.Content, report.content_id)
    if not content:
         raise HTTPException(status_code=404, detail="Content not found")

    if resolve_in.action == "block":
        report.status = models.ReportStatus.RESOLVED
        content.status = cms_models.ContentStatus.BLOCKED
        
        # Notify Creator
        await notification_service.create_notification(
            db,
            user_id=content.creator_id,
            title="Content Removed",
            message=f"Your content '{content.title}' has been removed due to a violation: {resolve_in.notes}",
            resource_type="content",
            resource_id=str(content.id)
        )
        
    elif resolve_in.action == "dismiss":
         report.status = models.ReportStatus.DISMISSED
    else:
        raise HTTPException(status_code=400, detail="Invalid action")
        
    report.reviewed_by = admin_id
    report.admin_notes = resolve_in.notes
    
    # Audit
    await admin_service.create_audit_log(
        db,
        action=f"moderation.{resolve_in.action}",
        user_id=admin_id,
        target_type="content",
        target_id=str(content.id),
        metadata={"report_id": str(report.id), "reason": resolve_in.notes}
    )

    await db.commit()
    await db.refresh(report)
    return report
