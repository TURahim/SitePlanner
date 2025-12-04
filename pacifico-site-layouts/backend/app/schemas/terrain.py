"""
Pydantic schemas for Terrain API endpoints (D-01).

Provides schemas for terrain visualization including:
- Terrain summary statistics
- Contour lines as GeoJSON
- Buildable area polygons
- Slope distribution data
"""
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ElevationStats(BaseModel):
    """Elevation statistics for a site."""
    
    min_m: float = Field(..., description="Minimum elevation in meters")
    max_m: float = Field(..., description="Maximum elevation in meters")
    range_m: float = Field(..., description="Elevation range (max - min) in meters")
    mean_m: float = Field(..., description="Mean elevation in meters")


class SlopeDistributionBucket(BaseModel):
    """A bucket in the slope distribution histogram."""
    
    range: str = Field(..., description="Slope range label (e.g., '0-5°')")
    min_deg: float = Field(..., description="Minimum slope in degrees")
    max_deg: float = Field(..., description="Maximum slope in degrees")
    percentage: float = Field(..., description="Percentage of site area in this range")
    area_m2: float = Field(..., description="Area in square meters")


class SlopeStats(BaseModel):
    """Slope statistics for a site."""
    
    min_deg: float = Field(..., description="Minimum slope in degrees")
    max_deg: float = Field(..., description="Maximum slope in degrees")
    mean_deg: float = Field(..., description="Mean slope in degrees")
    distribution: list[SlopeDistributionBucket] = Field(
        ..., description="Slope distribution histogram"
    )


class BuildableAreaStats(BaseModel):
    """Buildable area statistics for an asset type."""
    
    asset_type: str = Field(..., description="Asset type name")
    max_slope_deg: float = Field(..., description="Maximum allowed slope in degrees")
    area_m2: float = Field(..., description="Buildable area in square meters")
    area_ha: float = Field(..., description="Buildable area in hectares")
    percentage: float = Field(..., description="Percentage of total site area")


class TerrainSummaryResponse(BaseModel):
    """
    Complete terrain analysis summary for a site.
    
    Provides elevation, slope, and buildable area statistics
    computed from DEM data.
    """
    
    site_id: UUID = Field(..., description="Site identifier")
    dem_source: str = Field(..., description="DEM data source (e.g., 'USGS 3DEP')")
    dem_resolution_m: float = Field(..., description="DEM resolution in meters")
    
    elevation: ElevationStats = Field(..., description="Elevation statistics")
    slope: SlopeStats = Field(..., description="Slope statistics")
    
    buildable_area: list[BuildableAreaStats] = Field(
        ..., description="Buildable area statistics per asset type"
    )
    
    total_area_m2: float = Field(..., description="Total site area in square meters")
    total_area_ha: float = Field(..., description="Total site area in hectares")


class ContourFeature(BaseModel):
    """A single contour line as a GeoJSON Feature."""
    
    type: str = Field(default="Feature")
    geometry: dict[str, Any] = Field(..., description="LineString or MultiLineString geometry")
    properties: dict[str, Any] = Field(..., description="Contour properties (elevation)")


class ContoursResponse(BaseModel):
    """
    Contour lines for terrain visualization.
    
    Returns contour lines as a GeoJSON FeatureCollection.
    """
    
    site_id: UUID = Field(..., description="Site identifier")
    interval_m: float = Field(..., description="Contour interval in meters")
    
    type: str = Field(default="FeatureCollection")
    features: list[ContourFeature] = Field(..., description="Contour line features")
    
    min_elevation_m: float = Field(..., description="Minimum elevation with contour")
    max_elevation_m: float = Field(..., description="Maximum elevation with contour")
    contour_count: int = Field(..., description="Number of contour lines")


class BuildableAreaFeature(BaseModel):
    """A buildable area polygon as a GeoJSON Feature."""
    
    type: str = Field(default="Feature")
    geometry: dict[str, Any] = Field(..., description="Polygon or MultiPolygon geometry")
    properties: dict[str, Any] = Field(..., description="Buildable area properties")


class BuildableAreaResponse(BaseModel):
    """
    Buildable area polygons for a specific asset type.
    
    Returns areas where terrain slope is within acceptable limits
    for the specified asset type.
    """
    
    site_id: UUID = Field(..., description="Site identifier")
    asset_type: str = Field(..., description="Asset type for buildable calculation")
    max_slope_deg: float = Field(..., description="Maximum slope threshold in degrees")
    
    type: str = Field(default="FeatureCollection")
    features: list[BuildableAreaFeature] = Field(..., description="Buildable area features")
    
    buildable_area_m2: float = Field(..., description="Total buildable area in m²")
    buildable_area_ha: float = Field(..., description="Total buildable area in hectares")
    buildable_percentage: float = Field(..., description="Percentage of site that is buildable")


class SlopeHeatmapFeature(BaseModel):
    """A slope zone polygon as a GeoJSON Feature."""
    
    type: str = Field(default="Feature")
    geometry: dict[str, Any] = Field(..., description="Polygon geometry")
    properties: dict[str, Any] = Field(
        ..., 
        description="Zone properties including slope_class, min_slope, max_slope, color"
    )


class SlopeHeatmapResponse(BaseModel):
    """
    Slope heatmap as colored polygons by slope class.
    
    Returns polygons colored by slope severity:
    - Green (0-5°): Very gentle, suitable for all assets
    - Yellow (5-10°): Gentle, suitable for most assets
    - Orange (10-15°): Moderate, solar arrays only
    - Red (>15°): Steep, not buildable
    """
    
    site_id: UUID = Field(..., description="Site identifier")
    
    type: str = Field(default="FeatureCollection")
    features: list[SlopeHeatmapFeature] = Field(..., description="Slope zone features")
    
    legend: list[dict[str, Any]] = Field(
        ..., 
        description="Legend mapping slope classes to colors"
    )






