
import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

from sqlalchemy.future import select
from core.db import SessionLocal
from modules.auth.models import User, UserRole, KYCStatus
from core.security import get_password_hash

async def seed_admin():
    async with SessionLocal() as session:
        # Check if admin exists
        result = await session.execute(select(User).where(User.email == "admin@vod.com"))
        existing_admin = result.scalars().first()

        if existing_admin:
            print("Admin user already exists.")
            return

        print("Creating admin user...")
        admin_user = User(
            email="admin@vod.com",
            hashed_password=get_password_hash("admin123"),
            full_name="Super Admin",
            role=UserRole.ADMIN,
            is_active=True,
            kyc_status=KYCStatus.VERIFIED, # Auto verify admin
            subscription_enabled=True
        )
        session.add(admin_user)
        await session.commit()
        print("Admin created successfully!")
        print("Email: admin@vod.com")
        print("Password: admin123")

if __name__ == "__main__":
    asyncio.run(seed_admin())
