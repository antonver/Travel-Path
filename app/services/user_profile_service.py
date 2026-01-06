"""
Service for managing user profiles
"""
import firebase_admin
from firebase_admin import firestore
from fastapi import HTTPException
from app.models.schemas import UserProfile, UserProfileUpdate
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class UserProfileService:
    """Service for handling user profile operations"""
    
    def __init__(self):
        """Initialize Firestore client"""
        try:
            self.db = firestore.client()
            self.profiles_collection = "user_profiles"
            logger.info("UserProfileService initialized")
        except Exception as e:
            logger.error(f"Failed to initialize UserProfileService: {str(e)}")
            raise
    
    def create_profile(self, profile: UserProfile) -> str:
        """
        Создать профиль пользователя
        
        Args:
            profile: UserProfile объект
            
        Returns:
            user_id
        """
        try:
            profile_dict = profile.model_dump()
            
            # Использовать user_id как document ID
            profile_ref = self.db.collection(self.profiles_collection).document(
                profile.user_id
            )
            
            # Добавить server timestamp
            profile_dict["created_at"] = firestore.SERVER_TIMESTAMP
            profile_dict["updated_at"] = firestore.SERVER_TIMESTAMP
            
            profile_ref.set(profile_dict)
            
            logger.info(f"Created profile for user: {profile.user_id}")
            return profile.user_id
            
        except Exception as e:
            logger.error(f"Error creating profile: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create profile: {str(e)}"
            )
    
    def get_profile(self, user_id: str) -> Optional[UserProfile]:
        """
        Получить профиль пользователя
        
        Args:
            user_id: Firebase User ID
            
        Returns:
            UserProfile или None
        """
        try:
            profile_ref = self.db.collection(self.profiles_collection).document(user_id)
            profile_doc = profile_ref.get()
            
            if profile_doc.exists:
                profile_data = profile_doc.to_dict()
                return UserProfile(**profile_data)
            
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving profile: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to retrieve profile: {str(e)}"
            )
    
    def update_profile(
        self,
        user_id: str,
        profile_update: UserProfileUpdate
    ) -> UserProfile:
        """
        Обновить профиль пользователя
        
        Args:
            user_id: Firebase User ID
            profile_update: Данные для обновления
            
        Returns:
            Обновленный UserProfile
        """
        try:
            profile_ref = self.db.collection(self.profiles_collection).document(user_id)
            
            # Проверить существование профиля
            profile_doc = profile_ref.get()
            if not profile_doc.exists:
                raise HTTPException(
                    status_code=404,
                    detail=f"Profile for user {user_id} not found"
                )
            
            # Подготовить данные для обновления (только не-None поля)
            update_data = {
                k: v for k, v in profile_update.model_dump().items()
                if v is not None
            }
            
            if update_data:
                update_data["updated_at"] = firestore.SERVER_TIMESTAMP
                profile_ref.update(update_data)
                logger.info(f"Updated profile for user: {user_id}")
            
            # Получить обновленный профиль
            updated_doc = profile_ref.get()
            return UserProfile(**updated_doc.to_dict())
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating profile: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to update profile: {str(e)}"
            )
    
    def delete_profile(self, user_id: str) -> None:
        """
        Удалить профиль пользователя
        
        Args:
            user_id: Firebase User ID
        """
        try:
            profile_ref = self.db.collection(self.profiles_collection).document(user_id)
            
            # Проверить существование
            if not profile_ref.get().exists:
                raise HTTPException(
                    status_code=404,
                    detail=f"Profile for user {user_id} not found"
                )
            
            profile_ref.delete()
            logger.info(f"Deleted profile for user: {user_id}")
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error deleting profile: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to delete profile: {str(e)}"
            )
    
    def get_or_create_profile(
        self,
        user_id: str,
        email: Optional[str] = None,
        display_name: Optional[str] = None
    ) -> UserProfile:
        """
        Получить профиль или создать, если не существует
        
        Args:
            user_id: Firebase User ID
            email: User email (для создания)
            display_name: User display name (для создания)
            
        Returns:
            UserProfile
        """
        # Попытаться получить существующий профиль
        profile = self.get_profile(user_id)
        
        if profile:
            return profile
        
        # Создать новый профиль с дефолтными настройками
        new_profile = UserProfile(
            user_id=user_id,
            email=email,
            display_name=display_name
        )
        
        self.create_profile(new_profile)
        logger.info(f"Auto-created profile for user: {user_id}")
        
        return new_profile


# Global instance
user_profile_service = UserProfileService()






