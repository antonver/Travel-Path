"""
Place (POI) discovery endpoints for thematic trip planning
"""
from fastapi import APIRouter, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from app.models.schemas import (
    PlaceSearchRequest,
    PlaceSearchResponse,
    Place,
    TripTheme
)
from app.services.maps_service import maps_service
from pydantic import BaseModel
from typing import List
import logging
import httpx

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/places",
    tags=["places"]
)


# ============== Autocomplete Models ==============

class AutocompleteResponse(BaseModel):
    """Response model for place autocomplete"""
    suggestions: List[str]
    

# ============== Endpoints ==============


@router.get(
    "/suggest",
    response_model=PlaceSearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Get place suggestions by theme",
    description="Search for places (POIs) based on a theme and location using Google Places API"
)
async def suggest_places(
    location: str = Query(
        ...,
        description="Search center location (address or 'lat,lng')",
        example="New York, NY"
    ),
    theme: TripTheme = Query(
        ...,
        description="Theme category for place suggestions"
    ),
    radius: int = Query(
        default=5000,
        ge=100,
        le=50000,
        description="Search radius in meters (100-50000)"
    ),
    max_results: int = Query(
        default=20,
        ge=1,
        le=60,
        description="Maximum number of results"
    )
) -> PlaceSearchResponse:
    """
    Get place suggestions based on theme and location
    
    Themes map to specific Google Places types:
    - **culture**: museum, art_gallery, church, tourist_attraction
    - **gastronomy**: restaurant, cafe, bakery, bar
    - **nature**: park, natural_feature, campground
    - **leisure**: amusement_park, bowling_alley, movie_theater, shopping_mall
    - **mix**: general tourist attractions and points of interest
    
    Args:
        location: Search center (address or coordinates)
        theme: Trip theme category
        radius: Search radius in meters
        max_results: Maximum number of results to return
        
    Returns:
        PlaceSearchResponse with list of suggested places
        
    Example:
        GET /places/suggest?location=Paris,France&theme=culture&radius=3000
    """
    try:
        logger.info(
            f"Searching places for theme '{theme}' near '{location}' "
            f"with radius {radius}m"
        )
        
        # Search places using Google Places API
        center_coords, places = maps_service.search_places_by_theme(
            location=location,
            theme=theme,
            radius=radius,
            max_results=max_results
        )
        
        response = PlaceSearchResponse(
            status="OK",
            theme=theme,
            location=center_coords,
            places=places,
            total_results=len(places)
        )
        
        logger.info(f"Found {len(places)} places for theme '{theme}'")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error suggesting places: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to suggest places: {str(e)}"
        )


@router.get(
    "/autocomplete",
    response_model=AutocompleteResponse,
    status_code=status.HTTP_200_OK,
    summary="Autocomplete city/place names",
    description="Get autocomplete suggestions for cities and places (for input fields)"
)
async def autocomplete_places(
    query: str = Query(
        ...,
        min_length=2,
        description="Search query (minimum 2 characters)",
        example="Pari"
    ),
    language: str = Query(
        default="fr",
        description="Language code for results",
        example="fr"
    )
) -> AutocompleteResponse:
    """
    Get autocomplete suggestions for cities and places
    
    This endpoint is designed for input field autocomplete functionality.
    It returns city/locality names based on the user's query using Google Places API.
    
    Args:
        query: Search query (e.g., "Pari" → "Paris, France")
        language: Language code for results (default: "fr")
        
    Returns:
        AutocompleteResponse with list of suggestion strings
        
    Example:
        GET /places/autocomplete?query=Pari&language=fr
        Response: {"suggestions": ["Paris, France", "Paris, Texas, États-Unis", ...]}
    """
    try:
        logger.info(f"Autocomplete search for: '{query}' (language: {language})")
        
        # Use maps_service to get autocomplete suggestions
        suggestions = maps_service.get_autocomplete_suggestions(
            query=query,
            language=language
        )
        
        logger.info(f"Found {len(suggestions)} autocomplete suggestions")
        
        return AutocompleteResponse(suggestions=suggestions)
        
    except Exception as e:
        logger.error(f"Error in autocomplete: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get autocomplete suggestions: {str(e)}"
        )


