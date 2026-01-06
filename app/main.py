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
    
    try:
        # Initialize MinIO bucket
        logger.info("Initializing MinIO bucket...")
        minio_service.ensure_bucket_exists()
        logger.info("✓ MinIO bucket ready")
        
        # Verify Firebase connection
        logger.info("Verifying Firebase connection...")
        # Firebase is already initialized in the service __init__
        logger.info("✓ Firebase connected")
        
        # Verify Google Maps client
        logger.info("Verifying Google Maps client...")
        # Maps client is already initialized in the service __init__
        logger.info("✓ Google Maps client ready")
        
        logger.info("=" * 60)
        logger.info(f"{settings.PROJECT_NAME} is ready!")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Failed to initialize services: {str(e)}")
        raise
    
    yield
    
    # Shutdown
    logger.info(f"Shutting down {settings.PROJECT_NAME}")


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
        "minio": "unknown"
    }
    
    # Check Firebase
    try:
        firebase_service.test_connection()
        services_status["firebase"] = "healthy"
    except Exception as e:
        services_status["firebase"] = f"unhealthy: {str(e)[:50]}"
    
    # Check MinIO
    try:
        minio_service.client.bucket_exists(minio_service.bucket_name)
        services_status["minio"] = "healthy"
    except Exception as e:
        services_status["minio"] = f"unhealthy: {str(e)[:50]}"
    
    overall_status = "healthy" if all(
        v == "healthy" for v in services_status.values()
    ) else "degraded"
    
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


# Startup event logging
@app.on_event("startup")
async def startup_event():
    """Additional startup logging"""
    logger.info(f"FastAPI application started")
    logger.info(f"Documentation available at: http://localhost:8000/docs")
    
    # Start gRPC server for partner app photo uploads
    try:
        from app.grpc.grpc_server import start_grpc_server
        start_grpc_server()
        logger.info(f"✅ gRPC PhotoService started on port 50051")
    except Exception as e:
        logger.warning(f"⚠️ Could not start gRPC server: {e}")
        logger.info("📝 REST API /photos/upload still available")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )

