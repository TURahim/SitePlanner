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

from app.api.auth import get_current_user, DEMO_USER_SUB, DEMO_USER_EMAIL, DEMO_USER_NAME, DEMO_TOKEN
from app.api.layouts import router as layouts_router
from app.api.sites import router as sites_router
from app.api.exports import router as exports_router
from app.api.terrain import router as terrain_router
from app.api.exclusion_zones import router as exclusion_zones_router
from app.api.compliance import router as compliance_router
from app.models.user import User
from app.models.site import Site
from fastapi import Depends
from pydantic import BaseModel
from geoalchemy2.functions import ST_SetSRID, ST_GeomFromText, ST_Area
from geoalchemy2 import Geography
from sqlalchemy import select, cast

# Include API routers
app.include_router(sites_router)
app.include_router(layouts_router)
app.include_router(exports_router)  # Phase B export endpoints
app.include_router(terrain_router)  # Phase D terrain visualization endpoints
app.include_router(exclusion_zones_router)  # Phase D-03 exclusion zones
app.include_router(compliance_router)  # Phase 5 compliance and GIS endpoints


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


# =============================================================================
# Demo Login Endpoint
# =============================================================================


class DemoLoginResponse(BaseModel):
    """Response from demo login endpoint."""
    token: str
    user: dict
    message: str


# Demo site boundary - testsitereal.kml (Permian Basin 5GW site)
DEMO_SITE_BOUNDARY_WKT = """POLYGON((
    -102.577820 30.818940,
    -102.565990 30.827310,
    -102.552540 30.828880,
    -102.544200 30.823600,
    -102.535960 30.815100,
    -102.532880 30.805830,
    -102.540020 30.797400,
    -102.551950 30.792840,
    -102.564900 30.794220,
    -102.574780 30.800500,
    -102.579120 30.809910,
    -102.577820 30.818940
))"""

DEMO_SITE_NAME = "5GW Permian Basin Site"


@app.post("/api/auth/demo-login", tags=["Auth"], response_model=DemoLoginResponse)
async def demo_login() -> DemoLoginResponse:
    """
    Login as a demo user with a pre-seeded test site.
    
    This endpoint creates or retrieves a demo user account and ensures
    a demo site (Permian Basin 5GW) is available for testing.
    
    Returns a demo token that can be used for API authentication.
    """
    from app.database import async_session_maker
    
    async with async_session_maker() as db:
        try:
            # 1. Get or create demo user
            result = await db.execute(
                select(User).where(User.cognito_sub == DEMO_USER_SUB)
            )
            demo_user = result.scalar_one_or_none()
            
            if not demo_user:
                demo_user = User(
                    cognito_sub=DEMO_USER_SUB,
                    email=DEMO_USER_EMAIL,
                    name=DEMO_USER_NAME,
                )
                db.add(demo_user)
                await db.flush()
                logger.info(f"Created demo user: {demo_user.email}")
            
            # 2. Check if demo site exists
            site_result = await db.execute(
                select(Site).where(
                    Site.owner_id == demo_user.id,
                    Site.name == DEMO_SITE_NAME,
                )
            )
            demo_site = site_result.scalar_one_or_none()
            
            if not demo_site:
                # Create the demo site from testsitereal.kml boundary
                # Clean up the WKT (remove newlines/extra spaces)
                clean_wkt = " ".join(DEMO_SITE_BOUNDARY_WKT.split())
                
                demo_site = Site(
                    name=DEMO_SITE_NAME,
                    owner_id=demo_user.id,
                    boundary=ST_SetSRID(ST_GeomFromText(clean_wkt), 4326),
                )
                db.add(demo_site)
                await db.flush()
                
                # Calculate area in square meters
                area_result = await db.execute(
                    select(ST_Area(cast(Site.boundary, Geography))).where(Site.id == demo_site.id)
                )
                area_m2 = area_result.scalar() or 0.0
                demo_site.area_m2 = area_m2
                
                logger.info(f"Created demo site: {demo_site.name} ({area_m2/1e6:.2f} km²)")
            
            await db.commit()
            
            return DemoLoginResponse(
                token=DEMO_TOKEN,
                user={
                    "id": str(demo_user.id),
                    "email": demo_user.email,
                    "name": demo_user.name,
                },
                message="Demo login successful. A sample site has been pre-loaded.",
            )
            
        except Exception as e:
            logger.exception(f"Demo login failed: {e}")
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Demo login failed: {str(e)}",
            )


# =============================================================================
# DEBUG ENDPOINT - REMOVE IN PRODUCTION
# =============================================================================

