"""
Trip-related API endpoints
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status, Depends, Response
from fastapi.responses import JSONResponse
from app.models.schemas import (
    RoutePlanRequest,
    RouteResponse,
    PhotoUploadResponse,
    ErrorResponse,
    TripRatingRequest,
    TripListResponse,
    TripData,
    ExportRequest,
    ExportResponse,
    ExportFormat,
    RouteGenerationRequest,
    RouteGenerationResponse,
    RouteOption,
    PlaceWithPhotos,
    PlacePhotoSimple,
    Place,
    LatLng,
    SavedRoute,
    SaveRouteRequest,
    SavedRoutesResponse
)
from app.services.firebase_service import firebase_service
from app.services.minio_service import minio_service
from app.services.maps_service import maps_service
from app.services.time_slot_service import time_slot_service
from app.services.export_service import export_service
from app.models.schemas import PhotoMetadata
from app.core.auth_middleware import get_current_user
from typing import Optional, Dict
import logging
from datetime import datetime
import uuid
from google.cloud import firestore

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/trips",
    tags=["trips"]
)


def calculate_smart_difficulty(
    walking_distance: str,
    total_distance: str,
    duration: str,
    num_places: int,
    places: list
) -> str:
    """
    Умная система градации сложности маршрута
    
    Учитывает множество факторов:
    1. Walking distance (основной фактор) - физическая нагрузка
    2. Количество мест - ментальная нагрузка, переключение внимания
    3. Продолжительность - общая усталость
    4. Тип мест - некоторые места требуют больше энергии
    
    Возвращает: "easy", "moderate", "hard"
    """
    score = 0
    
    # 1. Walking distance (вес: 40 баллов)
    walking_km = float(walking_distance.replace(" km", "").replace(",", "."))
    if walking_km < 2:
        score += 5  # Очень лёгко
    elif walking_km < 3:
        score += 10  # Лёгко
    elif walking_km < 5:
        score += 20  # Средне
    elif walking_km < 7:
        score += 30  # Сложновато
    else:
        score += 40  # Сложно
    
    # 2. Количество мест (вес: 25 баллов)
    # Больше мест = больше переходов, больше информации для усвоения
    if num_places <= 3:
        score += 5
    elif num_places <= 5:
        score += 12
    elif num_places <= 7:
        score += 20
    else:
        score += 25
    
    # 3. Продолжительность (вес: 20 баллов)
    # Парсим duration (формат: "2h 30m" или "45m")
    try:
        duration_minutes = 0
        if "h" in duration:
            parts = duration.replace("m", "").split("h")
            hours = int(parts[0].strip())
            minutes = int(parts[1].strip()) if len(parts) > 1 and parts[1].strip() else 0
            duration_minutes = hours * 60 + minutes
        else:
            duration_minutes = int(duration.replace("m", "").strip())
        
        if duration_minutes < 120:  # < 2 часов
            score += 3
        elif duration_minutes < 180:  # < 3 часов
            score += 8
        elif duration_minutes < 240:  # < 4 часов
            score += 15
        else:  # > 4 часов
            score += 20
    except:
        score += 10  # Средний балл если не удалось распарсить
    
    # 4. Тип мест (вес: 15 баллов)
    # Музеи, галереи требуют больше концентрации
    # Парки, природа - расслабляют
    energy_demanding_types = {"museum", "art_gallery", "church", "library", "aquarium", "zoo"}
    relaxing_types = {"park", "garden", "natural_feature", "scenic_lookout"}
    
    energy_demanding_count = 0
    relaxing_count = 0
    
    for place in places:
        place_types = set(place.types) if place.types else set()
        if place_types & energy_demanding_types:
            energy_demanding_count += 1
        if place_types & relaxing_types:
            relaxing_count += 1
    
    # Чем больше "энергозатратных" мест, тем выше сложность
    energy_ratio = energy_demanding_count / max(num_places, 1)
    relaxing_ratio = relaxing_count / max(num_places, 1)
    
    if energy_ratio > 0.5:  # Больше половины - энергозатратные
        score += 15
    elif energy_ratio > 0.3:
        score += 10
    elif relaxing_ratio > 0.5:  # Больше половины - расслабляющие
        score += 3
    else:
        score += 7  # Смешанный тип
    
    # Итоговая градация (максимум 100 баллов)
    # 0-35: easy (лёгкий)
    # 36-65: moderate (средний)
    # 66-100: hard (сложный)
    
    logger.info(
        f"Difficulty calculation: walking={walking_km}km, places={num_places}, "
        f"duration={duration}, score={score}"
    )
    
    if score <= 35:
        return "easy"
    elif score <= 65:
        return "moderate"
    else:
        return "hard"


@router.post(
    "/generate-routes",
    response_model=RouteGenerationResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate 3 route options (New Architecture)",
    description="Generate 3 optimized route options (easy/moderate/hard) based on theme and preferences"
)
async def generate_routes(request: RouteGenerationRequest) -> RouteGenerationResponse:
    """
    Generate 3 route options with real data from Google Maps and MinIO
    
    **New Architecture - Core Endpoint:**
    This endpoint replaces the old client-side route generation logic.
    It creates 3 complete route options ready for user selection.
    
    **Process:**
    1. Geocode start_point (if address provided)
    2. Search 15-20 places by theme using Google Places API
    3. Build 3 route variants:
       - **Easy Route**: 3-4 closest places, <3km walking distance
       - **Moderate Route**: 5-6 places, 3-7km walking distance
       - **Hard Route**: 7-8 places, >7km walking distance
    4. For each place:
       - Get photos from MinIO (user-uploaded)
       - Get photos from Google Places API
       - Extract price_level from Google
       - Include rating and details
    5. Calculate average price for each route
    6. Build optimized route through Google Maps Directions API
    
    **Args:**
        request: RouteGenerationRequest with:
            - location: City/area (e.g., "Montpellier, France")
            - start_point: Starting coordinates or address
            - theme: Trip theme (culture, gastronomy, nature, etc.)
            - num_places: Desired number of places (1-20)
    
    **Returns:**
        RouteGenerationResponse with 3 complete route options
    """
    try:
        import time
        start_time = time.time()
        
        logger.info(
            f"⏱️ START: Generating routes for {request.location}, theme: {request.theme}, "
            f"num_places: {request.num_places}, transport: {request.transport_mode}"
        )
        
        # Reset failed transport modes cache for this new request
        maps_service.reset_failed_modes_cache()
        
        # 1. Geocode start_point
        # First, get the city center coordinates for validation
        city_center = maps_service._geocode_location(request.location)
        
        if request.start_point.lat and request.start_point.lng:
            provided_coords = LatLng(lat=request.start_point.lat, lng=request.start_point.lng)
            
            # Check if provided coordinates are within reasonable distance from the city (100km)
            distance_from_city = maps_service._calculate_distance(
                city_center.lat, city_center.lng,
                provided_coords.lat, provided_coords.lng
            )
            
            if distance_from_city > 100:  # More than 100km from city center
                logger.warning(
                    f"⚠️ GPS coordinates ({provided_coords.lat},{provided_coords.lng}) are "
                    f"{distance_from_city:.0f}km from {request.location}. Using city center instead."
                )
                start_coords = city_center
            else:
                start_coords = provided_coords
                logger.info(f"Using provided coordinates: {start_coords.lat},{start_coords.lng}")
        elif request.start_point.address:
            # Если адрес не содержит город/страну, добавляем location
            address_to_geocode = request.start_point.address
            
            # Проверяем есть ли в адресе запятая (признак полного адреса)
            if "," not in address_to_geocode:
                # Адрес неполный - добавляем location
                address_to_geocode = f"{address_to_geocode}, {request.location}"
                logger.info(f"Address incomplete, adding location: {address_to_geocode}")
            
            try:
                start_coords = maps_service._geocode_location(address_to_geocode)
                logger.info(f"Geocoded address to: {start_coords.lat},{start_coords.lng}")
            except HTTPException as e:
                # Если не удалось геокодировать, используем центр города
                logger.warning(f"Failed to geocode address '{address_to_geocode}', using city center instead")
                start_coords = maps_service._geocode_location(request.location)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start_point must have either coordinates (lat, lng) or address"
            )
        
        # 2. Search places by theme (get 3x more than requested for better selection)
        step_time = time.time()
        
        # Adjust search radius based on transport mode
        # Walking: smaller radius (3km), other modes: larger radius (10km)
        if request.transport_mode == "walking":
            search_radius = 3000  # 3km for walking - keep places close
        elif request.transport_mode == "bicycling":
            search_radius = 5000  # 5km for cycling
        else:
            search_radius = 10000  # 10km for driving/transit
        
        logger.info(f"Using search radius: {search_radius}m for transport mode: {request.transport_mode}")
        max_places_to_search = min(request.num_places * 3, 60)
        
        logger.info(f"⏱️ STEP 1: Searching {max_places_to_search} places...")
        center_coords, place_suggestions = maps_service.search_places_by_theme(
            location=f"{start_coords.lat},{start_coords.lng}",
            theme=request.theme,
            radius=search_radius,
            max_results=max_places_to_search
        )
        logger.info(f"⏱️ STEP 1 DONE: {time.time() - step_time:.2f}s")
        
        if len(place_suggestions) < 3:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Not enough places found for theme '{request.theme}' in {request.location}"
            )
        
        logger.info(f"Found {len(place_suggestions)} places for theme {request.theme}")
        
        # Filter by rating (>= 3.5)
        quality_places = [p for p in place_suggestions if (p.rating or 0) >= 3.5]
        if len(quality_places) < 3:
            quality_places = place_suggestions  # Fallback to all if not enough quality places
        
        logger.info(f"Filtered to {len(quality_places)} quality places (rating >= 3.5)")
        
        # 3. Create 3 route variants
        routes = []
        
        # Sort places by distance from start point
        for place in quality_places:
            if place.distance is None:
                place.distance = maps_service._calculate_distance(
                    start_coords.lat, start_coords.lng,
                    place.location.lat, place.location.lng
                )
        
        # IMPORTANT: User requested EXACTLY num_places places
        # All route variants should have the same number of places
        requested_places = min(request.num_places, len(quality_places))
        
        if requested_places < request.num_places:
            logger.warning(
                f"⚠️ Not enough places found! Requested: {request.num_places}, "
                f"Available: {len(quality_places)}, Using: {requested_places}"
            )
        
        # Sort by distance from start
        places_by_distance = sorted(quality_places, key=lambda p: p.distance or float('inf'))
        
        # Sort by rating (best first)
        places_by_rating = sorted(quality_places, key=lambda p: p.rating or 0, reverse=True)
        
        # NEW APPROACH: Create 3 routes with DIFFERENT place selections
        # After building, sort by walking_distance to assign: Facile, Moyen, Difficile
        
        route_configs = [
            {
                "id": "route_variant_1",
                "selection": "closest",  # Closest places = shortest walking
                "num_places": requested_places,
            },
            {
                "id": "route_variant_2", 
                "selection": "best_rated",  # Best rated = medium distance
                "num_places": requested_places,
            },
            {
                "id": "route_variant_3",
                "selection": "furthest_good",  # Good but further = longest walking
                "num_places": requested_places,
            }
        ]
        
        logger.info(f"⏱️ STEP 2: Building {len(route_configs)} route variants...")
        
        # Track used places to ensure variety between routes
        used_place_ids = set()
        
        for idx, config in enumerate(route_configs, 1):
            try:
                route_step_time = time.time()
                logger.info(f"⏱️ STEP 2.{idx}: Building route variant...")
                
                # Filter out already used places (for variety)
                # Keep at least 50% new places in each route
                min_new_places = config["num_places"] // 2
                
                # Available places excluding already used
                available_by_distance = [p for p in places_by_distance if p.google_place_id not in used_place_ids]
                available_by_rating = [p for p in places_by_rating if p.google_place_id not in used_place_ids]
                
                # Select places based on strategy
                if config["selection"] == "closest":
                    # Closest places = shortest walking distance
                    # Prefer unused places, but fill with used if needed
                    selected_places = available_by_distance[:config["num_places"]]
                    if len(selected_places) < config["num_places"]:
                        for p in places_by_distance:
                            if p not in selected_places:
                                selected_places.append(p)
                            if len(selected_places) >= config["num_places"]:
                                break
                    
                elif config["selection"] == "best_rated":
                    # Best rated places (may be further) - PREFER UNUSED
                    selected_places = available_by_rating[:config["num_places"]]
                    if len(selected_places) < config["num_places"]:
                        for p in places_by_rating:
                            if p not in selected_places:
                                selected_places.append(p)
                            if len(selected_places) >= config["num_places"]:
                                break
                    
                elif config["selection"] == "furthest_good":
                    # Good places that are further away - COMPLETELY DIFFERENT
                    # Skip closest ones, take from far end
                    skip_count = min(len(quality_places) // 2, config["num_places"])  # Skip more
                    further_places = [p for p in places_by_distance[skip_count:] if p.google_place_id not in used_place_ids]
                    # Sort these by rating
                    further_by_rating = sorted(further_places, key=lambda p: p.rating or 0, reverse=True)
                    selected_places = further_by_rating[:config["num_places"]]
                    # If not enough, add unused from middle range
                    if len(selected_places) < config["num_places"]:
                        middle_places = places_by_distance[skip_count//2:skip_count]
                        for p in middle_places:
                            if p not in selected_places and p.google_place_id not in used_place_ids:
                                selected_places.append(p)
                            if len(selected_places) >= config["num_places"]:
                                break
                    # Last resort: fill with any remaining
                    if len(selected_places) < config["num_places"]:
                        for p in places_by_distance:
                            if p not in selected_places:
                                selected_places.append(p)
                            if len(selected_places) >= config["num_places"]:
                                break
                else:
                    selected_places = quality_places[:config["num_places"]]
                
                # Mark these places as used for next iterations
                for p in selected_places:
                    used_place_ids.add(p.google_place_id)
                
                # Ensure we have exactly the requested number
                if len(selected_places) != config["num_places"]:
                    logger.warning(
                        f"⚠️ Place count mismatch for {config['name']}: "
                        f"expected {config['num_places']}, got {len(selected_places)}"
                    )
                
                # Convert PlaceSuggestion to Place objects and enrich with photos
                places_with_photos = []
                for place_sugg in selected_places:
                    # Get full place details
                    try:
                        place_details = maps_service.get_place_details(place_sugg.google_place_id)
                    except:
                        # Fallback: create Place from suggestion
                        place_details = Place(
                            google_place_id=place_sugg.google_place_id,
                            name=place_sugg.name,
                            types=place_sugg.types,
                            location=place_sugg.location,
                            address=place_sugg.address,
                            rating=place_sugg.rating
                        )
                    
                    # Get photos from MinIO/Firestore (user-uploaded from partner apps)
                    # Search by place_id AND coordinates for better matching
                    from app.grpc.photo_grpc_service import place_photo_service
                    user_photos = place_photo_service.get_place_photos_by_id_or_coords(
                        place_id=place_sugg.google_place_id,
                        latitude=place_sugg.location.lat if place_sugg.location else None,
                        longitude=place_sugg.location.lng if place_sugg.location else None,
                        max_photos=5
                    )
                    
                    # Get photos from Google (only if we need more)
                    google_photos_needed = max(0, 5 - len(user_photos))
                    google_photos = []
                    if google_photos_needed > 0:
                        google_photos = maps_service.get_place_photos(
                            place_id=place_sugg.google_place_id,
                            max_photos=google_photos_needed + 3  # Get extra in case some fail
                        )
                    
                    # Combine photos - USER PHOTOS FIRST, then Google
                    all_photos = []
                    for url in user_photos:
                        all_photos.append(PlacePhotoSimple(url=url, source="user"))
                    for url in google_photos:
                        if len(all_photos) < 8:  # Limit total photos
                            all_photos.append(PlacePhotoSimple(url=url, source="google"))
                    
                    # Create PlaceWithPhotos (photos field now contains combined list)
                    place_with_photos = PlaceWithPhotos(
                        google_place_id=place_details.google_place_id,
                        name=place_details.name,
                        types=place_details.types,
                        location=place_details.location,
                        address=place_details.address,
                        rating=place_details.rating,
                        user_ratings_total=place_details.user_ratings_total,
                        vicinity=place_details.vicinity,
                        price_level=place_details.price_level,
                        opening_hours=place_details.opening_hours,
                        photos=all_photos  # Combined: user photos FIRST, then Google
                    )
                    places_with_photos.append(place_with_photos)
                
                # Build optimized route (используем выбранный транспорт)
                # Convert PlaceWithPhotos to Place for route optimization
                places_for_route = []
                for p in places_with_photos:
                    places_for_route.append(Place(
                        google_place_id=p.google_place_id,
                        name=p.name,
                        types=p.types,
                        location=p.location,
                        address=p.address,
                        rating=p.rating
                    ))
                
                route_data = maps_service.build_route_with_optimization(
                    start_point=start_coords,
                    places=places_for_route,
                    mode=request.transport_mode
                )
                
                # Calculate MAX price (show highest price level from all places)
                price_levels = [p.price_level for p in places_with_photos if p.price_level is not None]
                if price_levels:
                    max_price_level = max(price_levels)
                    if max_price_level <= 1:
                        avg_price = "$"
                    elif max_price_level <= 2:
                        avg_price = "$$"
                    elif max_price_level <= 3:
                        avg_price = "$$$"
                    else:
                        avg_price = "$$$$"
                else:
                    avg_price = "$"
                
                # Умная градация сложности (scoring system)
                actual_difficulty = calculate_smart_difficulty(
                    walking_distance=route_data["walking_distance"],
                    total_distance=route_data["total_distance"],
                    duration=route_data["duration"],
                    num_places=len(places_with_photos),
                    places=places_with_photos
                )
                
                # Reorder places according to optimized order
                optimized_order = route_data.get("optimized_order", list(range(len(places_with_photos))))
                ordered_places = [places_with_photos[i] for i in optimized_order]
                
                # Convert route_points to LatLng objects
                route_points = [LatLng(**point) for point in route_data["route_points"]]
                
                # Create RouteOption (name will be assigned after sorting)
                route_option = RouteOption(
                    id=config["id"],
                    name="",  # Will be set after sorting
                    total_distance=route_data["total_distance"],
                    walking_distance=route_data["walking_distance"],
                    difficulty=actual_difficulty,
                    avg_price=avg_price,
                    duration=route_data["duration"],
                    num_places=len(ordered_places),
                    route_points=route_points,
                    polyline=route_data["polyline"],
                    places=ordered_places
                )
                
                routes.append(route_option)
                logger.info(
                    f"⏱️ STEP 2.{idx} DONE: {time.time() - route_step_time:.2f}s - "
                    f"{route_data['walking_distance']} walking, difficulty={actual_difficulty}"
                )
                
            except Exception as e:
                logger.error(f"Error creating route {config['id']}: {str(e)}")
                continue
        
        if len(routes) == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate any routes"
            )
        
        # Sort routes by walking distance (shortest first)
        def parse_distance(d: str) -> float:
            """Parse '4.2 km' to float 4.2"""
            try:
                return float(d.replace(" km", "").replace(",", "."))
            except:
                return 0.0
        
        routes.sort(key=lambda r: parse_distance(r.walking_distance))
        
        # Assign names AND difficulty based on walking distance order
        difficulty_names = ["Facile", "Moyen", "Difficile"]
        difficulty_values = ["easy", "moderate", "hard"]  # Sync with name
        difficulty_ids = ["route_facile", "route_moyen", "route_difficile"]
        
        for i, route in enumerate(routes):
            if i < len(difficulty_names):
                route.name = difficulty_names[i]
                route.id = difficulty_ids[i]
                route.difficulty = difficulty_values[i]  # Sync difficulty with name
        
        elapsed_time = time.time() - start_time
        logger.info(
            f"✅ SUCCESS: Generated {len(routes)} route options in {elapsed_time:.2f} seconds"
        )
        
        return RouteGenerationResponse(routes=routes)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating routes: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate routes: {str(e)}"
        )



@router.post(
    "/plan",
    response_model=RouteResponse,
    status_code=status.HTTP_200_OK,
    summary="Plan a trip route (Enhanced with themes and POIs)",
    description="Calculate optimized route with selected places or simple waypoints"
)
async def plan_trip(request: RoutePlanRequest) -> RouteResponse:
    """
    Plan a trip route with thematic POI support
    
    **New workflow:**
    1. User searches places by theme using GET /places/suggest
    2. User selects places from suggestions
    3. This endpoint optimizes route through selected places
    4. Returns route with ordered stops and full place details
    
    **Legacy support:**
    - Still supports simple waypoints (string addresses)
    - Backward compatible with old API usage
    
    Args:
        request: Route planning request with:
            - origin, destination (required)
            - theme (optional)
            - selected_places (optional, list of Place objects)
            - waypoints (optional, legacy string list)
            - optimize_route (default: true)
        
    Returns:
        RouteResponse with route geometry, distance, duration, and ordered stops
    """
    try:
        theme_info = f" (theme: {request.theme})" if request.theme else ""
        logger.info(
            f"Planning route from {request.origin} to {request.destination}{theme_info}"
        )
        
        # Use new Place-based routing if places are provided
        if request.selected_places and len(request.selected_places) > 0:
            logger.info(f"Using {len(request.selected_places)} selected places as waypoints")
            
            route_data = maps_service.get_route_with_places(
                origin=request.origin,
                destination=request.destination,
                places=request.selected_places,
                optimize=request.optimize_route
            )
        
        # Fall back to legacy waypoint-based routing
        else:
            waypoints_count = len(request.waypoints) if request.waypoints else 0
            logger.info(f"Using {waypoints_count} legacy waypoints")
            
            route_data = maps_service.get_route(
                origin=request.origin,
                destination=request.destination,
                waypoints=request.waypoints if request.waypoints and len(request.waypoints) > 0 else None
            )
        
        return RouteResponse(**route_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error planning trip: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to plan trip: {str(e)}"
        )


@router.post(
    "/{trip_id}/photo",
    response_model=PhotoUploadResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload photo to trip (Enhanced with place association)",
    description="Upload a photo to MinIO and associate it with a trip or specific place in Firestore"
)
async def upload_photo(
    trip_id: str,
    file: UploadFile = File(..., description="Photo file to upload"),
    lat: float = Form(..., description="Photo latitude"),
    lon: float = Form(..., description="Photo longitude"),
    user_id: str = Form(..., description="User ID uploading the photo"),
    place_id: Optional[str] = Form(None, description="Google Place ID if photo is for a specific place")
) -> PhotoUploadResponse:
    """
    Upload a photo and associate it with a trip or specific place
    
    **Enhanced functionality:**
    - If `place_id` is provided, photo is attached to that specific place in the trip
    - If `place_id` is not provided:
        - System finds nearest place from trip stops (within 100m)
        - Or attaches to general trip photos
    
    Args:
        trip_id: Unique trip identifier
        file: Photo file to upload
        lat: Photo latitude
        lon: Photo longitude
        user_id: ID of user uploading the photo
        place_id: (Optional) Google Place ID to associate photo with specific stop
        
    Returns:
        PhotoUploadResponse with upload confirmation and place association info
    """
    try:
        place_info = f" for place {place_id}" if place_id else ""
        logger.info(f"Uploading photo for trip {trip_id}{place_info} by user {user_id}")
        
        # Validate file type
        if not file.content_type or not file.content_type.startswith("image/"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file type. Expected image, got {file.content_type}"
            )
        
        # Generate unique object name
        file_extension = file.filename.split(".")[-1] if "." in file.filename else "jpg"
        object_name = f"trips/{trip_id}/{uuid.uuid4()}.{file_extension}"
        
        # Upload to MinIO
        photo_url = await minio_service.upload_file(
            file=file,
            object_name=object_name
        )
        
        logger.info(f"Photo uploaded to MinIO: {photo_url}")
        
        # Create photo metadata
        photo_metadata = PhotoMetadata(
            url=photo_url,
            lat=lat,
            lon=lon,
            user_id=user_id,
            place_id=place_id,
            uploaded_at=datetime.utcnow().isoformat()
        )
        
        # Update Firestore - intelligent place association
        if place_id:
            # Attach to specific place
            firebase_service.add_photo_to_place(
                trip_id=trip_id,
                place_id=place_id,
                photo_data=photo_metadata
            )
            logger.info(f"Photo attached to place {place_id} in trip {trip_id}")
        else:
            # Try to find nearest place or attach to general trip
            associated_place = firebase_service.add_photo_to_trip_smart(
                trip_id=trip_id,
                photo_data=photo_metadata
            )
            if associated_place:
                place_id = associated_place
                logger.info(f"Photo auto-associated with nearest place {place_id}")
            else:
                logger.info(f"Photo added to general trip photos")
        
        return PhotoUploadResponse(
            message="Photo uploaded successfully",
            photo_url=photo_url,
            trip_id=trip_id,
            place_id=place_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading photo: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload photo: {str(e)}"
        )


# ==================== Saved/Liked Routes Endpoints ====================
# NOTE: These endpoints MUST be defined BEFORE /{trip_id} to avoid route conflicts

@router.post(
    "/save",
    response_model=SavedRoute,
    status_code=status.HTTP_201_CREATED,
    summary="Save/like a route",
    description="Save a route to user's favorites"
)
async def save_route(
    request: SaveRouteRequest,
    current_user: dict = Depends(get_current_user)
) -> SavedRoute:
    """
    Save/like a route to user's favorites.
    
    The route will be stored in Firestore under the user's saved routes collection.
    """
    try:
        user_id = current_user["uid"]
        logger.info(f"💾 Saving route for user: {user_id}, location: {request.location}")
        
        # Check if this EXACT route (same type + same location) is already saved
        existing_routes = firebase_service.db.collection("saved_routes")\
            .where("user_id", "==", user_id)\
            .where("route.id", "==", request.route.id)\
            .where("location", "==", request.location)\
            .limit(1)\
            .stream()
        
        for doc in existing_routes:
            logger.info(f"⚠️ Route {request.route.id} for {request.location} already saved by user {user_id}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ce parcours ({request.route.name}) pour {request.location} est déjà enregistré"
            )
        
        # Generate unique ID for saved route
        saved_route_id = str(uuid.uuid4())
        logger.info(f"🆔 Generated route ID: {saved_route_id}")
        
        # Create SavedRoute object
        saved_route = SavedRoute(
            id=saved_route_id,
            user_id=user_id,
            route=request.route,
            saved_at=datetime.utcnow().isoformat(),
            location=request.location,
            theme=request.theme
        )
        logger.info(f"📦 SavedRoute object created")
        
        # Log photos info for debugging
        if request.route.places:
            for i, place in enumerate(request.route.places):
                photo_count = len(place.photos) if place.photos else 0
                logger.info(f"📸 Place {i+1} ({place.name}): {photo_count} photos")
        
        # Save to Firestore
        logger.info(f"💾 Saving to Firestore collection: saved_routes")
        route_data = saved_route.model_dump()
        logger.info(f"📊 Route data keys: {route_data.keys()}")
        firebase_service.db.collection("saved_routes").document(saved_route_id).set(
            route_data
        )
        
        logger.info(f"✅ Route saved successfully: {saved_route_id} for user {user_id}")
        
        return saved_route
    
    except HTTPException:
        # Re-raise HTTP exceptions (like 409 Conflict) as-is
        raise
        
    except Exception as e:
        logger.error(f"❌ Error saving route: {str(e)}")
        logger.exception("Full traceback:")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save route: {str(e)}"
        )


@router.get(
    "/saved",
    response_model=SavedRoutesResponse,
    status_code=status.HTTP_200_OK,
    summary="Get saved routes",
    description="Retrieve all saved/liked routes for the current user"
)
async def get_saved_routes(
    current_user: dict = Depends(get_current_user)
) -> SavedRoutesResponse:
    """
    Get all saved routes for the current user.
    
    Returns a list of routes that the user has liked/saved.
    """
    try:
        user_id = current_user["uid"]
        logger.info(f"🔍 Fetching saved routes for user: {user_id}")
        
        # Query Firestore for user's saved routes
        saved_routes_ref = firebase_service.db.collection("saved_routes")
        logger.info(f"📦 Collection reference created: saved_routes")
        
        # Try with order_by first, fallback to without if index doesn't exist
        try:
            query = saved_routes_ref.where("user_id", "==", user_id).order_by("saved_at", direction=firestore.Query.DESCENDING)
            logger.info(f"📊 Query with order_by created")
            
            saved_routes = []
            for doc in query.stream():
                logger.info(f"📄 Processing document: {doc.id}")
                route_data = doc.to_dict()
                # Log photos info for debugging
                if route_data.get("route") and route_data["route"].get("places"):
                    for i, place in enumerate(route_data["route"]["places"]):
                        photo_count = len(place.get("photos", []))
                        logger.info(f"📸 Loaded place {i+1} ({place.get('name', 'unknown')}): {photo_count} photos")
                saved_routes.append(SavedRoute(**route_data))
            
        except Exception as order_error:
            logger.warning(f"⚠️ Order by failed (may need index): {str(order_error)}")
            logger.info(f"🔄 Falling back to query without order_by")
            
            # Fallback: query without order_by
            query = saved_routes_ref.where("user_id", "==", user_id)
            
            saved_routes = []
            for doc in query.stream():
                logger.info(f"📄 Processing document: {doc.id}")
                route_data = doc.to_dict()
                # Log photos info for debugging
                if route_data.get("route") and route_data["route"].get("places"):
                    for i, place in enumerate(route_data["route"]["places"]):
                        photo_count = len(place.get("photos", []))
                        logger.info(f"📸 Loaded place {i+1} ({place.get('name', 'unknown')}): {photo_count} photos")
                saved_routes.append(SavedRoute(**route_data))
            
            # Sort in Python instead
            saved_routes.sort(key=lambda x: x.saved_at, reverse=True)
        
        logger.info(f"✅ Retrieved {len(saved_routes)} saved routes for user {user_id}")
        
        return SavedRoutesResponse(
            routes=saved_routes,
            total=len(saved_routes)
        )
        
    except Exception as e:
        logger.error(f"❌ Error retrieving saved routes: {str(e)}")
        logger.exception("Full traceback:")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve saved routes: {str(e)}"
        )


@router.delete(
    "/unsave/{route_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove saved route",
    description="Remove a route from user's favorites"
)
async def unsave_route(
    route_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Remove a saved route from user's favorites.
    
    Args:
        route_id: The ID of the saved route to remove
    """
    try:
        user_id = current_user["uid"]
        
        # Get the saved route
        doc_ref = firebase_service.db.collection("saved_routes").document(route_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Saved route {route_id} not found"
            )
        
        # Verify ownership
        route_data = doc.to_dict()
        if route_data.get("user_id") != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only delete your own saved routes"
            )
        
        # Delete the route
        doc_ref.delete()
        
        logger.info(f"Route unsaved: {route_id} for user {user_id}")
        
        return Response(status_code=status.HTTP_204_NO_CONTENT)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error unsaving route: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to unsave route: {str(e)}"
        )


