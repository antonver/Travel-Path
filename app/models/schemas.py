"""
Pydantic models for request and response validation
"""
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


# ==================== Enums ====================

class TripTheme(str, Enum):
    """Trip theme categories"""
    CULTURE = "culture"
    GASTRONOMY = "gastronomy"
    NATURE = "nature"
    LEISURE = "leisure"
    MIX = "mix"


class EffortLevel(str, Enum):
    """Physical effort level for trip planning"""
    VERY_EASY = "very_easy"  # Для пожилых людей, инвалидов
    EASY = "easy"  # Для детей, спокойный темп
    MODERATE = "moderate"  # Средний уровень активности
    HARD = "hard"  # Спортивные, активные люди


class WeatherSensitivity(str, Enum):
    """Weather sensitivity preferences"""
    LOW = "low"  # Не зависит от погоды
    MODERATE = "moderate"  # Предпочитает хорошую погоду
    HIGH = "high"  # Очень чувствителен к погоде (холод/жара)


class TimeOfDay(str, Enum):
    """Time slots for activities"""
    MORNING = "morning"  # 9:00-12:00
    AFTERNOON = "afternoon"  # 12:00-17:00
    EVENING = "evening"  # 17:00-21:00


# ==================== Location Models ====================

class LatLng(BaseModel):
    """Latitude and Longitude coordinates"""
    lat: float = Field(..., description="Latitude")
    lng: float = Field(..., description="Longitude")
    
    class Config:
        populate_by_name = True


class Waypoint(BaseModel):
    """Waypoint model for route planning"""
    lat: float = Field(..., description="Latitude")
    lon: float = Field(..., description="Longitude", alias="lng")
    
    class Config:
        populate_by_name = True


class PhotoLocation(BaseModel):
    """Photo location data"""
    lat: float = Field(..., description="Photo latitude")
    lon: float = Field(..., description="Photo longitude")


# ==================== Photo Models ====================

class PlacePhoto(BaseModel):
    """Photo associated with a specific place"""
    url: str = Field(..., description="Photo URL")
    attribution: Optional[str] = Field(None, description="Photo attribution")
    width: Optional[int] = Field(None, description="Photo width")
    height: Optional[int] = Field(None, description="Photo height")


class PhotoMetadata(BaseModel):
    """Photo metadata stored in Firestore"""
    url: str = Field(..., description="MinIO URL to the photo")
    lat: float = Field(..., description="Photo latitude")
    lon: float = Field(..., description="Photo longitude")
    user_id: str = Field(..., description="User ID who uploaded the photo")
    place_id: Optional[str] = Field(None, description="Google Place ID if photo is associated with a place")
    uploaded_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Upload timestamp"
    )


class PhotoUploadResponse(BaseModel):
    """Response after photo upload"""
    message: str = Field(..., description="Success message")
    photo_url: str = Field(..., description="URL to the uploaded photo")
    trip_id: str = Field(..., description="Trip ID")
    place_id: Optional[str] = Field(None, description="Place ID if photo was attached to a specific place")


# ==================== Budget Models ====================

class BudgetRange(BaseModel):
    """Budget range for trip planning"""
    min_budget: float = Field(..., ge=0, description="Minimum budget in EUR")
    max_budget: float = Field(..., ge=0, description="Maximum budget in EUR")
    
    @validator("max_budget")
    def validate_max_budget(cls, v, values):
        if "min_budget" in values and v < values["min_budget"]:
            raise ValueError("max_budget must be >= min_budget")
        return v


# ==================== Time Slot Models ====================

class TimeSlot(BaseModel):
    """Time slot for visiting a place"""
    place_id: str = Field(..., description="Google Place ID")
    place_name: str = Field(..., description="Place name")
    time_of_day: TimeOfDay = Field(..., description="Time slot category")
    start_time: str = Field(..., description="Suggested start time (HH:MM)")
    end_time: str = Field(..., description="Suggested end time (HH:MM)")
    duration_minutes: int = Field(..., description="Estimated visit duration in minutes")
    
    class Config:
        json_schema_extra = {
            "example": {
                "place_id": "ChIJ...",
                "place_name": "Musée Fabre",
                "time_of_day": "morning",
                "start_time": "09:30",
                "end_time": "11:30",
                "duration_minutes": 120
            }
        }


# ==================== User Profile Models ====================