@app.post("/debug/test-layout-generation", tags=["Debug"])
async def debug_test_layout_generation():
    """
    DEBUG ONLY: Test layout generation without authentication.
    
    This endpoint is for local debugging only and should be removed in production.
    It creates a test site and generates a layout to verify the terrain pipeline.
    """
    import uuid
    from shapely.geometry import Polygon
    from shapely import wkt as shapely_wkt
    from geoalchemy2.functions import ST_SetSRID, ST_GeomFromText
    from sqlalchemy import select
    
    from app.database import async_session_maker
    from app.models.site import Site
    from app.models.user import User
    from app.services.dem_service import get_dem_service
    from app.services.slope_service import get_slope_service
    from app.services.terrain_analysis_service import get_terrain_analysis_service
    from app.services.terrain_layout_generator import TerrainAwareLayoutGenerator
    
    logger.info("=" * 60)
    logger.info("DEBUG: Testing layout generation pipeline")
    logger.info("=" * 60)
    
    # Create a small test boundary (~50 acres in West Texas)
    # This is the same as sample-site.kml
    test_boundary_wkt = "POLYGON((-101.8500 35.2000, -101.8450 35.2000, -101.8450 35.1950, -101.8500 35.1950, -101.8500 35.2000))"
    test_boundary = shapely_wkt.loads(test_boundary_wkt)
    
    results = {
        "steps": [],
        "success": False,
        "error": None,
    }
    
    async with async_session_maker() as db:
        try:
            # Step 1: Create or get test user
            logger.info("Step 1: Creating test user...")
            test_user_result = await db.execute(
                select(User).where(User.email == "debug@test.local")
            )
            test_user = test_user_result.scalar_one_or_none()
            
            if not test_user:
                test_user = User(
                    cognito_sub="debug-test-sub",
                    email="debug@test.local",
                    name="Debug Test User",
                )
                db.add(test_user)
                await db.flush()
            
            results["steps"].append({"step": 1, "status": "ok", "message": f"Test user: {test_user.email}"})
            
            # Step 2: Create test site
            logger.info("Step 2: Creating test site...")
            test_site = Site(
                name=f"Debug Test Site {uuid.uuid4().hex[:8]}",
                owner_id=test_user.id,
                boundary=ST_SetSRID(ST_GeomFromText(test_boundary_wkt), 4326),
                area_m2=200000,  # ~50 acres
            )
            db.add(test_site)
            await db.flush()
            
            results["steps"].append({"step": 2, "status": "ok", "message": f"Test site: {test_site.id}"})
            
            # Step 3: Fetch DEM
            logger.info("Step 3: Fetching DEM from USGS 3DEP...")
            dem_service = get_dem_service()
            dem_s3_key = await dem_service.get_dem_for_site(
                site_id=test_site.id,
                boundary=test_boundary,
                db=db,
                resolution_m=30,  # Use 30m for faster testing
            )
            
            if not dem_s3_key:
                raise Exception("DEM fetch failed - check py3dep and network connectivity")
            
            results["steps"].append({"step": 3, "status": "ok", "message": f"DEM S3 key: {dem_s3_key}"})
            
            # Step 4: Compute slope
            logger.info("Step 4: Computing slope...")
            slope_service = get_slope_service()
            slope_s3_key = await slope_service.get_slope_for_site(
                site_id=test_site.id,
                dem_s3_key=dem_s3_key,
                db=db,
            )
            
            if not slope_s3_key:
                raise Exception("Slope computation failed")
            
            results["steps"].append({"step": 4, "status": "ok", "message": f"Slope S3 key: {slope_s3_key}"})
            
            # Step 5: Load raster data
            logger.info("Step 5: Loading raster data...")
            dem_array, dem_profile = await dem_service.get_dem_array(dem_s3_key)
            slope_array, slope_profile = await slope_service.get_slope_array(slope_s3_key)
            
            results["steps"].append({
                "step": 5, 
                "status": "ok", 
                "message": f"DEM shape: {dem_array.shape}, Slope range: {slope_array.min():.1f}° - {slope_array.max():.1f}°"
            })
            
            # Step 6: Terrain analysis
            logger.info("Step 6: Running terrain analysis...")
            terrain_analysis = get_terrain_analysis_service()
            transform = dem_profile["transform"]
            crs = dem_profile.get("crs", "EPSG:4326")
            
            terrain_metrics = terrain_analysis.analyze_terrain(
                dem_array=dem_array,
                transform=transform,
                crs=str(crs),
                apply_smoothing=True,
            )
            
            results["steps"].append({"step": 6, "status": "ok", "message": "Terrain analysis complete"})
            
            # Step 7: Generate layout
            logger.info("Step 7: Generating layout...")
            generator = TerrainAwareLayoutGenerator(target_capacity_kw=1000)
            
            placed_assets, placed_roads, cut_fill = generator.generate(
                boundary=test_boundary,
                dem_array=dem_array,
                slope_array=slope_array,
                transform=transform,
                num_assets=5,
            )
            
            results["steps"].append({
                "step": 7, 
                "status": "ok", 
                "message": f"Generated {len(placed_assets)} assets, {len(placed_roads)} roads"
            })
            
            # Step 8: Summary
            total_capacity = sum(a.capacity_kw for a in placed_assets)
            results["steps"].append({
                "step": 8,
                "status": "ok",
                "message": f"Total capacity: {total_capacity:.1f} kW, Cut: {cut_fill.cut_volume_m3:.0f} m³, Fill: {cut_fill.fill_volume_m3:.0f} m³"
            })
            
            results["success"] = True
            
            # Rollback the test data (we don't want to persist debug data)
            await db.rollback()
            
            logger.info("=" * 60)
            logger.info("DEBUG: Layout generation pipeline test PASSED")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.exception(f"DEBUG: Layout generation failed: {e}")
            results["error"] = str(e)
            results["error_type"] = type(e).__name__
            await db.rollback()
    
    return results


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
