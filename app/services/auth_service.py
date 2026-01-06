"""
Firebase Authentication Service
Handles user authentication and token verification
"""

import firebase_admin
from firebase_admin import auth
from firebase_admin.exceptions import FirebaseError
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class AuthService:
    """Service for handling Firebase Authentication"""
    
    def __init__(self):
        """Initialize Firebase Auth (already initialized in firebase_service)"""
        self.auth = auth
        logger.info("Firebase Auth service initialized")
    
    def verify_token(self, id_token: str) -> Optional[Dict[str, Any]]:
        """
        Verify Firebase ID token and return decoded token
        
        Args:
            id_token: Firebase ID token from client
            
        Returns:
            Decoded token dict with user info or None if invalid
        """
        try:
            decoded_token = self.auth.verify_id_token(id_token)
            logger.info(f"Token verified for user: {decoded_token.get('uid')}")
            return decoded_token
        except auth.InvalidIdTokenError:
            logger.warning("Invalid ID token")
            return None
        except auth.ExpiredIdTokenError:
            logger.warning("Expired ID token")
            return None
        except FirebaseError as e:
            logger.error(f"Firebase error verifying token: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error verifying token: {e}")
            return None
    
    def get_user(self, uid: str) -> Optional[auth.UserRecord]:
        """
        Get user record by UID
        
        Args:
            uid: Firebase user UID
            
        Returns:
            UserRecord or None if not found
        """
        try:
            user = self.auth.get_user(uid)
            logger.info(f"Retrieved user: {uid}")
            return user
        except auth.UserNotFoundError:
            logger.warning(f"User not found: {uid}")
            return None
        except FirebaseError as e:
            logger.error(f"Firebase error getting user: {e}")
            return None
    
    def create_user(self, email: str, password: str, display_name: Optional[str] = None) -> Optional[auth.UserRecord]:
        """
        Create a new user (optional, usually done on client side)
        
        Args:
            email: User email
            password: User password
            display_name: Optional display name
            
        Returns:
            Created UserRecord or None if error
        """
        try:
            user = self.auth.create_user(
                email=email,
                password=password,
                display_name=display_name,
                email_verified=False
            )
            logger.info(f"Created user: {user.uid}")
            return user
        except FirebaseError as e:
            logger.error(f"Firebase error creating user: {e}")
            return None
    
    def delete_user(self, uid: str) -> bool:
        """
        Delete a user
        
        Args:
            uid: Firebase user UID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.auth.delete_user(uid)
            logger.info(f"Deleted user: {uid}")
            return True
        except FirebaseError as e:
            logger.error(f"Firebase error deleting user: {e}")
            return False
    
    def set_custom_claims(self, uid: str, claims: Dict[str, Any]) -> bool:
        """
        Set custom claims for a user (e.g., admin role)
        
        Args:
            uid: Firebase user UID
            claims: Custom claims dict
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.auth.set_custom_user_claims(uid, claims)
            logger.info(f"Set custom claims for user {uid}: {claims}")
            return True
        except FirebaseError as e:
            logger.error(f"Firebase error setting custom claims: {e}")
            return False


# Global auth service instance
auth_service = AuthService()