class UserProfile(BaseModel):
    """User profile with preferences"""
    user_id: str = Field(..., description="Firebase User ID")
    display_name: Optional[str] = Field(None, description="User display name")
    email: Optional[str] = Field(None, description="User email")
    
    # Preferences
    default_effort_level: EffortLevel = Field(
        default=EffortLevel.MODERATE,
        description="Default physical effort level"
    )
    weather_sensitivity: WeatherSensitivity = Field(
        default=WeatherSensitivity.MODERATE,
        description="Weather sensitivity"
    )
    preferred_themes: List[TripTheme] = Field(
        default_factory=list,
        description="Preferred trip themes"
    )
    
    # Personal info
    age_range: Optional[str] = Field(None, description="Age range (18-25, 25-35, etc)")
    has_children: bool = Field(default=False, description="Traveling with children")
    is_senior: bool = Field(default=False, description="Senior citizen (60+)")
    has_disabilities: bool = Field(default=False, description="Has mobility restrictions")
    
    created_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Profile creation timestamp"
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Last update timestamp"
    )


class UserProfileUpdate(BaseModel):
    """Update user profile (all fields optional)"""
    display_name: Optional[str] = None
    default_effort_level: Optional[EffortLevel] = None
    weather_sensitivity: Optional[WeatherSensitivity] = None
    preferred_themes: Optional[List[TripTheme]] = None
    age_range: Optional[str] = None
    has_children: Optional[bool] = None
    is_senior: Optional[bool] = None
    has_disabilities: Optional[bool] = None


# ==================== Place (POI) Models ====================
# NOTE: These must be defined before RoutePlanRequest and RouteResponse use them

class Place(BaseModel):
    """Point of Interest (Place) model"""
    google_place_id: str = Field(..., description="Google Place ID")
    name: str = Field(..., description="Place name")
    types: List[str] = Field(default_factory=list, description="Place types from Google")
    location: LatLng = Field(..., description="Place coordinates")
    address: Optional[str] = Field(None, description="Formatted address")
    rating: Optional[float] = Field(None, description="Google rating (1-5)")
    user_ratings_total: Optional[int] = Field(None, description="Number of ratings")
    photos: List[PlacePhoto] = Field(
        default_factory=list,
        description="Photos from Google Places"
    )
    user_photos: List[PhotoMetadata] = Field(
        default_factory=list,
        description="User-uploaded photos for this place"
    )
    vicinity: Optional[str] = Field(None, description="Vicinity/neighborhood")
    price_level: Optional[int] = Field(None, description="Price level (0-4)")
    opening_hours: Optional[Dict[str, Any]] = Field(None, description="Opening hours info")
    
    # NEW: Visit duration and timing
    estimated_visit_duration: Optional[int] = Field(
        None,
        description="Estimated visit duration in minutes"
    )
    suggested_time_slot: Optional[TimeOfDay] = Field(
        None,
        description="Suggested time of day to visit"
    )
    
    # NEW: Accessibility and crowd info
    wheelchair_accessible: Optional[bool] = Field(None, description="Wheelchair accessible")
    current_crowd_level: Optional[str] = Field(None, description="Current crowd level (low/moderate/high)")
    
    # NEW: Cost estimation
    estimated_cost: Optional[float] = Field(None, description="Estimated cost per person in EUR")
    
    class Config:
        json_schema_extra = {
            "example": {
                "google_place_id": "ChIJN1t_tDeuEmsRUsoyG83frY4",
                "name": "Google Sydney",
                "types": ["establishment", "point_of_interest"],
                "location": {"lat": -33.8670522, "lng": 151.1957362},
                "address": "48 Pirrama Rd, Pyrmont NSW 2009, Australia",
                "rating": 4.5,
                "user_ratings_total": 1234
            }
        }


class PlaceSuggestion(BaseModel):
    """Simplified place suggestion for initial search results"""
    google_place_id: str = Field(..., description="Google Place ID")
    name: str = Field(..., description="Place name")
    types: List[str] = Field(default_factory=list, description="Place types")
    location: LatLng = Field(..., description="Place coordinates")
    address: Optional[str] = Field(None, description="Formatted address")
    rating: Optional[float] = Field(None, description="Google rating")
    distance: Optional[float] = Field(None, description="Distance from search center in meters")


# ==================== Route Planning Models ====================

