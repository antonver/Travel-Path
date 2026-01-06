"""
Weather API endpoints
"""

from fastapi import APIRouter, Query, HTTPException, status
from typing import Optional
import logging

from app.services.weather_service import weather_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/weather",
    tags=["weather"]
)


@router.get(
    "/current",
    status_code=status.HTTP_200_OK,
    summary="Get current weather",
    description="Get current weather information for a location"
)
async def get_current_weather(
    location: Optional[str] = Query(
        None,
        description="Location name (e.g., 'Montpellier,FR' or 'Paris')"
    ),
    lat: Optional[float] = Query(
        None,
        description="Latitude",
        ge=-90,
        le=90
    ),
    lon: Optional[float] = Query(
        None,
        description="Longitude",
        ge=-180,
        le=180
    ),
    units: str = Query(
        "metric",
        description="Temperature units: metric (°C), imperial (°F), or standard (K)"
    )
):
    """
    Get current weather for a specific location.
    
    You can specify location by:
    - City name: `location=Montpellier,FR`
    - Coordinates: `lat=43.6&lon=3.88`
    
    Example response:
    ```json
    {
      "location": {
        "name": "Montpellier",
        "country": "FR",
        "coordinates": {"lat": 43.61, "lon": 3.88}
      },
      "current": {
        "temp": 22.5,
        "feels_like": 21.8,
        "humidity": 65,
        "description": "clear sky",
        "icon": "01d",
        "wind_speed": 3.5
      }
    }
    ```
    """
    try:
        if not location and (lat is None or lon is None):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either 'location' or both 'lat' and 'lon' must be provided"
            )
        
        weather_data = weather_service.get_current_weather(
            location=location,
            lat=lat,
            lon=lon,
            units=units
        )
        
        return {
            "status": "success",
            "data": weather_data
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error fetching weather: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch weather data: {str(e)}"
        )


@router.get(
    "/forecast",
    status_code=status.HTTP_200_OK,
    summary="Get weather forecast",
    description="Get 5-day weather forecast (3-hour intervals)"
)
async def get_weather_forecast(
    location: Optional[str] = Query(
        None,
        description="Location name (e.g., 'Montpellier,FR')"
    ),
    lat: Optional[float] = Query(
        None,
        description="Latitude",
        ge=-90,
        le=90
    ),
    lon: Optional[float] = Query(
        None,
        description="Longitude",
        ge=-180,
        le=180
    ),
    units: str = Query(
        "metric",
        description="Temperature units"
    ),
    days: int = Query(
        5,
        description="Number of days to forecast (1-5)",
        ge=1,
        le=5
    )
):
    """
    Get weather forecast for up to 5 days.
    
    Returns forecast in 3-hour intervals.
    
    Example response:
    ```json
    {
      "location": {
        "name": "Montpellier",
        "country": "FR"
      },
      "forecast": [
        {
          "dt": 1640001600,
          "dt_txt": "2024-12-20 12:00:00",
          "temp": 18.5,
          "description": "light rain",
          "pop": 0.6
        }
      ]
    }
    ```
    """
    try:
        if not location and (lat is None or lon is None):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either 'location' or both 'lat' and 'lon' must be provided"
            )
        
        # Calculate number of 3-hour intervals (8 per day)
        cnt = days * 8
        
        forecast_data = weather_service.get_forecast(
            location=location,
            lat=lat,
            lon=lon,
            units=units,
            cnt=cnt
        )
        
        return {
            "status": "success",
            "data": forecast_data
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error fetching forecast: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch forecast data: {str(e)}"
        )