# ==================== Trip CRUD Endpoints ====================

@router.get(
    "/{trip_id}",
    status_code=status.HTTP_200_OK,
    summary="Get trip details",
    description="Retrieve trip information from Firestore"
)
async def get_trip(trip_id: str):
    """
    Get trip details by ID
    
    Args:
        trip_id: Unique trip identifier
        
    Returns:
        Trip data from Firestore
    """
    try:
        trip_data = firebase_service.get_trip(trip_id)
        
        if not trip_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Trip with ID {trip_id} not found"
            )
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=trip_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving trip: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve trip: {str(e)}"
        )


@router.put(
    "/{trip_id}/rating",
    status_code=status.HTTP_200_OK,
    summary="Rate/Like/Save trip",
    description="Update trip rating, like status, or save to favorites"
)
async def rate_trip(
    trip_id: str,
    rating_request: TripRatingRequest,
    current_user: Dict = Depends(get_current_user)
):
    """
    Обновить рейтинг, лайк или сохранение маршрута
    
    Требует авторизации. Пользователь может оценивать только свои маршруты.
    
    Args:
        trip_id: ID маршрута
        rating_request: Данные рейтинга (is_liked, rating, is_saved)
        current_user: Текущий пользователь (из токена)
        
    Returns:
        Обновленные данные маршрута
    """
    try:
        user_id = current_user["uid"]
        
        updated_trip = firebase_service.update_trip_rating(
            trip_id=trip_id,
            user_id=user_id,
            is_liked=rating_request.is_liked,
            rating=rating_request.rating,
            is_saved=rating_request.is_saved
        )
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=updated_trip
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rating trip: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to rate trip: {str(e)}"
        )


