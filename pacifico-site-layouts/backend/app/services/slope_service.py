"""
Slope computation service.

Computes slope rasters from DEM data using NumPy gradient.
Results are cached via TerrainCache for reuse.
"""
import logging
from typing import Optional
from uuid import UUID

import numpy as np
from rasterio.io import MemoryFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.terrain_cache import TerrainCache, TerrainType
from app.services.s3 import get_s3_service

logger = logging.getLogger(__name__)
settings = get_settings()


class SlopeService:
    """
    Service for computing and managing slope rasters.
    
    Slope is calculated from DEM using finite difference gradient method.
    Results are stored in S3 and referenced in TerrainCache.
    """
    
    TERRAIN_S3_PREFIX = "terrain"
    
    def __init__(self):
        """Initialize the slope service."""
        self._s3_service = get_s3_service()
    
    async def get_slope_for_site(
        self,
        site_id: UUID,
        dem_s3_key: str,
        db: AsyncSession,
        force_refresh: bool = False,
    ) -> Optional[str]:
        """
        Get slope raster for a site, computing if not cached.
        
        Args:
            site_id: UUID of the site
            dem_s3_key: S3 key of the source DEM
            db: Database session
            force_refresh: If True, recompute even if cached
            
        Returns:
            S3 key where slope raster is stored, or None if failed
        """
        # Check cache first
        if not force_refresh:
            cached_key = await self._get_cached_slope(site_id, db)
            if cached_key:
                logger.info(f"Using cached slope for site {site_id}")
                return cached_key
        
        logger.info(f"Computing slope for site {site_id}")
        
        try:
            # Download DEM from S3
            dem_bytes = await self._s3_service.download_terrain_file(dem_s3_key)
            
            # Compute slope
            slope_array, profile = self._compute_slope(dem_bytes)
            
            # Upload to S3
            s3_key = await self._upload_slope_to_s3(site_id, slope_array, profile)
            
            # Create cache record
            await self._update_cache_record(
                site_id=site_id,
                terrain_type=TerrainType.SLOPE,
                s3_key=s3_key,
                resolution_m=profile.get("resolution_m"),
                source="computed",
                db=db,
            )
            
            return s3_key
            
        except Exception as e:
            logger.error(f"Failed to compute slope for site {site_id}: {e}")
            return None
    
    async def get_slope_array(
        self,
        s3_key: str,
    ) -> tuple[np.ndarray, dict]:
        """
        Load slope array from S3.
        
        Args:
            s3_key: S3 key of the slope GeoTIFF
            
        Returns:
            Tuple of (slope array in degrees, rasterio profile)
        """
        slope_bytes = await self._s3_service.download_terrain_file(s3_key)
        
        with MemoryFile(slope_bytes) as memfile:
            with memfile.open() as src:
                slope_array = src.read(1)
                profile = src.profile.copy()
                
        return slope_array, profile
    
    def _compute_slope(
        self,
        dem_bytes: bytes,
    ) -> tuple[np.ndarray, dict]:
        """
        Compute slope in degrees from DEM.
        
        Uses finite difference gradient method:
        slope = arctan(sqrt((dz/dx)² + (dz/dy)²)) * (180/π)
        
        Args:
            dem_bytes: DEM GeoTIFF as bytes
            
        Returns:
            Tuple of (slope array in degrees, rasterio profile)
        """
        with MemoryFile(dem_bytes) as memfile:
            with memfile.open() as src:
                dem = src.read(1).astype(np.float64)
                transform = src.transform
                crs = src.crs
                nodata = src.nodata
                
                # Get cell size
                cell_size_x = abs(transform[0])
                cell_size_y = abs(transform[4])
                
                # Convert to meters if in geographic coordinates (degrees)
                if crs and crs.is_geographic:
                    # Approximate conversion: 1 degree ≈ 111km at equator
                    # More accurate: use center latitude
                    center_lat = (src.bounds.top + src.bounds.bottom) / 2
                    lat_factor = np.cos(np.radians(center_lat))
                    cell_size_x_m = cell_size_x * 111000 * lat_factor
                    cell_size_y_m = cell_size_y * 111000
                else:
                    cell_size_x_m = cell_size_x
                    cell_size_y_m = cell_size_y
        
        # Handle nodata values
        if nodata is not None:
            dem = np.where(dem == nodata, np.nan, dem)
        
        # Compute gradients (rise/run)
        # Note: np.gradient returns gradients in row (y) and column (x) order
        dy, dx = np.gradient(dem, cell_size_y_m, cell_size_x_m)
        
        # Calculate slope in degrees
        # slope = arctan(sqrt(dx² + dy²))
        slope_rad = np.arctan(np.sqrt(dx**2 + dy**2))
        slope_deg = np.degrees(slope_rad)
        
        # Handle NaN values (from nodata in DEM)
        slope_deg = np.where(np.isnan(slope_deg), -9999, slope_deg)
        
        # Build output profile
        profile = {
            "driver": "GTiff",
            "dtype": "float32",
            "width": dem.shape[1],
            "height": dem.shape[0],
            "count": 1,
            "crs": str(crs) if crs else "EPSG:4326",
            "transform": transform,
            "nodata": -9999,
            "compress": "lzw",
        }
        
        logger.info(
            f"Computed slope: min={np.nanmin(slope_deg[slope_deg != -9999]):.1f}°, "
            f"max={np.nanmax(slope_deg):.1f}°, "
            f"mean={np.nanmean(slope_deg[slope_deg != -9999]):.1f}°"
        )
        
        return slope_deg.astype(np.float32), profile
    
    async def _get_cached_slope(
        self,
        site_id: UUID,
        db: AsyncSession,
    ) -> Optional[str]:
        """Check if we have a cached slope raster for this site."""
        stmt = (
            select(TerrainCache)
            .where(TerrainCache.site_id == site_id)
            .where(TerrainCache.terrain_type == TerrainType.SLOPE.value)
            .where(TerrainCache.variant_key.is_(None))
        )
        result = await db.execute(stmt)
        cache_entry = result.scalar_one_or_none()
        
        if cache_entry:
            if await self._s3_service.terrain_file_exists(cache_entry.s3_key):
                return cache_entry.s3_key
            else:
                await db.delete(cache_entry)
                await db.commit()
        
        return None
    
    async def _upload_slope_to_s3(
        self,
        site_id: UUID,
        slope_array: np.ndarray,
        profile: dict,
    ) -> str:
        """Upload slope GeoTIFF to S3."""
        s3_key = f"{self.TERRAIN_S3_PREFIX}/{site_id}/slope.tif"
        
        with MemoryFile() as memfile:
            with memfile.open(**profile) as dst:
                dst.write(slope_array, 1)
            slope_bytes = memfile.read()
        
        await self._s3_service.upload_terrain_file(
            s3_key=s3_key,
            content=slope_bytes,
            content_type="image/tiff",
        )
        
        logger.info(f"Uploaded slope to s3://{settings.s3_outputs_bucket}/{s3_key}")
        return s3_key
    
    async def _update_cache_record(
        self,
        site_id: UUID,
        terrain_type: TerrainType,
        s3_key: str,
        resolution_m: Optional[float],
        source: str,
        db: AsyncSession,
        variant: Optional[str] = None,
    ) -> TerrainCache:
        """Create or update a TerrainCache record."""
        stmt = (
            select(TerrainCache)
            .where(TerrainCache.site_id == site_id)
            .where(TerrainCache.terrain_type == terrain_type.value)
        )
        if variant is None:
            stmt = stmt.where(TerrainCache.variant_key.is_(None))
        else:
            stmt = stmt.where(TerrainCache.variant_key == variant)

        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            existing.s3_key = s3_key
            existing.resolution_m = resolution_m
            existing.source = source
            cache_entry = existing
        else:
            cache_entry = TerrainCache(
                site_id=site_id,
                terrain_type=terrain_type.value,
                s3_key=s3_key,
                resolution_m=resolution_m,
                source=source,
                variant_key=variant,
            )
            db.add(cache_entry)
        
        await db.commit()
        await db.refresh(cache_entry)
        
        return cache_entry


# Global service instance
_slope_service: Optional[SlopeService] = None


def get_slope_service() -> SlopeService:
    """Get the slope service singleton."""
    global _slope_service
    if _slope_service is None:
        _slope_service = SlopeService()
    return _slope_service

