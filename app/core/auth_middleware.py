"""
Authentication middleware and dependencies for FastAPI
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any
import logging

from app.services.auth_service import auth_service

logger = logging.getLogger(__name__)

# HTTP Bearer token scheme
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Dict[str, Any]:
    """
    Dependency to get current authenticated user from Firebase token
    
    Usage:
        @app.get("/protected")
        async def protected_route(user: dict = Depends(get_current_user)):
            return {"user_id": user["uid"]}
    
    Returns:
        Decoded token with user info
        
    Raises:
        HTTPException 401 if token is missing or invalid
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    decoded_token = auth_service.verify_token(token)
    
    if not decoded_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return decoded_token


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[Dict[str, Any]]:
    """
    Optional authentication - returns user if authenticated, None otherwise
    
    Usage:
        @app.get("/public-or-private")
        async def flexible_route(user: Optional[dict] = Depends(get_current_user_optional)):
            if user:
                return {"message": f"Hello, {user['uid']}"}
            return {"message": "Hello, guest"}
    """
    if not credentials:
        return None
    
    token = credentials.credentials
    decoded_token = auth_service.verify_token(token)
    
    return decoded_token


def require_role(required_role: str):
    """
    Dependency factory to require specific role from custom claims
    
    Usage:
        @app.get("/admin")
        async def admin_route(user: dict = Depends(require_role("admin"))):
            return {"message": "Admin access granted"}
    """
    async def role_checker(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        user_role = user.get("role")
        if user_role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required role: {required_role}"
            )
        return user
    
    return role_checker