@router.get(
    "/user/history",
    response_model=TripListResponse,
    summary="Get user's trip history",
    description="Retrieve all trips for the current user with optional filters"
)
async def get_user_trips(
    current_user: Dict = Depends(get_current_user),
    is_saved: Optional[bool] = None,
    is_liked: Optional[bool] = None,
    theme: Optional[str] = None,
    page: int = 1,
    page_size: int = 10
):
    """
    Получить историю маршрутов пользователя
    
    Требует авторизации.
    
    Args:
        current_user: Текущий пользователь (из токена)
        is_saved: Фильтр по сохраненным
        is_liked: Фильтр по лайкнутым
        theme: Фильтр по теме
        page: Номер страницы (начиная с 1)
        page_size: Количество результатов на странице
        
    Returns:
        Список маршрутов с пагинацией
    """
    try:
        user_id = current_user["uid"]
        
        # Рассчитать offset
        offset = (page - 1) * page_size
        
        trips = firebase_service.get_user_trips(
            user_id=user_id,
            is_saved=is_saved,
            is_liked=is_liked,
            theme=theme,
            limit=page_size,
            offset=offset
        )
        
        # Преобразовать в TripData объекты
        trip_objects = [TripData(**trip) for trip in trips]
        
        return TripListResponse(
            trips=trip_objects,
            total=len(trip_objects),
            page=page,
            page_size=page_size
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving user trips: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve trips: {str(e)}"
        )


