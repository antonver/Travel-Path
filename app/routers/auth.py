"""
Authentication endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, Any
import logging

from app.core.auth_middleware import get_current_user, get_current_user_optional
from app.services.auth_service import auth_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/auth",
    tags=["authentication"]
)


class UserProfile(BaseModel):
    """User profile response"""
    uid: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    email_verified: bool = False
    photo_url: Optional[str] = None
    provider: Optional[str] = None


@router.get(
    "/me",
    response_model=UserProfile,
    status_code=status.HTTP_200_OK,
    summary="Get current user profile",
    description="Get authenticated user's profile information"
)
async def get_user_profile(user: Dict[str, Any] = Depends(get_current_user)):
    """
    Get current authenticated user's profile
    
    Requires: Bearer token in Authorization header
    """
    try:
        # Get full user record from Firebase
        user_record = auth_service.get_user(user["uid"])
        
        if not user_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return UserProfile(
            uid=user_record.uid,
            email=user_record.email,
            display_name=user_record.display_name,
            email_verified=user_record.email_verified,
            photo_url=user_record.photo_url,
            provider=user_record.provider_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user profile"
        )


@router.post(
    "/verify",
    status_code=status.HTTP_200_OK,
    summary="Verify authentication token",
    description="Verify that a Firebase ID token is valid"
)
async def verify_token(user: Dict[str, Any] = Depends(get_current_user)):
    """
    Verify that the provided token is valid
    
    Requires: Bearer token in Authorization header
    
    Returns:
        Token validity status and user UID
    """
    return {
        "valid": True,
        "uid": user["uid"],
        "email": user.get("email"),
        "message": "Token is valid"
    }


@router.get(
    "/test-protected",
    status_code=status.HTTP_200_OK,
    summary="Test protected endpoint",
    description="Test endpoint that requires authentication"
)
async def test_protected(user: Dict[str, Any] = Depends(get_current_user)):
    """
    Test endpoint to verify authentication is working
    """
    return {
        "message": f"Hello, authenticated user!",
        "uid": user["uid"],
        "email": user.get("email"),
        "token_info": {
            "issued_at": user.get("iat"),
            "expires_at": user.get("exp"),
            "auth_time": user.get("auth_time")
        }
    }


@router.get(
    "/test-optional",
    status_code=status.HTTP_200_OK,
    summary="Test optional authentication",
    description="Test endpoint with optional authentication"
)
async def test_optional(user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)):
    """
    Test endpoint that works with or without authentication
    """
    if user:
        return {
            "message": f"Hello, {user.get('email', 'user')}!",
            "authenticated": True,
            "uid": user["uid"]
        }
    else:
        return {
            "message": "Hello, guest!",
            "authenticated": False
        }

