from fastapi import Depends, HTTPException, status, Query
from fastapi import Depends, HTTPException, status, Query
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.config import settings
from core.db import get_db
from core import security
from modules.auth.models import User
from modules.auth.schemas import TokenData

# We set auto_error=False so we can manually check for token (query or header)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login", auto_error=False)
async def get_current_user(
    token_query: str | None = Query(None, alias="token"),
    token_query_alt: str | None = Query(None, alias="token_query"), # Support both
    token_header: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    token = token_query or token_query_alt or token_header
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    if not token:
        raise credentials_exception

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        token_data = TokenData(id=user_id)
    except JWTError:
        raise credentials_exception
    
    result = await db.execute(select(User).where(User.id == token_data.id))
    user = result.scalars().first()
    
    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

async def get_current_user_optional(
    token: str = Depends(OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login", auto_error=False)),
    db: AsyncSession = Depends(get_db)
) -> User | None:
    if not token:
        return None
        
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
    except JWTError:
        return None
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    return user