class RoutePlanRequest(BaseModel):
    """Request model for trip route planning (Enhanced with themes)"""
    origin: str = Field(..., description="Starting location (address or lat,lng)")
    destination: str = Field(..., description="Destination location (address or lat,lng)")
    theme: Optional[TripTheme] = Field(None, description="Trip theme")
    
    # Legacy support
    waypoints: Optional[List[str]] = Field(
        default=None,
        description="[Legacy] Simple waypoints (addresses or lat,lng)"
    )
    
    # New structure - selected places
    selected_places: Optional[List[Place]] = Field(
        default=None,
        description="Selected POIs to visit (from place suggestions)"
    )
    
    optimize_route: bool = Field(
        default=True,
        description="Whether to optimize the order of stops"
    )
    
    # NEW: Budget and duration
    budget: Optional[BudgetRange] = Field(
        None,
        description="Budget range for the trip"
    )
    trip_duration_days: int = Field(
        default=1,
        ge=1,
        le=30,
        description="Trip duration in days"
    )
    
    # NEW: Effort and preferences
    effort_level: EffortLevel = Field(
        default=EffortLevel.MODERATE,
        description="Desired physical effort level"
    )
    weather_sensitive: bool = Field(
        default=False,
        description="Consider weather conditions in planning"
    )
    
    # NEW: Time preferences
    preferred_start_time: Optional[str] = Field(
        None,
        description="Preferred start time (HH:MM)"
    )
    include_time_slots: bool = Field(
        default=True,
        description="Generate time slots for each place"
    )
    
    @validator("waypoints", pre=True)
    def validate_waypoints(cls, v):
        """Ensure waypoints is a list even if empty"""
        if v is None:
            return []
        return v
    
    @validator("selected_places", pre=True)
    def validate_selected_places(cls, v):
        """Ensure selected_places is a list even if empty"""
        if v is None:
            return []
        return v


class RouteResponse(BaseModel):
    """Response model for route planning (Enhanced)"""
    status: str = Field(..., description="API status")
    distance: Optional[str] = Field(None, description="Total distance")
    duration: Optional[str] = Field(None, description="Total duration")
    polyline: Optional[str] = Field(None, description="Encoded polyline")
    route_points: Optional[List[Dict[str, float]]] = Field(
        None,
        description="Decoded route points"
    )
    legs: Optional[List[Dict[str, Any]]] = Field(None, description="Route legs")
    optimized_order: Optional[List[int]] = Field(
        None,
        description="Optimized waypoint order (indices)"
    )
    stops: Optional[List[Place]] = Field(
        None,
        description="Ordered stops with full place details"
    )
    
    # NEW: Time slots and cost
    time_slots: Optional[List[TimeSlot]] = Field(
        None,
        description="Suggested time slots for each stop"
    )
    total_estimated_cost: Optional[float] = Field(
        None,
        description="Total estimated cost in EUR"
    )
    trip_id: Optional[str] = Field(None, description="Created trip ID")


# ==================== Place Search Models ====================

class PlaceSearchRequest(BaseModel):
    """Request model for place suggestions"""
    location: str = Field(
        ...,
        description="Search center location (lat,lng or address)"
    )
    theme: TripTheme = Field(..., description="Theme to search for")
    radius: int = Field(
        default=5000,
        ge=100,
        le=50000,
        description="Search radius in meters (100-50000)"
    )
    max_results: int = Field(
        default=20,
        ge=1,
        le=60,
        description="Maximum number of results to return"
    )


class PlaceSearchResponse(BaseModel):
    """Response model for place suggestions"""
    status: str = Field(..., description="Search status")
    theme: TripTheme = Field(..., description="Search theme")
    location: LatLng = Field(..., description="Search center coordinates")
    places: List[PlaceSuggestion] = Field(
        default_factory=list,
        description="List of suggested places"
    )
    total_results: int = Field(..., description="Total number of results found")


# ==================== Trip Models ====================

