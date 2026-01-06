"""
API endpoints for user profile management
"""
from fastapi import APIRouter, Depends, HTTPException
from app.models.schemas import UserProfile, UserProfileUpdate
from app.services.user_profile_service import user_profile_service
from app.core.auth_middleware import get_current_user
from typing import Dict
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profiles", tags=["User Profiles"])


@router.post("/", response_model=UserProfile)
async def create_profile(
    profile: UserProfile,
    current_user: Dict = Depends(get_current_user)
):
    """
    Создать профиль пользователя
    
    Требует авторизации.
    """
    # Убедиться, что user_id совпадает с текущим пользователем
    if profile.user_id != current_user["uid"]:
        raise HTTPException(
            status_code=403,
            detail="You can only create your own profile"
        )
    
    # Проверить, не существует ли уже профиль
    existing_profile = user_profile_service.get_profile(profile.user_id)
    if existing_profile:
        raise HTTPException(
            status_code=409,
            detail="Profile already exists. Use PUT to update."
        )
    
    user_profile_service.create_profile(profile)
    return profile


@router.get("/me", response_model=UserProfile)
async def get_my_profile(current_user: Dict = Depends(get_current_user)):
    """
    Получить профиль текущего пользователя
    
    Если профиль не существует, создается автоматически.
    """
    user_id = current_user["uid"]
    email = current_user.get("email")
    display_name = current_user.get("name")
    
    # Получить или создать профиль
    profile = user_profile_service.get_or_create_profile(
        user_id=user_id,
        email=email,
        display_name=display_name
    )
    
    return profile


@router.get("/{user_id}", response_model=UserProfile)
async def get_profile(
    user_id: str,
    current_user: Dict = Depends(get_current_user)
):
    """
    Получить профиль пользователя по ID
    
    Пользователи могут просматривать только свой профиль.
    """
    # Проверить права доступа
    if user_id != current_user["uid"]:
        raise HTTPException(
            status_code=403,
            detail="You can only view your own profile"
        )
    
    profile = user_profile_service.get_profile(user_id)
    
    if not profile:
        raise HTTPException(
            status_code=404,
            detail=f"Profile for user {user_id} not found"
        )
    
    return profile


@router.put("/me", response_model=UserProfile)
async def update_my_profile(
    profile_update: UserProfileUpdate,
    current_user: Dict = Depends(get_current_user)
):
    """
    Обновить профиль текущего пользователя
    """
    user_id = current_user["uid"]
    
    # Получить или создать профиль, если не существует
    existing_profile = user_profile_service.get_profile(user_id)
    if not existing_profile:
        # Создать базовый профиль
        base_profile = UserProfile(
            user_id=user_id,
            email=current_user.get("email"),
            display_name=current_user.get("name")
        )
        user_profile_service.create_profile(base_profile)
    
    # Обновить профиль
    updated_profile = user_profile_service.update_profile(user_id, profile_update)
    
    return updated_profile


@router.delete("/me")
async def delete_my_profile(current_user: Dict = Depends(get_current_user)):
    """
    Удалить профиль текущего пользователя
    """
    user_id = current_user["uid"]
    user_profile_service.delete_profile(user_id)
    
    return {"message": "Profile deleted successfully"}