@router.delete(
    "/{trip_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete trip",
    description="Delete a trip (only owner can delete)"
)
async def delete_trip(
    trip_id: str,
    current_user: Dict = Depends(get_current_user)
):
    """
    Удалить маршрут
    
    Требует авторизации. Пользователь может удалять только свои маршруты.
    
    Args:
        trip_id: ID маршрута
        current_user: Текущий пользователь (из токена)
        
    Returns:
        Подтверждение удаления
    """
    try:
        user_id = current_user["uid"]
        
        firebase_service.delete_trip(trip_id, user_id)
        
        return {"message": f"Trip {trip_id} deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting trip: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete trip: {str(e)}"
        )


@router.post(
    "/{trip_id}/export",
    status_code=status.HTTP_200_OK,
    summary="Export trip",
    description="Export trip to various formats (JSON, ICS, GPX)"
)
async def export_trip(
    trip_id: str,
    format: ExportFormat,
    include_photos: bool = False,
    current_user: Dict = Depends(get_current_user)
):
    """
    Экспортировать маршрут в указанный формат
    
    Требует авторизации.
    
    Поддерживаемые форматы:
    - JSON: Полные данные маршрута
    - ICS: Календарь с временными слотами
    - GPX: GPS навигация
    
    Args:
        trip_id: ID маршрута
        format: Формат экспорта (json/ics/gpx)
        include_photos: Включить фото (только для JSON)
        current_user: Текущий пользователь (из токена)
        
    Returns:
        Файл в указанном формате
    """
    try:
        user_id = current_user["uid"]
        
        # Получить данные маршрута
        trip_data_dict = firebase_service.get_trip(trip_id)
        
        if not trip_data_dict:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Trip {trip_id} not found"
            )
        
        # Проверить владельца
        if trip_data_dict.get("user_id") != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only export your own trips"
            )
        
        # Преобразовать в TripData
        trip_data = TripData(**trip_data_dict)
        
        # Экспортировать
        exported_content = export_service.export_trip(
            trip_data=trip_data,
            format=format,
            include_photos=include_photos
        )
        
        # Определить MIME type и имя файла
        mime_type = export_service.get_mime_type(format)
        filename = export_service.get_export_filename(trip_id, format)
        
        # Вернуть файл
        return Response(
            content=exported_content,
            media_type=mime_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting trip: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export trip: {str(e)}"
        )
