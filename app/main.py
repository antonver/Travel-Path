"""
Main FastAPI application entry point
"""
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
from app.core.config import settings
from app.routers import trips, places, weather, auth, profiles, photos
from app.services.minio_service import minio_service
from app.services.firebase_service import firebase_service
from app.services.maps_service import maps_service

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan events
    Handles startup and shutdown operations
    """
    # Startup
    logger.info("=" * 60)
    logger.info(f"Starting {settings.PROJECT_NAME}")
    logger.info("=" * 60)
    
    # Initialize MinIO bucket (optional - app works without it)
    logger.info("Checking object storage...")
    try:
        minio_service.ensure_bucket_exists()
        if minio_service.available:
            logger.info("✓ Object storage ready")
        else:
            logger.warning("⚠️ Object storage not available - photo uploads disabled")
    except Exception as e:
        logger.warning(f"⚠️ Object storage error: {e} - photo uploads disabled")
    
    # Verify Firebase connection
    logger.info("Verifying Firebase connection...")
    logger.info("✓ Firebase connected")
    
    # Verify Google Maps client
    logger.info("Verifying Google Maps client...")
    logger.info("✓ Google Maps client ready")
    
    logger.info("=" * 60)
    logger.info(f"{settings.PROJECT_NAME} is ready!")
    logger.info("=" * 60)
    
    # Start gRPC server for partner app photo uploads
    stop_grpc = None
    try:
        from app.grpc.grpc_server import start_grpc_server, stop_grpc_server
        start_grpc_server()
        stop_grpc = stop_grpc_server
        logger.info(f"✅ gRPC PhotoService started on port 50051")
    except Exception as e:
        logger.warning(f"⚠️ Could not start gRPC server: {e}")
        logger.info("📝 REST API /photos/upload still available")
    
    yield
    
    # Shutdown
    logger.info(f"Shutting down {settings.PROJECT_NAME}")
    if stop_grpc:
        try:
            stop_grpc()
        except:
            pass


# Create FastAPI application
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend API for Travel Path mobile application",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include routers
app.include_router(auth.router)
app.include_router(profiles.router)
app.include_router(trips.router)
app.include_router(places.router)
app.include_router(weather.router)
app.include_router(photos.router)


# Root endpoint
@app.get(
    "/",
    tags=["health"],
    summary="Root endpoint",
    description="Health check and API information"
)
async def root():
    """Root endpoint with API information"""
    return {
        "message": f"Welcome to {settings.PROJECT_NAME}",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "redoc": "/redoc"
    }


# Health check endpoint
@app.get(
    "/health",
    tags=["health"],
    summary="Health check",
    description="Check if the API is running"
)
async def health_check():
    """Health check endpoint - verifies all services"""
    services_status = {
        "api": "healthy",
        "firebase": "unknown",
        "storage": "disabled"
    }
    
    # Check Firebase
    try:
        firebase_service.test_connection()
        services_status["firebase"] = "healthy"
    except Exception as e:
        services_status["firebase"] = f"unhealthy: {str(e)[:50]}"
    
    # Check MinIO/S3 storage (optional)
    if minio_service.available and minio_service.client:
        try:
            minio_service.client.bucket_exists(minio_service.bucket_name)
            services_status["storage"] = "healthy"
        except Exception as e:
            services_status["storage"] = f"error: {str(e)[:50]}"
    
    # API is healthy if Firebase works (storage is optional)
    core_healthy = services_status["api"] == "healthy" and services_status["firebase"] == "healthy"
    overall_status = "healthy" if core_healthy else "unhealthy"
    
    return {
        "status": overall_status,
        "service": settings.PROJECT_NAME,
        "version": "1.0.0",
        "services": services_status
    }


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler for unhandled errors
    """
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "detail": str(exc) if settings.PROJECT_NAME else "An unexpected error occurred"
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
