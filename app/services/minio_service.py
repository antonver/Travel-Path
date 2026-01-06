"""
MinIO Service for object storage operations
Supports MinIO, Cloudflare R2, AWS S3, and other S3-compatible storage
"""
from minio import Minio
from minio.error import S3Error
from fastapi import UploadFile, HTTPException
from app.core.config import settings
import logging
from typing import Optional
import io

logger = logging.getLogger(__name__)


def clean_endpoint(endpoint: str) -> str:
    """
    Clean endpoint for MinIO client - remove protocol and paths
    Examples:
        https://abc123.r2.cloudflarestorage.com -> abc123.r2.cloudflarestorage.com
        http://minio:9000 -> minio:9000
        abc123.r2.cloudflarestorage.com/bucket -> abc123.r2.cloudflarestorage.com
    """
    # Remove protocol
    endpoint = endpoint.replace("https://", "").replace("http://", "")
    # Remove trailing slash and path
    endpoint = endpoint.split("/")[0]
    return endpoint


class MinioService:
    """Service for handling MinIO/S3-compatible object storage operations"""
    
    def __init__(self):
        """Initialize MinIO client"""
        self.client = None
        self.bucket_name = settings.MINIO_BUCKET_NAME
        self.available = False
        
        try:
            # Clean endpoint (remove https://, paths, etc.)
            endpoint = clean_endpoint(settings.MINIO_ENDPOINT)
            
            self.client = Minio(
                endpoint,
                access_key=settings.MINIO_ROOT_USER,
                secret_key=settings.MINIO_ROOT_PASSWORD,
                secure=settings.MINIO_USE_SSL,
                region=getattr(settings, 'MINIO_REGION', None)
            )
            self.available = True
            logger.info(f"✅ MinIO/S3 client initialized for endpoint: {endpoint}")
        except Exception as e:
            logger.warning(f"⚠️ MinIO/S3 not available: {str(e)}")
            logger.info("📝 Photo upload features will be disabled")
    
    def ensure_bucket_exists(self) -> None:
        """
        Check if bucket exists, create if it doesn't
        Should be called on application startup
        """
        if not self.available or not self.client:
            logger.info("⏭️ Skipping bucket check - storage not available")
            return
            
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
                try:
                    self.client.set_bucket_policy(
                        self.bucket_name,
                        json.dumps(policy)
                    )
                    logger.info(f"Set public read policy for bucket: {self.bucket_name}")
                except Exception as e:
                    # R2 and some providers don't support bucket policies
                    logger.warning(f"Could not set bucket policy (may be unsupported): {e}")
            else:
                logger.info(f"✅ Bucket exists: {self.bucket_name}")
        except S3Error as e:
            logger.error(f"MinIO S3 error: {str(e)}")
            self.available = False
        except Exception as e:
            logger.error(f"Unexpected error ensuring bucket: {str(e)}")
            self.available = False
    
    async def upload_file(
        self,
        file: UploadFile,
        object_name: str
    ) -> str:
        """
        Upload a file to MinIO/S3 and return its URL
        
        Args:
            file: FastAPI UploadFile object
            object_name: Name/path for the object in MinIO
            
        Returns:
            str: Direct URL to the uploaded file
        """
        if not self.available or not self.client:
            raise HTTPException(
                status_code=503,
                detail="Object storage not available"
            )
            
        try:
            # Read file content
            contents = await file.read()
            file_size = len(contents)
            
            # Determine content type
            content_type = file.content_type or "application/octet-stream"
            
            # Upload to storage
            self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                data=io.BytesIO(contents),
                length=file_size,
                content_type=content_type
            )
            
            url = self.get_file_url(object_name)
            logger.info(f"Successfully uploaded file: {object_name}")
            return url
            
        except S3Error as e:
            logger.error(f"S3 error during upload: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to upload file: {str(e)}"
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
        endpoint = clean_endpoint(settings.MINIO_ENDPOINT)
        protocol = "https" if settings.MINIO_USE_SSL else "http"
        
        # For Cloudflare R2, use the public bucket URL format
        if "r2.cloudflarestorage.com" in endpoint:
            # R2 public access requires bucket to be set up with custom domain or R2.dev subdomain
            # Using the S3-compatible endpoint for now
            return f"{protocol}://{endpoint}/{self.bucket_name}/{object_name}"
        
        # For local development, replace internal hostname with localhost
        if endpoint.startswith("minio:"):
            endpoint = endpoint.replace("minio:", "localhost:")
        
        return f"{protocol}://{endpoint}/{self.bucket_name}/{object_name}"
    
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
        if not self.available or not self.client:
            return []
            
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
            logger.error(f"S3 error searching photos: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Error searching place photos: {str(e)}")
            return []


# Global instance
minio_service = MinioService()

