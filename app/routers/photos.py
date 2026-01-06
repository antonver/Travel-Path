"""
Photo upload and retrieval endpoints.
Provides REST API for photo management from partner applications.
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List
import logging
import base64
import httpx

from app.grpc.photo_grpc_service import place_photo_service
from app.services.minio_service import minio_service
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/photos", tags=["photos"])


class PlacePhotoUploadRequest(BaseModel):
    """Request model for photo upload via JSON (base64 encoded)"""
    photo_base64: str = Field(..., description="Base64 encoded photo data")
    filename: str = Field(..., description="Photo filename")
    content_type: str = Field(default="image/jpeg", description="Content type")
    place_name: str = Field(..., description="Place name")
    address: str = Field(..., description="Place address")
    city: str = Field(..., description="City name")
    latitude: float = Field(..., description="Latitude")
    longitude: float = Field(..., description="Longitude")
    google_place_id: Optional[str] = Field(None, description="Google Place ID if known")
    source_app: str = Field(default="partner_app", description="Source application identifier")
    source_user_id: Optional[str] = Field(None, description="User ID from source app")
    place_types: Optional[List[str]] = Field(default=[], description="Place types")


class PhotoUploadResponse(BaseModel):
    """Response model for photo upload"""
    success: bool
    photo_url: Optional[str] = None
    photo_id: Optional[str] = None
    matched_place_id: Optional[str] = None
    error_message: Optional[str] = None


class PlacePhotosRequest(BaseModel):
    """Request model for getting place photos"""
    place_id: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    max_photos: int = Field(default=10, ge=1, le=50)


@router.post(
    "/upload",
    response_model=PhotoUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload place photo (JSON with base64)",
    description="Upload a photo for a place using base64 encoding. Used by partner applications."
)
async def upload_place_photo_json(request: PlacePhotoUploadRequest) -> PhotoUploadResponse:
    """
    Upload a photo for a place using JSON with base64 encoded image.
    
    This endpoint is designed for partner applications (like Instagram clone)
    to send photos with place metadata.
    """
    try:
        # Decode base64 photo
        try:
            photo_data = base64.b64decode(request.photo_base64)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid base64 encoding: {str(e)}"
            )
        
        # Upload photo
        result = await place_photo_service.upload_place_photo(
            photo_data=photo_data,
            filename=request.filename,
            content_type=request.content_type,
            place_name=request.place_name,
            address=request.address,
            city=request.city,
            latitude=request.latitude,
            longitude=request.longitude,
            google_place_id=request.google_place_id,
            source_app=request.source_app,
            source_user_id=request.source_user_id,
            place_types=request.place_types
        )
        
        return PhotoUploadResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading photo: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload photo: {str(e)}"
        )


@router.post(
    "/upload-multipart",
    response_model=PhotoUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload place photo (multipart/form-data)",
    description="Upload a photo for a place using multipart form data."
)
async def upload_place_photo_multipart(
    file: UploadFile = File(..., description="Photo file"),
    place_name: str = Form(..., description="Place name"),
    address: str = Form(..., description="Place address"),
    city: str = Form(..., description="City name"),
    latitude: float = Form(..., description="Latitude"),
    longitude: float = Form(..., description="Longitude"),
    google_place_id: Optional[str] = Form(None, description="Google Place ID"),
    source_app: str = Form(default="partner_app", description="Source app"),
    source_user_id: Optional[str] = Form(None, description="Source user ID")
) -> PhotoUploadResponse:
    """
    Upload a photo using multipart/form-data.
    Alternative to JSON upload for direct file uploads.
    """
    try:
        # Read file data
        photo_data = await file.read()
        
        # Upload photo
        result = await place_photo_service.upload_place_photo(
            photo_data=photo_data,
            filename=file.filename or "photo.jpg",
            content_type=file.content_type or "image/jpeg",
            place_name=place_name,
            address=address,
            city=city,
            latitude=latitude,
            longitude=longitude,
            google_place_id=google_place_id,
            source_app=source_app,
            source_user_id=source_user_id
        )
        
        return PhotoUploadResponse(**result)
        
    except Exception as e:
        logger.error(f"Error uploading photo: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload photo: {str(e)}"
        )


@router.post(
    "/by-place",
    summary="Get photos for a place",
    description="Get user-uploaded photos for a place by ID or coordinates"
)
async def get_place_photos(request: PlacePhotosRequest):
    """
    Get all user-uploaded photos for a specific place.
    Can search by Google Place ID or coordinates.
    """
    try:
        photos = place_photo_service.get_place_photos_by_id_or_coords(
            place_id=request.place_id,
            latitude=request.latitude,
            longitude=request.longitude,
            max_photos=request.max_photos
        )
        
        return {
            "photos": photos,
            "count": len(photos)
        }
        
    except Exception as e:
        logger.error(f"Error getting place photos: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get photos: {str(e)}"
        )


@router.get(
    "/minio-proxy",
    summary="Proxy MinIO photos",
    description="Proxy endpoint to fetch user-uploaded photos from MinIO storage"
)
async def minio_photo_proxy(
    path: str = Query(
        ...,
        description="Object path in MinIO (e.g. 'places/ChIJ.../photos/image.jpg')",
        example="places/ChIJofpYVAivthIRXw08nwXMzco/photos/20260106_140232_xxx.jpg"
    )
):
    """
    Proxy для загрузки фотографий из MinIO.
    
    Android клиент не может напрямую обратиться к localhost:9000,
    поэтому мы проксируем запросы через бэкенд.
    """
    try:
        logger.info(f"Proxying MinIO photo: {path[:80]}...")
        
        # Get object from MinIO
        try:
            response = minio_service.client.get_object(
                bucket_name=minio_service.bucket_name,
                object_name=path
            )
            
            # Read content
            content = response.read()
            response.close()
            response.release_conn()
            
            # Determine content type from extension
            if path.lower().endswith('.png'):
                content_type = "image/png"
            elif path.lower().endswith('.webp'):
                content_type = "image/webp"
            else:
                content_type = "image/jpeg"
            
            logger.info(f"Successfully proxied MinIO photo: {len(content)} bytes")
            
            return StreamingResponse(
                iter([content]),
                media_type=content_type,
                headers={
                    "Cache-Control": "public, max-age=86400",
                    "Content-Length": str(len(content))
                }
            )
            
        except Exception as minio_error:
            logger.warning(f"MinIO object not found: {path}, error: {minio_error}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Photo not found: {path}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error proxying MinIO photo: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to proxy photo: {str(e)}"
        )

