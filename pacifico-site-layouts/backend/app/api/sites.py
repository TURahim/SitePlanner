"""
Site management API endpoints.

Handles site upload, retrieval, and listing.

D-05-06: Added preferred layout management endpoint.
"""
import json
import logging
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from geoalchemy2.functions import ST_Area, ST_AsGeoJSON, ST_GeomFromText, ST_SetSRID
from pydantic import BaseModel
from sqlalchemy import cast, select
from geoalchemy2 import Geography
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.layout import Layout
from app.models.site import Site
from app.models.user import User
from app.schemas.site import SiteListResponse, SiteResponse, SiteUploadResponse
from app.schemas.exclusion_zone import ExclusionZoneTypesResponse, ZONE_TYPE_INFO
from app.services.kml_parser import KMLParseError, KMLParser
from app.services.s3 import get_s3_service


# =============================================================================
# D-05-06: Preferred Layout Schema
# =============================================================================


class SetPreferredLayoutRequest(BaseModel):
    """Request to set or clear preferred layout for a site."""
    layout_id: Optional[UUID] = None  # None to clear


class PreferredLayoutResponse(BaseModel):
    """Response for preferred layout operation."""
    site_id: UUID
    preferred_layout_id: Optional[UUID]
    message: str

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sites", tags=["Sites"])

# Maximum file size: 10 MB
MAX_FILE_SIZE = 10 * 1024 * 1024


# =============================================================================
# Exclusion Zone Types (must be BEFORE /{site_id} to avoid path conflict)
# =============================================================================


@router.get(
    "/exclusion-zone-types",
    response_model=ExclusionZoneTypesResponse,
    summary="Get available exclusion zone types",
    description="Returns all available exclusion zone types with their default colors and buffers.",
    tags=["Exclusion Zones"],
)
async def get_zone_types() -> ExclusionZoneTypesResponse:
    """
    Get all available exclusion zone types.
    
    This endpoint does not require authentication as zone types are static.
    It must be defined before /{site_id} routes to avoid path conflicts.
    """
    return ExclusionZoneTypesResponse(types=ZONE_TYPE_INFO)


# =============================================================================
# Site Upload
# =============================================================================


@router.post(
    "/upload",
    response_model=SiteUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload site boundary",
    description="Upload a KML or KMZ file containing a site boundary polygon.",
)
async def upload_site(
    file: Annotated[UploadFile, File(description="KML or KMZ file with site boundary")],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SiteUploadResponse:
    """
    Upload a KML/KMZ file to create a new site.
    
    The file must contain at least one Polygon or MultiPolygon geometry.
    The first polygon found will be used as the site boundary.
    
    - **file**: KML or KMZ file (max 10MB)
    
    Returns the created site with boundary as GeoJSON.
    """
    # Validate file type
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )
    
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ("kml", "kmz"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Only KML and KMZ files are accepted.",
        )
    
    # Read file content
    content = await file.read()
    
    # Validate file size
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB.",
        )
    
    # Parse KML/KMZ
    try:
        geometry, kml_name = KMLParser.parse(content, file.filename)
    except KMLParseError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    # Use KML name or filename as site name
    site_name = kml_name or file.filename.rsplit(".", 1)[0]
    
    # Convert geometry to WKT for PostGIS
    wkt = KMLParser.geometry_to_wkt(geometry)
    
    # Create Site record
    # Use SRID 4326 (WGS84) for geographic coordinates
    site = Site(
        name=site_name,
        owner_id=current_user.id,
        boundary=ST_SetSRID(ST_GeomFromText(wkt), 4326),
    )
    
    db.add(site)
    await db.flush()  # Get the ID
    
    # Calculate area in square meters using PostGIS
    # Cast geometry to geography to get area in square meters
    area_result = await db.execute(
        select(ST_Area(cast(Site.boundary, Geography))).where(Site.id == site.id)
    )
    area_m2 = area_result.scalar() or 0.0
    
    # Update site with calculated area
    site.area_m2 = area_m2
    
    # Upload original file to S3
    try:
        s3_service = get_s3_service()
        await s3_service.upload_site_file(
            site_id=str(site.id),
            content=content,
            filename=file.filename,
            content_type=file.content_type,
        )
    except Exception as e:
        logger.error(f"Failed to upload to S3: {e}")
        # Continue without S3 - the site record is still valid
        # In production, you might want to rollback or retry
    
    # Get boundary as GeoJSON for response
    geojson_result = await db.execute(
        select(ST_AsGeoJSON(Site.boundary)).where(Site.id == site.id)
    )
    boundary_geojson = json.loads(geojson_result.scalar() or "{}")
    
    await db.commit()
    
    logger.info(f"Created site {site.id} for user {current_user.email}")
    
    return SiteUploadResponse(
        id=site.id,
        name=site.name,
        area_m2=site.area_m2,
        boundary=boundary_geojson,
        created_at=site.created_at,
    )


