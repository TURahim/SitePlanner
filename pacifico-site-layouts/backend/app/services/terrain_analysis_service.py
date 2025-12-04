"""
Enhanced terrain analysis service.

Provides advanced terrain metrics beyond basic slope:
- Curvature (convex/concave terrain detection)
- Aspect (slope direction for solar orientation)
- Composite suitability scoring
- DEM smoothing and noise reduction
- Morphological filtering for buildable areas

These metrics feed into improved layout generation algorithms.
"""
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from uuid import UUID

import numpy as np
from rasterio.io import MemoryFile
from rasterio.transform import Affine
from scipy import ndimage
from scipy.ndimage import gaussian_filter, binary_opening, binary_closing
from skimage.morphology import disk, remove_small_objects, remove_small_holes

logger = logging.getLogger(__name__)


class AspectCategory(str, Enum):
    """Cardinal direction categories for aspect."""
    NORTH = "north"       # 337.5° - 22.5°
    NORTHEAST = "northeast"  # 22.5° - 67.5°
    EAST = "east"         # 67.5° - 112.5°
    SOUTHEAST = "southeast"  # 112.5° - 157.5°
    SOUTH = "south"       # 157.5° - 202.5°
    SOUTHWEST = "southwest"  # 202.5° - 247.5°
    WEST = "west"         # 247.5° - 292.5°
    NORTHWEST = "northwest"  # 292.5° - 337.5°
    FLAT = "flat"         # Slope < 1°


@dataclass
class TerrainMetrics:
    """Container for computed terrain analysis results."""
    slope_deg: np.ndarray           # Slope in degrees
    aspect_deg: np.ndarray          # Aspect in degrees (0-360, clockwise from north)
    curvature: np.ndarray           # Profile curvature (positive=convex, negative=concave)
    plan_curvature: np.ndarray      # Plan curvature (affects water flow)
    roughness: np.ndarray           # Terrain roughness index
    transform: Affine               # Georeferencing transform
    cell_size_m: float              # Cell size in meters
    crs: str                        # Coordinate reference system


@dataclass
class SuitabilityConfig:
    """Configuration for suitability scoring."""
    # Slope weights by asset type
    max_slope_deg: float = 15.0
    optimal_slope_deg: float = 5.0
    
    # Curvature preferences (negative = concave preferred for drainage)
    max_curvature: float = 0.1
    curvature_weight: float = 0.15
    
    # Aspect preferences (south-facing for solar in northern hemisphere)
    preferred_aspect: float = 180.0  # South
    aspect_tolerance: float = 90.0   # ±90° from preferred
    aspect_weight: float = 0.10
    
    # Roughness penalty
    max_roughness: float = 5.0
    roughness_weight: float = 0.10
    
    # Slope is primary factor
    slope_weight: float = 0.65
    
    # Minimum contiguous area (in cells) for valid buildable zones
    min_contiguous_cells: int = 9  # ~3x3 cells minimum


