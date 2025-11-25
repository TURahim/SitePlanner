"""
DEM (Digital Elevation Model) fetching service.

Provides terrain elevation data for site bounding boxes using:
- Primary: USGS 3DEP via py3dep (10-30m resolution, US coverage)
- Fallback: Returns None for international sites (SRTM can be added later)

Implements caching via TerrainCache model to avoid repeated API calls.
"""
import io
import logging
import tempfile
from pathlib import Path
from typing import Optional
from uuid import UUID

import numpy as np
import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds
from shapely.geometry import Polygon, box, mapping
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.terrain_cache import TerrainCache, TerrainType
from app.services.s3 import get_s3_service

logger = logging.getLogger(__name__)
settings = get_settings()


class DEMService:
    """
    Service for fetching and managing DEM (Digital Elevation Model) data.
    
    Fetches elevation data from USGS 3DEP for US sites and caches
    results in S3 with references stored in TerrainCache table.
    """
    
    # Default resolution in meters
    DEFAULT_RESOLUTION_M = 10
    
    # S3 path template for terrain data
    TERRAIN_S3_PREFIX = "terrain"
    
    def __init__(self):
        """Initialize the DEM service."""
        self._s3_service = get_s3_service()
    
    async def get_dem_for_site(
        self,
        site_id: UUID,
        boundary: Polygon,
        db: AsyncSession,
        resolution_m: int = DEFAULT_RESOLUTION_M,
        force_refresh: bool = False,
    ) -> Optional[str]:
        """
        Get DEM for a site, using cache if available.
        
        Args:
            site_id: UUID of the site
            boundary: Site boundary as Shapely Polygon
            db: Database session
            resolution_m: Desired resolution in meters (10 or 30)
            force_refresh: If True, bypass cache and fetch fresh data
            
        Returns:
            S3 key where DEM is stored, or None if fetch failed
        """
        # Check cache first (unless force_refresh)
        if not force_refresh:
            cached_key = await self._get_cached_dem(site_id, db)
            if cached_key:
                logger.info(f"Using cached DEM for site {site_id}")
                return cached_key
        
        # Fetch DEM from external source
        logger.info(f"Fetching fresh DEM for site {site_id}")
        
        try:
            dem_data, dem_profile = await self._fetch_dem_from_3dep(
                boundary, resolution_m
            )
            
            if dem_data is None:
                logger.warning(f"Could not fetch DEM for site {site_id}")
                return None
            
            # Upload to S3
            s3_key = await self._upload_dem_to_s3(site_id, dem_data, dem_profile)
            
            # Create/update cache record
            await self._update_cache_record(
                site_id=site_id,
                terrain_type=TerrainType.ELEVATION,
                s3_key=s3_key,
                resolution_m=resolution_m,
                source="usgs_3dep",
                db=db,
            )
            
            return s3_key
            
        except Exception as e:
            logger.error(f"Failed to fetch DEM for site {site_id}: {e}")
            return None
    
    async def get_dem_array(
        self,
        s3_key: str,
    ) -> tuple[np.ndarray, dict]:
        """
        Load DEM array from S3.
        
        Args:
            s3_key: S3 key of the DEM GeoTIFF
            
        Returns:
            Tuple of (elevation array, rasterio profile)
        """
        dem_bytes = await self._s3_service.download_terrain_file(s3_key)
        
        with MemoryFile(dem_bytes) as memfile:
            with memfile.open() as src:
                dem_array = src.read(1)
                profile = src.profile.copy()
                
        return dem_array, profile
    
    async def _get_cached_dem(
        self,
        site_id: UUID,
        db: AsyncSession,
    ) -> Optional[str]:
        """Check if we have a cached DEM for this site."""
        result = await db.execute(
            select(TerrainCache)
            .where(TerrainCache.site_id == site_id)
            .where(TerrainCache.terrain_type == TerrainType.ELEVATION.value)
        )
        cache_entry = result.scalar_one_or_none()
        
        if cache_entry:
            # Verify file still exists in S3
            if await self._s3_service.terrain_file_exists(cache_entry.s3_key):
                return cache_entry.s3_key
            else:
                # Cache entry is stale, delete it
                await db.delete(cache_entry)
                await db.commit()
        
        return None
    
    async def _fetch_dem_from_3dep(
        self,
        boundary: Polygon,
        resolution_m: int,
    ) -> tuple[Optional[np.ndarray], Optional[dict]]:
        """
        Fetch DEM from USGS 3DEP using py3dep.
        
        Args:
            boundary: Site boundary polygon
            resolution_m: Desired resolution (10 or 30 meters)
            
        Returns:
            Tuple of (elevation array, rasterio profile) or (None, None) if failed
        """
        try:
            import py3dep
        except ImportError:
            logger.error("py3dep not installed. Run: pip install py3dep")
            return None, None
        
        # Get bounding box
        minx, miny, maxx, maxy = boundary.bounds
        
        # Add small buffer to ensure full coverage
        buffer = 0.001  # ~100m at equator
        bbox = (minx - buffer, miny - buffer, maxx + buffer, maxy + buffer)
        
        logger.info(f"Fetching 3DEP DEM for bbox: {bbox} at {resolution_m}m resolution")
        
        try:
            # py3dep returns an xarray DataArray
            # Resolution options: 10 (1/3 arc-second) or 30 (1 arc-second)
            dem_xarray = py3dep.get_dem(bbox, resolution=resolution_m)
            
            # Convert to numpy array
            dem_array = dem_xarray.values.astype(np.float32)
            
            # Handle nodata values
            dem_array = np.where(np.isnan(dem_array), -9999, dem_array)
            
            # Build rasterio profile
            height, width = dem_array.shape
            transform = from_bounds(bbox[0], bbox[1], bbox[2], bbox[3], width, height)
            
            profile = {
                "driver": "GTiff",
                "dtype": "float32",
                "width": width,
                "height": height,
                "count": 1,
                "crs": "EPSG:4326",
                "transform": transform,
                "nodata": -9999,
                "compress": "lzw",
            }
            
            logger.info(f"Successfully fetched DEM: {width}x{height} pixels")
            return dem_array, profile
            
        except Exception as e:
            logger.error(f"Failed to fetch from 3DEP: {e}")
            # Could add SRTM fallback here for international sites
            return None, None
    
    async def _upload_dem_to_s3(
        self,
        site_id: UUID,
        dem_array: np.ndarray,
        profile: dict,
    ) -> str:
        """Upload DEM GeoTIFF to S3."""
        s3_key = f"{self.TERRAIN_S3_PREFIX}/{site_id}/dem.tif"
        
        # Write to memory buffer
        with MemoryFile() as memfile:
            with memfile.open(**profile) as dst:
                dst.write(dem_array, 1)
            
            dem_bytes = memfile.read()
        
        # Upload to S3
        await self._s3_service.upload_terrain_file(
            s3_key=s3_key,
            content=dem_bytes,
            content_type="image/tiff",
        )
        
        logger.info(f"Uploaded DEM to s3://{settings.s3_outputs_bucket}/{s3_key}")
        return s3_key
    
    async def _update_cache_record(
        self,
        site_id: UUID,
        terrain_type: TerrainType,
        s3_key: str,
        resolution_m: int,
        source: str,
        db: AsyncSession,
    ) -> TerrainCache:
        """Create or update a TerrainCache record."""
        # Check for existing record
        result = await db.execute(
            select(TerrainCache)
            .where(TerrainCache.site_id == site_id)
            .where(TerrainCache.terrain_type == terrain_type.value)
        )
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
            )
            db.add(cache_entry)
        
        await db.commit()
        await db.refresh(cache_entry)
        
        return cache_entry


# Global service instance
_dem_service: Optional[DEMService] = None


def get_dem_service() -> DEMService:
    """Get the DEM service singleton."""
    global _dem_service
    if _dem_service is None:
        _dem_service = DEMService()
    return _dem_service

