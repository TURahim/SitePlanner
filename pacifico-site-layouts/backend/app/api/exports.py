"""
Export API endpoints.

Provides layout exports in various formats:
- GeoJSON (B-08)
- KMZ for Google Earth (B-09)
- PDF report (B-10)
- CSV tabular data (D-04-05)

Phase D-04 enhancements:
- Filenames include site name and timestamp
- PDF includes terrain summary
- GeoJSON includes terrain metadata
- KMZ includes slope/buildability styling
"""
import json
import logging
import re
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from geoalchemy2.functions import ST_AsGeoJSON
from pydantic import BaseModel, Field
from shapely.geometry import shape
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
from app.services.terrain_visualization_service import get_terrain_visualization_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/layouts", tags=["Exports"])


def sanitize_filename(name: str) -> str:
    """Sanitize site name for use in filename."""
    # Replace spaces with underscores, remove special chars
    sanitized = re.sub(r'[^\w\s-]', '', name)
    sanitized = re.sub(r'\s+', '_', sanitized)
    return sanitized[:50]  # Limit length


def generate_export_filename(site_name: str, layout_id: UUID, format_ext: str) -> str:
    """
    Generate export filename with site name and timestamp.
    
    D-04-06: Format: {site_name}_{layout_id_short}_{timestamp}.{format}
    Example: Permian_Basin_Site_a1b2c3_20251125_143022.pdf
    """
    sanitized_name = sanitize_filename(site_name)
    layout_id_short = str(layout_id)[:8]
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    return f"{sanitized_name}_{layout_id_short}_{timestamp}.{format_ext}"


class ExportResponse(BaseModel):
    """Response schema for export endpoints."""
    
    download_url: str = Field(..., description="Presigned URL for downloading the export")
    format: str = Field(..., description="Export format (geojson, kmz, pdf, csv)")
    filename: str = Field(..., description="Suggested filename for download")
    expires_in_seconds: int = Field(default=3600, description="URL expiration time")