class TerrainAnalysisService:
    """
    Advanced terrain analysis for layout optimization.
    
    Computes multiple terrain derivatives from DEM data:
    - Slope: steepness of terrain
    - Aspect: direction slope faces (important for solar)
    - Curvature: convexity/concavity (affects drainage, stability)
    - Roughness: local terrain variability
    
    These feed into a composite suitability score for asset placement.
    """
    
    def __init__(self, smoothing_sigma: float = 1.0):
        """
        Initialize the terrain analysis service.
        
        Args:
            smoothing_sigma: Gaussian smoothing sigma for DEM noise reduction.
                            Higher values = more smoothing. 0 = no smoothing.
                            Recommended: 0.5-2.0 for 10m DEMs.
        """
        self.smoothing_sigma = smoothing_sigma
    
    def analyze_terrain(
        self,
        dem_array: np.ndarray,
        transform: Affine,
        crs: str = "EPSG:4326",
        apply_smoothing: bool = True,
    ) -> TerrainMetrics:
        """
        Perform comprehensive terrain analysis on DEM.
        
        Args:
            dem_array: Elevation data (meters)
            transform: Rasterio affine transform
            crs: Coordinate reference system
            apply_smoothing: Whether to apply Gaussian smoothing
            
        Returns:
            TerrainMetrics with all computed derivatives
        """
        # Get cell size in meters
        cell_size_x = abs(transform[0])
        cell_size_y = abs(transform[4])
        
        # Convert to meters if in degrees
        if cell_size_x < 1:  # Likely geographic coordinates
            # Use center latitude for more accurate conversion
            center_lat = transform[5] - (dem_array.shape[0] / 2) * cell_size_y
            lat_factor = np.cos(np.radians(abs(center_lat)))
            cell_size_m = cell_size_x * 111000 * lat_factor
        else:
            cell_size_m = (cell_size_x + cell_size_y) / 2
        
        logger.info(f"Analyzing terrain: {dem_array.shape}, cell size: {cell_size_m:.1f}m")
        
        # Handle nodata values
        dem = dem_array.astype(np.float64)
        nodata_mask = (dem < -9000) | np.isnan(dem)
        dem[nodata_mask] = np.nan
        
        # Apply Gaussian smoothing to reduce DEM noise
        if apply_smoothing and self.smoothing_sigma > 0:
            dem_smooth = self._smooth_dem(dem)
            logger.info(f"Applied Gaussian smoothing (sigma={self.smoothing_sigma})")
        else:
            dem_smooth = dem
        
        # Compute terrain derivatives
        slope_deg, aspect_deg = self._compute_slope_aspect(dem_smooth, cell_size_m)
        curvature, plan_curvature = self._compute_curvature(dem_smooth, cell_size_m)
        roughness = self._compute_roughness(dem_smooth)
        
        # Restore nodata
        slope_deg[nodata_mask] = -9999
        aspect_deg[nodata_mask] = -9999
        curvature[nodata_mask] = -9999
        plan_curvature[nodata_mask] = -9999
        roughness[nodata_mask] = -9999
        
        logger.info(
            f"Terrain analysis complete: "
            f"slope range [{np.nanmin(slope_deg[slope_deg > -9000]):.1f}°, "
            f"{np.nanmax(slope_deg):.1f}°], "
            f"roughness range [{np.nanmin(roughness[roughness > -9000]):.2f}, "
            f"{np.nanmax(roughness):.2f}]"
        )
        
        return TerrainMetrics(
            slope_deg=slope_deg.astype(np.float32),
            aspect_deg=aspect_deg.astype(np.float32),
            curvature=curvature.astype(np.float32),
            plan_curvature=plan_curvature.astype(np.float32),
            roughness=roughness.astype(np.float32),
            transform=transform,
            cell_size_m=cell_size_m,
            crs=crs,
        )
    
    def _smooth_dem(self, dem: np.ndarray) -> np.ndarray:
        """
        Apply Gaussian smoothing to DEM to reduce noise.
        
        Uses scipy's gaussian_filter with nan-aware handling.
        """
        # Create mask for valid data
        valid_mask = ~np.isnan(dem)
        
        # Replace NaN with local mean for smoothing
        dem_filled = dem.copy()
        dem_filled[~valid_mask] = np.nanmean(dem)
        
        # Apply Gaussian filter
        smoothed = gaussian_filter(dem_filled, sigma=self.smoothing_sigma)
        
        # Restore NaN positions
        smoothed[~valid_mask] = np.nan
        
        return smoothed
    
    def _compute_slope_aspect(
        self,
        dem: np.ndarray,
        cell_size_m: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Compute slope and aspect using Horn's method (3x3 neighborhood).
        
        This is more accurate than simple gradient for rough terrain.
        
        Args:
            dem: Elevation array (meters)
            cell_size_m: Cell size in meters
            
        Returns:
            Tuple of (slope in degrees, aspect in degrees 0-360 clockwise from north)
        """
        # Use Sobel-like kernels for better edge handling (Horn's method)
        # dz/dx kernel
        kernel_x = np.array([
            [-1, 0, 1],
            [-2, 0, 2],
            [-1, 0, 1]
        ]) / (8 * cell_size_m)
        
        # dz/dy kernel  
        kernel_y = np.array([
            [1, 2, 1],
            [0, 0, 0],
            [-1, -2, -1]
        ]) / (8 * cell_size_m)
        
        # Convolve with kernels
        dzdx = ndimage.convolve(dem, kernel_x, mode='nearest')
        dzdy = ndimage.convolve(dem, kernel_y, mode='nearest')
        
        # Calculate slope (in radians, then convert to degrees)
        slope_rad = np.arctan(np.sqrt(dzdx**2 + dzdy**2))
        slope_deg = np.degrees(slope_rad)
        
        # Calculate aspect (direction of steepest descent)
        # atan2 gives angle from -π to π, convert to 0-360 clockwise from north
        aspect_rad = np.arctan2(-dzdx, dzdy)  # Note: -dzdx for clockwise from north
        aspect_deg = np.degrees(aspect_rad)
        aspect_deg = np.where(aspect_deg < 0, aspect_deg + 360, aspect_deg)
        
        # Mark flat areas (slope < 1°) with special aspect value
        aspect_deg = np.where(slope_deg < 1.0, -1, aspect_deg)
        
        return slope_deg, aspect_deg
    
    def _compute_curvature(
        self,
        dem: np.ndarray,
        cell_size_m: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Compute profile and plan curvature.
        
        Profile curvature: curvature in direction of max slope
            - Positive = convex (ridge, nose)
            - Negative = concave (valley, channel)
            
        Plan curvature: curvature perpendicular to slope direction
            - Affects water flow convergence/divergence
        
        Args:
            dem: Elevation array (meters)
            cell_size_m: Cell size in meters
            
        Returns:
            Tuple of (profile curvature, plan curvature)
        """
        # Second derivatives using Laplacian-like kernels
        kernel_xx = np.array([
            [0, 0, 0],
            [1, -2, 1],
            [0, 0, 0]
        ]) / (cell_size_m ** 2)
        
        kernel_yy = np.array([
            [0, 1, 0],
            [0, -2, 0],
            [0, 1, 0]
        ]) / (cell_size_m ** 2)
        
        kernel_xy = np.array([
            [1, 0, -1],
            [0, 0, 0],
            [-1, 0, 1]
        ]) / (4 * cell_size_m ** 2)
        
        # First derivatives
        kernel_x = np.array([
            [0, 0, 0],
            [-1, 0, 1],
            [0, 0, 0]
        ]) / (2 * cell_size_m)
        
        kernel_y = np.array([
            [0, 1, 0],
            [0, 0, 0],
            [0, -1, 0]
        ]) / (2 * cell_size_m)
        
        # Compute derivatives
        zx = ndimage.convolve(dem, kernel_x, mode='nearest')
        zy = ndimage.convolve(dem, kernel_y, mode='nearest')
        zxx = ndimage.convolve(dem, kernel_xx, mode='nearest')
        zyy = ndimage.convolve(dem, kernel_yy, mode='nearest')
        zxy = ndimage.convolve(dem, kernel_xy, mode='nearest')
        
        # Compute curvatures using Zevenbergen & Thorne formulas
        p = zx ** 2 + zy ** 2
        q = p + 1
        
        # Profile curvature (in direction of max slope)
        with np.errstate(divide='ignore', invalid='ignore'):
            profile_curv = np.where(
                p > 1e-10,
                (zxx * zx**2 + 2 * zxy * zx * zy + zyy * zy**2) / (p * np.sqrt(q**3)),
                0
            )
            
            # Plan curvature (perpendicular to slope)
            plan_curv = np.where(
                p > 1e-10,
                (zxx * zy**2 - 2 * zxy * zx * zy + zyy * zx**2) / (p ** 1.5),
                0
            )
        
        # Clip extreme values
        profile_curv = np.clip(profile_curv, -1, 1)
        plan_curv = np.clip(plan_curv, -1, 1)
        
        return profile_curv, plan_curv
    
    def _compute_roughness(self, dem: np.ndarray, window_size: int = 3) -> np.ndarray:
        """
        Compute terrain roughness index (TRI).
        
        TRI = mean absolute difference between center cell and neighbors.
        Higher values = rougher terrain = harder to build on.
        
        Args:
            dem: Elevation array (meters)
            window_size: Size of analysis window (default 3x3)
            
        Returns:
            Roughness index array
        """
        # Use a simple approach: standard deviation in local window
        from scipy.ndimage import generic_filter
        
        def local_roughness(values):
            center = values[len(values) // 2]
            if np.isnan(center):
                return np.nan
            diffs = np.abs(values - center)
            return np.nanmean(diffs)
        
        roughness = generic_filter(
            dem,
            local_roughness,
            size=window_size,
            mode='nearest'
        )
        
        return roughness
    
    def compute_suitability_score(
        self,
        metrics: TerrainMetrics,
        boundary_mask: np.ndarray,
        config: Optional[SuitabilityConfig] = None,
        asset_type: str = "solar_array",
    ) -> np.ndarray:
        """
        Compute composite suitability score for asset placement.
        
        Score ranges from 0 (unsuitable) to 1 (optimal).
        Combines slope, curvature, aspect, and roughness.
        
        Args:
            metrics: TerrainMetrics from analyze_terrain()
            boundary_mask: Boolean mask of site boundary
            config: Suitability scoring configuration
            asset_type: Type of asset being placed
            
        Returns:
            Suitability score array (0-1, higher = better)
        """
        if config is None:
            config = self._get_default_config(asset_type)
        
        height, width = metrics.slope_deg.shape
        
        # Initialize scores
        slope_score = np.zeros((height, width), dtype=np.float32)
        aspect_score = np.ones((height, width), dtype=np.float32)
        curvature_score = np.ones((height, width), dtype=np.float32)
        roughness_score = np.ones((height, width), dtype=np.float32)
        
        # Valid data mask
        valid = (metrics.slope_deg >= 0) & boundary_mask
        
        # --- Slope Score ---
        # 1.0 for slope <= optimal, decreasing to 0 at max_slope
        slope = metrics.slope_deg[valid]
        s_score = np.ones_like(slope)
        
        # Linear decrease from optimal to max
        transition_mask = (slope > config.optimal_slope_deg) & (slope <= config.max_slope_deg)
        s_score[transition_mask] = 1 - (
            (slope[transition_mask] - config.optimal_slope_deg) /
            (config.max_slope_deg - config.optimal_slope_deg)
        )
        
        # Zero for slopes above max
        s_score[slope > config.max_slope_deg] = 0
        
        slope_score[valid] = s_score
        
        # --- Aspect Score (for solar assets) ---
        if asset_type == "solar_array" and config.aspect_weight > 0:
            aspect = metrics.aspect_deg[valid]
            flat_mask = aspect < 0  # Flat areas (no aspect)
            
            # Calculate angular difference from preferred aspect
            diff = np.abs(aspect - config.preferred_aspect)
            diff = np.minimum(diff, 360 - diff)  # Handle wrap-around
            
            a_score = np.ones_like(aspect)
            a_score[~flat_mask] = np.maximum(
                0,
                1 - diff[~flat_mask] / config.aspect_tolerance
            )
            a_score[flat_mask] = 1.0  # Flat areas are neutral
            
            aspect_score[valid] = a_score
        
        # --- Curvature Score ---
        # Prefer flat to slightly concave (better drainage)
        # Penalize highly convex (ridge) or highly concave (channel)
        curv = np.abs(metrics.curvature[valid])
        c_score = np.maximum(0, 1 - curv / config.max_curvature)
        curvature_score[valid] = c_score
        
        # --- Roughness Score ---
        rough = metrics.roughness[valid]
        r_score = np.maximum(0, 1 - rough / config.max_roughness)
        roughness_score[valid] = r_score
        
        # --- Combine Scores ---
        combined = (
            config.slope_weight * slope_score +
            config.aspect_weight * aspect_score +
            config.curvature_weight * curvature_score +
            config.roughness_weight * roughness_score
        )
        
        # Normalize to 0-1
        combined = np.clip(combined, 0, 1)
        
        # Zero out invalid areas
        combined[~boundary_mask] = 0
        combined[metrics.slope_deg < 0] = 0
        
        logger.info(
            f"Suitability score for {asset_type}: "
            f"mean={np.mean(combined[boundary_mask]):.2f}, "
            f"max={np.max(combined):.2f}, "
            f"buildable_pct={np.sum(combined > 0.5) / np.sum(boundary_mask) * 100:.1f}%"
        )
        
        return combined
    
    def _get_default_config(self, asset_type: str) -> SuitabilityConfig:
        """Get default suitability config for asset type."""
        configs = {
            "solar_array": SuitabilityConfig(
                max_slope_deg=15.0,
                optimal_slope_deg=5.0,
                preferred_aspect=180.0,  # South-facing
                aspect_weight=0.10,
                slope_weight=0.65,
            ),
            "battery": SuitabilityConfig(
                max_slope_deg=5.0,
                optimal_slope_deg=2.0,
                aspect_weight=0.0,  # Aspect doesn't matter for batteries
                slope_weight=0.75,
            ),
            "generator": SuitabilityConfig(
                max_slope_deg=5.0,
                optimal_slope_deg=2.0,
                aspect_weight=0.0,
                slope_weight=0.75,
            ),
            "substation": SuitabilityConfig(
                max_slope_deg=5.0,
                optimal_slope_deg=1.0,
                aspect_weight=0.0,
                slope_weight=0.80,
                roughness_weight=0.15,  # Extra penalty for rough terrain
            ),
            "wind_turbine": SuitabilityConfig(
                max_slope_deg=20.0,  # Phase 5: More tolerant to slope than other assets
                optimal_slope_deg=8.0,
                preferred_aspect=180.0,  # North/south orientation less critical
                aspect_weight=0.05,  # Lower aspect weight
                slope_weight=0.60,
                roughness_weight=0.10,
                curvature_weight=0.25,  # Higher curvature weight - prefers convex terrain for wind exposure
            ),
        }
        return configs.get(asset_type, SuitabilityConfig())
    
    def filter_buildable_mask(
        self,
        suitability_score: np.ndarray,
        threshold: float = 0.5,
        min_area_cells: int = 9,
        cell_size_m: float = 10.0,
    ) -> np.ndarray:
        """
        Create filtered buildable mask with morphological cleaning.
        
        Removes small isolated patches and fills small holes to create
        contiguous buildable zones suitable for asset placement.
        
        Args:
            suitability_score: Suitability score array (0-1)
            threshold: Minimum score to be considered buildable
            min_area_cells: Minimum contiguous area in cells
            cell_size_m: Cell size for area calculation
            
        Returns:
            Boolean mask of buildable areas
        """
        # Initial threshold
        buildable = suitability_score >= threshold
        
        # Morphological opening to remove thin connections and small protrusions
        # This helps separate distinct buildable zones
        struct_element = disk(1)  # Small structuring element
        buildable = binary_opening(buildable, structure=struct_element)
        
        # Remove small isolated regions
        buildable = remove_small_objects(buildable, min_size=min_area_cells)
        
        # Fill small holes within buildable regions
        buildable = remove_small_holes(buildable, area_threshold=min_area_cells)
        
        # Morphological closing to smooth edges
        buildable = binary_closing(buildable, structure=struct_element)
        
        logger.info(
            f"Filtered buildable mask: "
            f"{np.sum(buildable)} cells, "
            f"{np.sum(buildable) * cell_size_m**2 / 10000:.1f} hectares"
        )
        
        return buildable
    
    def get_aspect_category(self, aspect_deg: float) -> AspectCategory:
        """Convert aspect angle to cardinal direction category."""
        if aspect_deg < 0:
            return AspectCategory.FLAT
        
        # Normalize to 0-360
        aspect = aspect_deg % 360
        
        if aspect < 22.5 or aspect >= 337.5:
            return AspectCategory.NORTH
        elif aspect < 67.5:
            return AspectCategory.NORTHEAST
        elif aspect < 112.5:
            return AspectCategory.EAST
        elif aspect < 157.5:
            return AspectCategory.SOUTHEAST
        elif aspect < 202.5:
            return AspectCategory.SOUTH
        elif aspect < 247.5:
            return AspectCategory.SOUTHWEST
        elif aspect < 292.5:
            return AspectCategory.WEST
        else:
            return AspectCategory.NORTHWEST


# Global service instance
_terrain_analysis_service: Optional[TerrainAnalysisService] = None


def get_terrain_analysis_service(smoothing_sigma: float = 1.0) -> TerrainAnalysisService:
    """Get the terrain analysis service singleton."""
    global _terrain_analysis_service
    if _terrain_analysis_service is None:
        _terrain_analysis_service = TerrainAnalysisService(smoothing_sigma=smoothing_sigma)
    return _terrain_analysis_service

