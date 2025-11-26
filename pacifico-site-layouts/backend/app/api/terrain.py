"""
Terrain visualization API endpoints (D-01).

Provides endpoints for terrain analysis and visualization:
- Terrain summary statistics
- Contour lines
- Buildable area polygons
- Slope heatmap
"""
import json
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from geoalchemy2.functions import ST_AsGeoJSON
from shapely.geometry import shape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.site import Site
from app.models.user import User
from app.schemas.terrain import (
    BuildableAreaResponse,
    ContoursResponse,
    SlopeHeatmapResponse,
    TerrainSummaryResponse,
)
from app.services.terrain_visualization_service import get_terrain_visualization_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sites", tags=["Terrain"])


async def get_site_with_boundary(
    site_id: UUID,
    db: AsyncSession,
    current_user: User,
) -> tuple[Site, dict]:
    """
    Get site and parse its boundary as Shapely geometry.
    
    Raises HTTPException if site not found or not owned by user.
    """
    # Query site with ownership check
    result = await db.execute(
        select(Site).where(
            Site.id == site_id,
            Site.owner_id == current_user.id,
        )
    )
    site = result.scalar_one_or_none()
    
    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site not found",
        )
    
    # Get boundary as GeoJSON
    geojson_result = await db.execute(
        select(ST_AsGeoJSON(Site.boundary)).where(Site.id == site.id)
    )
    boundary_geojson = json.loads(geojson_result.scalar() or "{}")
    
    return site, boundary_geojson


@router.get(
    "/{site_id}/terrain/summary",
    response_model=TerrainSummaryResponse,
    summary="Get terrain analysis summary",
    description="Returns elevation, slope, and buildable area statistics for a site.",
)
async def get_terrain_summary(
    site_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TerrainSummaryResponse:
    """
    Get comprehensive terrain analysis summary for a site.
    
    Computes and returns:
    - Elevation statistics (min, max, mean, range)
    - Slope statistics with distribution histogram
    - Buildable area percentages per asset type
    
    This endpoint triggers DEM fetching if not already cached.
    """
    site, boundary_geojson = await get_site_with_boundary(site_id, db, current_user)
    
    try:
        boundary = shape(boundary_geojson)
    except Exception as e:
        logger.error(f"Failed to parse boundary geometry: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invalid site boundary geometry",
        )
    
    terrain_service = get_terrain_visualization_service()
    
    try:
        summary = await terrain_service.get_terrain_summary(site_id, db, boundary)
        return TerrainSummaryResponse(**summary)
    except ValueError as e:
        logger.error(f"Terrain summary failed for site {site_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error computing terrain summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to compute terrain summary",
        )


@router.get(
    "/{site_id}/terrain/contours",
    response_model=ContoursResponse,
    summary="Get contour lines",
    description="Returns contour lines as GeoJSON LineStrings at specified intervals.",
)
async def get_contours(
    site_id: UUID,
    interval_m: float = Query(
        default=5.0,
        ge=1.0,
        le=100.0,
        description="Contour interval in meters",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ContoursResponse:
    """
    Generate contour lines from DEM.
    
    Returns contour lines at the specified elevation interval.
    Lines are clipped to the site boundary.
    
    - **interval_m**: Contour interval in meters (1-100, default 5)
    """
    site, boundary_geojson = await get_site_with_boundary(site_id, db, current_user)
    
    try:
        boundary = shape(boundary_geojson)
    except Exception as e:
        logger.error(f"Failed to parse boundary geometry: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invalid site boundary geometry",
        )
    
    terrain_service = get_terrain_visualization_service()
    
    try:
        contours = await terrain_service.get_contours(site_id, db, boundary, interval_m)
        return ContoursResponse(**contours)
    except ValueError as e:
        logger.error(f"Contour generation failed for site {site_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
    except Exception as e:
        logger.exception(f"Unexpected error generating contours for site {site_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate contours: {str(e)}. Check server logs for details.",
        )


@router.get(
    "/{site_id}/terrain/buildable-area",
    response_model=BuildableAreaResponse,
    summary="Get buildable area polygons",
    description="Returns areas where terrain slope is suitable for the specified asset type.",
)
async def get_buildable_area(
    site_id: UUID,
    asset_type: str = Query(
        default="solar_array",
        description="Asset type for slope threshold (solar_array, battery, generator, substation)",
    ),
    max_slope: Optional[float] = Query(
        default=None,
        ge=0.0,
        le=45.0,
        description="Override maximum slope in degrees (uses asset default if not specified)",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BuildableAreaResponse:
    """
    Generate buildable area polygons.
    
    Returns polygons representing areas where terrain slope is below
    the threshold for the specified asset type.
    
    Default slope limits:
    - solar_array: 15°
    - battery: 5°
    - generator: 5°
    - substation: 5°
    """
    site, boundary_geojson = await get_site_with_boundary(site_id, db, current_user)
    
    try:
        boundary = shape(boundary_geojson)
    except Exception as e:
        logger.error(f"Failed to parse boundary geometry: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invalid site boundary geometry",
        )
    
    terrain_service = get_terrain_visualization_service()
    
    try:
        buildable = await terrain_service.get_buildable_area(
            site_id, db, boundary, asset_type, max_slope
        )
        return BuildableAreaResponse(**buildable)
    except ValueError as e:
        logger.error(f"Buildable area failed for site {site_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error computing buildable area: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to compute buildable area",
        )


@router.get(
    "/{site_id}/terrain/slope-heatmap",
    response_model=SlopeHeatmapResponse,
    summary="Get slope heatmap polygons",
    description="Returns slope zones as colored polygons for visualization.",
)
async def get_slope_heatmap(
    site_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SlopeHeatmapResponse:
    """
    Generate slope heatmap as colored zone polygons.
    
    Returns polygons colored by slope severity:
    - Green (0-5°): Very gentle, suitable for all assets
    - Yellow (5-10°): Gentle, suitable for most assets
    - Orange (10-15°): Moderate, solar arrays only
    - Red (>15°): Steep, not buildable
    
    Includes legend with color mapping.
    """
    site, boundary_geojson = await get_site_with_boundary(site_id, db, current_user)
    
    try:
        boundary = shape(boundary_geojson)
    except Exception as e:
        logger.error(f"Failed to parse boundary geometry: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invalid site boundary geometry",
        )
    
    terrain_service = get_terrain_visualization_service()
    
    try:
        heatmap = await terrain_service.get_slope_heatmap(site_id, db, boundary)
        return SlopeHeatmapResponse(**heatmap)
    except ValueError as e:
        logger.error(f"Slope heatmap failed for site {site_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error generating slope heatmap: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate slope heatmap",
        )