class TripData(BaseModel):
    """Trip data model for Firestore (Enhanced with themes and stops)"""
    trip_id: str = Field(..., description="Unique trip identifier")
    user_id: str = Field(..., description="User who created the trip")
    origin: str = Field(..., description="Trip origin")
    destination: str = Field(..., description="Trip destination")
    theme: Optional[TripTheme] = Field(None, description="Trip theme")
    
    # Legacy support - keep waypoints for backward compatibility
    waypoints: List[str] = Field(default_factory=list, description="[Legacy] Simple waypoints")
    
    # New structure - POI-based stops
    stops: List[Place] = Field(
        default_factory=list,
        description="Detailed stops (Places) along the route"
    )
    
    route_polyline: Optional[str] = Field(None, description="Encoded route polyline")
    
    # Legacy photo list (not associated with specific places)
    photos: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="[Legacy] General trip photos"
    )
    
    distance: Optional[str] = Field(None, description="Total trip distance")
    duration: Optional[str] = Field(None, description="Total trip duration")
    
    # NEW: Budget and effort
    budget_range: Optional[BudgetRange] = Field(None, description="Budget range")
    estimated_cost: Optional[float] = Field(None, description="Estimated total cost in EUR")
    effort_level: Optional[EffortLevel] = Field(None, description="Physical effort level")
    trip_duration_days: int = Field(default=1, description="Trip duration in days")
    
    # NEW: Time slots
    time_slots: List[TimeSlot] = Field(
        default_factory=list,
        description="Time slots for each stop"
    )
    
    # NEW: User interactions
    is_liked: Optional[bool] = Field(None, description="User liked this trip")
    is_saved: bool = Field(default=False, description="Saved to user's favorites")
    rating: Optional[int] = Field(None, ge=1, le=5, description="User rating (1-5)")
    
    created_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Creation timestamp"
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Last update timestamp"
    )


# ==================== Trip Interaction Models ====================

class TripRatingRequest(BaseModel):
    """Request to rate/like a trip"""
    is_liked: Optional[bool] = Field(None, description="Like (true) or dislike (false)")
    rating: Optional[int] = Field(None, ge=1, le=5, description="Rating 1-5")
    is_saved: Optional[bool] = Field(None, description="Save to favorites")


class TripListResponse(BaseModel):
    """Response with list of trips"""
    trips: List[TripData] = Field(default_factory=list, description="List of trips")
    total: int = Field(..., description="Total number of trips")
    page: int = Field(default=1, description="Current page")
    page_size: int = Field(default=10, description="Items per page")


class TripFilterRequest(BaseModel):
    """Filter trips by criteria"""
    theme: Optional[TripTheme] = Field(None, description="Filter by theme")
    is_saved: Optional[bool] = Field(None, description="Only saved trips")
    is_liked: Optional[bool] = Field(None, description="Only liked trips")
    min_rating: Optional[int] = Field(None, ge=1, le=5, description="Minimum rating")
    from_date: Optional[str] = Field(None, description="From date (ISO format)")
    to_date: Optional[str] = Field(None, description="To date (ISO format)")


# ==================== Export Models ====================

class ExportFormat(str, Enum):
    """Export format options"""
    PDF = "pdf"
    ICS = "ics"  # Calendar format
    GPX = "gpx"  # GPS exchange format
    JSON = "json"


class ExportRequest(BaseModel):
    """Request to export a trip"""
    trip_id: str = Field(..., description="Trip ID to export")
    format: ExportFormat = Field(..., description="Export format")
    include_photos: bool = Field(default=False, description="Include photos in export")


class ExportResponse(BaseModel):
    """Response with export file URL"""
    status: str = Field(..., description="Export status")
    download_url: str = Field(..., description="URL to download the exported file")
    format: ExportFormat = Field(..., description="Export format")
    expires_at: Optional[str] = Field(None, description="URL expiration time")


# ==================== Route Generation Models (New Architecture) ====================

class StartPoint(BaseModel):
    """Starting point - can be coordinates or address"""
    lat: Optional[float] = Field(None, description="Latitude (if using coordinates)")
    lng: Optional[float] = Field(None, description="Longitude (if using coordinates)")
    address: Optional[str] = Field(None, description="Address (if using address search)")
    
    @validator("address")
    def validate_start_point(cls, v, values):
        """Ensure either coordinates or address is provided"""
        if v is None and (values.get("lat") is None or values.get("lng") is None):
            raise ValueError("Either coordinates (lat, lng) or address must be provided")
        return v


class RouteGenerationRequest(BaseModel):
    """Request to generate 3 route options"""
    location: str = Field(..., description="City or area (e.g., 'Montpellier, France')")
    start_point: StartPoint = Field(..., description="Starting point (coordinates or address)")
    theme: TripTheme = Field(..., description="Trip theme")
    num_places: int = Field(..., ge=1, le=20, description="Desired number of places (1-20)")
    transport_mode: str = Field(
        default="driving",
        description="Transportation mode: 'walking', 'driving', 'transit', 'bicycling'"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "location": "Montpellier, France",
                "start_point": {
                    "lat": 43.6117881,
                    "lng": 3.8801634
                },
                "theme": "culture",
                "num_places": 5,
                "transport_mode": "driving"
            }
        }


