"""
gRPC service for receiving photos from partner applications
"""
import grpc
from concurrent import futures
import logging
import uuid
import io
from datetime import datetime
from typing import Optional, List
import pygeohash as pgh

# These will be generated from proto file
# For now we'll use a REST-based fallback
from app.services.minio_service import minio_service
from app.services.firebase_service import firebase_service
from app.services.maps_service import maps_service
from app.core.config import settings

logger = logging.getLogger(__name__)


def get_continent_from_coords(lat: float, lng: float) -> str:
    """
    Determine continent from coordinates (simple approximation).
    """
    # Simple continent detection based on coordinates
    if lat > 35 and lng > -30 and lng < 60:
        return "Europe"
    elif lat > 10 and lng > 60 and lng < 150:
        return "Asia"
    elif lat < 10 and lat > -40 and lng > 100 and lng < 180:
        return "Oceania"
    elif lat > -60 and lat < 15 and lng > -80 and lng < -30:
        return "South America"
    elif lat > 15 and lng > -170 and lng < -50:
        return "North America"
    elif lat > -40 and lat < 40 and lng > -20 and lng < 55:
        return "Africa"
    elif lat < -60:
        return "Antarctica"
    else:
        return "Unknown"


class PhotoService:
    """
    Service for handling photo uploads from partner applications.
    Supports both new Photo format and legacy PlacePhoto format.
    """
    
    def __init__(self):
        self.minio = minio_service
        self.firebase = firebase_service
        self.maps = maps_service
    
    async def upload_photo(
        self,
        photo_id: str = "",
        media_uris: List[str] = None,
        thumbnail_url: str = "",
        audio_url: str = "",
        description: str = "",
        ai_tags: List[str] = None,
        category: str = "",
        location_name: str = "",
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        geohash: str = "",
        continent: str = "",
        author_id: str = "",
        author_name: str = "",
        author_avatar: str = "",
        visibility: str = "PUBLIC",
        group_id: str = "",
        like_count: int = 0,
        timestamp: Optional[int] = None,
        photo_data: Optional[bytes] = None,
        content_type: str = "image/jpeg",
        source_app: str = "partner_app"
    ) -> dict:
        """
        Upload a photo with all metadata in new format.
        
        Returns:
            dict with photo_id, media_urls, thumbnail_url, audio_url, success status
        """
        try:
            media_uris = media_uris or []
            ai_tags = ai_tags or []
            
            logger.info(f"📸 Receiving photo: {location_name}, author: {author_name}")
            
            # Generate photo ID if not provided
            if not photo_id:
                photo_id = str(uuid.uuid4())
            
            now = datetime.utcnow()
            timestamp_str = now.strftime("%Y%m%d_%H%M%S")
            
            # Calculate geohash if not provided but coordinates are
            if not geohash and latitude is not None and longitude is not None:
                try:
                    geohash = pgh.encode(latitude, longitude, precision=8)
                except:
                    geohash = ""
            
            # Determine continent if not provided
            if not continent and latitude is not None and longitude is not None:
                continent = get_continent_from_coords(latitude, longitude)
            
            uploaded_media_urls = []
            uploaded_thumbnail_url = thumbnail_url
            uploaded_audio_url = audio_url
            
            # Upload photo_data to MinIO if provided
            if photo_data:
                ext = "jpg"
                if content_type == "image/png":
                    ext = "png"
                elif content_type == "image/webp":
                    ext = "webp"
                
                # Create object path
                if author_id:
                    object_path = f"photos/{author_id}/{timestamp_str}_{photo_id}.{ext}"
                else:
                    object_path = f"photos/anonymous/{timestamp_str}_{photo_id}.{ext}"
                
                # Upload to MinIO
                photo_url = self._upload_to_minio(
                    photo_data=photo_data,
                    object_path=object_path,
                    content_type=content_type,
                    metadata={
                        "photo_id": photo_id,
                        "author_id": author_id or "",
                        "location_name": location_name,
                        "category": category,
                        "visibility": visibility,
                        "source_app": source_app,
                        "uploaded_at": now.isoformat()
                    }
                )
                uploaded_media_urls.append(photo_url)
                
                # Also set as thumbnail if not provided
                if not uploaded_thumbnail_url:
                    uploaded_thumbnail_url = photo_url
            else:
                # Use provided media_uris
                uploaded_media_urls = media_uris
            
            # Save metadata to Firestore in new Photo format
            self._save_photo_to_firestore(
                photo_id=photo_id,
                media_uris=uploaded_media_urls,
                thumbnail_url=uploaded_thumbnail_url,
                audio_url=uploaded_audio_url,
                description=description,
                ai_tags=ai_tags,
                category=category,
                location_name=location_name,
                latitude=latitude,
                longitude=longitude,
                geohash=geohash,
                continent=continent,
                author_id=author_id,
                author_name=author_name,
                author_avatar=author_avatar,
                visibility=visibility,
                group_id=group_id,
                like_count=like_count,
                source_app=source_app
            )
            
            logger.info(f"✅ Photo uploaded successfully: {photo_id}")
            
            return {
                "success": True,
                "photo_id": photo_id,
                "media_urls": uploaded_media_urls,
                "thumbnail_url": uploaded_thumbnail_url,
                "audio_url": uploaded_audio_url,
                "error_message": None
            }
            
        except Exception as e:
            logger.error(f"❌ Error uploading photo: {str(e)}")
            return {
                "success": False,
                "photo_id": photo_id or "",
                "media_urls": [],
                "thumbnail_url": "",
                "audio_url": "",
                "error_message": str(e)
            }
    
    def _save_photo_to_firestore(
        self,
        photo_id: str,
        media_uris: List[str],
        thumbnail_url: str,
        audio_url: str,
        description: str,
        ai_tags: List[str],
        category: str,
        location_name: str,
        latitude: Optional[float],
        longitude: Optional[float],
        geohash: str,
        continent: str,
        author_id: str,
        author_name: str,
        author_avatar: str,
        visibility: str,
        group_id: str,
        like_count: int,
        source_app: str
    ) -> None:
        """
        Save photo metadata to Firestore in the new Photo format.
        """
        try:
            from google.cloud.firestore import GeoPoint
            
            # Build GeoPoint if coordinates provided
            geo_point = None
            if latitude is not None and longitude is not None:
                geo_point = GeoPoint(latitude, longitude)
            
            doc_data = {
                "photoId": photo_id,
                "mediaUris": media_uris,
                "thumbnailUrl": thumbnail_url,
                "audioUrl": audio_url if audio_url else None,
                "description": description,
                "aiTags": ai_tags,
                "category": category,
                "locationName": location_name,
                "geoPoint": geo_point,
                "geohash": geohash,
                "continent": continent,
                "authorId": author_id,
                "authorName": author_name,
                "authorAvatar": author_avatar,
                "visibility": visibility,
                "groupId": group_id if group_id else None,
                "likeCount": like_count,
                "timestamp": datetime.utcnow(),
                "sourceApp": source_app
            }
            
            # Save to 'photos' collection (matching Android app)
            self.firebase.db.collection("photos").document(photo_id).set(doc_data)
            
            logger.info(f"Photo metadata saved to Firestore: {photo_id}")
            
        except Exception as e:
            logger.error(f"Firestore save error: {str(e)}")
            # Don't raise - photo might already be in MinIO
    
    # ========== Legacy methods for backwards compatibility ==========
    
    async def upload_place_photo(
        self,
        photo_data: bytes,
        filename: str,
        content_type: str,
        place_name: str,
        address: str,
        city: str,
        latitude: float,
        longitude: float,
        google_place_id: Optional[str] = None,
        source_app: str = "partner_app",
        source_user_id: Optional[str] = None,
        place_types: Optional[list] = None
    ) -> dict:
        """
        Legacy: Upload a photo and associate it with a place.
        
        If google_place_id is not provided, tries to find matching place by coordinates/name.
        
        Returns:
            dict with photo_url, photo_id, matched_place_id, success status
        """
        try:
            logger.info(f"📸 Receiving photo for place: {place_name}, city: {city}")
            
            # Generate unique photo ID
            photo_id = str(uuid.uuid4())
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            
            # Try to find Google Place ID if not provided
            matched_place_id = google_place_id
            if not matched_place_id:
                matched_place_id = await self._find_place_by_coords_or_name(
                    name=place_name,
                    lat=latitude,
                    lng=longitude,
                    city=city
                )
                if matched_place_id:
                    logger.info(f"✅ Matched place: {matched_place_id}")
                else:
                    logger.warning(f"⚠️ Could not find Google Place ID for: {place_name}")
            
            # Create object path in MinIO
            # Structure: places/{place_id or coords}/photos/{photo_id}.{ext}
            ext = filename.split('.')[-1] if '.' in filename else 'jpg'
            
            if matched_place_id:
                object_path = f"places/{matched_place_id}/photos/{timestamp}_{photo_id}.{ext}"
            else:
                # Use coordinates as fallback path
                coord_key = f"{latitude:.6f}_{longitude:.6f}".replace('.', '_').replace('-', 'n')
                object_path = f"places/coords_{coord_key}/photos/{timestamp}_{photo_id}.{ext}"
            
            # Upload to MinIO with metadata
            photo_url = self._upload_to_minio(
                photo_data=photo_data,
                object_path=object_path,
                content_type=content_type,
                metadata={
                    "place_id": matched_place_id or "",
                    "place_name": place_name,
                    "city": city,
                    "address": address,
                    "latitude": str(latitude),
                    "longitude": str(longitude),
                    "source_app": source_app,
                    "source_user_id": source_user_id or "",
                    "uploaded_at": datetime.utcnow().isoformat()
                }
            )
            
            # Save metadata to Firestore (legacy format)
            self._save_place_photo_metadata_to_firestore(
                photo_id=photo_id,
                photo_url=photo_url,
                place_id=matched_place_id,
                place_name=place_name,
                address=address,
                city=city,
                latitude=latitude,
                longitude=longitude,
                source_app=source_app,
                source_user_id=source_user_id,
                place_types=place_types or []
            )
            
            logger.info(f"✅ Photo uploaded successfully: {photo_url}")
            
            return {
                "success": True,
                "photo_url": photo_url,
                "photo_id": photo_id,
                "matched_place_id": matched_place_id,
                "error_message": None
            }
            
        except Exception as e:
            logger.error(f"❌ Error uploading photo: {str(e)}")
            return {
                "success": False,
                "photo_url": None,
                "photo_id": None,
                "matched_place_id": None,
                "error_message": str(e)
            }
    
    async def _find_place_by_coords_or_name(
        self,
        name: str,
        lat: float,
        lng: float,
        city: str
    ) -> Optional[str]:
        """
        Try to find a Google Place ID by coordinates or name.
        """
        try:
            # Try nearby search first with name
            search_query = f"{name} {city}"
            
            # Use Google Places API to find place
            places = self.maps.client.places_nearby(
                location=(lat, lng),
                radius=100,  # 100 meters
                keyword=name
            )
            
            if places.get("results"):
                # Return first match
                return places["results"][0].get("place_id")
            
            # Try text search as fallback
            text_results = self.maps.client.places(search_query)
            if text_results.get("results"):
                return text_results["results"][0].get("place_id")
            
            return None
            
        except Exception as e:
            logger.warning(f"Could not find place: {str(e)}")
            return None
    
    def _upload_to_minio(
        self,
        photo_data: bytes,
        object_path: str,
        content_type: str,
        metadata: dict
    ) -> str:
        """
        Upload photo bytes to MinIO with metadata.
        """
        import urllib.parse
        
        try:
            # Convert metadata values to ASCII-safe strings (URL encode non-ASCII)
            str_metadata = {}
            for k, v in metadata.items():
                val = str(v)
                # URL encode non-ASCII characters for MinIO compatibility
                try:
                    val.encode('ascii')
                    str_metadata[k] = val
                except UnicodeEncodeError:
                    str_metadata[k] = urllib.parse.quote(val, safe='')
            
            # Upload to MinIO
            self.minio.client.put_object(
                bucket_name=self.minio.bucket_name,
                object_name=object_path,
                data=io.BytesIO(photo_data),
                length=len(photo_data),
                content_type=content_type,
                metadata=str_metadata
            )
            
            # Return proxy URL instead of direct MinIO URL
            # Android emulator can't access localhost:9000, so we use backend proxy
            from app.core.config import settings
            proxy_url = f"{settings.api_base_url}/photos/minio-proxy?path={object_path}"
            return proxy_url
            
        except Exception as e:
            logger.error(f"MinIO upload error: {str(e)}")
            raise
    
    def _save_place_photo_metadata_to_firestore(
        self,
        photo_id: str,
        photo_url: str,
        place_id: Optional[str],
        place_name: str,
        address: str,
        city: str,
        latitude: float,
        longitude: float,
        source_app: str,
        source_user_id: Optional[str],
        place_types: list
    ) -> None:
        """
        Legacy: Save photo metadata to Firestore for quick lookup.
        """
        try:
            doc_data = {
                "photo_id": photo_id,
                "photo_url": photo_url,
                "place_id": place_id,
                "place_name": place_name,
                "address": address,
                "city": city,
                "location": {
                    "lat": latitude,
                    "lng": longitude
                },
                "source_app": source_app,
                "source_user_id": source_user_id,
                "place_types": place_types,
                "uploaded_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow()
            }
            
            # Save to 'place_photos' collection
            self.firebase.db.collection("place_photos").document(photo_id).set(doc_data)
            
            logger.info(f"Photo metadata saved to Firestore: {photo_id}")
            
        except Exception as e:
            logger.error(f"Firestore save error: {str(e)}")
            # Don't raise - photo is already in MinIO
    
    def _convert_to_proxy_url(self, url: str) -> str:
        """
        Convert direct MinIO URL to proxy URL for Android compatibility.
        localhost:9000 is not accessible from Android emulator.
        """
        if not url:
            return url
            
        # If already a proxy URL, return as is
        if "/photos/minio-proxy" in url:
            return url
            
        # Extract path from MinIO URL
        # Format: http://localhost:9000/travel-photos/places/.../photo.jpg
        import urllib.parse
        
        try:
            from app.core.config import settings
            parsed = urllib.parse.urlparse(url)
            # Get path after bucket name
            path_parts = parsed.path.split('/', 2)  # ['', 'travel-photos', 'places/...']
            if len(path_parts) >= 3:
                object_path = path_parts[2]  # 'places/...'
                return f"{settings.api_base_url}/photos/minio-proxy?path={urllib.parse.quote(object_path)}"
        except:
            pass
        
        return url
    
    def get_place_photos_by_id_or_coords(
        self,
        place_id: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        max_photos: int = 10
    ) -> list:
        """
        Get photos for a place by Google Place ID or coordinates.
        Searches BOTH collections:
        - 'place_photos' (legacy REST uploads)
        - 'photos' (new gRPC uploads)
        
        Returns list of proxy URLs (accessible from Android).
        """
        photo_urls = []
        
        try:
            # Method 1: Search legacy 'place_photos' collection by place_id
            if place_id:
                photos_ref = self.firebase.db.collection("place_photos")
                query = photos_ref.where("place_id", "==", place_id).limit(max_photos)
                
                for doc in query.stream():
                    data = doc.to_dict()
                    if data.get("photo_url"):
                        proxy_url = self._convert_to_proxy_url(data["photo_url"])
                        photo_urls.append(proxy_url)
            
            # Method 2: Search NEW 'photos' collection by coordinates
            if latitude and longitude and len(photo_urls) < max_photos:
                lat_delta = 0.002  # ~200m radius
                lng_delta = 0.002
                
                photos_ref = self.firebase.db.collection("photos")
                query = photos_ref.limit(100)
                
                for doc in query.stream():
                    if len(photo_urls) >= max_photos:
                        break
                    
                    data = doc.to_dict()
                    geo_point = data.get("geoPoint")
                    
                    if geo_point:
                        doc_lat = geo_point.latitude if hasattr(geo_point, 'latitude') else None
                        doc_lng = geo_point.longitude if hasattr(geo_point, 'longitude') else None
                        
                        if doc_lat and doc_lng:
                            if (abs(doc_lat - latitude) <= lat_delta and 
                                abs(doc_lng - longitude) <= lng_delta):
                                # Get URLs from mediaUris
                                media_uris = data.get("mediaUris", [])
                                for url in media_uris:
                                    if url and url not in photo_urls:
                                        proxy_url = self._convert_to_proxy_url(url)
                                        photo_urls.append(proxy_url)
                                        if len(photo_urls) >= max_photos:
                                            break
                                
                                # Also check thumbnailUrl
                                thumb = data.get("thumbnailUrl")
                                if thumb and thumb not in photo_urls and len(photo_urls) < max_photos:
                                    proxy_url = self._convert_to_proxy_url(thumb)
                                    if proxy_url not in photo_urls:
                                        photo_urls.append(proxy_url)
            
            # Method 3: Search legacy by coordinates
            if latitude and longitude and len(photo_urls) < max_photos:
                lat_delta = 0.001
                lng_delta = 0.001
                
                photos_ref = self.firebase.db.collection("place_photos")
                query = photos_ref.limit(100)
                
                for doc in query.stream():
                    if len(photo_urls) >= max_photos:
                        break
                        
                    data = doc.to_dict()
                    loc = data.get("location", {})
                    doc_lat = loc.get("lat")
                    doc_lng = loc.get("lng")
                    
                    if doc_lat and doc_lng:
                        if (abs(doc_lat - latitude) <= lat_delta and 
                            abs(doc_lng - longitude) <= lng_delta):
                            url = data.get("photo_url")
                            if url:
                                proxy_url = self._convert_to_proxy_url(url)
                                if proxy_url not in photo_urls:
                                    photo_urls.append(proxy_url)
            
            logger.info(f"Found {len(photo_urls)} user photos for place")
            return photo_urls[:max_photos]
            
        except Exception as e:
            logger.error(f"Error getting place photos: {str(e)}")
            return []


# Global instance (new name)
photo_service = PhotoService()

# Legacy alias for backwards compatibility
place_photo_service = photo_service
