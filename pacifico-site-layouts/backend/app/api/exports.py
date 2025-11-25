"""
Export API endpoints.

Provides layout exports in various formats:
- GeoJSON (B-08)
- KMZ for Google Earth (B-09)
- PDF report (B-10)
"""
import json
import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from geoalchemy2.functions import ST_AsGeoJSON
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import get_current_user
from app.database import get_db
from app.models.asset import Asset
from app.models.layout import Layout
from app.models.road import Road
from app.models.site import Site
from app.models.user import User
from app.services.export_service import get_export_service
from app.services.terrain_layout_generator import TerrainAwareLayoutGenerator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/layouts", tags=["Exports"])


class ExportResponse(BaseModel):
    """Response schema for export endpoints."""
    
    download_url: str = Field(..., description="Presigned URL for downloading the export")
    format: str = Field(..., description="Export format (geojson, kmz, pdf)")
    expires_in_seconds: int = Field(default=3600, description="URL expiration time")


async def _get_layout_with_details(
    layout_id: UUID,
    current_user: User,
    db: AsyncSession,
) -> tuple[Layout, Site, list[dict], list[dict]]:
    """
    Get layout with ownership verification and full details.
    
    Returns tuple of (layout, site, assets_list, roads_list)
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
    
    # Get site
    site_result = await db.execute(
        select(Site).where(Site.id == layout.site_id)
    )
    site = site_result.scalar_one()
    
    # Build asset list with GeoJSON positions
    assets = []
    for asset in layout.assets:
        pos_result = await db.execute(
            select(ST_AsGeoJSON(Asset.position)).where(Asset.id == asset.id)
        )
        position_geojson = json.loads(pos_result.scalar() or "{}")
        
        assets.append({
            "id": str(asset.id),
            "asset_type": asset.asset_type,
            "name": asset.name,
            "capacity_kw": asset.capacity_kw,
            "elevation_m": asset.elevation_m,
            "slope_deg": asset.slope_deg,
            "position": position_geojson,
        })
    
    # Build road list with GeoJSON geometries
    roads = []
    for road in layout.roads:
        geom_result = await db.execute(
            select(ST_AsGeoJSON(Road.geometry)).where(Road.id == road.id)
        )
        geometry_geojson = json.loads(geom_result.scalar() or "{}")
        
        roads.append({
            "id": str(road.id),
            "name": road.name,
            "length_m": road.length_m,
            "max_grade_pct": road.max_grade_pct,
            "geometry": geometry_geojson,
        })
    
    return layout, site, assets, roads


@router.get(
    "/{layout_id}/export/geojson",
    response_model=ExportResponse,
    summary="Export layout as GeoJSON",
    description="Generate a GeoJSON export of the layout with all assets and roads.",
)
async def export_geojson(
    layout_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExportResponse:
    """
    Export layout as GeoJSON FeatureCollection.
    
    Returns a presigned URL to download the GeoJSON file.
    """
    layout, site, assets, roads = await _get_layout_with_details(
        layout_id, current_user, db
    )
    
    # Build GeoJSON FeatureCollection
    features = []
    
    for asset in assets:
        features.append({
            "type": "Feature",
            "geometry": asset["position"],
            "properties": {
                "feature_type": "asset",
                "id": asset["id"],
                "asset_type": asset["asset_type"],
                "name": asset["name"],
                "capacity_kw": asset["capacity_kw"],
                "elevation_m": asset["elevation_m"],
                "slope_deg": asset["slope_deg"],
            },
        })
    
    for road in roads:
        features.append({
            "type": "Feature",
            "geometry": road["geometry"],
            "properties": {
                "feature_type": "road",
                "id": road["id"],
                "name": road["name"],
                "length_m": road["length_m"],
                "max_grade_pct": road["max_grade_pct"],
            },
        })
    
    geojson = {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "layout_id": str(layout.id),
            "site_id": str(site.id),
            "site_name": site.name,
            "total_capacity_kw": layout.total_capacity_kw,
            "cut_volume_m3": layout.cut_volume_m3,
            "fill_volume_m3": layout.fill_volume_m3,
        },
    }
    
    export_service = get_export_service()
    download_url = await export_service.export_geojson(
        layout_id=layout.id,
        geojson=geojson,
        site_name=site.name,
    )
    
    return ExportResponse(
        download_url=download_url,
        format="geojson",
        expires_in_seconds=3600,
    )


@router.get(
    "/{layout_id}/export/kmz",
    response_model=ExportResponse,
    summary="Export layout as KMZ",
    description="Generate a KMZ export for viewing in Google Earth.",
)
async def export_kmz(
    layout_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExportResponse:
    """
    Export layout as KMZ for Google Earth.
    
    Returns a presigned URL to download the KMZ file.
    """
    layout, site, assets, roads = await _get_layout_with_details(
        layout_id, current_user, db
    )
    
    # Get site boundary as GeoJSON
    boundary_result = await db.execute(
        select(ST_AsGeoJSON(Site.boundary)).where(Site.id == site.id)
    )
    boundary_geojson = json.loads(boundary_result.scalar() or "{}")
    
    export_service = get_export_service()
    download_url = await export_service.export_kmz(
        layout_id=layout.id,
        site_name=site.name,
        site_boundary=boundary_geojson,
        assets=assets,
        roads=roads,
    )
    
    return ExportResponse(
        download_url=download_url,
        format="kmz",
        expires_in_seconds=3600,
    )


@router.get(
    "/{layout_id}/export/pdf",
    response_model=ExportResponse,
    summary="Export layout as PDF report",
    description="Generate a PDF report with layout summary and asset inventory.",
)
async def export_pdf(
    layout_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExportResponse:
    """
    Export layout as PDF report.
    
    Returns a presigned URL to download the PDF file.
    """
    layout, site, assets, roads = await _get_layout_with_details(
        layout_id, current_user, db
    )
    
    layout_data = {
        "total_capacity_kw": layout.total_capacity_kw,
        "cut_volume_m3": layout.cut_volume_m3,
        "fill_volume_m3": layout.fill_volume_m3,
        "terrain_processed": layout.terrain_processed,
    }
    
    export_service = get_export_service()
    download_url = await export_service.export_pdf(
        layout_id=layout.id,
        site_name=site.name,
        site_area_m2=site.area_m2 or 0,
        layout_data=layout_data,
        assets=assets,
        roads=roads,
    )
    
    return ExportResponse(
        download_url=download_url,
        format="pdf",
        expires_in_seconds=3600,
    )

