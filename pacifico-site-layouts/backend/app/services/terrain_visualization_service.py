"""
Terrain visualization service for D-01.

Generates terrain visualization data including:
- Contour lines from DEM
- Buildable area polygons from slope data
- Slope heatmap polygons
- Terrain summary statistics
"""
import json
import logging
from typing import Any, Optional
from uuid import UUID

import numpy as np
from rasterio.features import shapes
from rasterio.io import MemoryFile
from rasterio.transform import Affine
from scipy import ndimage
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Polygon, shape, mapping
from shapely.ops import unary_union
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.terrain_cache import TerrainCache, TerrainType
from app.services.dem_service import get_dem_service
from app.services.slope_service import get_slope_service
from app.services.s3 import get_s3_service

logger = logging.getLogger(__name__)


# Slope limits by asset type (degrees) - matches terrain_layout_generator.py
SLOPE_LIMITS = {
    "solar_array": 15.0,
    "battery": 5.0,
    "generator": 5.0,
    "substation": 5.0,
}

# Slope classification for heatmap
SLOPE_CLASSES = [
    {"class": "very_gentle", "min": 0, "max": 5, "color": "#22c55e", "label": "0-5° (Very Gentle)"},
    {"class": "gentle", "min": 5, "max": 10, "color": "#eab308", "label": "5-10° (Gentle)"},
    {"class": "moderate", "min": 10, "max": 15, "color": "#f97316", "label": "10-15° (Moderate)"},
    {"class": "steep", "min": 15, "max": 90, "color": "#ef4444", "label": ">15° (Steep)"},
]