class PlacePhotoSimple(BaseModel):
    """Simplified photo model for route generation"""
    url: str = Field(..., description="Photo URL (from MinIO or Google)")
    source: str = Field(default="unknown", description="Photo source: 'user' or 'google'")


class PlaceWithPhotos(BaseModel):
    """Place with photos - used in route generation responses"""
    # Place fields (copied, not inherited, to allow overriding photos)
    google_place_id: str = Field(..., description="Google Places API ID")
    name: str = Field(..., description="Place name")
    types: List[str] = Field(default_factory=list, description="Place types")
    location: Optional[LatLng] = Field(None, description="Place coordinates")
    address: Optional[str] = Field(None, description="Formatted address")
    rating: Optional[float] = Field(None, description="Average rating")
    user_ratings_total: Optional[int] = Field(None, description="Total number of ratings")
    vicinity: Optional[str] = Field(None, description="Simplified address")
    price_level: Optional[int] = Field(None, description="Price level 0-4")
    opening_hours: Optional[dict] = Field(None, description="Opening hours")
    
    # Photos - combined list with user photos FIRST
    photos: List[PlacePhotoSimple] = Field(
        default_factory=list,
        description="Combined photos: user-uploaded first, then Google"
    )


class RouteOption(BaseModel):
    """One of 3 route options (short/medium/long)"""
    id: str = Field(..., description="Route ID (e.g., 'route_1_easy')")
    name: str = Field(..., description="Route name (e.g., 'Short Route')")
    total_distance: str = Field(..., description="Total distance (e.g., '4.2 km')")
    walking_distance: str = Field(..., description="Walking distance (e.g., '2.1 km')")
    difficulty: str = Field(..., description="Difficulty: 'easy', 'moderate', 'hard'")
    avg_price: str = Field(..., description="Average price: '$', '$$', '$$$'")
    duration: str = Field(..., description="Estimated duration (e.g., '2h 30m')")
    num_places: int = Field(..., description="Number of places in route")
    route_points: List[LatLng] = Field(..., description="Decoded route coordinates")
    polyline: str = Field(..., description="Encoded polyline string")
    places: List[PlaceWithPhotos] = Field(..., description="Ordered list of places with photos")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "route_1_easy",
                "name": "Short Route",
                "total_distance": "4.2 km",
                "walking_distance": "2.1 km",
                "difficulty": "easy",
                "avg_price": "$",
                "duration": "2h 30m",
                "num_places": 4,
                "route_points": [
                    {"lat": 43.611, "lng": 3.880},
                    {"lat": 43.612, "lng": 3.881}
                ],
                "polyline": "encoded_string",
                "places": []
            }
        }


class RouteGenerationResponse(BaseModel):
    """Response with 3 route options"""
    routes: List[RouteOption] = Field(..., description="3 route options (easy/moderate/hard)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "routes": [
                    {"id": "route_1_easy", "name": "Short Route", "num_places": 4},
                    {"id": "route_2_moderate", "name": "Medium Route", "num_places": 6},
                    {"id": "route_3_hard", "name": "Long Route", "num_places": 8}
                ]
            }
        }


# ==================== Saved Routes Models ====================

class SavedRoute(BaseModel):
    """Saved/liked route with metadata"""
    id: str = Field(..., description="Unique saved route ID")
    user_id: str = Field(..., description="User ID (from Firebase)")
    route: RouteOption = Field(..., description="The saved route data")
    saved_at: str = Field(..., description="ISO timestamp when saved")
    location: str = Field(..., description="Location/city of the route")
    theme: Optional[str] = Field(None, description="Trip theme")


class SaveRouteRequest(BaseModel):
    """Request to save a route"""
    route: RouteOption = Field(..., description="Route to save")
    location: str = Field(..., description="Location/city")
    theme: Optional[str] = Field(None, description="Trip theme")


class SavedRoutesResponse(BaseModel):
    """Response with list of saved routes"""
    routes: List[SavedRoute] = Field(..., description="List of saved routes")
    total: int = Field(..., description="Total number of saved routes")


# ==================== Error Models ====================

class ErrorResponse(BaseModel):
    """Standard error response"""
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Detailed error information")