async def _get_layout_with_details(
    layout_id: UUID,
    current_user: User,
    db: AsyncSession,
    include_terrain: bool = False,
) -> tuple[Layout, Site, list[dict], list[dict], Optional[dict]]:
    """
    Get layout with ownership verification and full details.
    
    Args:
        layout_id: UUID of the layout
        current_user: Authenticated user
        db: Database session
        include_terrain: Whether to fetch terrain summary (D-04)
    
    Returns tuple of (layout, site, assets_list, roads_list, terrain_summary)
    """
    # Query layout with ownership check through site
    # Note: Must specify join condition explicitly because Site has preferred_layout_id FK back to Layout
    result = await db.execute(
        select(Layout)
        .options(selectinload(Layout.assets), selectinload(Layout.roads))
        .join(Site, Layout.site_id == Site.id)
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
    
    # Get site with boundary
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
            "footprint_length_m": asset.footprint_length_m,
            "footprint_width_m": asset.footprint_width_m,
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
    
    # D-04: Fetch terrain summary if requested and terrain was processed
    terrain_summary = None
    if include_terrain and layout.terrain_processed:
        try:
            # Get site boundary as shapely geometry
            boundary_result = await db.execute(
                select(ST_AsGeoJSON(Site.boundary)).where(Site.id == site.id)
            )
            boundary_geojson = json.loads(boundary_result.scalar() or "{}")
            if boundary_geojson:
                boundary_polygon = shape(boundary_geojson)
                terrain_service = get_terrain_visualization_service()
                terrain_summary = await terrain_service.get_terrain_summary(
                    site.id, db, boundary_polygon
                )
        except ValueError as e:
            # DEM/slope data not available - continue without terrain summary
            logger.warning(f"Terrain data not available for export: {e}")
        except Exception as e:
            logger.warning(f"Could not fetch terrain summary for export: {e}")
    
    return layout, site, assets, roads, terrain_summary


@router.get(
    "/{layout_id}/export/geojson",
    response_model=ExportResponse,
    summary="Export layout as GeoJSON",
    description="Generate a GeoJSON export of the layout with all assets and roads. D-04-03: Includes terrain metadata.",
)
async def export_geojson(
    layout_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExportResponse:
    """
    Export layout as GeoJSON FeatureCollection.
    
    D-04-03: Includes terrain metadata per feature and collection-level terrain stats.
    D-04-06: Filename includes site name and timestamp.
    
    Returns a presigned URL to download the GeoJSON file.
    """
    layout, site, assets, roads, terrain_summary = await _get_layout_with_details(
        layout_id, current_user, db, include_terrain=True
    )
    
    # Build GeoJSON FeatureCollection
    features = []
    
    for asset in assets:
        # D-04-03: Enhanced properties with terrain context
        properties = {
            "feature_type": "asset",
            "id": asset["id"],
            "asset_type": asset["asset_type"],
            "name": asset["name"],
            "capacity_kw": asset["capacity_kw"],
            "elevation_m": asset["elevation_m"],
            "slope_deg": asset["slope_deg"],
            "footprint_length_m": asset.get("footprint_length_m"),
            "footprint_width_m": asset.get("footprint_width_m"),
        }
        
        # Add slope suitability based on asset type limits
        if asset.get("slope_deg") is not None:
            slope_limits = {"solar_array": 15.0, "battery": 5.0, "generator": 5.0, "substation": 5.0}
            max_slope = slope_limits.get(asset["asset_type"], 15.0)
            properties["slope_within_limit"] = asset["slope_deg"] <= max_slope
            properties["slope_limit_deg"] = max_slope
        
        features.append({
            "type": "Feature",
            "geometry": asset["position"],
            "properties": properties,
        })
    
    for road in roads:
        # D-04-03: Enhanced road properties
        properties = {
            "feature_type": "road",
            "id": road["id"],
            "name": road["name"],
            "length_m": road["length_m"],
            "max_grade_pct": road["max_grade_pct"],
        }
        
        # Add grade classification
        if road.get("max_grade_pct") is not None:
            grade = road["max_grade_pct"]
            properties["grade_class"] = "easy" if grade < 5 else "moderate" if grade <= 10 else "steep"
            properties["grade_within_limit"] = grade <= 10  # 10% max road grade
        
        features.append({
            "type": "Feature",
            "geometry": road["geometry"],
            "properties": properties,
        })
    
    # D-04-03: Collection-level properties with terrain summary
    collection_properties = {
        "layout_id": str(layout.id),
        "site_id": str(site.id),
        "site_name": site.name,
        "site_area_m2": site.area_m2,
        "total_capacity_kw": layout.total_capacity_kw,
        "cut_volume_m3": layout.cut_volume_m3,
        "fill_volume_m3": layout.fill_volume_m3,
        "net_earthwork_m3": (layout.cut_volume_m3 or 0) - (layout.fill_volume_m3 or 0),
        "terrain_processed": layout.terrain_processed,
        "asset_count": len(assets),
        "road_count": len(roads),
        "total_road_length_m": sum(r.get("length_m", 0) or 0 for r in roads),
        "generated_at": datetime.utcnow().isoformat(),
    }
    
    # D-04-03: Add terrain summary if available
    if terrain_summary:
        collection_properties["terrain"] = {
            "dem_source": terrain_summary.get("dem_source"),
            "dem_resolution_m": terrain_summary.get("dem_resolution_m"),
            "elevation": terrain_summary.get("elevation"),
            "slope": {
                "min_deg": terrain_summary.get("slope", {}).get("min_deg"),
                "max_deg": terrain_summary.get("slope", {}).get("max_deg"),
                "mean_deg": terrain_summary.get("slope", {}).get("mean_deg"),
            },
            "buildable_area": terrain_summary.get("buildable_area"),
        }
    
    geojson = {
        "type": "FeatureCollection",
        "features": features,
        "properties": collection_properties,
    }
    
    export_service = get_export_service()
    download_url = await export_service.export_geojson(
        layout_id=layout.id,
        geojson=geojson,
        site_name=site.name,
    )
    
    # D-04-06: Generate proper filename
    filename = generate_export_filename(site.name, layout.id, "geojson")
    
    return ExportResponse(
        download_url=download_url,
        format="geojson",
        filename=filename,
        expires_in_seconds=3600,
    )


@router.get(
    "/{layout_id}/export/kmz",
    response_model=ExportResponse,
    summary="Export layout as KMZ",
    description="Generate a KMZ export for viewing in Google Earth. D-04-04: Includes slope/buildability styling.",
)
async def export_kmz(
    layout_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExportResponse:
    """
    Export layout as KMZ for Google Earth.
    
    D-04-04: Includes slope/buildability styling with color-coded assets.
    D-04-06: Filename includes site name and timestamp.
    
    Returns a presigned URL to download the KMZ file.
    """
    layout, site, assets, roads, terrain_summary = await _get_layout_with_details(
        layout_id, current_user, db, include_terrain=True
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
        layout_data={
            "total_capacity_kw": layout.total_capacity_kw,
            "cut_volume_m3": layout.cut_volume_m3,
            "fill_volume_m3": layout.fill_volume_m3,
            "terrain_processed": layout.terrain_processed,
        },
        terrain_summary=terrain_summary,
    )
    
    # D-04-06: Generate proper filename
    filename = generate_export_filename(site.name, layout.id, "kmz")
    
    return ExportResponse(
        download_url=download_url,
        format="kmz",
        filename=filename,
        expires_in_seconds=3600,
    )


@router.get(
    "/{layout_id}/export/pdf",
    response_model=ExportResponse,
    summary="Export layout as PDF report",
    description="Generate a PDF report with layout summary, asset inventory, and terrain analysis. D-04-01: Includes terrain summary.",
)
async def export_pdf(
    layout_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExportResponse:
    """
    Export layout as PDF report.
    
    D-04-01: Includes terrain summary (slope stats, buildable %).
    D-04-06: Filename includes site name and timestamp.
    
    Returns a presigned URL to download the PDF file.
    """
    layout, site, assets, roads, terrain_summary = await _get_layout_with_details(
        layout_id, current_user, db, include_terrain=True
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
        terrain_summary=terrain_summary,
    )
    
    # D-04-06: Generate proper filename
    filename = generate_export_filename(site.name, layout.id, "pdf")
    
    return ExportResponse(
        download_url=download_url,
        format="pdf",
        filename=filename,
        expires_in_seconds=3600,
    )


@router.get(
    "/{layout_id}/export/csv",
    response_model=ExportResponse,
    summary="Export layout as CSV",
    description="Generate a CSV export with tabular asset and road data. D-04-05: New export format.",
)
async def export_csv(
    layout_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExportResponse:
    """
    Export layout as CSV for spreadsheet analysis.
    
    D-04-05: New export format with tabular asset/road data.
    D-04-06: Filename includes site name and timestamp.
    
    Returns a presigned URL to download the CSV file.
    """
    layout, site, assets, roads, _ = await _get_layout_with_details(
        layout_id, current_user, db, include_terrain=False
    )
    
    export_service = get_export_service()
    download_url = await export_service.export_csv(
        layout_id=layout.id,
        site_name=site.name,
        site_area_m2=site.area_m2 or 0,
        layout_data={
            "total_capacity_kw": layout.total_capacity_kw,
            "cut_volume_m3": layout.cut_volume_m3,
            "fill_volume_m3": layout.fill_volume_m3,
        },
        assets=assets,
        roads=roads,
    )
    
    # D-04-06: Generate proper filename
    filename = generate_export_filename(site.name, layout.id, "csv")
    
    return ExportResponse(
        download_url=download_url,
        format="csv",
        filename=filename,
        expires_in_seconds=3600,
    )

