"""
Layout management API endpoints.

Handles layout generation, retrieval, and listing.
"""
import json
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from geoalchemy2.functions import ST_AsGeoJSON, ST_GeomFromText, ST_Length, ST_SetSRID
from shapely import wkt
from shapely.geometry import mapping
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import get_current_user
from app.database import get_db
from app.models.asset import Asset
from app.models.layout import Layout, LayoutStatus
from app.models.road import Road
from app.models.site import Site
from app.models.user import User
from app.schemas.layout import (
    AssetResponse,
    GenerateLayoutRequest,
    LayoutDetailResponse,
    LayoutGenerateResponse,
    LayoutListResponse,
    LayoutResponse,
    RoadResponse,
)
from app.services.layout_generator import DummyLayoutGenerator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/layouts", tags=["Layouts"])


@router.post(
    "/generate",
    response_model=LayoutGenerateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate layout",
    description="Generate a new layout with dummy asset placement for a site.",
)
async def generate_layout(
    request: GenerateLayoutRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LayoutGenerateResponse:
    """
    Generate a new layout for a site.
    
    For Phase A, this creates dummy assets placed in a grid pattern
    within the site boundary. Phase B will implement terrain-aware placement.
    
    - **site_id**: UUID of the site to generate layout for
    - **target_capacity_kw**: Target total capacity in kW (default: 1000)
    
    Returns the generated layout with assets and roads as GeoJSON.
    """
    # Load site with ownership check
    site_result = await db.execute(
        select(Site).where(
            Site.id == request.site_id,
            Site.owner_id == current_user.id,
        )
    )
    site = site_result.scalar_one_or_none()
    
    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site not found",
        )
    
    # Get site boundary as WKT for Shapely
    boundary_wkt_result = await db.execute(
        select(Site.boundary.ST_AsText()).where(Site.id == site.id)
    )
    boundary_wkt = boundary_wkt_result.scalar()
    
    if not boundary_wkt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Site has no boundary geometry",
        )
    
    # Parse boundary with Shapely
    try:
        boundary = wkt.loads(boundary_wkt)
    except Exception as e:
        logger.error(f"Failed to parse site boundary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to parse site boundary",
        )
    
    # Create Layout record
    layout = Layout(
        site_id=site.id,
        status=LayoutStatus.COMPLETED.value,  # Synchronous for Phase A
    )
    db.add(layout)
    await db.flush()  # Get the ID
    
    # Generate dummy layout
    generator = DummyLayoutGenerator(target_capacity_kw=request.target_capacity_kw)
    
    try:
        placed_assets, placed_roads = generator.generate(
            boundary=boundary,
            num_assets=random_asset_count(request.target_capacity_kw),
        )
    except Exception as e:
        logger.exception(f"Layout generation failed: {e}")
        layout.status = LayoutStatus.FAILED.value
        layout.error_message = str(e)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Layout generation failed: {e}",
        )
    
    # Create Asset records
    total_capacity = 0.0
    asset_responses = []
    
    for placed in placed_assets:
        asset = Asset(
            layout_id=layout.id,
            asset_type=placed.asset_type,
            name=placed.name,
            position=ST_SetSRID(
                ST_GeomFromText(placed.position.wkt),
                4326
            ),
            capacity_kw=placed.capacity_kw,
            footprint_length_m=placed.footprint_length_m,
            footprint_width_m=placed.footprint_width_m,
        )
        db.add(asset)
        await db.flush()
        
        total_capacity += placed.capacity_kw or 0
        
        asset_responses.append(AssetResponse(
            id=asset.id,
            asset_type=asset.asset_type,
            name=asset.name,
            capacity_kw=asset.capacity_kw,
            position=mapping(placed.position),
        ))
    
    # Create Road records
    road_responses = []
    total_road_length = 0.0
    
    for placed in placed_roads:
        road = Road(
            layout_id=layout.id,
            name=placed.name,
            geometry=ST_SetSRID(
                ST_GeomFromText(placed.geometry.wkt),
                4326
            ),
            length_m=placed.length_m,
            width_m=placed.width_m,
        )
        db.add(road)
        await db.flush()
        
        total_road_length += placed.length_m or 0
        
        road_responses.append(RoadResponse(
            id=road.id,
            name=road.name,
            length_m=road.length_m,
            geometry=mapping(placed.geometry),
        ))
    
    # Update layout with totals
    layout.total_capacity_kw = round(total_capacity, 1)
    
    await db.commit()
    
    # Generate GeoJSON
    geojson = DummyLayoutGenerator.to_geojson_feature_collection(
        placed_assets,
        placed_roads,
    )
    
    logger.info(
        f"Generated layout {layout.id} for site {site.id}: "
        f"{len(asset_responses)} assets, {len(road_responses)} roads, "
        f"{total_capacity:.1f} kW total capacity"
    )
    
    return LayoutGenerateResponse(
        layout=LayoutResponse(
            id=layout.id,
            site_id=layout.site_id,
            status=layout.status,
            total_capacity_kw=layout.total_capacity_kw,
            cut_volume_m3=layout.cut_volume_m3,
            fill_volume_m3=layout.fill_volume_m3,
            error_message=layout.error_message,
            created_at=layout.created_at,
            updated_at=layout.updated_at,
        ),
        assets=asset_responses,
        roads=road_responses,
        geojson=geojson,
    )


