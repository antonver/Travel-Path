"""
MinIO Service for object storage operations
"""
from minio import Minio
from minio.error import S3Error
from fastapi import UploadFile, HTTPException
from app.core.config import settings
import logging
from typing import Optional
import io

logger = logging.getLogger(__name__)


class MinioService:
    """Service for handling MinIO object storage operations"""
    
    def __init__(self):
        """Initialize MinIO client"""
        try:
            self.client = Minio(
                settings.MINIO_ENDPOINT,
                access_key=settings.MINIO_ROOT_USER,
                secret_key=settings.MINIO_ROOT_PASSWORD,
                secure=settings.MINIO_USE_SSL
            )
            self.bucket_name = settings.MINIO_BUCKET_NAME
            logger.info(f"MinIO client initialized for endpoint: {settings.MINIO_ENDPOINT}")
        except Exception as e:
            logger.error(f"Failed to initialize MinIO client: {str(e)}")
            raise
    
    def ensure_bucket_exists(self) -> None:
        """
        Check if bucket exists, create if it doesn't
        Should be called on application startup
        """
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                logger.info(f"Created bucket: {self.bucket_name}")
                
                # Set bucket policy to allow public read access
                policy = {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"AWS": "*"},
                            "Action": ["s3:GetObject"],
                            "Resource": [f"arn:aws:s3:::{self.bucket_name}/*"]
                        }
                    ]
                }
                import json
                self.client.set_bucket_policy(
                    self.bucket_name,
                    json.dumps(policy)
                )
                logger.info(f"Set public read policy for bucket: {self.bucket_name}")
            else:
                logger.info(f"Bucket already exists: {self.bucket_name}")
        except S3Error as e:
            logger.error(f"MinIO S3 error: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to ensure bucket exists: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Unexpected error ensuring bucket: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to ensure bucket exists: {str(e)}"
            )
    
    async def upload_file(
        self,
        file: UploadFile,
        object_name: str
    ) -> str:
        """
        Upload a file to MinIO and return its URL
        
        Args:
            file: FastAPI UploadFile object
            object_name: Name/path for the object in MinIO
            
        Returns:
            str: Direct URL to the uploaded file
        """
        try:
            # Read file content
            contents = await file.read()
            file_size = len(contents)
            
            # Determine content type
            content_type = file.content_type or "application/octet-stream"
            
            # Upload to MinIO
            self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                data=io.BytesIO(contents),
                length=file_size,
                content_type=content_type
            )
            
            # Construct URL
            protocol = "https" if settings.MINIO_USE_SSL else "http"
            # Use external endpoint for URL (assuming minio is accessible at localhost:9000)
            external_endpoint = settings.MINIO_ENDPOINT.replace("minio", "localhost")
            url = f"{protocol}://{external_endpoint}/{self.bucket_name}/{object_name}"
            
            logger.info(f"Successfully uploaded file: {object_name}")
            return url
            
        except S3Error as e:
            logger.error(f"MinIO S3 error during upload: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to upload file to MinIO: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Unexpected error during file upload: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to upload file: {str(e)}"
            )
    
    def get_file_url(self, object_name: str) -> str:
        """
        Get the public URL for an object
        
        Args:
            object_name: Name/path of the object in MinIO
            
        Returns:
            str: Public URL to the object
        """
        protocol = "https" if settings.MINIO_USE_SSL else "http"
        external_endpoint = settings.MINIO_ENDPOINT.replace("minio", "localhost")
        return f"{protocol}://{external_endpoint}/{self.bucket_name}/{object_name}"
    
    def get_place_photos(self, place_id: str, max_photos: int = 10) -> list[str]:
        """
        Get all user-uploaded photos for a specific place from MinIO
        
        Searches for objects in the bucket that have metadata with matching place_id.
        Photos are typically stored under trips/{trip_id}/photos/ with metadata.
        
        Args:
            place_id: Google Place ID to search for
            max_photos: Maximum number of photos to return
            
        Returns:
            List of photo URLs from MinIO
        """
        try:
            photo_urls = []
            
            # List all objects in the bucket
            objects = self.client.list_objects(
                bucket_name=self.bucket_name,
                prefix="trips/",  # Photos are stored under trips/
                recursive=True
            )
            
            for obj in objects:
                # Only process image files in photos directories
                if "/photos/" in obj.object_name and obj.object_name.lower().endswith(
                    ('.jpg', '.jpeg', '.png', '.webp')
                ):
                    try:
                        # Get object metadata
                        stat = self.client.stat_object(
                            bucket_name=self.bucket_name,
                            object_name=obj.object_name
                        )
                        
                        # Check if metadata contains matching place_id
                        metadata = stat.metadata
                        if metadata and metadata.get("place_id") == place_id:
                            url = self.get_file_url(obj.object_name)
                            photo_urls.append(url)
                            
                            if len(photo_urls) >= max_photos:
                                break
                                
                    except Exception as e:
                        # Skip objects we can't read metadata from
                        logger.debug(f"Could not read metadata for {obj.object_name}: {str(e)}")
                        continue
            
            logger.info(f"Found {len(photo_urls)} user photos for place {place_id}")
            return photo_urls
            
        except S3Error as e:
            logger.error(f"MinIO S3 error searching photos: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Error searching place photos: {str(e)}")
            return []


# Global instance
minio_service = MinioService()

