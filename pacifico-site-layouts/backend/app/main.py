"""
Pacifico Site Layouts API - Main FastAPI Application
"""
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import check_db_connection

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler for startup/shutdown events.
    """
    # Startup
    logger.info("Starting Pacifico Site Layouts API...")
    logger.info(f"Environment: debug={settings.debug}")
    
    # Check database connection on startup
    if await check_db_connection():
        logger.info("Database connection verified")
    else:
        logger.warning("Database connection failed - service may not work correctly")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Pacifico Site Layouts API...")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="AI-powered geospatial layout tool for DG/microgrid/data center site planning",
    version="0.1.0",
    lifespan=lifespan,
)

# =============================================================================
# CORS Middleware (must be added early, before routes)
# =============================================================================
# Handles preflight OPTIONS requests automatically.
# Allowed origins are configured in app/config.py via CORS_ORIGINS env var.
# TODO: Add production frontend URLs to CORS_ORIGINS (e.g., CloudFront URL)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# =============================================================================
# Exception Handlers (with CORS headers for cross-origin error responses)
# =============================================================================


def _get_cors_headers(request: Request) -> dict[str, str]:
    """Get CORS headers based on request origin."""
    origin = request.headers.get("origin", "")
    if origin in settings.cors_origins:
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
            "Access-Control-Allow-Headers": "*",
        }
    return {}


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle HTTP exceptions with consistent JSON response and CORS headers."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
        },
        headers=_get_cors_headers(request),
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions with CORS headers."""
    logger.exception(f"Unexpected error: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "status_code": 500,
        },
        headers=_get_cors_headers(request),
    )


# =============================================================================
# Health Check Endpoints (Phase C - C-09: Enhanced health checks)
# =============================================================================


@app.get("/health", tags=["Health"])
async def health() -> dict[str, str]:
    """
    Basic liveness check endpoint.
    
    Returns 200 OK if the service is running.
    Used by ECS/ALB for basic liveness probes.
    """
    return {"status": "ok"}


@app.get("/health/ready", tags=["Health"])
async def health_ready() -> dict[str, Any]:
    """
    Readiness check that verifies database connectivity.
    
    Returns 200 if the service is ready to handle requests.
    Returns 503 if the database is not accessible.
    
    Used by ECS/ALB for readiness probes to determine if the
    container should receive traffic.
    """
    db_healthy = await check_db_connection()
    
    if not db_healthy:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed",
        )
    
    return {
        "status": "ready",
        "database": "connected",
    }


@app.get("/health/live", tags=["Health"])
async def health_live() -> dict[str, Any]:
    """
    Comprehensive health check for monitoring systems.
    
    Returns detailed status of all dependencies:
    - Database connectivity
    - SQS queue status (if async enabled)
    - Memory/resource usage
    
    Always returns 200 with status details for monitoring dashboards.
    """
    import os
    import psutil
    
    health_status: dict[str, Any] = {
        "status": "ok",
        "version": "0.1.0",
        "checks": {},
    }
    
    # Database check
    try:
        db_healthy = await check_db_connection()
        health_status["checks"]["database"] = {
            "status": "healthy" if db_healthy else "unhealthy",
            "message": "Connection successful" if db_healthy else "Connection failed",
        }
    except Exception as e:
        health_status["checks"]["database"] = {
            "status": "unhealthy",
            "message": str(e),
        }
        health_status["status"] = "degraded"
    
    # SQS check (if async enabled)
    if settings.enable_async_layout_generation and settings.sqs_queue_url:
        try:
            from app.services.sqs_service import get_sqs_service
            sqs = get_sqs_service()
            attrs = await sqs.get_queue_attributes()
            health_status["checks"]["sqs"] = {
                "status": "healthy",
                "queue_depth": attrs.get("ApproximateNumberOfMessages", "unknown"),
            }
        except Exception as e:
            health_status["checks"]["sqs"] = {
                "status": "unhealthy",
                "message": str(e),
            }
            health_status["status"] = "degraded"
    
    # System resources
    try:
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        health_status["checks"]["resources"] = {
            "status": "healthy",
            "memory_mb": round(memory_info.rss / 1024 / 1024, 2),
            "cpu_percent": process.cpu_percent(),
        }
    except Exception:
        health_status["checks"]["resources"] = {
            "status": "unknown",
            "message": "Could not retrieve resource info",
        }
    
    return health_status


# =============================================================================
# API Info
# =============================================================================


@app.get("/", tags=["Info"])
async def root() -> dict[str, str]:
    """API root - returns basic info."""
    return {
        "name": settings.app_name,
        "version": "0.1.0",
        "docs": "/docs",
    }


# =============================================================================
# API Routes
# =============================================================================

from app.api.auth import get_current_user
from app.api.layouts import router as layouts_router
from app.api.sites import router as sites_router
from app.api.exports import router as exports_router
from app.api.terrain import router as terrain_router
from app.api.exclusion_zones import router as exclusion_zones_router
from app.models.user import User
from fastapi import Depends

# Include API routers
app.include_router(sites_router)
app.include_router(layouts_router)
app.include_router(exports_router)  # Phase B export endpoints
app.include_router(terrain_router)  # Phase D terrain visualization endpoints
app.include_router(exclusion_zones_router)  # Phase D-03 exclusion zones


@app.get("/api/me", tags=["Auth"])
async def get_me(user: User = Depends(get_current_user)) -> dict:
    """
    Get the current authenticated user's information.
    
    This is a protected endpoint that requires a valid JWT token.
    """
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
    }


# API endpoints implemented:
# Phase A:
# - POST /api/sites/upload (A-05)
# - GET /api/sites/{id} (A-06)
# - GET /api/sites (list)
# - DELETE /api/sites/{id}
# - POST /api/layouts/generate (A-07, updated for B-01 to B-07)
# - GET /api/layouts/{id}
# - GET /api/layouts (list)
# - DELETE /api/layouts/{id}
# Phase B:
# - GET /api/layouts/{id}/export/geojson (B-08)
# - GET /api/layouts/{id}/export/kmz (B-09)
# - GET /api/layouts/{id}/export/pdf (B-10)
# Phase D:
# - GET /api/sites/{id}/terrain/summary (D-01)
# - GET /api/sites/{id}/terrain/contours (D-01)
# - GET /api/sites/{id}/terrain/buildable-area (D-01)
# - GET /api/sites/{id}/terrain/slope-heatmap (D-01)
# - GET /api/layouts/{id}/export/csv (D-04)
# - GET /api/sites/exclusion-zone-types (D-03)
# - GET /api/sites/{id}/exclusion-zones (D-03)
# - POST /api/sites/{id}/exclusion-zones (D-03)
# - PUT /api/sites/{id}/exclusion-zones/{zone_id} (D-03)
# - DELETE /api/sites/{id}/exclusion-zones/{zone_id} (D-03)