@router.get(
    "/{layout_id}",
    response_model=LayoutDetailResponse,
    summary="Get layout details",
    description="Retrieve layout details including assets and roads.",
)
async def get_layout(
    layout_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LayoutDetailResponse:
    """
    Get layout details by ID.
    
    Returns 404 if the layout doesn't exist or belongs to another user.
    """
    # Query layout with ownership check through site
    result = await db.execute(
        select(Layout)
        .options(selectinload(Layout.assets), selectinload(Layout.roads))
        .join(Site)
        .where(
            Layout.id == layout_id,
            Site.owner_id == current_user.id,
        )
    )
    layout = result.scalar_one_or_none()
    
    if not layout:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Layout not found",
        )
    
    # Build asset responses with GeoJSON positions
    asset_responses = []
    for asset in layout.assets:
        # Get position as GeoJSON
        pos_result = await db.execute(
            select(ST_AsGeoJSON(Asset.position)).where(Asset.id == asset.id)
        )
        position_geojson = json.loads(pos_result.scalar() or "{}")
        
        asset_responses.append(AssetResponse(
            id=asset.id,
            asset_type=asset.asset_type,
            name=asset.name,
            capacity_kw=asset.capacity_kw,
            position=position_geojson,
        ))
    
    # Build road responses with GeoJSON geometries
    road_responses = []
    for road in layout.roads:
        # Get geometry as GeoJSON
        geom_result = await db.execute(
            select(ST_AsGeoJSON(Road.geometry)).where(Road.id == road.id)
        )
        geometry_geojson = json.loads(geom_result.scalar() or "{}")
        
        road_responses.append(RoadResponse(
            id=road.id,
            name=road.name,
            length_m=road.length_m,
            geometry=geometry_geojson,
        ))
    
    return LayoutDetailResponse(
        id=layout.id,
        site_id=layout.site_id,
        status=layout.status,
        total_capacity_kw=layout.total_capacity_kw,
        cut_volume_m3=layout.cut_volume_m3,
        fill_volume_m3=layout.fill_volume_m3,
        error_message=layout.error_message,
        created_at=layout.created_at,
        updated_at=layout.updated_at,
        assets=asset_responses,
        roads=road_responses,
    )


@router.get(
    "",
    response_model=LayoutListResponse,
    summary="List layouts",
    description="List all layouts for the current user.",
)
async def list_layouts(
    site_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LayoutListResponse:
    """
    List layouts for the current user.
    
    Optionally filter by site_id.
    """
    query = (
        select(Layout)
        .join(Site)
        .where(Site.owner_id == current_user.id)
        .order_by(Layout.created_at.desc())
    )
    
    if site_id:
        query = query.where(Layout.site_id == site_id)
    
    result = await db.execute(query)
    layouts = result.scalars().all()
    
    return LayoutListResponse(
        layouts=[
            {
                "id": layout.id,
                "site_id": layout.site_id,
                "status": layout.status,
                "total_capacity_kw": layout.total_capacity_kw,
                "created_at": layout.created_at,
            }
            for layout in layouts
        ],
        total=len(layouts),
    )


@router.delete(
    "/{layout_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete layout",
    description="Delete a layout and all associated assets and roads.",
)
async def delete_layout(
    layout_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """
    Delete a layout by ID.
    """
    # Query layout with ownership check through site
    result = await db.execute(
        select(Layout)
        .join(Site)
        .where(
            Layout.id == layout_id,
            Site.owner_id == current_user.id,
        )
    )
    layout = result.scalar_one_or_none()
    
    if not layout:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Layout not found",
        )
    
    # Delete layout (cascades to assets and roads)
    await db.delete(layout)
    await db.commit()
    
    logger.info(f"Deleted layout {layout_id}")


def random_asset_count(target_capacity_kw: float) -> int:
    """
    Determine number of assets based on target capacity.
    
    Roughly scales between 5-15 assets based on capacity.
    """
    import random
    
    base = 5
    if target_capacity_kw > 500:
        base += int((target_capacity_kw - 500) / 500)
    
    # Add some randomness
    return min(15, max(5, base + random.randint(-1, 2)))

