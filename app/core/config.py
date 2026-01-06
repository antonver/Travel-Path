"""
Application configuration using Pydantic Settings
Supports both local development and cloud deployment (Render, etc.)
"""
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator, model_validator
from typing import Optional, Any
import os
import json


def setup_firebase_from_json():
    """
    If FIREBASE_CREDENTIALS_JSON env var is set, write it to a temp file.
    This runs BEFORE Settings validation.
    """
    json_creds = os.environ.get('FIREBASE_CREDENTIALS_JSON')
    if json_creds:
        try:
            creds = json.loads(json_creds)
            temp_path = "/tmp/firebase_credentials.json"
            with open(temp_path, 'w') as f:
                json.dump(creds, f)
            os.environ['FIREBASE_CREDENTIALS_PATH'] = temp_path
            print(f"✅ Firebase credentials written to {temp_path}")
            return temp_path
        except json.JSONDecodeError as e:
            print(f"❌ Invalid FIREBASE_CREDENTIALS_JSON: {e}")
    return None


# Setup Firebase credentials before Settings loads
_firebase_path = setup_firebase_from_json()


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables
    """
    
    # Project
    PROJECT_NAME: str = Field(default="TravelPath", description="Project name")
    
    # Firebase - supports both file path and JSON string
    FIREBASE_CREDENTIALS_PATH: str = Field(
        default="/app/serviceAccountKey.json",
        description="Path to Firebase service account JSON file"
    )
    FIREBASE_CREDENTIALS_JSON: Optional[str] = Field(
        default=None,
        description="Firebase credentials as JSON string (for cloud deployment)"
    )
    FIRESTORE_DATABASE: str = Field(
        default="default",
        description="Firestore database name"
    )
    
    # Google Maps
    MAPS_API_KEY: str = Field(..., description="Google Maps API key")
    
    # Weather API (OpenWeatherMap)
    WEATHER_API_KEY: Optional[str] = Field(
        default=None,
        description="OpenWeatherMap API key (free tier available)"
    )
    
    # MinIO / S3 Compatible Storage
    MINIO_ENDPOINT: str = Field(
        default="minio:9000",
        description="MinIO/S3 endpoint (host:port)"
    )
    MINIO_ROOT_USER: str = Field(default="minioadmin", description="MinIO root user / S3 Access Key")
    MINIO_ROOT_PASSWORD: str = Field(default="minioadmin", description="MinIO root password / S3 Secret Key")
    MINIO_BUCKET_NAME: str = Field(
        default="travel-photos",
        description="MinIO bucket name for storing photos"
    )
    MINIO_USE_SSL: bool = Field(
        default=False,
        description="Use SSL for MinIO connection"
    )
    MINIO_REGION: str = Field(
        default="us-east-1",
        description="S3 region (for cloud storage)"
    )
    
    # Server settings
    PORT: int = Field(default=8000, description="HTTP server port")
    GRPC_PORT: int = Field(default=50051, description="gRPC server port")
    
    @model_validator(mode='after')
    def validate_firebase_path(self):
        """Validate that Firebase credentials file exists"""
        if not os.path.exists(self.FIREBASE_CREDENTIALS_PATH):
            raise ValueError(
                f"Firebase credentials file not found at: {self.FIREBASE_CREDENTIALS_PATH}. "
                f"Set FIREBASE_CREDENTIALS_JSON environment variable or mount serviceAccountKey.json"
            )
        return self
    
    @field_validator("MAPS_API_KEY")
    @classmethod
    def validate_maps_key(cls, v: str) -> str:
        """Validate that Maps API key is not empty"""
        if not v or v == "your_google_maps_api_key_here":
            raise ValueError(
                "MAPS_API_KEY must be set to a valid Google Maps API key"
            )
        return v
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Global settings instance
settings = Settings()

