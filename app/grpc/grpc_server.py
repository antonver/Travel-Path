"""
gRPC server for photo service.
Runs alongside FastAPI server on port 50051.
"""
import grpc
from concurrent import futures
import logging
import asyncio
import threading
from typing import Optional

from app.grpc import photo_service_pb2
from app.grpc import photo_service_pb2_grpc
from app.grpc.photo_grpc_service import place_photo_service

logger = logging.getLogger(__name__)

# Port for gRPC server
GRPC_PORT = 50051


class PhotoServiceServicer(photo_service_pb2_grpc.PhotoServiceServicer):
    """
    Implementation of PhotoService gRPC service.
    """
    
    def __init__(self):
        self.photo_service = place_photo_service
    
    def UploadPlacePhoto(self, request, context):
        """
        Handle single photo upload from partner application.
        """
        try:
            logger.info(f"📸 gRPC: Receiving photo for place: {request.place_info.name}")
            
            # Extract data from request
            photo_data = request.photo_data
            filename = request.filename
            content_type = request.content_type or "image/jpeg"
            
            place_info = request.place_info
            place_name = place_info.name
            address = place_info.address
            city = place_info.city
            latitude = place_info.latitude
            longitude = place_info.longitude
            google_place_id = place_info.google_place_id or None
            place_types = list(place_info.types) if place_info.types else []
            
            source_app = request.source_app or "partner_app"
            source_user_id = request.source_user_id or None
            
            # Use asyncio to run async upload
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                result = loop.run_until_complete(
                    self.photo_service.upload_place_photo(
                        photo_data=photo_data,
                        filename=filename,
                        content_type=content_type,
                        place_name=place_name,
                        address=address,
                        city=city,
                        latitude=latitude,
                        longitude=longitude,
                        google_place_id=google_place_id,
                        source_app=source_app,
                        source_user_id=source_user_id,
                        place_types=place_types
                    )
                )
            finally:
                loop.close()
            
            # Build response
            response = photo_service_pb2.PlacePhotoResponse(
                success=result.get("success", False),
                photo_url=result.get("photo_url", ""),
                photo_id=result.get("photo_id", ""),
                matched_place_id=result.get("matched_place_id", ""),
                error_message=result.get("error_message", "")
            )
            
            if result.get("success"):
                logger.info(f"✅ gRPC: Photo uploaded successfully: {result.get('photo_id')}")
            else:
                logger.error(f"❌ gRPC: Photo upload failed: {result.get('error_message')}")
            
            return response
            
        except Exception as e:
            logger.error(f"❌ gRPC Error: {str(e)}")
            return photo_service_pb2.PlacePhotoResponse(
                success=False,
                error_message=str(e)
            )
    
    def UploadPlacePhotoBatch(self, request_iterator, context):
        """
        Handle batch photo upload (streaming).
        """
        success_count = 0
        failed_count = 0
        responses = []
        
        for request in request_iterator:
            response = self.UploadPlacePhoto(request, context)
            responses.append(response)
            
            if response.success:
                success_count += 1
            else:
                failed_count += 1
        
        logger.info(f"📦 gRPC Batch: {success_count} success, {failed_count} failed")
        
        return photo_service_pb2.BatchPhotoResponse(
            success_count=success_count,
            failed_count=failed_count,
            responses=responses
        )


class GRPCServer:
    """
    gRPC server manager.
    Runs in a separate thread alongside FastAPI.
    """
    
    def __init__(self, port: int = GRPC_PORT):
        self.port = port
        self.server: Optional[grpc.Server] = None
        self._thread: Optional[threading.Thread] = None
        self._started = False
        
    def start(self):
        """Start gRPC server in a separate thread"""
        if self._started:
            logger.info("gRPC server already running")
            return
            
        try:
            # Create server with thread pool
            self.server = grpc.server(
                futures.ThreadPoolExecutor(max_workers=10),
                options=[
                    ('grpc.max_receive_message_length', 50 * 1024 * 1024),  # 50MB max
                    ('grpc.max_send_message_length', 50 * 1024 * 1024),
                ]
            )
            
            # Add service
            photo_service_pb2_grpc.add_PhotoServiceServicer_to_server(
                PhotoServiceServicer(),
                self.server
            )
            
            # Add port
            self.server.add_insecure_port(f'[::]:{self.port}')
            
            # Start server in thread
            def serve():
                self.server.start()
                logger.info(f"✅ gRPC server started on port {self.port}")
                self.server.wait_for_termination()
            
            self._thread = threading.Thread(target=serve, daemon=True)
            self._thread.start()
            self._started = True
            
            logger.info(f"🚀 gRPC PhotoService listening on port {self.port}")
                
        except Exception as e:
            logger.error(f"❌ Failed to start gRPC server: {str(e)}")
    
    def stop(self):
        """Stop gRPC server"""
        if self.server:
            self.server.stop(grace=5)
            self._started = False
            logger.info("gRPC server stopped")


# Global instance
grpc_server = GRPCServer()


def start_grpc_server():
    """Convenience function to start gRPC server"""
    grpc_server.start()


def stop_grpc_server():
    """Convenience function to stop gRPC server"""
    grpc_server.stop()
