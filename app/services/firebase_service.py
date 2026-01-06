"""
Firebase Service for Firestore database operations
"""
import firebase_admin
from firebase_admin import credentials, firestore
from fastapi import HTTPException
from app.core.config import settings
from app.models.schemas import PhotoMetadata, TripData
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)


class FirebaseService:
    """Service for handling Firebase/Firestore operations"""
    
    def __init__(self):
        """Initialize Firebase Admin SDK"""
        try:
            logger.info("🔧 Initializing Firebase Service...")
            logger.info(f"📁 Credentials path: {settings.FIREBASE_CREDENTIALS_PATH}")
            
            # Get database name from settings or use default
            database_name = getattr(settings, 'FIRESTORE_DATABASE', 'default')
            logger.info(f"🗄️ Using Firestore database: {database_name}")
            
            # Initialize Firebase only if not already initialized
            if not firebase_admin._apps:
                logger.info("🔑 Loading Firebase credentials...")
                cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
                self._app = firebase_admin.initialize_app(cred)
                logger.info("✅ Firebase Admin SDK initialized successfully")
            else:
                logger.info("♻️ Firebase Admin SDK already initialized")
                self._app = firebase_admin.get_app()
            
            logger.info("🔗 Creating Firestore client...")
            # Try to use named database, fallback to default
            try:
                from google.cloud.firestore_v1 import Client
                from google.auth.credentials import Credentials
                import google.auth
                
                # Get credentials from Firebase app
                credentials_obj = self._app.credential.get_credential()
                project_id = self._app.project_id
                
                logger.info(f"📋 Project ID: {project_id}")
                
                # Create Firestore client with named database
                self.db = Client(
                    project=project_id,
                    credentials=credentials_obj,
                    database=database_name
                )
                logger.info(f"✅ Firestore client initialized (database: {database_name})")
            except Exception as named_db_error:
                logger.warning(f"⚠️ Could not use named database: {named_db_error}")
                logger.info("🔄 Falling back to default Firestore client...")
                self.db = firestore.client()
                logger.info(f"✅ Firestore client initialized (default database)")
            
            self.trips_collection = "trips"
            logger.info(f"📚 Default collection: {self.trips_collection}")
            
            # Test connection
            try:
                logger.info("🧪 Testing Firestore connection...")
                collections = list(self.db.collections())
                logger.info(f"✅ Firestore connection OK. Available collections: {[c.id for c in collections]}")
            except Exception as test_error:
                logger.warning(f"⚠️ Could not list collections (may be empty): {test_error}")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Firebase: {str(e)}")
            logger.exception("Full traceback:")
            raise
    
    def test_connection(self) -> bool:
        """
        Test Firestore connection by listing collections
        
        Returns:
            True if connection is successful
        """
        try:
            # Try to list collections - this will fail if connection is broken
            list(self.db.collections())
            return True
        except Exception as e:
            logger.error(f"Firestore connection test failed: {e}")
            raise
    
    def add_photo_to_trip(
        self,
        trip_id: str,
        photo_data: PhotoMetadata
    ) -> None:
        """
        Add a photo to an existing trip using arrayUnion (Legacy method)
        
        Args:
            trip_id: Unique trip identifier
            photo_data: Photo metadata to add
        """
        try:
            trip_ref = self.db.collection(self.trips_collection).document(trip_id)
            
            # Check if trip exists
            trip_doc = trip_ref.get()
            if not trip_doc.exists:
                raise HTTPException(
                    status_code=404,
                    detail=f"Trip with ID {trip_id} not found"
                )
            
            # Update trip with new photo using arrayUnion
            trip_ref.update({
                "photos": firestore.ArrayUnion([photo_data.model_dump()]),
                "updated_at": firestore.SERVER_TIMESTAMP
            })
            
            logger.info(f"Added photo to trip {trip_id}")
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error adding photo to trip: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to add photo to trip: {str(e)}"
            )
    
    def add_photo_to_place(
        self,
        trip_id: str,
        place_id: str,
        photo_data: PhotoMetadata
    ) -> None:
        """
        Add a photo to a specific place within a trip
        
        Args:
            trip_id: Trip identifier
            place_id: Google Place ID
            photo_data: Photo metadata to add
        """
        try:
            trip_ref = self.db.collection(self.trips_collection).document(trip_id)
            trip_doc = trip_ref.get()
            
            if not trip_doc.exists:
                raise HTTPException(
                    status_code=404,
                    detail=f"Trip with ID {trip_id} not found"
                )
            
            trip_data = trip_doc.to_dict()
            stops = trip_data.get("stops", [])
            
            # Find the place in stops
            place_found = False
            for stop in stops:
                if stop.get("google_place_id") == place_id:
                    # Add photo to this place's user_photos array
                    if "user_photos" not in stop:
                        stop["user_photos"] = []
                    stop["user_photos"].append(photo_data.model_dump())
                    place_found = True
                    break
            
            if not place_found:
                raise HTTPException(
                    status_code=404,
                    detail=f"Place {place_id} not found in trip {trip_id}"
                )
            
            # Update the entire stops array
            trip_ref.update({
                "stops": stops,
                "updated_at": firestore.SERVER_TIMESTAMP
            })
            
            logger.info(f"Added photo to place {place_id} in trip {trip_id}")
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error adding photo to place: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to add photo to place: {str(e)}"
            )
    
    def add_photo_to_trip_smart(
        self,
        trip_id: str,
        photo_data: PhotoMetadata
    ) -> Optional[str]:
        """
        Intelligently add photo to trip - find nearest place or add to general photos
        
        Args:
            trip_id: Trip identifier
            photo_data: Photo metadata with coordinates
            
        Returns:
            Place ID if photo was associated with a place, None otherwise
        """
        try:
            trip_ref = self.db.collection(self.trips_collection).document(trip_id)
            trip_doc = trip_ref.get()
            
            if not trip_doc.exists:
                raise HTTPException(
                    status_code=404,
                    detail=f"Trip with ID {trip_id} not found"
                )
            
            trip_data = trip_doc.to_dict()
            stops = trip_data.get("stops", [])
            
            # Find nearest place within 100m
            nearest_place = None
            min_distance = 100  # meters threshold
            
            for stop in stops:
                location = stop.get("location", {})
                stop_lat = location.get("lat")
                stop_lng = location.get("lng")
                
                if stop_lat and stop_lng:
                    distance = self._calculate_distance(
                        photo_data.lat, photo_data.lon,
                        stop_lat, stop_lng
                    )
                    
                    if distance < min_distance:
                        min_distance = distance
                        nearest_place = stop
            
            # If found nearby place, attach photo to it
            if nearest_place:
                place_id = nearest_place.get("google_place_id")
                if "user_photos" not in nearest_place:
                    nearest_place["user_photos"] = []
                nearest_place["user_photos"].append(photo_data.model_dump())
                
                # Update stops
                trip_ref.update({
                    "stops": stops,
                    "updated_at": firestore.SERVER_TIMESTAMP
                })
                
                logger.info(
                    f"Photo auto-associated with place {place_id} "
                    f"(distance: {min_distance:.1f}m)"
                )
                return place_id
            
            # No nearby place found, add to general trip photos
            else:
                trip_ref.update({
                    "photos": firestore.ArrayUnion([photo_data.model_dump()]),
                    "updated_at": firestore.SERVER_TIMESTAMP
                })
                logger.info("Photo added to general trip photos (no nearby place)")
                return None
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error adding photo smartly: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to add photo: {str(e)}"
            )
    
    def _calculate_distance(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float
    ) -> float:
        """
        Calculate distance between two coordinates using Haversine formula
        
        Returns:
            Distance in meters
        """
        from math import radians, sin, cos, sqrt, atan2
        
        R = 6371000  # Earth radius in meters
        
        lat1_rad = radians(lat1)
        lat2_rad = radians(lat2)
        delta_lat = radians(lat2 - lat1)
        delta_lon = radians(lon2 - lon1)
        
        a = sin(delta_lat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        
        return R * c
    
    def save_trip(self, trip_data: TripData) -> str:
        """
        Create a new trip document in Firestore
        
        Args:
            trip_data: Trip data to save
            
        Returns:
            str: Trip ID
        """
        try:
            trip_dict = trip_data.model_dump()
            
            # Use trip_id as document ID or generate new one
            if trip_data.trip_id:
                trip_ref = self.db.collection(self.trips_collection).document(
                    trip_data.trip_id
                )
            else:
                trip_ref = self.db.collection(self.trips_collection).document()
                trip_dict["trip_id"] = trip_ref.id
            
            # Add server timestamp
            trip_dict["created_at"] = firestore.SERVER_TIMESTAMP
            trip_dict["updated_at"] = firestore.SERVER_TIMESTAMP
            
            trip_ref.set(trip_dict)
            
            trip_id = trip_dict["trip_id"]
            logger.info(f"Created new trip: {trip_id}")
            return trip_id
            
        except Exception as e:
            logger.error(f"Error saving trip: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to save trip: {str(e)}"
            )
    
    def get_trip(self, trip_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a trip by ID
        
        Args:
            trip_id: Trip identifier
            
        Returns:
            Dict containing trip data or None if not found
        """
        try:
            trip_ref = self.db.collection(self.trips_collection).document(trip_id)
            trip_doc = trip_ref.get()
            
            if trip_doc.exists:
                return trip_doc.to_dict()
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving trip: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to retrieve trip: {str(e)}"
            )
    
    def update_trip_route(
        self,
        trip_id: str,
        route_polyline: str
    ) -> None:
        """
        Update trip with route polyline
        
        Args:
            trip_id: Trip identifier
            route_polyline: Encoded polyline string
        """
        try:
            trip_ref = self.db.collection(self.trips_collection).document(trip_id)
            
            trip_ref.update({
                "route_polyline": route_polyline,
                "updated_at": firestore.SERVER_TIMESTAMP
            })
            
            logger.info(f"Updated route for trip {trip_id}")
            
        except Exception as e:
            logger.error(f"Error updating trip route: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to update trip route: {str(e)}"
            )
    
    def update_trip_rating(
        self,
        trip_id: str,
        user_id: str,
        is_liked: Optional[bool] = None,
        rating: Optional[int] = None,
        is_saved: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        Обновить рейтинг/лайк/сохранение маршрута
        
        Args:
            trip_id: Trip identifier
            user_id: User ID (для проверки владельца)
            is_liked: Лайк (True) или дизлайк (False)
            rating: Рейтинг 1-5
            is_saved: Сохранить в избранное
            
        Returns:
            Обновленные данные маршрута
        """
        try:
            trip_ref = self.db.collection(self.trips_collection).document(trip_id)
            trip_doc = trip_ref.get()
            
            if not trip_doc.exists:
                raise HTTPException(
                    status_code=404,
                    detail=f"Trip with ID {trip_id} not found"
                )
            
            trip_data = trip_doc.to_dict()
            
            # Проверить, что пользователь - владелец маршрута
            if trip_data.get("user_id") != user_id:
                raise HTTPException(
                    status_code=403,
                    detail="You can only rate your own trips"
                )
            
            # Подготовить данные для обновления
            update_data = {"updated_at": firestore.SERVER_TIMESTAMP}
            
            if is_liked is not None:
                update_data["is_liked"] = is_liked
            
            if rating is not None:
                if not 1 <= rating <= 5:
                    raise ValueError("Rating must be between 1 and 5")
                update_data["rating"] = rating
            
            if is_saved is not None:
                update_data["is_saved"] = is_saved
            
            # Обновить документ
            trip_ref.update(update_data)
            
            logger.info(f"Updated rating for trip {trip_id}")
            
            # Вернуть обновленные данные
            updated_doc = trip_ref.get()
            return updated_doc.to_dict()
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating trip rating: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to update trip rating: {str(e)}"
            )
    
    def get_user_trips(
        self,
        user_id: str,
        is_saved: Optional[bool] = None,
        is_liked: Optional[bool] = None,
        theme: Optional[str] = None,
        limit: int = 10,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Получить маршруты пользователя с фильтрами
        
        Args:
            user_id: User ID
            is_saved: Фильтр по сохраненным
            is_liked: Фильтр по лайкнутым
            theme: Фильтр по теме
            limit: Количество результатов
            offset: Смещение для пагинации
            
        Returns:
            Список маршрутов
        """
        try:
            # Базовый запрос
            query = self.db.collection(self.trips_collection).where(
                "user_id", "==", user_id
            )
            
            # Применить фильтры
            if is_saved is not None:
                query = query.where("is_saved", "==", is_saved)
            
            if is_liked is not None:
                query = query.where("is_liked", "==", is_liked)
            
            if theme:
                query = query.where("theme", "==", theme)
            
            # Сортировка по дате создания (новые первыми)
            query = query.order_by("created_at", direction=firestore.Query.DESCENDING)
            
            # Пагинация
            query = query.limit(limit).offset(offset)
            
            # Выполнить запрос
            docs = query.stream()
            
            trips = [doc.to_dict() for doc in docs]
            
            logger.info(f"Retrieved {len(trips)} trips for user {user_id}")
            return trips
            
        except Exception as e:
            logger.error(f"Error retrieving user trips: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to retrieve trips: {str(e)}"
            )
    
    def delete_trip(self, trip_id: str, user_id: str) -> None:
        """
        Удалить маршрут
        
        Args:
            trip_id: Trip identifier
            user_id: User ID (для проверки владельца)
        """
        try:
            trip_ref = self.db.collection(self.trips_collection).document(trip_id)
            trip_doc = trip_ref.get()
            
            if not trip_doc.exists:
                raise HTTPException(
                    status_code=404,
                    detail=f"Trip with ID {trip_id} not found"
                )
            
            trip_data = trip_doc.to_dict()
            
            # Проверить владельца
            if trip_data.get("user_id") != user_id:
                raise HTTPException(
                    status_code=403,
                    detail="You can only delete your own trips"
                )
            
            trip_ref.delete()
            logger.info(f"Deleted trip {trip_id}")
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error deleting trip: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to delete trip: {str(e)}"
            )


# Global instance
firebase_service = FirebaseService()

