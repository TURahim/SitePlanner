"""
Site management API endpoints.

Handles site upload, retrieval, and listing.

D-05-06: Added preferred layout management endpoint.
Phase 2 (GAP): Added regulatory-sync endpoint for auto-populating exclusion zones.
"""
import json
import logging
from typing import Annotated, Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from geoalchemy2.functions import ST_Area, ST_AsGeoJSON, ST_GeomFromText, ST_SetSRID, ST_Transform
from pydantic import BaseModel, Field
from shapely import wkt
from shapely.geometry import shape
from sqlalchemy import cast, select
from geoalchemy2 import Geography
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.exclusion_zone import ExclusionZone
from app.models.layout import Layout
from app.models.site import Site
from app.models.user import User
from app.schemas.site import SiteListResponse, SiteResponse, SiteUploadResponse
from app.schemas.exclusion_zone import ExclusionZoneTypesResponse, ExclusionZoneResponse, ZONE_TYPE_INFO
from app.services.kml_parser import KMLParseError, KMLParser
from app.services.regulatory_service import get_regulatory_service, RegulatoryLayerType
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


# =============================================================================
# Phase 2 (GAP): Regulatory Sync Schemas
# =============================================================================


class RegulatoryLayerInfo(BaseModel):
    """Information about a regulatory data layer."""
    type: str
    name: str
    zone_type: str
    default_buffer_m: float
    default_cost_multiplier: float
    description: str


class RegulatorySyncRequest(BaseModel):
    """Request schema for regulatory data sync."""
    layer_types: Optional[list[str]] = Field(
        None,
        description="List of layer types to sync (None = all available)",
        examples=[["wetland", "floodplain", "setback"]]
    )
    replace_existing: bool = Field(
        False,
        description="If true, delete existing auto-synced zones before creating new ones"
    )


class RegulatorySyncResponse(BaseModel):
    """Response schema for regulatory data sync."""
    site_id: UUID
    zones_created: int
    zones_deleted: int = 0
    zones: list[ExclusionZoneResponse]
    message: str


class RegulatoryLayersResponse(BaseModel):
    """Response schema for available regulatory layers."""
    layers: list[RegulatoryLayerInfo]


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
# Phase 2 (GAP): Regulatory Data Integration
# =============================================================================


@router.get(
    "/regulatory-layers",
    response_model=RegulatoryLayersResponse,
    summary="Get available regulatory layers",
    description="Phase 2: Returns available regulatory data layers that can be synced.",
)
async def get_regulatory_layers() -> RegulatoryLayersResponse:
    """
    Get available regulatory data layers (Phase 2).
    
    Returns information about layer types that can be fetched via regulatory-sync.
    """
    service = get_regulatory_service()
    layers = service.get_available_layers()
    
    return RegulatoryLayersResponse(
        layers=[RegulatoryLayerInfo(**layer) for layer in layers]
    )


@router.post(
    "/{site_id}/regulatory-sync",
    response_model=RegulatorySyncResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Sync regulatory data",
    description="Phase 2: Fetch regulatory/environmental data and create exclusion zones.",
)
async def sync_regulatory_data(
    site_id: UUID,
    request: RegulatorySyncRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RegulatorySyncResponse:
    """
    Sync regulatory data for a site (Phase 2 GAP Implementation).
    
    Fetches regulatory and environmental constraint data (e.g., wetlands,
    flood zones, setbacks) and creates corresponding exclusion zones.
    
    **Layer Types:**
    - `wetland`: NWI wetland areas
    - `floodplain`: FEMA flood zones
    - `setback`: Property line setbacks
    - `utility_corridor`: Existing utility corridors
    
    **Note:** Currently uses mock data for development. Real API integrations
    (FEMA, NWI, etc.) will be added in future iterations.
    
    Parameters:
    - **site_id**: UUID of the site
    - **layer_types**: Optional list of layer types (None = all)
    - **replace_existing**: If true, deletes existing synced zones first
    """
    # Verify site ownership
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
    
    # Get site boundary as Shapely polygon
    boundary_wkt_result = await db.execute(
        select(Site.boundary.ST_AsText()).where(Site.id == site.id)
    )
    boundary_wkt = boundary_wkt_result.scalar()
    
    if not boundary_wkt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Site has no boundary geometry",
        )
    
    try:
        boundary = wkt.loads(boundary_wkt)
    except Exception as e:
        logger.error(f"Failed to parse site boundary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to parse site boundary",
        )
    
    # Optionally delete existing synced zones
    zones_deleted = 0
    if request.replace_existing:
        # Delete zones that were created by regulatory sync (have description starting with mock/regulatory source)
        # For now, we'll delete all zones with certain names pattern
        existing_result = await db.execute(
            select(ExclusionZone).where(
                ExclusionZone.site_id == site_id,
                ExclusionZone.description.like("%Mock%") | 
                ExclusionZone.description.like("%FEMA%") |
                ExclusionZone.description.like("%NWI%")
            )
        )
        existing_zones = existing_result.scalars().all()
        for zone in existing_zones:
            await db.delete(zone)
            zones_deleted += 1
        
        if zones_deleted > 0:
            await db.flush()
            logger.info(f"Deleted {zones_deleted} existing synced zones for site {site_id}")
    
    # Fetch regulatory data
    service = get_regulatory_service()
    zone_data_list = await service.sync_regulatory_data(
        site_id=site_id,
        boundary=boundary,
        layer_types=request.layer_types,
    )
    
    # Create exclusion zone records
    created_zones = []
    for zone_data in zone_data_list:
        geometry_geojson = zone_data.pop("geometry")
        zone_site_id = zone_data.pop("site_id")
        
        # Convert GeoJSON to WKT for PostGIS
        try:
            geom_shape = shape(geometry_geojson)
            geom_wkt = geom_shape.wkt
        except Exception as e:
            logger.warning(f"Failed to convert geometry: {e}")
            continue
        
        # Calculate area
        area_m2 = geom_shape.area * (111000 ** 2)  # Approximate conversion from degrees²
        
        zone = ExclusionZone(
            site_id=zone_site_id,
            name=zone_data["name"],
            zone_type=zone_data["zone_type"],
            geometry=ST_SetSRID(ST_GeomFromText(geom_wkt), 4326),
            buffer_m=zone_data["buffer_m"],
            cost_multiplier=zone_data["cost_multiplier"],
            description=zone_data.get("description"),
            area_m2=area_m2,
        )
        db.add(zone)
        await db.flush()
        
        # Get geometry as GeoJSON for response
        geojson_result = await db.execute(
            select(ST_AsGeoJSON(ExclusionZone.geometry)).where(ExclusionZone.id == zone.id)
        )
        geometry_json = json.loads(geojson_result.scalar() or "{}")
        
        created_zones.append(ExclusionZoneResponse(
            id=zone.id,
            site_id=zone.site_id,
            name=zone.name,
            zone_type=zone.zone_type,
            geometry=geometry_json,
            buffer_m=zone.buffer_m,
            cost_multiplier=zone.cost_multiplier,
            description=zone.description,
            area_m2=zone.area_m2,
            color=zone.color,
            created_at=zone.created_at,
            updated_at=zone.updated_at,
        ))
    
    await db.commit()
    
    logger.info(
        f"Regulatory sync for site {site_id}: created {len(created_zones)} zones, "
        f"deleted {zones_deleted} existing"
    )
    
    return RegulatorySyncResponse(
        site_id=site_id,
        zones_created=len(created_zones),
        zones_deleted=zones_deleted,
        zones=created_zones,
        message=f"Created {len(created_zones)} exclusion zones from regulatory data",
    )


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

