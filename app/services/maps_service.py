"""
Google Maps Service for directions, navigation, and place discovery
"""
import googlemaps
import httpx
from fastapi import HTTPException
from app.core.config import settings
from app.models.schemas import (
    TripTheme, LatLng, Place, PlacePhoto, PlaceSuggestion
)
from typing import List, Dict, Any, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


# Theme to Google Places type mapping
THEME_PLACE_TYPES = {
    TripTheme.CULTURE: [
        "museum",
        "art_gallery",
        "church",
        "tourist_attraction",
        "library",
        "historical_landmark"
    ],
    TripTheme.GASTRONOMY: [
        "restaurant",
        "cafe",
        "bakery",
        "bar",
        "meal_takeaway",
        "food"
    ],
    TripTheme.NATURE: [
        "park",
        "natural_feature",
        "campground",
        "hiking_area",
        "scenic_lookout"
    ],
    TripTheme.LEISURE: [
        "amusement_park",
        "bowling_alley",
        "movie_theater",
        "shopping_mall",
        "spa",
        "night_club",
        "casino"
    ],
    TripTheme.MIX: [
        "tourist_attraction",
        "point_of_interest"
    ]
}


class MapsService:
    """Service for handling Google Maps API operations"""
    
    def __init__(self):
        """Initialize Google Maps client"""
        try:
            # Add timeout to prevent hanging requests
            self.client = googlemaps.Client(
                key=settings.MAPS_API_KEY,
                timeout=10  # 10 seconds timeout for each API call (reduced for faster fallback)
            )
            # Cache to track which transport modes are not working (to avoid repeated timeouts)
            self._failed_modes = set()
            logger.info("Google Maps client initialized successfully with 10s timeout")
        except Exception as e:
            logger.error(f"Failed to initialize Google Maps client: {str(e)}")
            raise
    
    def reset_failed_modes_cache(self):
        """Reset the cache of failed transport modes (call at the start of each new route generation)"""
        if self._failed_modes:
            logger.info(f"🔄 Resetting failed modes cache (was: {self._failed_modes})")
            self._failed_modes.clear()
    
    def get_route(
        self,
        origin: str,
        destination: str,
        waypoints: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Get route directions from Google Maps API
        
        Args:
            origin: Starting location (address or "lat,lng")
            destination: Ending location (address or "lat,lng")
            waypoints: Optional list of waypoints
            
        Returns:
            Dict containing route information with polyline and route details
        """
        try:
            # Prepare waypoints
            waypoints_param = None
            if waypoints and len(waypoints) > 0:
                waypoints_param = waypoints
            
            # Call Google Maps Directions API
            directions_result = self.client.directions(
                origin=origin,
                destination=destination,
                waypoints=waypoints_param,
                mode="driving",
                alternatives=False,
                optimize_waypoints=True
            )
            
            if not directions_result:
                raise HTTPException(
                    status_code=404,
                    detail="No route found between the specified locations"
                )
            
            # Extract first route (we requested no alternatives)
            route = directions_result[0]
            
            # Extract overview polyline
            overview_polyline = route.get("overview_polyline", {}).get("points", "")
            
            # Calculate total distance and duration
            total_distance_meters = 0
            total_duration_seconds = 0
            
            legs = []
            for leg in route.get("legs", []):
                distance = leg.get("distance", {})
                duration = leg.get("duration", {})
                
                total_distance_meters += distance.get("value", 0)
                total_duration_seconds += duration.get("value", 0)
                
                legs.append({
                    "start_address": leg.get("start_address"),
                    "end_address": leg.get("end_address"),
                    "distance": distance.get("text"),
                    "duration": duration.get("text"),
                    "steps_count": len(leg.get("steps", []))
                })
            
            # Format distance and duration
            distance_km = total_distance_meters / 1000
            distance_text = f"{distance_km:.2f} km"
            
            duration_hours = total_duration_seconds // 3600
            duration_minutes = (total_duration_seconds % 3600) // 60
            if duration_hours > 0:
                duration_text = f"{duration_hours}h {duration_minutes}m"
            else:
                duration_text = f"{duration_minutes}m"
            
            # Decode polyline to points (optional)
            route_points = self._decode_polyline(overview_polyline)
            
            result = {
                "status": "OK",
                "distance": distance_text,
                "duration": duration_text,
                "polyline": overview_polyline,
                "route_points": route_points,
                "legs": legs,
                "waypoint_order": route.get("waypoint_order", [])
            }
            
            logger.info(
                f"Route calculated: {distance_text}, {duration_text}, "
                f"{len(route_points)} points"
            )
            
            return result
            
        except googlemaps.exceptions.ApiError as e:
            logger.error(f"Google Maps API error: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail=f"Google Maps API error: {str(e)}"
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Unexpected error calculating route: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to calculate route: {str(e)}"
            )
    
    def get_route_with_places(
        self,
        origin: str,
        destination: str,
        places: List[Place],
        optimize: bool = True
    ) -> Dict[str, Any]:
        """
        Get route directions with Place objects as waypoints
        
        Args:
            origin: Starting location
            destination: Ending location
            places: List of Place objects to visit
            optimize: Whether to optimize waypoint order
            
        Returns:
            Dict with route info and optimized place order
        """
        try:
            # Convert places to waypoint strings
            waypoints = []
            for place in places:
                waypoint = f"{place.location.lat},{place.location.lng}"
                waypoints.append(waypoint)
            
            # Call standard route method
            route_data = self.get_route(
                origin=origin,
                destination=destination,
                waypoints=waypoints if waypoints else None
            )
            
            # If optimized, reorder places according to waypoint_order
            if optimize and "waypoint_order" in route_data:
                waypoint_order = route_data["waypoint_order"]
                optimized_places = [places[i] for i in waypoint_order]
                route_data["stops"] = optimized_places
                route_data["optimized_order"] = waypoint_order
            else:
                route_data["stops"] = places
            
            return route_data
            
        except Exception as e:
            logger.error(f"Error calculating route with places: {str(e)}")
            raise
    
    def search_places_by_theme(
        self,
        location: str,
        theme: TripTheme,
        radius: int = 5000,
        max_results: int = 20
    ) -> Tuple[LatLng, List[PlaceSuggestion]]:
        """
        Search for places by theme using Google Places API (New)
        
        Args:
            location: Center location (address or "lat,lng")
            theme: Theme category to search for
            radius: Search radius in meters (max 50000)
            max_results: Maximum number of results
            
        Returns:
            Tuple of (center_coordinates, list_of_place_suggestions)
        """
        try:
            # Geocode location if it's an address
            center_coords = self._geocode_location(location)
            
            # Get place types for theme
            place_types = THEME_PLACE_TYPES.get(theme, THEME_PLACE_TYPES[TripTheme.MIX])
            
            logger.info(
                f"Searching places for theme '{theme}' at {center_coords.lat},{center_coords.lng} "
                f"with radius {radius}m using Places API (New)"
            )
            
            all_places = []
            seen_place_ids = set()
            
            # Use new Places API (New) via HTTP
            url = "https://places.googleapis.com/v1/places:searchNearby"
            headers = {
                "Content-Type": "application/json",
                "X-Goog-Api-Key": settings.MAPS_API_KEY,
                "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.location,places.rating,places.userRatingCount,places.types,places.primaryType"
            }
            
            # Try to get places for each type
            for place_type in place_types:
                if len(all_places) >= max_results:
                    break
                
                try:
                    # Prepare request body for new API
                    body = {
                        "locationRestriction": {
                            "circle": {
                                "center": {
                                    "latitude": center_coords.lat,
                                    "longitude": center_coords.lng
                                },
                                "radius": float(radius)
                            }
                        },
                        "includedTypes": [place_type],
                        "maxResultCount": min(20, max_results - len(all_places))
                    }
                    
                    # Make synchronous HTTP request
                    with httpx.Client(timeout=10.0) as client:
                        response = client.post(url, json=body, headers=headers)
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        for place in data.get("places", []):
                            place_id = place.get("id")
                            
                            # Avoid duplicates
                            if place_id in seen_place_ids:
                                continue
                            seen_place_ids.add(place_id)
                            
                            # Extract location
                            loc = place.get("location", {})
                            place_lat = loc.get("latitude")
                            place_lng = loc.get("longitude")
                            
                            if not place_lat or not place_lng:
                                continue
                            
                            # Calculate distance from center
                            distance = self._calculate_distance(
                                center_coords.lat, center_coords.lng,
                                place_lat, place_lng
                            )
                            
                            # Extract display name
                            display_name = place.get("displayName", {})
                            name = display_name.get("text", "Unknown") if isinstance(display_name, dict) else "Unknown"
                            
                            place_suggestion = PlaceSuggestion(
                                google_place_id=place_id,
                                name=name,
                                types=place.get("types", []),
                                location=LatLng(
                                    lat=place_lat,
                                    lng=place_lng
                                ),
                                address=place.get("formattedAddress"),
                                rating=place.get("rating"),
                                distance=distance
                            )
                            all_places.append(place_suggestion)
                            
                            if len(all_places) >= max_results:
                                break
                    else:
                        logger.warning(
                            f"Places API returned {response.status_code} for type '{place_type}': {response.text[:200]}"
                        )
                        
                except Exception as e:
                    logger.warning(f"Error searching for type '{place_type}': {str(e)}")
                    continue
            
            # Sort by rating (descending) and distance (ascending)
            all_places.sort(
                key=lambda p: (-(p.rating or 0), p.distance or float('inf'))
            )
            
            # Limit results
            all_places = all_places[:max_results]
            
            logger.info(f"Found {len(all_places)} places for theme '{theme}' using new API")
            
            return center_coords, all_places
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error searching places: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to search places: {str(e)}"
            )
    
    def get_place_details(self, place_id: str) -> Place:
        """
        Get detailed information about a specific place using Places API (New)
        
        Args:
            place_id: Google Place ID
            
        Returns:
            Place object with full details
        """
        try:
            # Use new Places API (New) via HTTP
            url = f"https://places.googleapis.com/v1/places/{place_id}"
            headers = {
                "Content-Type": "application/json",
                "X-Goog-Api-Key": settings.MAPS_API_KEY,
                "X-Goog-FieldMask": "id,displayName,formattedAddress,location,types,rating,userRatingCount,photos,priceLevel,currentOpeningHours"
            }
            
            # Make synchronous HTTP request
            with httpx.Client(timeout=10.0) as client:
                response = client.get(url, headers=headers)
            
            if response.status_code != 200:
                logger.error(
                    f"Places API (New) returned {response.status_code} for place {place_id}: {response.text[:200]}"
                )
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to get place details: {response.text[:200]}"
                )
            
            place_data = response.json()
            
            # Extract location
            location = place_data.get("location", {})
            place_lat = location.get("latitude")
            place_lng = location.get("longitude")
            
            if not place_lat or not place_lng:
                raise HTTPException(
                    status_code=400,
                    detail="Place has no valid location"
                )
            
            # Process photos using new API format and proxy
            photos = []
            for photo in place_data.get("photos", [])[:5]:
                photo_name = photo.get("name")
                if photo_name:
                    # Use backend proxy instead of direct Google URLs
                    from urllib.parse import quote
                    photo_url = (
                        f"http://10.0.2.2:8000/places/photo-proxy?"
                        f"photo_name={quote(photo_name)}&max_width=400"
                    )
                    photos.append(PlacePhoto(
                        url=photo_url,
                        attribution=None,  # New API handles attributions differently
                        width=photo.get("widthPx"),
                        height=photo.get("heightPx")
                    ))
            
            # Extract display name
            display_name = place_data.get("displayName", {})
            name = display_name.get("text", "Unknown") if isinstance(display_name, dict) else "Unknown"
            
            # Map price level from new API
            # New API: PRICE_LEVEL_FREE, PRICE_LEVEL_INEXPENSIVE, PRICE_LEVEL_MODERATE, 
            #          PRICE_LEVEL_EXPENSIVE, PRICE_LEVEL_VERY_EXPENSIVE
            price_level_map = {
                "PRICE_LEVEL_FREE": 0,
                "PRICE_LEVEL_INEXPENSIVE": 1,
                "PRICE_LEVEL_MODERATE": 2,
                "PRICE_LEVEL_EXPENSIVE": 3,
                "PRICE_LEVEL_VERY_EXPENSIVE": 4
            }
            price_level_str = place_data.get("priceLevel")
            price_level = price_level_map.get(price_level_str) if price_level_str else None
            
            place = Place(
                google_place_id=place_id,
                name=name,
                types=place_data.get("types", []),
                location=LatLng(
                    lat=place_lat,
                    lng=place_lng
                ),
                address=place_data.get("formattedAddress"),
                rating=place_data.get("rating"),
                user_ratings_total=place_data.get("userRatingCount"),
                photos=photos,
                vicinity=place_data.get("formattedAddress"),  # New API doesn't have vicinity
                price_level=price_level,
                opening_hours=place_data.get("currentOpeningHours")
            )
            
            return place
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting place details: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to get place details: {str(e)}"
            )
    
    def _geocode_location(self, location: str) -> LatLng:
        """
        Convert location string to coordinates
        
        Args:
            location: Address or "lat,lng" string
            
        Returns:
            LatLng coordinates
        """
        try:
            # Check if already in lat,lng format
            if "," in location:
                parts = location.split(",")
                if len(parts) == 2:
                    try:
                        lat = float(parts[0].strip())
                        lng = float(parts[1].strip())
                        return LatLng(lat=lat, lng=lng)
                    except ValueError:
                        pass
            
            # Geocode the address
            geocode_result = self.client.geocode(location)
            if not geocode_result:
                raise HTTPException(
                    status_code=404,
                    detail=f"Could not find location: {location}"
                )
            
            loc = geocode_result[0]["geometry"]["location"]
            return LatLng(lat=loc["lat"], lng=loc["lng"])
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error geocoding location: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail=f"Failed to geocode location: {str(e)}"
            )
    
    def _calculate_distance(
        self,
        lat1: float,
        lng1: float,
        lat2: float,
        lng2: float
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
        delta_lng = radians(lng2 - lng1)
        
        a = sin(delta_lat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lng / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        
        return R * c
    
    def _decode_polyline(self, polyline_str: str) -> List[Dict[str, float]]:
        """
        Decode a polyline string into a list of lat/lng coordinates
        
        Args:
            polyline_str: Encoded polyline string
            
        Returns:
            List of dicts with 'lat' and 'lng' keys
        """
        try:
            points = googlemaps.convert.decode_polyline(polyline_str)
            return [{"lat": point["lat"], "lng": point["lng"]} for point in points]
        except Exception as e:
            logger.warning(f"Failed to decode polyline: {str(e)}")
            return []
    
    # ==================== NEW METHODS FOR ROUTE GENERATION ====================
    
    def get_place_photos(self, place_id: str, max_photos: int = 5) -> List[str]:
        """
        Get photo URLs from Google Places API (New) for a specific place
        
        Args:
            place_id: Google Place ID
            max_photos: Maximum number of photos to retrieve
            
        Returns:
            List of photo URLs from Google
        """
        try:
            # Use new Places API (New) via HTTP
            url = f"https://places.googleapis.com/v1/places/{place_id}"
            headers = {
                "Content-Type": "application/json",
                "X-Goog-Api-Key": settings.MAPS_API_KEY,
                "X-Goog-FieldMask": "photos"
            }
            
            # Make synchronous HTTP request
            with httpx.Client(timeout=10.0) as client:
                response = client.get(url, headers=headers)
            
            if response.status_code != 200:
                logger.warning(
                    f"Places API (New) returned {response.status_code} for place {place_id}: {response.text[:200]}"
                )
                return []
            
            data = response.json()
            photos = []
            
            # Extract photo names and build proxy URLs
            for photo in data.get("photos", [])[:max_photos]:
                photo_name = photo.get("name")
                if photo_name:
                    # Use backend proxy instead of direct Google URLs
                    # This solves authentication issues with Android client
                    from urllib.parse import quote
                    photo_url = (
                        f"http://10.0.2.2:8000/places/photo-proxy?"
                        f"photo_name={quote(photo_name)}&max_width=800"
                    )
                    photos.append(photo_url)
            
            logger.info(f"Retrieved {len(photos)} photos for place {place_id} using new API")
            return photos
            
        except Exception as e:
            logger.warning(f"Error getting photos for place {place_id}: {str(e)}")
            return []
    
    def build_route_with_optimization(
        self,
        start_point: LatLng,
        places: List[Place],
        mode: str = "driving"
    ) -> Dict[str, Any]:
        """
        Build an optimized route through a list of places
        
        Args:
            start_point: Starting coordinates
            places: List of Place objects to visit
            mode: Transportation mode (walking, driving, transit, bicycling)
            
        Returns:
            Dict with:
                - total_distance: str (e.g., "8.5 km")
                - walking_distance: str (e.g., "4.2 km")
                - duration: str (e.g., "4h 15m")
                - route_points: List[Dict] (decoded polyline)
                - polyline: str (encoded polyline)
                - optimized_order: List[int] (optimized indices)
        """
        try:
            if not places:
                raise ValueError("Places list cannot be empty")
            
            # Convert places to waypoint strings
            waypoints = [f"{p.location.lat},{p.location.lng}" for p in places]
            
            origin = f"{start_point.lat},{start_point.lng}"
            # Return to start point (circular route)
            destination = origin
            
            # Check if this mode has failed before in this session
            effective_mode = mode
            if mode in self._failed_modes and mode != "driving":
                logger.warning(f"⚠️ Mode '{mode}' previously failed, using 'driving' instead")
                effective_mode = "driving"
            
            # Call Google Maps Directions API with optimization
            logger.info(f"⏱️ Calling Directions API: mode={effective_mode}, waypoints={len(waypoints)}, origin={origin[:20]}...")
            
            try:
                directions_result = self.client.directions(
                    origin=origin,
                    destination=destination,
                    waypoints=waypoints,
                    mode=effective_mode,
                    alternatives=False,
                    optimize_waypoints=True
                )
            except googlemaps.exceptions.Timeout:
                # Timeout occurred, cache this failure and try fallback to driving mode
                logger.warning(f"⚠️ Timeout for mode '{effective_mode}', falling back to 'driving'")
                if effective_mode != "driving":
                    # Remember this mode doesn't work
                    self._failed_modes.add(effective_mode)
                    logger.info(f"🚫 Cached '{effective_mode}' as non-working mode for this session")
                    
                    directions_result = self.client.directions(
                        origin=origin,
                        destination=destination,
                        waypoints=waypoints,
                        mode="driving",
                        alternatives=False,
                        optimize_waypoints=True
                    )
                    effective_mode = "driving"  # Update mode for further calculations
                else:
                    raise
            except Exception as e:
                logger.error(f"❌ Directions API call failed: {type(e).__name__}: {str(e)}")
                raise
            
            logger.info(f"✅ Directions API responded in {effective_mode} mode")
            
            if not directions_result:
                raise HTTPException(
                    status_code=404,
                    detail="No route found through the specified places"
                )
            
            route = directions_result[0]
            overview_polyline = route.get("overview_polyline", {}).get("points", "")
            
            # Calculate totals
            total_distance_meters = 0
            total_duration_seconds = 0
            
            for leg in route.get("legs", []):
                distance = leg.get("distance", {})
                duration = leg.get("duration", {})
                total_distance_meters += distance.get("value", 0)
                total_duration_seconds += duration.get("value", 0)
            
            # Format distance
            distance_km = total_distance_meters / 1000
            total_distance_text = f"{distance_km:.1f} km"
            
            # Estimate walking distance (зависит от режима транспорта)
            walking_distance_km = self.calculate_walking_distance(distance_km, effective_mode)
            walking_distance_text = f"{walking_distance_km:.1f} km"
            
            # Calculate total duration with visit time
            # 1. Travel time (from Google)
            travel_time_seconds = total_duration_seconds
            
            # 2. Visit time (зависит от количества мест и их типа)
            visit_time_seconds = self._estimate_visit_time(places, effective_mode)
            
            # 3. Overhead (parking, waiting for transport, etc.)
            overhead_seconds = self._estimate_overhead(len(places), effective_mode)
            
            # Total duration
            total_with_visits = travel_time_seconds + visit_time_seconds + overhead_seconds
            
            duration_hours = total_with_visits // 3600
            duration_minutes = (total_with_visits % 3600) // 60
            if duration_hours > 0:
                duration_text = f"{duration_hours}h {duration_minutes}m"
            else:
                duration_text = f"{duration_minutes}m"
            
            # Decode polyline
            route_points = self._decode_polyline(overview_polyline)
            
            # Get optimized order
            optimized_order = route.get("waypoint_order", list(range(len(places))))
            
            result = {
                "total_distance": total_distance_text,
                "walking_distance": walking_distance_text,
                "duration": duration_text,
                "route_points": route_points,
                "polyline": overview_polyline,
                "optimized_order": optimized_order
            }
            
            logger.info(
                f"Built optimized route: {total_distance_text} total, "
                f"{walking_distance_text} walking, {duration_text}"
            )
            
            return result
            
        except googlemaps.exceptions.ApiError as e:
            logger.error(f"Google Maps API error in route optimization: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail=f"Google Maps API error: {str(e)}"
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error building optimized route: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to build route: {str(e)}"
            )
    
    def _estimate_visit_time(self, places: List[Place], mode: str) -> int:
        """
        Оценить время посещения мест
        
        Время зависит от типа места:
        - Музей/Галерея: 60-90 минут
        - Ресторан/Кафе: 45-60 минут
        - Парк/Природа: 30-45 минут
        - Магазин/Торговый центр: 40-60 минут
        - Церковь/Памятник: 15-30 минут
        - Другое: 30 минут
        
        Args:
            places: Список мест для посещения
            mode: Режим транспорта (не влияет на время посещения)
            
        Returns:
            Общее время посещения в секундах
        """
        total_minutes = 0
        
        for place in places:
            place_types = set(place.types) if place.types else set()
            
            # Определяем время посещения по типу
            if place_types & {"museum", "art_gallery", "aquarium", "zoo"}:
                # Музеи, галереи - долгое посещение
                visit_minutes = 75
            elif place_types & {"restaurant", "cafe", "bar", "meal_takeaway"}:
                # Рестораны, кафе - средняя длительность
                visit_minutes = 50
            elif place_types & {"park", "natural_feature", "garden", "hiking_area"}:
                # Парки, природа - среднее время
                visit_minutes = 35
            elif place_types & {"shopping_mall", "store", "clothing_store"}:
                # Магазины - среднее время
                visit_minutes = 45
            elif place_types & {"church", "tourist_attraction", "landmark", "monument"}:
                # Церкви, памятники - быстрое посещение
                visit_minutes = 20
            elif place_types & {"amusement_park", "movie_theater", "bowling_alley"}:
                # Развлечения - долгое посещение
                visit_minutes = 90
            else:
                # По умолчанию
                visit_minutes = 30
            
            total_minutes += visit_minutes
        
        return total_minutes * 60  # Конвертируем в секунды
    
    def _estimate_overhead(self, num_places: int, mode: str) -> int:
        """
        Оценить дополнительное время (парковка, пересадки, etc.)
        
        Args:
            num_places: Количество мест
            mode: Режим транспорта
            
        Returns:
            Overhead time в секундах
        """
        if mode == "walking":
            # Пешком - минимальный overhead (только переходы)
            return num_places * 60  # 1 минута на место
        elif mode == "transit":
            # Общественный транспорт - большой overhead (ожидание)
            return num_places * 10 * 60  # 10 минут на место
        elif mode == "bicycling":
            # Велосипед - средний overhead (парковка)
            return num_places * 3 * 60  # 3 минуты на место
        else:  # driving
            # Машина - средний overhead (парковка, поиск места)
            return num_places * 7 * 60  # 7 минут на место
    
    def calculate_walking_distance(self, total_distance_km: float, mode: str = "driving") -> float:
        """
        Estimate walking distance from total route distance
        
        Логика зависит от транспорта:
        - **driving/transit**: 35% (парковка, переходы между остановками, прогулка по месту)
        - **bicycling**: 20% (только прогулка по месту, велосипед можно припарковать рядом)
        - **walking**: 100% (весь маршрут пешком)
        
        Args:
            total_distance_km: Total route distance in kilometers
            mode: Transportation mode (walking, driving, transit, bicycling)
            
        Returns:
            Estimated walking distance in kilometers
        """
        if mode == "walking":
            return total_distance_km  # Всё пешком
        elif mode == "bicycling":
            return total_distance_km * 0.20  # Только прогулка по местам
        elif mode == "transit":
            return total_distance_km * 0.40  # Больше пешком (от остановки до места)
        else:  # driving
            return total_distance_km * 0.35  # Парковка + прогулка
    
    def get_autocomplete_suggestions(
        self,
        query: str,
        language: str = "fr"
    ) -> List[str]:
        """
        Get autocomplete suggestions for cities/places using Google Places API (New)
        
        Args:
            query: Search query (e.g., "Pari")
            language: Language code for results (default: "fr")
            
        Returns:
            List of suggestion strings (e.g., ["Paris, France", "Paris, Texas, USA"])
        """
        try:
            url = "https://places.googleapis.com/v1/places:autocomplete"
            
            headers = {
                "Content-Type": "application/json",
                "X-Goog-Api-Key": settings.MAPS_API_KEY
            }
            
            payload = {
                "input": query,
                "includedPrimaryTypes": ["locality", "administrative_area_level_1"],
                "languageCode": language
            }
            
            # Use httpx for async HTTP request
            with httpx.Client() as client:
                response = client.post(url, json=payload, headers=headers, timeout=10.0)
                response.raise_for_status()
                
                data = response.json()
                suggestions = []
                
                if "suggestions" in data:
                    for suggestion in data["suggestions"]:
                        place_prediction = suggestion.get("placePrediction", {})
                        text_obj = place_prediction.get("text", {})
                        text = text_obj.get("text", "")
                        if text:
                            suggestions.append(text)
                
                logger.info(f"Autocomplete for '{query}': found {len(suggestions)} suggestions")
                return suggestions
                
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error in autocomplete: {e.response.status_code} - {e.response.text}")
            raise HTTPException(
                status_code=500,
                detail=f"Google Places API error: {e.response.status_code}"
            )
        except Exception as e:
            logger.error(f"Error in autocomplete: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to get autocomplete suggestions: {str(e)}"
            )


# Global instance
maps_service = MapsService()

