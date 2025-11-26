"""
Exclusion Zones API endpoints.

Phase D-03: CRUD operations for exclusion zones.
Allows users to define areas where assets cannot be placed.
"""
import json
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from geoalchemy2.functions import ST_AsGeoJSON, ST_Area, ST_Transform, ST_GeomFromGeoJSON
from shapely.geometry import shape
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.exclusion_zone import ExclusionZone, ZONE_TYPE_DEFAULTS, ExclusionZoneType as ModelZoneType
from app.models.site import Site
from app.models.user import User
from app.schemas.exclusion_zone import (
    ExclusionZoneCreate,
    ExclusionZoneListResponse,
    ExclusionZoneResponse,
    ExclusionZoneTypesResponse,
    ExclusionZoneUpdate,
    ZONE_TYPE_INFO,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sites", tags=["Exclusion Zones"])


async def _verify_site_ownership(
    site_id: UUID,
    current_user: User,
    db: AsyncSession,
) -> Site:
    """Verify user owns the site and return it."""
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
    
    return site


def _zone_to_response(zone: ExclusionZone, geometry_geojson: dict) -> ExclusionZoneResponse:
    """Convert ExclusionZone model to response schema."""
    # Get color from zone type defaults
    try:
        zone_type_enum = ModelZoneType(zone.zone_type)
        color = ZONE_TYPE_DEFAULTS.get(zone_type_enum, {}).get("color", "#6b7280")
    except ValueError:
        color = "#6b7280"
    
    return ExclusionZoneResponse(
        id=zone.id,
        site_id=zone.site_id,
        name=zone.name,
        zone_type=zone.zone_type,
        geometry=geometry_geojson,
        buffer_m=zone.buffer_m,
        description=zone.description,
        area_m2=zone.area_m2,
        color=color,
        created_at=zone.created_at,
        updated_at=zone.updated_at,
    )


# Note: /exclusion-zone-types endpoint moved to sites.py to avoid path conflict with /{site_id}


@router.get(
    "/{site_id}/exclusion-zones",
    response_model=ExclusionZoneListResponse,
    summary="List exclusion zones for a site",
    description="Get all exclusion zones defined for a specific site.",
)
async def list_exclusion_zones(
    site_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExclusionZoneListResponse:
    """List all exclusion zones for a site."""
    # Verify site ownership
    await _verify_site_ownership(site_id, current_user, db)
    
    # Get all zones for this site
    result = await db.execute(
        select(ExclusionZone).where(ExclusionZone.site_id == site_id)
        .order_by(ExclusionZone.created_at.desc())
    )
    zones = result.scalars().all()
    
    # Build response with GeoJSON geometries
    zone_responses = []
    for zone in zones:
        geom_result = await db.execute(
            select(ST_AsGeoJSON(ExclusionZone.geometry))
            .where(ExclusionZone.id == zone.id)
        )
        geometry_geojson = json.loads(geom_result.scalar() or "{}")
        zone_responses.append(_zone_to_response(zone, geometry_geojson))
    
    return ExclusionZoneListResponse(
        zones=zone_responses,
        total=len(zone_responses),
        site_id=site_id,
    )


@router.get(
    "/{site_id}/exclusion-zones/{zone_id}",
    response_model=ExclusionZoneResponse,
    summary="Get a specific exclusion zone",
    description="Get details for a specific exclusion zone.",
)
async def get_exclusion_zone(
    site_id: UUID,
    zone_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExclusionZoneResponse:
    """Get a specific exclusion zone."""
    # Verify site ownership
    await _verify_site_ownership(site_id, current_user, db)
    
    # Get the zone
    result = await db.execute(
        select(ExclusionZone).where(
            ExclusionZone.id == zone_id,
            ExclusionZone.site_id == site_id,
        )
    )
    zone = result.scalar_one_or_none()
    
    if not zone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exclusion zone not found",
        )
    
    # Get geometry as GeoJSON
    geom_result = await db.execute(
        select(ST_AsGeoJSON(ExclusionZone.geometry))
        .where(ExclusionZone.id == zone.id)
    )
    geometry_geojson = json.loads(geom_result.scalar() or "{}")
    
    return _zone_to_response(zone, geometry_geojson)


@router.post(
    "/{site_id}/exclusion-zones",
    response_model=ExclusionZoneResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an exclusion zone",
    description="Create a new exclusion zone for a site.",
)
async def create_exclusion_zone(
    site_id: UUID,
    zone_data: ExclusionZoneCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExclusionZoneResponse:
    """Create a new exclusion zone."""
    # Verify site ownership
    await _verify_site_ownership(site_id, current_user, db)
    
    # Convert GeoJSON to WKT for PostGIS
    geojson_str = json.dumps(zone_data.geometry)
    
    # Calculate area in square meters using ST_Area with transform to UTM
    # We'll calculate this after insertion using the stored geometry
    
    # Create the zone
    zone = ExclusionZone(
        name=zone_data.name,
        zone_type=zone_data.zone_type.value,
        geometry=f"SRID=4326;{shape(zone_data.geometry).wkt}",
        buffer_m=zone_data.buffer_m,
        description=zone_data.description,
        site_id=site_id,
    )
    
    db.add(zone)
    await db.flush()
    
    # Calculate area in m² using PostGIS
    # Transform to a suitable projection for area calculation (EPSG:3857 for web mercator)
    area_result = await db.execute(
        select(ST_Area(ST_Transform(ExclusionZone.geometry, 3857)))
        .where(ExclusionZone.id == zone.id)
    )
    area_m2 = area_result.scalar() or 0
    
    # Update the zone with calculated area
    zone.area_m2 = area_m2
    
    await db.commit()
    await db.refresh(zone)
    
    # Get geometry as GeoJSON for response
    geom_result = await db.execute(
        select(ST_AsGeoJSON(ExclusionZone.geometry))
        .where(ExclusionZone.id == zone.id)
    )
    geometry_geojson = json.loads(geom_result.scalar() or "{}")
    
    logger.info(f"Created exclusion zone {zone.id} for site {site_id}: {zone.name}")
    
    return _zone_to_response(zone, geometry_geojson)


@router.put(
    "/{site_id}/exclusion-zones/{zone_id}",
    response_model=ExclusionZoneResponse,
    summary="Update an exclusion zone",
    description="Update an existing exclusion zone.",
)
async def update_exclusion_zone(
    site_id: UUID,
    zone_id: UUID,
    zone_data: ExclusionZoneUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExclusionZoneResponse:
    """Update an exclusion zone."""
    # Verify site ownership
    await _verify_site_ownership(site_id, current_user, db)
    
    # Get the zone
    result = await db.execute(
        select(ExclusionZone).where(
            ExclusionZone.id == zone_id,
            ExclusionZone.site_id == site_id,
        )
    )
    zone = result.scalar_one_or_none()
    
    if not zone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exclusion zone not found",
        )
    
    # Update fields
    if zone_data.name is not None:
        zone.name = zone_data.name
    if zone_data.zone_type is not None:
        zone.zone_type = zone_data.zone_type.value
    if zone_data.buffer_m is not None:
        zone.buffer_m = zone_data.buffer_m
    if zone_data.description is not None:
        zone.description = zone_data.description
    
    # Update geometry if provided
    if zone_data.geometry is not None:
        zone.geometry = f"SRID=4326;{shape(zone_data.geometry).wkt}"
        
        # Recalculate area
        await db.flush()
        area_result = await db.execute(
            select(ST_Area(ST_Transform(ExclusionZone.geometry, 3857)))
            .where(ExclusionZone.id == zone.id)
        )
        zone.area_m2 = area_result.scalar() or 0
    
    await db.commit()
    await db.refresh(zone)
    
    # Get geometry as GeoJSON for response
    geom_result = await db.execute(
        select(ST_AsGeoJSON(ExclusionZone.geometry))
        .where(ExclusionZone.id == zone.id)
    )
    geometry_geojson = json.loads(geom_result.scalar() or "{}")
    
    logger.info(f"Updated exclusion zone {zone.id}: {zone.name}")
    
    return _zone_to_response(zone, geometry_geojson)


@router.delete(
    "/{site_id}/exclusion-zones/{zone_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an exclusion zone",
    description="Delete an exclusion zone from a site.",
)
async def delete_exclusion_zone(
    site_id: UUID,
    zone_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete an exclusion zone."""
    # Verify site ownership
    await _verify_site_ownership(site_id, current_user, db)
    
    # Delete the zone
    result = await db.execute(
        delete(ExclusionZone).where(
            ExclusionZone.id == zone_id,
            ExclusionZone.site_id == site_id,
        )
    )
    
    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exclusion zone not found",
        )
    
    await db.commit()
    
    logger.info(f"Deleted exclusion zone {zone_id} from site {site_id}")