@router.get(
    "/photo-proxy",
    summary="Proxy Google Places photos",
    description="Proxy endpoint to fetch photos from Google Places API with proper authentication"
)
async def photo_proxy(
    photo_name: str = Query(
        ...,
        description="Full photo name from Places API (e.g. 'places/{place_id}/photos/{photo_id}')",
        example="places/ChIJofpYVAivthIRXw08nwXMzco/photos/ABC123..."
    ),
    max_width: int = Query(
        default=800,
        ge=100,
        le=2000,
        description="Maximum width in pixels"
    )
):
    """
    Proxy для загрузки фотографий из Google Places API.
    
    Решает проблему с прямым доступом Android клиента к Google фотографиям.
    Backend скачивает фото с правильной авторизацией и передает клиенту.
    """
    try:
        from app.core.config import settings
        
        # Build Google Places API URL
        url = f"https://places.googleapis.com/v1/{photo_name}/media?maxWidthPx={max_width}"
        
        logger.info(f"Proxying photo: {photo_name[:50]}... (max_width={max_width})")
        
        # Fetch from Google with proper headers
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url,
                headers={
                    "X-Goog-Api-Key": settings.MAPS_API_KEY
                },
                follow_redirects=True
            )
        
        if response.status_code != 200:
            logger.warning(f"Google Photos API returned {response.status_code} for {photo_name[:50]}...")
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Failed to fetch photo from Google: {response.status_code}"
            )
        
        # Return image as StreamingResponse
        return StreamingResponse(
            iter([response.content]),
            media_type=response.headers.get("content-type", "image/jpeg"),
            headers={
                "Cache-Control": "public, max-age=86400",  # Cache for 24 hours
                "Content-Length": str(len(response.content))
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error proxying photo: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to proxy photo: {str(e)}"
        )


@router.get(
    "/{place_id}",
    response_model=Place,
    status_code=status.HTTP_200_OK,
    summary="Get detailed place information",
    description="Retrieve full details about a specific place by its Google Place ID"
)
async def get_place_details(place_id: str) -> Place:
    """
    Get detailed information about a specific place
    
    Args:
        place_id: Google Place ID
        
    Returns:
        Place object with full details including photos, ratings, and opening hours
        
    Example:
        GET /places/ChIJN1t_tDeuEmsRUsoyG83frY4
    """
    try:
        logger.info(f"Fetching details for place: {place_id}")
        
        place = maps_service.get_place_details(place_id)
        
        logger.info(f"Retrieved details for place: {place.name}")
        
        return place
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting place details: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get place details: {str(e)}"
        )


@router.post(
    "/search",
    response_model=PlaceSearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Search places with detailed parameters",
    description="Advanced place search with POST body for complex queries"
)
async def search_places(request: PlaceSearchRequest) -> PlaceSearchResponse:
    """
    Search for places using POST request body
    
    This is an alternative to the GET /suggest endpoint that allows
    for more complex query parameters in the request body.
    
    Args:
        request: PlaceSearchRequest with search parameters
        
    Returns:
        PlaceSearchResponse with list of suggested places
    """
    try:
        logger.info(
            f"Searching places (POST) for theme '{request.theme}' "
            f"near '{request.location}'"
        )
        
        center_coords, places = maps_service.search_places_by_theme(
            location=request.location,
            theme=request.theme,
            radius=request.radius,
            max_results=request.max_results
        )
        
        response = PlaceSearchResponse(
            status="OK",
            theme=request.theme,
            location=center_coords,
            places=places,
            total_results=len(places)
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching places: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search places: {str(e)}"
        )