@router.get(
    "/{site_id}",
    response_model=SiteResponse,
    summary="Get site details",
    description="Retrieve site details including boundary as GeoJSON.",
)
async def get_site(
    site_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SiteResponse:
    """
    Get site details by ID.
    
    Returns 404 if the site doesn't exist or belongs to another user.
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
    
    return SiteResponse(
        id=site.id,
        project_id=site.project_id,
        name=site.name,
        area_m2=site.area_m2,
        boundary=boundary_geojson,
        created_at=site.created_at,
        updated_at=site.updated_at,
    )


@router.get(
    "",
    response_model=SiteListResponse,
    summary="List sites",
    description="List all sites owned by the current user.",
)
async def list_sites(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SiteListResponse:
    """
    List all sites for the current user.
    
    Returns basic site info without full geometry.
    """
    result = await db.execute(
        select(Site)
        .where(Site.owner_id == current_user.id)
        .order_by(Site.created_at.desc())
    )
    sites = result.scalars().all()
    
    return SiteListResponse(
        sites=[
            {
                "id": site.id,
                "name": site.name,
                "area_m2": site.area_m2,
                "created_at": site.created_at,
            }
            for site in sites
        ],
        total=len(sites),
    )


@router.delete(
    "/{site_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete site",
    description="Delete a site and all associated data.",
)
async def delete_site(
    site_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """
    Delete a site by ID.
    
    Also deletes associated files from S3.
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
    
    # Delete from S3
    try:
        s3_service = get_s3_service()
        await s3_service.delete_site_files(str(site.id))
    except Exception as e:
        logger.warning(f"Failed to delete S3 files for site {site_id}: {e}")
    
    # Delete from database
    await db.delete(site)
    await db.commit()
    
    logger.info(f"Deleted site {site_id} for user {current_user.email}")


# =============================================================================
# D-05-06: Preferred Layout Management
# =============================================================================


@router.put(
    "/{site_id}/preferred-layout",
    response_model=PreferredLayoutResponse,
    summary="Set preferred layout",
    description="D-05-06: Set or clear the preferred layout variant for a site.",
)
async def set_preferred_layout(
    site_id: UUID,
    request: SetPreferredLayoutRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PreferredLayoutResponse:
    """
    Set the preferred layout for a site (D-05-06).
    
    - **layout_id**: UUID of the layout to mark as preferred, or null to clear
    
    The layout must belong to this site. Returns 400 if the layout
    doesn't exist or belongs to a different site.
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
    
    # If layout_id provided, verify it belongs to this site
    if request.layout_id:
        layout_result = await db.execute(
            select(Layout).where(
                Layout.id == request.layout_id,
                Layout.site_id == site_id,
            )
        )
        layout = layout_result.scalar_one_or_none()
        
        if not layout:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Layout not found or does not belong to this site",
            )
        
        site.preferred_layout_id = request.layout_id
        message = f"Layout {request.layout_id} marked as preferred"
        logger.info(f"Set preferred layout {request.layout_id} for site {site_id}")
    else:
        # Clear preferred layout
        site.preferred_layout_id = None
        message = "Preferred layout cleared"
        logger.info(f"Cleared preferred layout for site {site_id}")
    
    await db.commit()
    
    return PreferredLayoutResponse(
        site_id=site.id,
        preferred_layout_id=site.preferred_layout_id,
        message=message,
    )


@router.get(
    "/{site_id}/preferred-layout",
    response_model=PreferredLayoutResponse,
    summary="Get preferred layout",
    description="D-05-06: Get the current preferred layout for a site.",
)
async def get_preferred_layout(
    site_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PreferredLayoutResponse:
    """
    Get the preferred layout for a site (D-05-06).
    
    Returns the preferred layout ID or null if none is set.
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
    
    return PreferredLayoutResponse(
        site_id=site.id,
        preferred_layout_id=site.preferred_layout_id,
        message="Preferred layout retrieved" if site.preferred_layout_id else "No preferred layout set",
    )

