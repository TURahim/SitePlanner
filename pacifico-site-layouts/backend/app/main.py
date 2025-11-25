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
# CORS Middleware
# =============================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# Exception Handlers
# =============================================================================


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle HTTP exceptions with consistent JSON response."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions."""
    logger.exception(f"Unexpected error: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "status_code": 500,
        },
    )


# =============================================================================
# Health Check Endpoints
# =============================================================================


@app.get("/health", tags=["Health"])
async def health() -> dict[str, str]:
    """
    Basic health check endpoint.
    
    Returns 200 OK if the service is running.
    """
    return {"status": "ok"}


@app.get("/health/ready", tags=["Health"])
async def health_ready() -> dict[str, Any]:
    """
    Readiness check that verifies database connectivity.
    
    Returns 200 if the service is ready to handle requests.
    Returns 503 if the database is not accessible.
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
from app.models.user import User
from fastapi import Depends

# Include API routers
app.include_router(sites_router)
app.include_router(layouts_router)


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
# - POST /api/sites/upload (A-05)
# - GET /api/sites/{id} (A-06)
# - GET /api/sites (list)
# - DELETE /api/sites/{id}
# - POST /api/layouts/generate (A-07)
# - GET /api/layouts/{id}
# - GET /api/layouts (list)
# - DELETE /api/layouts/{id}