class TerrainVisualizationService:
    """
    Service for generating terrain visualization data.
    
    Provides methods for computing contours, buildable areas,
    and slope heatmaps from cached DEM and slope data.
    """
    
    def __init__(self):
        self._dem_service = get_dem_service()
        self._slope_service = get_slope_service()
        self._s3_service = get_s3_service()
    
    async def _get_cached_geojson(
        self,
        site_id: UUID,
        terrain_type: TerrainType,
        variant: str,
        db: AsyncSession,
    ) -> Optional[dict]:
        """Retrieve cached GeoJSON from TerrainCache/S3."""
        stmt = (
            select(TerrainCache)
            .where(TerrainCache.site_id == site_id)
            .where(TerrainCache.terrain_type == terrain_type.value)
            .where(TerrainCache.variant_key == variant)
        )
        result = await db.execute(stmt)
        cache_entry = result.scalar_one_or_none()
        
        if not cache_entry:
            return None
        
        if not await self._s3_service.terrain_file_exists(cache_entry.s3_key):
            await db.delete(cache_entry)
            await db.commit()
            return None
        
        try:
            data_bytes = await self._s3_service.download_terrain_file(cache_entry.s3_key)
            return json.loads(data_bytes.decode("utf-8"))
        except Exception as exc:
            logger.warning(f"Failed to load cached {terrain_type.value} for site {site_id}: {exc}")
            return None
    
    async def _cache_geojson(
        self,
        site_id: UUID,
        terrain_type: TerrainType,
        variant: str,
        data: dict,
        db: AsyncSession,
    ) -> None:
        """Persist GeoJSON output to S3 and TerrainCache."""
        safe_variant = variant.replace(":", "_").replace("|", "_").replace("/", "_").replace(" ", "_")
        s3_key = f"terrain/{site_id}/{terrain_type.value}_{safe_variant}.json"
        try:
            await self._s3_service.upload_json(s3_key, data)
            await self._upsert_cache_entry(
                site_id=site_id,
                terrain_type=terrain_type,
                variant=variant,
                s3_key=s3_key,
                db=db,
            )
        except Exception as exc:
            logger.warning(f"Failed to cache {terrain_type.value} for site {site_id}: {exc}")

    async def _upsert_cache_entry(
        self,
        site_id: UUID,
        terrain_type: TerrainType,
        variant: str,
        s3_key: str,
        db: AsyncSession,
    ) -> None:
        """Create or update TerrainCache entry for generated artifacts."""
        stmt = (
            select(TerrainCache)
            .where(TerrainCache.site_id == site_id)
            .where(TerrainCache.terrain_type == terrain_type.value)
            .where(TerrainCache.variant_key == variant)
        )
        result = await db.execute(stmt)
        entry = result.scalar_one_or_none()

        if entry:
            entry.s3_key = s3_key
            entry.source = "generated"
        else:
            entry = TerrainCache(
                site_id=site_id,
                terrain_type=terrain_type.value,
                s3_key=s3_key,
                source="generated",
                variant_key=variant,
            )
            db.add(entry)

        await db.commit()
    
    async def get_terrain_summary(
        self,
        site_id: UUID,
        db: AsyncSession,
        boundary: Polygon,
    ) -> dict[str, Any]:
        """
        Compute terrain summary statistics for a site.
        
        Args:
            site_id: Site UUID
            db: Database session
            boundary: Site boundary polygon
            
        Returns:
            Dictionary with elevation, slope, and buildable area stats
        """
        # Get DEM and slope data
        dem_s3_key = await self._dem_service.get_dem_for_site(site_id, boundary, db)
        if not dem_s3_key:
            raise ValueError(f"Could not fetch DEM for site {site_id}")
        
        slope_s3_key = await self._slope_service.get_slope_for_site(site_id, dem_s3_key, db)
        if not slope_s3_key:
            raise ValueError(f"Could not compute slope for site {site_id}")
        
        # Load arrays
        dem_array, dem_profile = await self._dem_service.get_dem_array(dem_s3_key)
        slope_array, slope_profile = await self._slope_service.get_slope_array(slope_s3_key)
        
        # Get cell size for area calculations
        transform = dem_profile.get("transform") or Affine.identity()
        cell_size_deg = abs(transform[0]) if transform else 0.0001
        # Convert to meters (approximate)
        cell_size_m = cell_size_deg * 111000
        cell_area_m2 = cell_size_m ** 2
        
        # Create boundary mask
        boundary_mask = self._rasterize_boundary(boundary, transform, dem_array.shape)
        
        # Filter arrays to boundary
        dem_valid = dem_array[boundary_mask & (dem_array > -9000)]
        slope_valid = slope_array[boundary_mask & (slope_array >= 0)]
        
        # Elevation statistics
        elevation_stats = {
            "min_m": float(np.min(dem_valid)) if len(dem_valid) > 0 else 0,
            "max_m": float(np.max(dem_valid)) if len(dem_valid) > 0 else 0,
            "range_m": float(np.ptp(dem_valid)) if len(dem_valid) > 0 else 0,
            "mean_m": float(np.mean(dem_valid)) if len(dem_valid) > 0 else 0,
        }
        
        # Slope statistics
        slope_distribution = self._compute_slope_distribution(
            slope_array, boundary_mask, cell_area_m2
        )
        
        slope_stats = {
            "min_deg": float(np.min(slope_valid)) if len(slope_valid) > 0 else 0,
            "max_deg": float(np.max(slope_valid)) if len(slope_valid) > 0 else 0,
            "mean_deg": float(np.mean(slope_valid)) if len(slope_valid) > 0 else 0,
            "distribution": slope_distribution,
        }
        
        # Total site area
        total_cells = np.sum(boundary_mask)
        total_area_m2 = total_cells * cell_area_m2
        
        # Buildable area per asset type
        buildable_areas = []
        for asset_type, max_slope in SLOPE_LIMITS.items():
            buildable_mask = boundary_mask & (slope_array >= 0) & (slope_array < max_slope)
            buildable_cells = np.sum(buildable_mask)
            buildable_m2 = buildable_cells * cell_area_m2
            
            buildable_areas.append({
                "asset_type": asset_type,
                "max_slope_deg": max_slope,
                "area_m2": round(buildable_m2, 1),
                "area_ha": round(buildable_m2 / 10000, 2),
                "percentage": round(buildable_cells / total_cells * 100, 1) if total_cells > 0 else 0,
            })
        
        return {
            "site_id": site_id,
            "dem_source": "USGS 3DEP",
            "dem_resolution_m": dem_profile.get("resolution_m") or cell_size_m,
            "elevation": elevation_stats,
            "slope": slope_stats,
            "buildable_area": buildable_areas,
            "total_area_m2": round(total_area_m2, 1),
            "total_area_ha": round(total_area_m2 / 10000, 2),
        }
    
    def _compute_slope_distribution(
        self,
        slope_array: np.ndarray,
        boundary_mask: np.ndarray,
        cell_area_m2: float,
    ) -> list[dict[str, Any]]:
        """Compute slope distribution histogram."""
        distribution = []
        
        total_cells = np.sum(boundary_mask)
        
        for slope_class in SLOPE_CLASSES:
            min_slope = slope_class["min"]
            max_slope = slope_class["max"]
            
            # Count cells in this slope range
            if max_slope >= 90:
                mask = boundary_mask & (slope_array >= min_slope)
            else:
                mask = boundary_mask & (slope_array >= min_slope) & (slope_array < max_slope)
            
            count = np.sum(mask)
            area_m2 = count * cell_area_m2
            percentage = (count / total_cells * 100) if total_cells > 0 else 0
            
            distribution.append({
                "range": slope_class["label"],
                "min_deg": min_slope,
                "max_deg": min(max_slope, 90),
                "percentage": round(percentage, 1),
                "area_m2": round(area_m2, 1),
            })
        
        return distribution
    
    async def get_contours(
        self,
        site_id: UUID,
        db: AsyncSession,
        boundary: Polygon,
        interval_m: float = 5.0,
    ) -> dict[str, Any]:
        """
        Generate contour lines from DEM.
        
        Uses marching squares algorithm via scipy to extract
        contour lines at specified elevation intervals.
        
        Args:
            site_id: Site UUID
            db: Database session
            boundary: Site boundary polygon
            interval_m: Contour interval in meters
            
        Returns:
            GeoJSON FeatureCollection with contour LineStrings
        """
        variant = f"interval:{interval_m:.2f}"
        cached = await self._get_cached_geojson(site_id, TerrainType.CONTOURS, variant, db)
        if cached:
            return cached

        # Get DEM data
        dem_s3_key = await self._dem_service.get_dem_for_site(site_id, boundary, db)
        if not dem_s3_key:
            raise ValueError(f"Could not fetch DEM for site {site_id}")
        
        dem_array, dem_profile = await self._dem_service.get_dem_array(dem_s3_key)
        transform = dem_profile.get("transform") or Affine.identity()
        
        # Create boundary mask
        boundary_mask = self._rasterize_boundary(boundary, transform, dem_array.shape)
        
        # Get valid elevation range
        dem_masked = np.where(boundary_mask & (dem_array > -9000), dem_array, np.nan)
        min_elev = np.nanmin(dem_masked)
        max_elev = np.nanmax(dem_masked)
        
        if np.isnan(min_elev) or np.isnan(max_elev):
            return {
                "site_id": site_id,
                "interval_m": interval_m,
                "type": "FeatureCollection",
                "features": [],
                "min_elevation_m": 0,
                "max_elevation_m": 0,
                "contour_count": 0,
            }
        
        # Generate contour elevations
        start_elev = np.ceil(min_elev / interval_m) * interval_m
        end_elev = np.floor(max_elev / interval_m) * interval_m
        contour_elevations = np.arange(start_elev, end_elev + interval_m, interval_m)
        
        features = []
        
        for elevation in contour_elevations:
            # Use marching squares to find contour
            contour_coords = self._extract_contour_at_elevation(
                dem_masked, elevation, transform
            )
            
            if contour_coords:
                # Create LineString or MultiLineString
                if len(contour_coords) == 1:
                    geometry = LineString(contour_coords[0])
                else:
                    geometry = MultiLineString(contour_coords)
                
                # Clip to boundary
                try:
                    clipped = geometry.intersection(boundary)
                    if not clipped.is_empty:
                        features.append({
                            "type": "Feature",
                            "geometry": mapping(clipped),
                            "properties": {
                                "elevation_m": float(elevation),
                                "type": "contour",
                            }
                        })
                except Exception as e:
                    logger.warning(f"Could not clip contour at {elevation}m: {e}")
        
        result = {
            "site_id": site_id,
            "interval_m": interval_m,
            "type": "FeatureCollection",
            "features": features,
            "min_elevation_m": float(start_elev),
            "max_elevation_m": float(end_elev),
            "contour_count": len(features),
        }
        
        await self._cache_geojson(site_id, TerrainType.CONTOURS, variant, result, db)
        return result
    
    def _extract_contour_at_elevation(
        self,
        dem: np.ndarray,
        elevation: float,
        transform: Affine,
    ) -> list[list[tuple[float, float]]]:
        """
        Extract contour line coordinates at a specific elevation.
        
        Uses scipy.ndimage to find contour edges.
        """
        from skimage import measure
        
        try:
            # Find contours using marching squares
            contours = measure.find_contours(dem, elevation)
            
            result = []
            for contour in contours:
                if len(contour) < 2:
                    continue
                
                # Convert pixel coordinates to geographic coordinates
                coords = []
                for row, col in contour:
                    # Apply affine transform: x = a*col + b*row + c
                    x = transform[0] * col + transform[1] * row + transform[2]
                    y = transform[3] * col + transform[4] * row + transform[5]
                    coords.append((x, y))
                
                if len(coords) >= 2:
                    result.append(coords)
            
            return result
            
        except Exception as e:
            logger.warning(f"Contour extraction failed at {elevation}m: {e}")
            return []
    
    async def get_buildable_area(
        self,
        site_id: UUID,
        db: AsyncSession,
        boundary: Polygon,
        asset_type: str = "solar_array",
        max_slope_deg: Optional[float] = None,
    ) -> dict[str, Any]:
        """
        Generate buildable area polygons for an asset type.
        
        Args:
            site_id: Site UUID
            db: Database session
            boundary: Site boundary polygon
            asset_type: Asset type for slope threshold
            max_slope_deg: Override max slope (uses asset default if None)
            
        Returns:
            GeoJSON FeatureCollection with buildable area polygons
        """
        # Determine slope threshold
        if max_slope_deg is None:
            max_slope_deg = SLOPE_LIMITS.get(asset_type, 15.0)
        variant = f"asset:{asset_type}|max:{max_slope_deg}"
        cached = await self._get_cached_geojson(site_id, TerrainType.BUILDABLE_AREA, variant, db)
        if cached:
            return cached
        
        # Get DEM and slope data
        dem_s3_key = await self._dem_service.get_dem_for_site(site_id, boundary, db)
        if not dem_s3_key:
            raise ValueError(f"Could not fetch DEM for site {site_id}")
        
        slope_s3_key = await self._slope_service.get_slope_for_site(site_id, dem_s3_key, db)
        if not slope_s3_key:
            raise ValueError(f"Could not compute slope for site {site_id}")
        
        slope_array, slope_profile = await self._slope_service.get_slope_array(slope_s3_key)
        transform = slope_profile.get("transform") or Affine.identity()
        
        # Create boundary mask
        boundary_mask = self._rasterize_boundary(boundary, transform, slope_array.shape)
        
        # Create buildable mask
        buildable_mask = boundary_mask & (slope_array >= 0) & (slope_array < max_slope_deg)
        
        # Convert mask to polygons
        features = self._mask_to_polygons(
            buildable_mask.astype(np.uint8),
            transform,
            boundary,
            properties={
                "type": "buildable_area",
                "asset_type": asset_type,
                "max_slope_deg": max_slope_deg,
                "buildable": True,
            }
        )
        
        # Calculate total buildable area
        cell_size_deg = abs(transform[0])
        cell_size_m = cell_size_deg * 111000
        cell_area_m2 = cell_size_m ** 2
        
        buildable_cells = np.sum(buildable_mask)
        total_cells = np.sum(boundary_mask)
        buildable_m2 = buildable_cells * cell_area_m2
        
        result = {
            "site_id": site_id,
            "asset_type": asset_type,
            "max_slope_deg": max_slope_deg,
            "type": "FeatureCollection",
            "features": features,
            "buildable_area_m2": round(buildable_m2, 1),
            "buildable_area_ha": round(buildable_m2 / 10000, 2),
            "buildable_percentage": round(buildable_cells / total_cells * 100, 1) if total_cells > 0 else 0,
        }
        
        await self._cache_geojson(site_id, TerrainType.BUILDABLE_AREA, variant, result, db)
        return result
    
    async def get_slope_heatmap(
        self,
        site_id: UUID,
        db: AsyncSession,
        boundary: Polygon,
    ) -> dict[str, Any]:
        """
        Generate slope heatmap as colored polygons by slope class.
        
        Args:
            site_id: Site UUID
            db: Database session
            boundary: Site boundary polygon
            
        Returns:
            GeoJSON FeatureCollection with slope zone polygons
        """
        # Get DEM and slope data
        variant = "default"
        cached = await self._get_cached_geojson(site_id, TerrainType.SLOPE_HEATMAP, variant, db)
        if cached:
            return cached

        dem_s3_key = await self._dem_service.get_dem_for_site(site_id, boundary, db)
        if not dem_s3_key:
            raise ValueError(f"Could not fetch DEM for site {site_id}")
        
        slope_s3_key = await self._slope_service.get_slope_for_site(site_id, dem_s3_key, db)
        if not slope_s3_key:
            raise ValueError(f"Could not compute slope for site {site_id}")
        
        slope_array, slope_profile = await self._slope_service.get_slope_array(slope_s3_key)
        transform = slope_profile.get("transform") or Affine.identity()
        
        # Create boundary mask
        boundary_mask = self._rasterize_boundary(boundary, transform, slope_array.shape)
        
        features = []
        
        for slope_class in SLOPE_CLASSES:
            min_slope = slope_class["min"]
            max_slope = slope_class["max"]
            
            # Create mask for this slope range
            if max_slope >= 90:
                class_mask = boundary_mask & (slope_array >= min_slope)
            else:
                class_mask = boundary_mask & (slope_array >= min_slope) & (slope_array < max_slope)
            
            if not np.any(class_mask):
                continue
            
            # Convert mask to polygons
            class_features = self._mask_to_polygons(
                class_mask.astype(np.uint8),
                transform,
                boundary,
                properties={
                    "type": "slope_zone",
                    "slope_class": slope_class["class"],
                    "min_slope_deg": min_slope,
                    "max_slope_deg": min(max_slope, 90),
                    "color": slope_class["color"],
                    "label": slope_class["label"],
                }
            )
            
            features.extend(class_features)
        
        result = {
            "site_id": site_id,
            "type": "FeatureCollection",
            "features": features,
            "legend": [
                {
                    "class": sc["class"],
                    "label": sc["label"],
                    "color": sc["color"],
                    "min_deg": sc["min"],
                    "max_deg": min(sc["max"], 90),
                }
                for sc in SLOPE_CLASSES
            ],
        }
        
        await self._cache_geojson(site_id, TerrainType.SLOPE_HEATMAP, variant, result, db)
        return result
    
    def _mask_to_polygons(
        self,
        mask: np.ndarray,
        transform: Affine,
        clip_boundary: Polygon,
        properties: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Convert a binary mask to GeoJSON polygon features.
        
        Uses rasterio.features.shapes to vectorize the mask.
        """
        features = []
        
        try:
            # Clean up mask with morphological operations
            from scipy.ndimage import binary_closing, binary_opening
            
            # Apply morphological operations to reduce noise
            kernel_size = 2
            kernel = np.ones((kernel_size, kernel_size), dtype=bool)
            cleaned_mask = binary_closing(mask, kernel)
            cleaned_mask = binary_opening(cleaned_mask, kernel)
            
            # Extract polygons from mask
            for geom, value in shapes(
                cleaned_mask.astype(np.uint8),
                mask=cleaned_mask > 0,
                transform=transform,
            ):
                if value == 0:
                    continue
                
                poly = shape(geom)
                
                # Skip tiny polygons
                if poly.area < 1e-10:
                    continue
                
                # Clip to boundary
                try:
                    clipped = poly.intersection(clip_boundary)
                    if clipped.is_empty:
                        continue
                    
                    # Simplify to reduce vertex count
                    simplified = clipped.simplify(0.0001, preserve_topology=True)
                    
                    if not simplified.is_empty:
                        features.append({
                            "type": "Feature",
                            "geometry": mapping(simplified),
                            "properties": properties.copy(),
                        })
                        
                except Exception as e:
                    logger.warning(f"Could not process polygon: {e}")
                    
        except Exception as e:
            logger.error(f"Mask to polygon conversion failed: {e}")
        
        return features
    
    def _rasterize_boundary(
        self,
        boundary: Polygon,
        transform: Affine,
        shape: tuple[int, int],
    ) -> np.ndarray:
        """
        Create a boolean mask of the boundary polygon.
        """
        from rasterio.features import rasterize
        
        mask = rasterize(
            [(boundary, 1)],
            out_shape=shape,
            transform=transform,
            fill=0,
            dtype=np.uint8,
        )
        return mask.astype(bool)


# Global service instance
_terrain_viz_service: Optional[TerrainVisualizationService] = None


def get_terrain_visualization_service() -> TerrainVisualizationService:
    """Get the terrain visualization service singleton."""
    global _terrain_viz_service
    if _terrain_viz_service is None:
        _terrain_viz_service = TerrainVisualizationService()
    return _terrain_viz_service

