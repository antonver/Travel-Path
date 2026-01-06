"""
Weather Service using OpenWeatherMap API
Google doesn't have a dedicated Weather API, so we use OpenWeatherMap instead
"""

import requests
from typing import Dict, Any, Optional
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


class WeatherService:
    """Service for fetching weather information"""
    
    BASE_URL = "https://api.openweathermap.org/data/2.5"
    
    def __init__(self):
        """Initialize weather service"""
        self.api_key = getattr(settings, 'WEATHER_API_KEY', None)
        if not self.api_key:
            logger.warning("WEATHER_API_KEY not configured. Weather endpoints will not work.")
    
    def get_current_weather(
        self, 
        location: str = None,
        lat: float = None, 
        lon: float = None,
        units: str = "metric"
    ) -> Dict[str, Any]:
        """
        Get current weather for a location
        
        Args:
            location: City name (e.g., "Montpellier,FR")
            lat: Latitude
            lon: Longitude
            units: Temperature units (metric, imperial, standard)
        
        Returns:
            Weather data dictionary
        """
        if not self.api_key:
            raise ValueError("WEATHER_API_KEY not configured")
        
        params = {
            "appid": self.api_key,
            "units": units
        }
        
        # Use coordinates if provided, otherwise use location name
        if lat is not None and lon is not None:
            params["lat"] = lat
            params["lon"] = lon
        elif location:
            params["q"] = location
        else:
            raise ValueError("Either location or (lat, lon) must be provided")
        
        try:
            response = requests.get(
                f"{self.BASE_URL}/weather",
                params=params,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            # Parse and format the response
            weather_info = {
                "location": {
                    "name": data.get("name", "Unknown"),
                    "country": data.get("sys", {}).get("country", ""),
                    "coordinates": {
                        "lat": data.get("coord", {}).get("lat"),
                        "lon": data.get("coord", {}).get("lon")
                    }
                },
                "current": {
                    "temp": data.get("main", {}).get("temp"),
                    "feels_like": data.get("main", {}).get("feels_like"),
                    "temp_min": data.get("main", {}).get("temp_min"),
                    "temp_max": data.get("main", {}).get("temp_max"),
                    "pressure": data.get("main", {}).get("pressure"),
                    "humidity": data.get("main", {}).get("humidity"),
                    "description": data.get("weather", [{}])[0].get("description", ""),
                    "main": data.get("weather", [{}])[0].get("main", ""),
                    "icon": data.get("weather", [{}])[0].get("icon", ""),
                    "wind_speed": data.get("wind", {}).get("speed"),
                    "wind_deg": data.get("wind", {}).get("deg"),
                    "clouds": data.get("clouds", {}).get("all"),
                    "visibility": data.get("visibility"),
                },
                "sunrise": data.get("sys", {}).get("sunrise"),
                "sunset": data.get("sys", {}).get("sunset"),
                "timezone": data.get("timezone"),
                "dt": data.get("dt"),
                "units": units
            }
            
            logger.info(f"Weather data fetched for {weather_info['location']['name']}")
            return weather_info
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching weather data: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in weather service: {e}")
            raise
    
    def get_forecast(
        self,
        location: str = None,
        lat: float = None,
        lon: float = None,
        units: str = "metric",
        cnt: int = 5
    ) -> Dict[str, Any]:
        """
        Get weather forecast (5 day / 3 hour intervals)
        
        Args:
            location: City name
            lat: Latitude
            lon: Longitude
            units: Temperature units
            cnt: Number of timestamps to return (max 40)
        
        Returns:
            Forecast data dictionary
        """
        if not self.api_key:
            raise ValueError("WEATHER_API_KEY not configured")
        
        params = {
            "appid": self.api_key,
            "units": units,
            "cnt": min(cnt, 40)  # API limit is 40
        }
        
        if lat is not None and lon is not None:
            params["lat"] = lat
            params["lon"] = lon
        elif location:
            params["q"] = location
        else:
            raise ValueError("Either location or (lat, lon) must be provided")
        
        try:
            response = requests.get(
                f"{self.BASE_URL}/forecast",
                params=params,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            # Format forecast data
            forecast_list = []
            for item in data.get("list", []):
                forecast_list.append({
                    "dt": item.get("dt"),
                    "temp": item.get("main", {}).get("temp"),
                    "feels_like": item.get("main", {}).get("feels_like"),
                    "temp_min": item.get("main", {}).get("temp_min"),
                    "temp_max": item.get("main", {}).get("temp_max"),
                    "pressure": item.get("main", {}).get("pressure"),
                    "humidity": item.get("main", {}).get("humidity"),
                    "description": item.get("weather", [{}])[0].get("description", ""),
                    "main": item.get("weather", [{}])[0].get("main", ""),
                    "icon": item.get("weather", [{}])[0].get("icon", ""),
                    "wind_speed": item.get("wind", {}).get("speed"),
                    "clouds": item.get("clouds", {}).get("all"),
                    "pop": item.get("pop", 0),  # Probability of precipitation
                    "dt_txt": item.get("dt_txt")
                })
            
            forecast_info = {
                "location": {
                    "name": data.get("city", {}).get("name", "Unknown"),
                    "country": data.get("city", {}).get("country", ""),
                    "coordinates": {
                        "lat": data.get("city", {}).get("coord", {}).get("lat"),
                        "lon": data.get("city", {}).get("coord", {}).get("lon")
                    }
                },
                "forecast": forecast_list,
                "units": units
            }
            
            logger.info(f"Forecast data fetched for {forecast_info['location']['name']}")
            return forecast_info
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching forecast data: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in forecast service: {e}")
            raise


# Global weather service instance
weather_service = WeatherService()

