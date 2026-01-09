from fastapi import FastAPI
from core.config import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

from modules.worker.runner import worker

@app.on_event("startup")
async def startup_event():
    await worker.start()

@app.on_event("shutdown")
async def shutdown_event():
    await worker.stop()

@app.get("/")
def root():
    return {"message": "Welcome to VOD SaaS API", "docs": "/docs"}

from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from modules.auth.router import router as auth_router
from modules.plans.router import router as plans_router
from modules.cms.router import router as cms_router
from modules.subscriptions.router import router as subscriptions_router
from modules.delivery.router import router as delivery_router
from modules.auth.explore_router import router as explore_router
from modules.compliance.router import router as compliance_router
from modules.sales.router import router as sales_router
from modules.admin.router import router as admin_router

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from core.middleware import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware, limit_per_minute=100) # Global limit

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(auth_router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(explore_router, prefix=f"{settings.API_V1_STR}/creators", tags=["explore"])
app.include_router(plans_router, prefix=f"{settings.API_V1_STR}/plans", tags=["plans"])
app.include_router(cms_router, prefix=f"{settings.API_V1_STR}/cms", tags=["cms"])
app.include_router(subscriptions_router, prefix=f"{settings.API_V1_STR}/subscriptions", tags=["subscriptions"])
app.include_router(delivery_router, prefix=f"{settings.API_V1_STR}/delivery", tags=["delivery"])
app.include_router(compliance_router, prefix=f"{settings.API_V1_STR}/compliance", tags=["compliance"])
app.include_router(admin_router, prefix=f"{settings.API_V1_STR}/admin", tags=["admin"])
app.include_router(sales_router, prefix=f"{settings.API_V1_STR}/sales", tags=["sales"])
app.include_router(delivery_router, prefix=f"{settings.API_V1_STR}/playback", tags=["playback"])

from modules.notifications.router import router as notifications_router
app.include_router(notifications_router, prefix=f"{settings.API_V1_STR}/notifications", tags=["notifications"])

from modules.moderation.router import router as moderation_router
app.include_router(moderation_router, prefix=f"{settings.API_V1_STR}/moderation", tags=["moderation"])

# Force Reload Touch 2
# Debugging B2 Paths

