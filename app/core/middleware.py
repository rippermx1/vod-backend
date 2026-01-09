import time
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from collections import defaultdict

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limit_per_minute: int = 60):
        super().__init__(app)
        self.limit = limit_per_minute
        # Simple in-memory store: IP -> [timestamp1, timestamp2, ...]
        # For production use Redis.
        self.requests = defaultdict(list)
        
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host
        now = time.time()
        
        # Clean up old requests (older than 60s)
        self.requests[client_ip] = [t for t in self.requests[client_ip] if now - t < 60]
        
        # Specific Limits (e.g. Login)
        path = request.url.path
        limit = self.limit
        
        if "/auth/login" in path and request.method == "POST":
            limit = 30 # Strict limit for login (relaxed for dev)
        
        if len(self.requests[client_ip]) >= limit:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please try again later."}
            )
            
        self.requests[client_ip].append(now)
        
        response = await call_next(request)
        return response
