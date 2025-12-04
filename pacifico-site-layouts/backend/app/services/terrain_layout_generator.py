"""
Terrain-aware layout generation service.

Generates layouts respecting terrain constraints including:
- Slope-based buildable area filtering
- Asset type-specific slope limits
- Minimum spacing enforcement
- Optimized road routing

D-05: Supports multiple variant strategies:
- Balanced: Default terrain-aware placement
- Density: Maximize capacity per hectare
- Low Earthwork: Minimize cut/fill volumes
- Clustered: Group assets tightly near hub

Enhanced algorithms (Phase E):
- Composite suitability scoring (slope + curvature + aspect + roughness)
- Poisson-disk sampling for better spatial distribution
- True rectangular footprint geometry with rotation
- MST-based road network optimization
- Road corridor earthwork calculation

Replaces DummyLayoutGenerator from Phase A with real terrain analysis.
"""
import heapq
import logging
import math
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
from uuid import UUID

import numpy as np
from rasterio.transform import Affine, rowcol, xy
from scipy import ndimage
from scipy.ndimage import distance_transform_edt
from scipy.spatial import distance_matrix, cKDTree
from shapely.geometry import LineString, Point, Polygon, box, mapping
from shapely.affinity import rotate, translate
from shapely.ops import unary_union

logger = logging.getLogger(__name__)


class LayoutStrategy(str, Enum):
    """
    D-05: Layout optimization strategies.
    
    Each strategy optimizes for different objectives while respecting terrain constraints.
    """
    BALANCED = "balanced"        # Default: balance capacity, earthwork, access
    DENSITY = "density"          # Maximize kW/ha, may increase earthwork
    LOW_EARTHWORK = "low_earthwork"  # Minimize cut/fill, may reduce capacity
    CLUSTERED = "clustered"      # Group assets tightly, minimize road network


# Strategy display names and descriptions
STRATEGY_INFO = {
    LayoutStrategy.BALANCED: {
        "name": "Balanced",
        "description": "Balance capacity, earthwork, and access roads",
    },
    LayoutStrategy.DENSITY: {
        "name": "High Density",
        "description": "Maximize capacity per hectare",
    },
    LayoutStrategy.LOW_EARTHWORK: {
        "name": "Low Earthwork",
        "description": "Minimize grading and cut/fill volumes",
    },
    LayoutStrategy.CLUSTERED: {
        "name": "Clustered",
        "description": "Group assets tightly to minimize infrastructure",
    },
}


@dataclass
class PlacedAsset:
    """Represents a placed asset with terrain information."""
    asset_type: str
    name: str
    position: Point
    capacity_kw: float
    elevation_m: float = 0.0
    slope_deg: float = 0.0
    aspect_deg: float = -1.0  # Slope direction (-1 = flat)
    suitability_score: float = 1.0  # Composite terrain score
    footprint_length_m: float = 20.0
    footprint_width_m: float = 20.0
    rotation_deg: float = 0.0  # Rotation angle for optimal orientation
    # Grid position for cut/fill
    grid_row: int = 0
    grid_col: int = 0
    
    @property
    def footprint_polygon(self) -> Polygon:
        """Get the actual footprint as a rotated rectangle polygon."""
        # Create rectangle centered at origin
        half_l = self.footprint_length_m / 2
        half_w = self.footprint_width_m / 2
        rect = box(-half_l, -half_w, half_l, half_w)
        
        # Rotate around center
        if self.rotation_deg != 0:
            rect = rotate(rect, self.rotation_deg, origin=(0, 0))
        
        # Translate to actual position
        rect = translate(rect, self.position.x, self.position.y)
        
        return rect


@dataclass
class PlacedRoad:
    """Represents a placed road segment."""
    name: str
    geometry: LineString
    length_m: float
    width_m: float = 5.0
    max_grade_pct: float = 0.0
    max_cumulative_cost: float = 0.0
    road_class: str = "tertiary"  # spine, secondary, tertiary
    parent_segment_id: Optional[UUID] = None
    stationing: list[dict] = field(default_factory=list)
    kpi_flags: list[str] = field(default_factory=list)
    retry_count: int = 0
    failure_reason: Optional[str] = None


@dataclass
class CutFillResult:
    """Cut/fill calculation results."""
    cut_volume_m3: float = 0.0
    fill_volume_m3: float = 0.0
    road_cut_m3: float = 0.0  # Cut volume for road corridors
    road_fill_m3: float = 0.0  # Fill volume for road corridors
    per_asset: list[dict] = field(default_factory=list)
    per_road: list[dict] = field(default_factory=list)
    
    @property
    def total_cut_m3(self) -> float:
        """Total cut including roads."""
        return self.cut_volume_m3 + self.road_cut_m3
    
    @property
    def total_fill_m3(self) -> float:
        """Total fill including roads."""
        return self.fill_volume_m3 + self.road_fill_m3
    
    @property
    def net_balance_m3(self) -> float:
        """Net earthwork balance (positive = excess cut, negative = need import)."""
        return self.total_cut_m3 - self.total_fill_m3


class TerrainAwareLayoutGenerator:
    """
    Generates layouts respecting terrain constraints.
    
    Slope limits by asset type (in degrees):
    - Solar arrays: <15° (can tolerate some slope with tracking)
    - Battery: <5° (need flat pad for containers)
    - Generator: <5° (need flat pad for equipment)
    - Substation: <5° (critical infrastructure, must be level)
    """
    
    # Maximum slope in degrees for each asset type
    # Phase E: Tightened limits for better terrain compliance
    SLOPE_LIMITS = {
        "solar_array": 10.0,  # Reduced from 15° - trackers work best on gentler slopes
        "battery": 4.0,       # Reduced from 5° - BESS needs level ground
        "generator": 5.0,     # Kept at 5° - generators need flat pads
        "substation": 3.0,    # Reduced from 5° - critical infrastructure must be very level
        "wind_turbine": 15.0, # Phase 5: Wind turbines more tolerant to slope
    }
    
    # Optimal slope targets for scoring (positions below this get bonus)
    SLOPE_OPTIMAL = {
        "solar_array": 5.0,   # Prefer slopes under 5°
        "battery": 2.0,       # Prefer slopes under 2°
        "generator": 3.0,     # Prefer slopes under 3°
        "substation": 1.0,    # Prefer nearly flat
        "wind_turbine": 8.0,  # Phase 5: Prefer moderate slopes for wind exposure
    }
    
    # Asset configurations
    ASSET_CONFIGS = {
        "solar_array": {
            "capacity_range": (100, 500),  # kW per unit
            "weight": 0.6,  # Probability weight for type selection
            "footprint": (30, 20),  # length x width in meters
            "pad_size_m": 35,  # Grading pad size
        },
        "battery": {
            "capacity_range": (50, 200),
            "weight": 0.2,
            "footprint": (15, 10),
            "pad_size_m": 20,
        },
        "generator": {
            "capacity_range": (100, 300),
            "weight": 0.15,
            "footprint": (10, 8),
            "pad_size_m": 15,
        },
        "substation": {
            "capacity_range": (500, 2000),
            "weight": 0.05,
            "footprint": (20, 15),
            "pad_size_m": 25,
        },
        "wind_turbine": {
            "capacity_range": (1000, 5000),  # kW per turbine (larger than solar)
            "weight": 0.0,  # Phase 5: Not selected by default, explicit placement only
            "footprint": (60, 60),  # Larger footprint for turbine base
            "pad_size_m": 80,  # Larger grading pad
        },
    }
    
    # Minimum spacing between assets in meters (varies by strategy)
    MIN_SPACING_M = 15.0
    
    # Maximum road grade (percent)
    MAX_ROAD_GRADE_PCT = 10.0
    
    # D-05: Strategy-specific configurations
    # Phase E: Rebalanced to prioritize terrain compliance
    STRATEGY_CONFIGS = {
        LayoutStrategy.BALANCED: {
            "min_spacing_m": 15.0,
            "slope_weight": 0.65,      # Increased from 0.5 - prioritize flat terrain
            "proximity_weight": 0.15,  # Reduced from 0.3 - less pull toward hub
            "suitability_weight": 0.20,# Keep suitability importance
            "capacity_multiplier": 1.0,
            "solar_weight": 0.6,       # Asset type weights
            "use_poisson_disk": True,  # Use Poisson-disk sampling
            "use_mst_roads": True,     # Use MST for road network
        },
        LayoutStrategy.DENSITY: {
            "min_spacing_m": 10.0,     # Tighter spacing
            "slope_weight": 0.50,      # Increased from 0.3 - still respect terrain
            "proximity_weight": 0.15,  # Reduced from 0.2
            "suitability_weight": 0.35,# Adjusted for density
            "capacity_multiplier": 1.3,# Higher capacity per asset
            "solar_weight": 0.8,       # More solar arrays
            "use_poisson_disk": True,
            "use_mst_roads": True,
        },
        LayoutStrategy.LOW_EARTHWORK: {
            "min_spacing_m": 20.0,     # More spacing for easier grading
            "slope_weight": 0.80,      # Increased from 0.7 - very strong flat preference
            "proximity_weight": 0.05,  # Reduced from 0.1 - ignore proximity
            "suitability_weight": 0.15,
            "capacity_multiplier": 0.8,# Lower capacity to stay on flat land
            "solar_weight": 0.5,
            "use_poisson_disk": True,
            "use_mst_roads": False,    # Star topology may be shorter for sparse layouts
        },
        LayoutStrategy.CLUSTERED: {
            "min_spacing_m": 12.0,     # Tight clustering
            "slope_weight": 0.45,      # Increased from 0.3 - still respect terrain
            "proximity_weight": 0.40,  # Reduced from 0.6 - cluster but on good terrain
            "suitability_weight": 0.15,
            "capacity_multiplier": 1.0,
            "solar_weight": 0.6,
            "use_poisson_disk": False, # Grid-like placement for clusters
            "use_mst_roads": True,
        },
    }
    
    def __init__(
        self, 
        target_capacity_kw: float = 1000.0,
        strategy: LayoutStrategy = LayoutStrategy.BALANCED,
        generation_profile: Optional[str] = None,
    ):
        """
        Initialize the generator.
        
        Args:
            target_capacity_kw: Target total capacity in kW
            strategy: D-05 - Optimization strategy for layout generation
            generation_profile: Optional generation profile (solar_farm, gas_bess, wind_hybrid, hybrid)
        """
        self.target_capacity_kw = target_capacity_kw
        self.strategy = strategy
        self.strategy_config = self.STRATEGY_CONFIGS.get(strategy, self.STRATEGY_CONFIGS[LayoutStrategy.BALANCED])
        self._block_asset_counter = 0
        
        # Block layout tracking (populated during asset placement)
        self._block_layout_metadata: Optional[dict[str, Any]] = None
        
        # Apply generation profile if provided
        self._profile_config = None
        if generation_profile:
            self._apply_generation_profile(generation_profile)
    
    def _apply_generation_profile(self, profile_name: str) -> None:
        """
        Apply a generation profile to override default asset configs.
        
        Args:
            profile_name: Name of the profile (solar_farm, gas_bess, wind_hybrid, hybrid)
        """
        from app.services.generation_profiles import GenerationProfile, get_profile
        
        try:
            profile_enum = GenerationProfile(profile_name)
            profile = get_profile(profile_enum)
            self._profile_config = profile
            
            # Override ASSET_CONFIGS with profile settings
            self.ASSET_CONFIGS = {}
            self.SLOPE_LIMITS = {}
            self.SLOPE_OPTIMAL = {}
            
            for asset_type, config in profile.asset_configs.items():
                self.ASSET_CONFIGS[asset_type] = {
                    "capacity_range": config.capacity_range,
                    "weight": config.weight,
                    "footprint": config.footprint,
                    "pad_size_m": config.pad_size_m,
                }
                self.SLOPE_LIMITS[asset_type] = config.slope_limit_deg
                self.SLOPE_OPTIMAL[asset_type] = config.optimal_slope_deg
            
            # Override min spacing from profile
            self.MIN_SPACING_M = profile.min_spacing_m
            
            logger.info(f"Applied generation profile: {profile.name} with {len(self.ASSET_CONFIGS)} asset types")
            
        except ValueError:
            logger.warning(f"Unknown generation profile: {profile_name}, using defaults")
    
    def generate(
        self,
        boundary: Polygon,
        dem_array: np.ndarray,
        slope_array: np.ndarray,
        transform: Affine,
        num_assets: int = 8,
        exclusion_zones: Optional[list[dict[str, Any]]] = None,
        aspect_array: Optional[np.ndarray] = None,
        curvature_array: Optional[np.ndarray] = None,
        plan_curvature_array: Optional[np.ndarray] = None,
        suitability_scores: Optional[dict[str, np.ndarray]] = None,
        entry_point: Optional[Point] = None,
    ) -> tuple[list[PlacedAsset], list[PlacedRoad], CutFillResult]:
        """
        Generate a terrain-aware layout.
        
        Args:
            boundary: Site boundary as Shapely Polygon
            dem_array: Elevation data (meters)
            slope_array: Slope data (degrees)
            transform: Rasterio affine transform
            num_assets: Target number of assets
            exclusion_zones: Optional list of exclusion zone dicts (polygon, cost_multiplier)
            aspect_array: Optional aspect data
            curvature_array: Optional curvature data
            plan_curvature_array: Optional plan curvature data
            suitability_scores: Optional dict of asset_type -> suitability score array
            entry_point: Optional site entry point for road network optimization
            
        Returns:
            Tuple of (assets, roads, cut_fill_result)
        """
        if not boundary.is_valid:
            boundary = boundary.buffer(0)
        
        # 1. Normalize Inputs: Fill nodata
        dem_array = self._fill_nodata(dem_array)
        slope_array = self._fill_nodata(slope_array, fill_value=0)
        
        # Get raster dimensions and cell size
        height, width = slope_array.shape
        cell_size_x = abs(transform[0])
        cell_size_y = abs(transform[4])
        
        # Convert cell size to meters if in degrees
        if cell_size_x < 1:  # Likely degrees
            # Use center latitude for more accurate conversion
            center_lat = transform[5] - (height / 2) * cell_size_y
            lat_factor = np.cos(np.radians(abs(center_lat)))
            cell_size_m = cell_size_x * 111000 * lat_factor
        else:
            cell_size_m = cell_size_x
        
        logger.info(f"Grid: {width}x{height}, cell size: {cell_size_m:.1f}m")
        
        # Store for use in other methods
        self._dem_array = dem_array
        self._slope_array = slope_array # Also useful
        self._aspect_array = aspect_array
        self._curvature_array = curvature_array
        self._plan_curvature_array = plan_curvature_array
        self._suitability_scores = suitability_scores or {}
        self._entry_point = entry_point
        
        # Create boundary mask
        boundary_mask = self._rasterize_boundary(boundary, transform, (height, width))
        
        # D-03: Create exclusion zone mask and allowance mask
        exclusion_mask = np.zeros((height, width), dtype=bool)
        self._allowance_mask = np.ones((height, width), dtype=np.float32)
        
        if exclusion_zones:
            exclusion_mask, self._allowance_mask = self._process_exclusion_zones(
                exclusion_zones=exclusion_zones,
                transform=transform,
                shape=(height, width),
            )
            excluded_pct = np.sum(exclusion_mask & boundary_mask) / np.sum(boundary_mask) * 100
            logger.info(f"Exclusion zones: {len(exclusion_zones)} zones, {excluded_pct:.1f}% of site excluded")
        
        # Create buildable masks for each asset type
        buildable_masks = {}
        for asset_type, max_slope in self.SLOPE_LIMITS.items():
            # D-03: Buildable where slope is below limit AND within boundary AND NOT in exclusion zone
            mask = (slope_array < max_slope) & (slope_array >= 0) & boundary_mask & ~exclusion_mask
            buildable_masks[asset_type] = mask
            buildable_pct = np.sum(mask) / np.sum(boundary_mask) * 100
            logger.info(f"{asset_type}: {buildable_pct:.1f}% buildable (slope < {max_slope}°)")
        
        # Place assets
        assets = self._place_assets_terrain_aware(
            boundary=boundary,
            dem_array=dem_array,
            slope_array=slope_array,
            buildable_masks=buildable_masks,
            transform=transform,
            cell_size_m=cell_size_m,
            num_assets=num_assets,
        )
        
        # Generate roads connecting assets
        roads = self._generate_roads_terrain_aware(
            assets=assets,
            slope_array=slope_array,
            transform=transform,
            cell_size_m=cell_size_m,
        )
        
        # Calculate cut/fill volumes
        cut_fill = self._compute_cut_fill(
            assets=assets,
            roads=roads,
            dem_array=dem_array,
            transform=transform,
            cell_size_m=cell_size_m,
        )
        
        return assets, roads, cut_fill
    
    def _fill_nodata(self, array: np.ndarray, fill_value: float = None) -> np.ndarray:
        """
        Fill nodata/NaN values in raster array using nearest neighbor interpolation.
        """
        # Treat large negative values as nodata
        mask = np.isnan(array) | (array < -9000)
        if not np.any(mask):
            return array
            
        if fill_value is not None:
            filled = array.copy()
            filled[mask] = fill_value
            return filled
            
        # Nearest neighbor interpolation using distance transform
        # indices returns the indices of the nearest background point (where mask is 0/False)
        # So we invert mask: valid data is background (0), nodata is foreground (1)
        indices = distance_transform_edt(mask, return_distances=False, return_indices=True)
        return array[tuple(indices)]

    def _process_exclusion_zones(
        self,
        exclusion_zones: list[dict[str, Any]],
        transform: Affine,
        shape: tuple[int, int],
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Process exclusion zones to create binary mask and cost multiplier mask.
            
        Returns:
            Tuple of (exclusion_mask, allowance_mask)
        """
        from rasterio.features import rasterize
        
        exclusion_mask = np.zeros(shape, dtype=bool)
        allowance_mask = np.ones(shape, dtype=np.float32)
        
        # Separate hard exclusions vs allowances
        hard_zones = []
        allowance_zones = []
        
        for zone in exclusion_zones:
            poly = zone["polygon"]
            multiplier = zone.get("cost_multiplier", 1.0)
            
            if not poly.is_valid:
                poly = poly.buffer(0)
                
            # Treat very high cost (>= 100) as hard exclusion for buildable area
            # But only if it's not an allowance (multiplier < 1.0)
            if multiplier >= 100.0: 
                 hard_zones.append(poly)
            elif abs(multiplier - 1.0) > 0.001:
                 allowance_zones.append((poly, multiplier))
            
        # Rasterize hard exclusions
        if hard_zones:
            exclusion_mask = rasterize(
                [(p, 1) for p in hard_zones],
                out_shape=shape,
                transform=transform,
                fill=0,
                dtype=np.uint8,
            ).astype(bool)
            
        # Rasterize allowances/penalties
        for poly, multiplier in allowance_zones:
             try:
                 mask = rasterize(
                    [(poly, 1)],
                    out_shape=shape,
                    transform=transform,
                    fill=0,
                    dtype=np.uint8,
                ).astype(bool)
                 # Apply multiplier where mask is True
                 allowance_mask[mask] *= multiplier
             except Exception:
                 logger.warning("Failed to rasterize allowance zone")
             
        return exclusion_mask, allowance_mask
    
    def _rasterize_boundary(
        self,
        boundary: Polygon,
        transform: Affine,
        shape: tuple[int, int],
    ) -> np.ndarray:
        """
        Create a boolean mask of the boundary polygon.
        
        Args:
            boundary: Site boundary polygon
            transform: Rasterio affine transform
            shape: Output shape (height, width)
            
        Returns:
            Boolean mask where True = inside boundary
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
    
    def _place_assets_terrain_aware(
        self,
        boundary: Polygon,
        dem_array: np.ndarray,
        slope_array: np.ndarray,
        buildable_masks: dict[str, np.ndarray],
        transform: Affine,
        cell_size_m: float,
        num_assets: int,
    ) -> list[PlacedAsset]:
        """
        Place assets using terrain-aware heuristics.
        
        Enhanced Strategy (Phase E):
        1. Use Poisson-disk sampling for better spatial distribution (if enabled)
        2. Find flattest area for substation (centroid of flat region)
        3. Place batteries/generators near substation with suitability scoring
        4. Fill remaining capacity with solar arrays, considering aspect
        5. Compute optimal rotation for each asset based on terrain aspect
        """
        assets = []
        placed_positions = []  # Track placed asset grid positions
        placed_footprints = []  # Track actual footprint polygons for collision detection
        
        # Structured block layouts (gas campus, etc.)
        block_assets = self._place_block_layout_assets(
            boundary=boundary,
            dem_array=dem_array,
            slope_array=slope_array,
            buildable_masks=buildable_masks,
            transform=transform,
            cell_size_m=cell_size_m,
        )
        if block_assets:
            return block_assets
        
        # Determine asset type distribution
        asset_types = self._select_asset_types(num_assets)
        
        # Ensure at least one substation
        if "substation" not in asset_types and num_assets >= 3:
            asset_types[0] = "substation"
        
        # Sort to place substation first, then batteries/generators, then solar
        priority_order = {"substation": 0, "battery": 1, "generator": 2, "solar_array": 3}
        asset_types.sort(key=lambda t: priority_order.get(t, 99))
        
        # Calculate capacity per asset
        capacity_per_asset = self.target_capacity_kw / max(num_assets, 1)
        
        # Check if we should use Poisson-disk sampling
        use_poisson = self.strategy_config.get("use_poisson_disk", False)
        
        # Pre-generate candidate positions using Poisson-disk if enabled
        if use_poisson:
            min_spacing = self.strategy_config.get("min_spacing_m", self.MIN_SPACING_M)
            # Calculate min_spacing_cells, ensuring it's at least 1 to avoid division by zero
            min_spacing_cells = max(1, int(min_spacing / cell_size_m))
            
            # Use solar buildable mask (most permissive) for initial candidates
            candidate_positions = self._poisson_disk_sample(
                buildable_masks.get("solar_array", buildable_masks["substation"]),
                min_spacing_cells=min_spacing_cells,
                num_candidates=num_assets * 3,  # Generate extra candidates
            )
            logger.info(f"Poisson-disk sampling generated {len(candidate_positions)} candidates (spacing={min_spacing_cells} cells)")
        else:
            candidate_positions = None
        
        # Place each asset
        for i, asset_type in enumerate(asset_types):
            buildable_mask = buildable_masks[asset_type]
            
            # Find best position for this asset
            position = self._find_best_position_enhanced(
                asset_type=asset_type,
                buildable_mask=buildable_mask,
                slope_array=slope_array,
                dem_array=dem_array,
                transform=transform,
                cell_size_m=cell_size_m,
                placed_positions=placed_positions,
                placed_footprints=placed_footprints,
                existing_assets=assets,
                candidate_positions=candidate_positions,
            )
            
            if position is None:
                logger.warning(f"Could not place {asset_type} {i+1}")
                continue
            
            row, col = position
            placed_positions.append((row, col))
            
            # Get coordinates and terrain values
            x, y = xy(transform, row, col)
            elevation = float(dem_array[row, col])
            slope = float(slope_array[row, col])
            
            # Get aspect if available
            aspect = -1.0
            if self._aspect_array is not None:
                aspect = float(self._aspect_array[row, col])
            
            # Get suitability score if available
            suitability = 1.0
            if asset_type in self._suitability_scores:
                suitability = float(self._suitability_scores[asset_type][row, col])
            
            # Calculate optimal rotation based on aspect (for solar arrays)
            rotation = self._compute_optimal_rotation(asset_type, aspect)
            
            # Calculate capacity - scale based on target, clamped to profile range
            config = self.ASSET_CONFIGS[asset_type]
            min_cap, max_cap = config["capacity_range"]
            
            if max_cap > 0:
                # Use capacity_per_asset as target, add ±20% random variation
                variation = random.uniform(0.8, 1.2)
                target_cap = capacity_per_asset * variation
                # Clamp to the profile's min/max
                final_capacity = max(min_cap, min(target_cap, max_cap))
            else:
                final_capacity = 0.0
            
            asset = PlacedAsset(
                asset_type=asset_type,
                name=f"{asset_type.replace('_', ' ').title()} {i + 1}",
                position=Point(x, y),
                capacity_kw=round(final_capacity, 1),
                elevation_m=round(elevation, 1),
                slope_deg=round(slope, 1),
                aspect_deg=round(aspect, 1),
                suitability_score=round(suitability, 3),
                footprint_length_m=config["footprint"][0],
                footprint_width_m=config["footprint"][1],
                rotation_deg=rotation,
                grid_row=row,
                grid_col=col,
            )
            assets.append(asset)
            placed_footprints.append(asset.footprint_polygon)
            
            # Phase E: Log each asset placement for debugging
            logger.info(f"Placed {asset_type} at slope={slope:.1f}° (limit={self.SLOPE_LIMITS[asset_type]}°)")
        
        # Summary statistics
        slopes_placed = [a.slope_deg for a in assets]
        logger.info(f"Placed {len(assets)} assets: slope range {min(slopes_placed):.1f}°-{max(slopes_placed):.1f}°, avg {np.mean(slopes_placed):.1f}°")
        return assets

    def _find_optimal_block_anchor(
        self,
        buildable_masks: dict[str, np.ndarray],
        slope_array: np.ndarray,
        layout_config,
        cell_size_m: float,
        actual_rows: int,
        actual_cols: int,
        sample_step: int = 15,
    ) -> tuple[Optional[int], Optional[int]]:
        """Find the optimal anchor point for block layout based on suitability.
        
        Calculates the ACTUAL footprint needed for the grid and finds the best
        location that can accommodate the entire layout.
        """
        import math
        
        # Get a combined buildable mask (use gas_turbine mask as reference for block layouts)
        primary_mask = buildable_masks.get("gas_turbine")
        if primary_mask is None:
            primary_mask = buildable_masks.get("substation")
        if primary_mask is None:
            primary_mask = next(iter(buildable_masks.values()), None)
        if primary_mask is None:
            return None, None
        
        height, width = primary_mask.shape
        
        # Calculate ACTUAL grid footprint based on blocks needed (not profile defaults)
        grid_height_cells = int((actual_rows * layout_config.spacing_row_m) / cell_size_m)
        grid_width_cells = int((actual_cols * layout_config.spacing_col_m) / cell_size_m)
        half_h = grid_height_cells // 2
        half_w = grid_width_cells // 2
        
        logger.info(
            f"Block anchor search: need {actual_rows}x{actual_cols} grid, "
            f"footprint {grid_height_cells}x{grid_width_cells} cells "
            f"({grid_height_cells * cell_size_m:.0f}m x {grid_width_cells * cell_size_m:.0f}m)"
        )
        
        # Get suitability array for gas turbines (primary asset in block layout)
        suitability = self._suitability_scores.get("gas_turbine")
        if suitability is None:
            # Fall back to using inverse slope as proxy for suitability
            suitability = 1.0 - (slope_array / 15.0)
            suitability = np.clip(suitability, 0, 1)
        
        best_anchor = (None, None)
        best_score = -float("inf")
        
        # Ensure we have enough margin from edges
        margin_h = max(half_h, 10)
        margin_w = max(half_w, 10)
        
        # Sample candidate anchor points across the buildable area
        for row in range(margin_h, height - margin_h, sample_step):
            for col in range(margin_w, width - margin_w, sample_step):
                # Define the region this anchor would cover
                r_min = max(0, row - half_h)
                r_max = min(height, row + half_h)
                c_min = max(0, col - half_w)
                c_max = min(width, col + half_w)
                
                # Check if region is mostly buildable
                region_mask = primary_mask[r_min:r_max, c_min:c_max]
                if region_mask.size == 0:
                    continue
                
                buildable_ratio = region_mask.sum() / region_mask.size
                if buildable_ratio < 0.6:  # Require at least 60% buildable for large layouts
                    continue
                
                # Calculate average suitability in the region
                region_suitability = suitability[r_min:r_max, c_min:c_max]
                avg_suitability = float(np.mean(region_suitability[region_mask]))
                
                # Calculate average slope in the region
                region_slope = slope_array[r_min:r_max, c_min:c_max]
                avg_slope = float(np.mean(region_slope[region_mask]))
                
                # Score: prioritize high suitability, low slope, and high buildable ratio
                # Also prefer locations closer to center of buildable area
                center_row = height // 2
                center_col = width // 2
                distance_from_center = math.sqrt((row - center_row)**2 + (col - center_col)**2)
                max_distance = math.sqrt(height**2 + width**2) / 2
                centrality = 1.0 - (distance_from_center / max_distance)
                
                score = (
                    avg_suitability * 100 
                    - avg_slope * 3  # Penalize slope more
                    + buildable_ratio * 30  # Reward buildable area
                    + centrality * 20  # Prefer central locations
                )
                
                if score > best_score:
                    best_score = score
                    best_anchor = (row, col)
        
        if best_anchor[0] is not None:
            logger.info(
                f"Block anchor: found optimal at ({best_anchor[0]}, {best_anchor[1]}) "
                f"with score={best_score:.1f}"
            )
        else:
            # Fallback to center of buildable area
            buildable_rows, buildable_cols = np.where(primary_mask)
            if len(buildable_rows) > 0:
                center_row = int(np.mean(buildable_rows))
                center_col = int(np.mean(buildable_cols))
                best_anchor = (center_row, center_col)
                logger.info(f"Block anchor: using buildable centroid ({center_row}, {center_col})")
        
        return best_anchor

    def _place_block_layout_assets(
        self,
        boundary: Polygon,
        dem_array: np.ndarray,
        slope_array: np.ndarray,
        buildable_masks: dict[str, np.ndarray],
        transform: Affine,
        cell_size_m: float,
    ) -> Optional[list[PlacedAsset]]:
        """Place assets using structured block layout if profile defines one."""
        import math
        
        layout_config = getattr(self._profile_config, "block_layout", None)
        if not layout_config:
            return None
        
        # Define which asset types actually generate power (vs storage/infrastructure)
        GENERATING_ASSET_TYPES = {"gas_turbine", "solar_array", "wind_turbine", "generator"}
        
        # STEP 1: Calculate how many blocks we need FIRST
        block_generation_kw = 0.0
        generators_per_block = 0
        for blueprint in layout_config.assets:
            if blueprint.asset_type in GENERATING_ASSET_TYPES:
                if blueprint.asset_type in self.ASSET_CONFIGS:
                    cfg = self.ASSET_CONFIGS[blueprint.asset_type]
                    min_cap, max_cap = cfg["capacity_range"]
                    block_generation_kw += (min_cap + max_cap) / 2
                    generators_per_block += 1
        
        if block_generation_kw > 0:
            blocks_needed = max(1, int(round(self.target_capacity_kw / block_generation_kw)))
        else:
            blocks_needed = layout_config.rows * layout_config.columns
        
        # Calculate grid dimensions (prefer roughly square layout)
        actual_cols = max(1, int(math.ceil(math.sqrt(blocks_needed))))
        actual_rows = max(1, int(math.ceil(blocks_needed / actual_cols)))
        
        # Cap to reasonable site coverage
        max_grid_dimension = 20  # Allow up to 20x20 = 400 blocks (~17 GW)
        actual_rows = min(actual_rows, max_grid_dimension)
        actual_cols = min(actual_cols, max_grid_dimension)
        
        total_blocks = actual_rows * actual_cols
        total_generators = total_blocks * generators_per_block
        capacity_per_generator = self.target_capacity_kw / max(1, total_generators)
        
        # STEP 2: Now find optimal anchor that can fit the ACTUAL grid size
        anchor_row, anchor_col = self._find_optimal_block_anchor(
            buildable_masks=buildable_masks,
            slope_array=slope_array,
            layout_config=layout_config,
            cell_size_m=cell_size_m,
            actual_rows=actual_rows,
            actual_cols=actual_cols,
        )
        if anchor_row is None:
            logger.warning("Block layout: could not find suitable anchor point")
            return None
        
        logger.info(
            f"Block layout: target={self.target_capacity_kw/1000:.1f}MW, "
            f"block_gen={block_generation_kw/1000:.1f}MW, "
            f"blocks={total_blocks} ({actual_rows}x{actual_cols}), "
            f"generators={total_generators}, cap_per_gen={capacity_per_generator/1000:.1f}MW"
        )
        
        used_mask = np.zeros_like(slope_array, dtype=bool)
        assets: list[PlacedAsset] = []
        
        # Track block center positions for corridor generation
        block_centers: list[tuple[int, int]] = []  # (row, col) in grid coords
        row_corridors: list[list[tuple[int, int]]] = []  # blocks grouped by row
        
        row_center = (actual_rows - 1) / 2
        col_center = (actual_cols - 1) / 2
        
        for row_idx in range(actual_rows):
            row_blocks: list[tuple[int, int]] = []
            for col_idx in range(actual_cols):
                base_row = anchor_row + int(
                    round(((row_idx - row_center) * layout_config.spacing_row_m) / cell_size_m)
                )
                base_col = anchor_col + int(
                    round(((col_idx - col_center) * layout_config.spacing_col_m) / cell_size_m)
                )
                
                block_centers.append((base_row, base_col))
                row_blocks.append((base_row, base_col))
                
                for blueprint in layout_config.assets:
                    target_row = base_row - int(round(blueprint.offset_north_m / cell_size_m))
                    target_col = base_col + int(round(blueprint.offset_east_m / cell_size_m))
                    
                    buildable_mask = buildable_masks.get(
                        blueprint.asset_type,
                        buildable_masks.get("substation"),
                    )
                    if buildable_mask is None:
                        buildable_mask = next(iter(buildable_masks.values()))
                    placed_cell = self._find_nearest_buildable_cell(
                        asset_type=blueprint.asset_type,
                        target_row=target_row,
                        target_col=target_col,
                        buildable_mask=buildable_mask,
                        used_mask=used_mask,
                        slope_array=slope_array,
                    )
                    if placed_cell is None:
                        logger.warning(f"Block layout: could not place {blueprint.asset_type}")
                        continue
                    
                    # Only generators get capacity targeting; others get 0 or their natural range
                    is_generator = blueprint.asset_type in GENERATING_ASSET_TYPES
                    asset = self._create_asset_from_cell(
                        asset_type=blueprint.asset_type,
                        cell=placed_cell,
                        dem_array=dem_array,
                        slope_array=slope_array,
                        transform=transform,
                        capacity_per_asset=capacity_per_generator if is_generator else 0,
                        is_generator=is_generator,
                    )
                    assets.append(asset)
                    used_mask[placed_cell] = True
            
            row_corridors.append(row_blocks)
        
        # Global assets (single control center / substation) - these are infrastructure, not generators
        global_asset_positions: list[tuple[int, int]] = []
        for blueprint in layout_config.global_assets:
            target_row = anchor_row - int(round(blueprint.offset_north_m / cell_size_m))
            target_col = anchor_col + int(round(blueprint.offset_east_m / cell_size_m))
            buildable_mask = buildable_masks.get(
                blueprint.asset_type,
                buildable_masks.get("substation"),
            )
            if buildable_mask is None:
                buildable_mask = next(iter(buildable_masks.values()))
            placed_cell = self._find_nearest_buildable_cell(
                asset_type=blueprint.asset_type,
                target_row=target_row,
                target_col=target_col,
                buildable_mask=buildable_mask,
                used_mask=used_mask,
                slope_array=slope_array,
            )
            if placed_cell is None:
                logger.warning(f"Block layout: failed to place {blueprint.asset_type}")
                continue
            # Global assets (control center, substation) are infrastructure, not generators
            asset = self._create_asset_from_cell(
                asset_type=blueprint.asset_type,
                cell=placed_cell,
                dem_array=dem_array,
                slope_array=slope_array,
                transform=transform,
                capacity_per_asset=0,
                is_generator=False,
            )
            assets.append(asset)
            used_mask[placed_cell] = True
            global_asset_positions.append(placed_cell)
        
        # Store block layout metadata for corridor road generation
        if assets:
            self._block_layout_metadata = {
                "anchor": (anchor_row, anchor_col),
                "block_centers": block_centers,
                "row_corridors": row_corridors,
                "global_asset_positions": global_asset_positions,
                "rows": actual_rows,
                "columns": actual_cols,
                "spacing_row_m": layout_config.spacing_row_m,
                "spacing_col_m": layout_config.spacing_col_m,
            }
            logger.info(
                f"Block layout placed {len(assets)} assets "
                f"({actual_rows}x{actual_cols} blocks)"
            )
        return assets if assets else None

    def _find_nearest_buildable_cell(
        self,
        asset_type: str,
        target_row: int,
        target_col: int,
        buildable_mask: Optional[np.ndarray],
        used_mask: np.ndarray,
        slope_array: np.ndarray,
        max_radius_cells: int = 60,
    ) -> Optional[tuple[int, int]]:
        """Find the best buildable cell near the target position.
        
        Balances proximity, slope, and suitability to find optimal placement.
        """
        if buildable_mask is None:
            return None
        
        height, width = buildable_mask.shape
        target_row = int(np.clip(target_row, 0, height - 1))
        target_col = int(np.clip(target_col, 0, width - 1))
        
        # Get suitability array for this asset type
        suitability = self._suitability_scores.get(asset_type)
        
        best_cell: Optional[tuple[int, int]] = None
        best_score = float("inf")
        
        for radius in range(1, max_radius_cells + 1):
            row_min = max(0, target_row - radius)
            row_max = min(height - 1, target_row + radius)
            col_min = max(0, target_col - radius)
            col_max = min(width - 1, target_col + radius)
            
            for r in range(row_min, row_max + 1):
                for c in range(col_min, col_max + 1):
                    if not buildable_mask[r, c]:
                        continue
                    if used_mask[r, c]:
                        continue
                    
                    slope = slope_array[r, c]
                    if slope > self.SLOPE_LIMITS.get(asset_type, 15.0):
                        continue
                    
                    distance = abs(r - target_row) + abs(c - target_col)
                    
                    # Score: lower is better
                    # - Distance penalty (want to stay close to target)
                    # - Slope penalty (prefer flat)
                    # - Suitability bonus (prefer high suitability)
                    suit_score = suitability[r, c] if suitability is not None else 0.5
                    score = (
                        distance * 0.5  # Reduced distance weight
                        + slope * 2.0   # Increased slope penalty
                        - suit_score * 30  # Suitability bonus (higher = better = lower score)
                    )
                    
                    if score < best_score:
                        best_score = score
                        best_cell = (r, c)
            
            # Don't return immediately - search the full radius for best quality
            # Only stop if we've found something good enough
            if best_cell is not None and radius >= 3:
                return best_cell
        
        return best_cell

    def _create_asset_from_cell(
        self,
        asset_type: str,
        cell: tuple[int, int],
        dem_array: np.ndarray,
        slope_array: np.ndarray,
        transform: Affine,
        capacity_per_asset: float,
        is_generator: bool = True,
    ) -> PlacedAsset:
        """Instantiate a PlacedAsset using raster cell metadata.
        
        Args:
            is_generator: If True, this asset generates power and its capacity_kw
                         counts toward the site's total generation capacity.
                         If False, it's storage/infrastructure and gets 0 capacity_kw.
        """
        row, col = cell
        x, y = xy(transform, row, col)
        elevation = float(dem_array[row, col])
        slope = float(slope_array[row, col])
        aspect = -1.0
        if self._aspect_array is not None:
            aspect = float(self._aspect_array[row, col])
        suitability = 1.0
        if asset_type in self._suitability_scores:
            suitability = float(self._suitability_scores[asset_type][row, col])
        
        config = self.ASSET_CONFIGS[asset_type]
        min_cap, max_cap = config["capacity_range"]
        
        if is_generator and max_cap > 0:
            # Generating asset: scale capacity based on target, clamped to profile's range
            variation = random.uniform(0.8, 1.2)
            target_cap = capacity_per_asset * variation
            final_capacity = max(min_cap, min(target_cap, max_cap))
        else:
            # Non-generating assets (battery, control center, cooling, substation)
            # These don't contribute to generation capacity
            # Battery's MW is discharge rate, not generation
            final_capacity = 0.0
        
        rotation = self._compute_optimal_rotation(asset_type, aspect)
        
        self._block_asset_counter += 1
        asset = PlacedAsset(
            asset_type=asset_type,
            name=f"{asset_type.replace('_', ' ').title()} {self._block_asset_counter}",
            position=Point(x, y),
            capacity_kw=round(final_capacity, 1),
            elevation_m=round(elevation, 1),
            slope_deg=round(slope, 1),
            aspect_deg=round(aspect, 1),
            suitability_score=round(suitability, 3),
            footprint_length_m=config["footprint"][0],
            footprint_width_m=config["footprint"][1],
            rotation_deg=rotation,
            grid_row=row,
            grid_col=col,
        )
        logger.info(f"Block asset placed: {asset_type} at slope {slope:.1f}°")
        return asset
    
    def _poisson_disk_sample(
        self,
        buildable_mask: np.ndarray,
        min_spacing_cells: int,
        num_candidates: int,
        k: int = 30,
    ) -> list[tuple[int, int]]:
        """
        Generate well-distributed candidate positions using Poisson-disk sampling.
        
        This produces more uniform spatial distribution than random sampling,
        avoiding both clustering and large gaps.
        
        Args:
            buildable_mask: Boolean mask of buildable areas
            min_spacing_cells: Minimum spacing between samples in cells
            num_candidates: Target number of candidates to generate
            k: Number of attempts before rejecting a point
            
        Returns:
            List of (row, col) positions
        """
        height, width = buildable_mask.shape
        cell_size = min_spacing_cells / np.sqrt(2)  # Grid cell size for acceleration
        
        # Initialize grid for spatial lookup
        grid_h = int(np.ceil(height / cell_size))
        grid_w = int(np.ceil(width / cell_size))
        grid = {}  # (grid_row, grid_col) -> (row, col)
        
        samples = []
        active = []
        
        # Find a valid starting point
        valid_positions = np.argwhere(buildable_mask)
        if len(valid_positions) == 0:
            return []
        
        # Start from a random valid position
        start_idx = random.randint(0, len(valid_positions) - 1)
        start = tuple(valid_positions[start_idx])
        samples.append(start)
        active.append(start)
        
        grid_key = (int(start[0] / cell_size), int(start[1] / cell_size))
        grid[grid_key] = start
        
        while active and len(samples) < num_candidates:
            # Pick a random active point
            idx = random.randint(0, len(active) - 1)
            point = active[idx]
            
            found = False
            for _ in range(k):
                # Generate random point in annulus around current point
                angle = random.uniform(0, 2 * np.pi)
                radius = random.uniform(min_spacing_cells, 2 * min_spacing_cells)
                
                new_row = int(point[0] + radius * np.sin(angle))
                new_col = int(point[1] + radius * np.cos(angle))
                
                # Check bounds
                if not (0 <= new_row < height and 0 <= new_col < width):
                    continue
                
                # Check buildable
                if not buildable_mask[new_row, new_col]:
                    continue
                
                # Check distance to existing samples using grid
                grid_r = int(new_row / cell_size)
                grid_c = int(new_col / cell_size)
                
                too_close = False
                for dr in range(-2, 3):
                    for dc in range(-2, 3):
                        neighbor_key = (grid_r + dr, grid_c + dc)
                        if neighbor_key in grid:
                            neighbor = grid[neighbor_key]
                            dist = np.sqrt((new_row - neighbor[0])**2 + (new_col - neighbor[1])**2)
                            if dist < min_spacing_cells:
                                too_close = True
                                break
                    if too_close:
                        break
                
                if not too_close:
                    new_point = (new_row, new_col)
                    samples.append(new_point)
                    active.append(new_point)
                    grid[(grid_r, grid_c)] = new_point
                    found = True
                    break
            
            if not found:
                active.pop(idx)
        
        return samples
    
    def _compute_optimal_rotation(self, asset_type: str, aspect_deg: float) -> float:
        """
        Compute optimal rotation angle for an asset based on terrain aspect.
        
        For solar arrays: align long axis perpendicular to slope direction
        (panels face downhill for optimal sun exposure in northern hemisphere)
        
        For other assets: no rotation (0°)
        
        Args:
            asset_type: Type of asset
            aspect_deg: Terrain aspect in degrees (0-360, clockwise from north)
            
        Returns:
            Rotation angle in degrees
        """
        if asset_type != "solar_array":
            return 0.0
        
        if aspect_deg < 0:  # Flat terrain
            return 0.0
        
        # For solar: rotate so long axis is perpendicular to aspect
        # This means panels face the downhill direction
        # Aspect is direction of steepest descent, so panels should face that way
        # Rotation is measured from east (0°) counterclockwise
        
        # Convert aspect (clockwise from north) to rotation angle
        # North (0°) -> panels face north, long axis E-W -> rotation 0°
        # East (90°) -> panels face east, long axis N-S -> rotation 90°
        # South (180°) -> panels face south (ideal), long axis E-W -> rotation 0°
        
        # Simplify: just align to nearest cardinal direction
        cardinal_rotations = {
            0: 0,      # North-facing
            90: 90,    # East-facing
            180: 0,    # South-facing (ideal)
            270: 90,   # West-facing
        }
        
        # Find nearest cardinal direction
        nearest = min(cardinal_rotations.keys(), key=lambda x: min(abs(aspect_deg - x), 360 - abs(aspect_deg - x)))
        
        return float(cardinal_rotations[nearest])
    
    def _find_best_position_enhanced(
        self,
        asset_type: str,
        buildable_mask: np.ndarray,
        slope_array: np.ndarray,
        dem_array: np.ndarray,
        transform: Affine,
        cell_size_m: float,
        placed_positions: list[tuple[int, int]],
        placed_footprints: list[Polygon],
        existing_assets: list[PlacedAsset],
        candidate_positions: Optional[list[tuple[int, int]]] = None,
    ) -> Optional[tuple[int, int]]:
        """
        Find the best position for an asset using enhanced scoring.
        
        Enhanced features (Phase E):
        - Uses pre-computed suitability scores when available
        - Considers actual footprint geometry for collision detection
        - Integrates aspect scoring for solar arrays
        - Uses Poisson-disk candidates when provided
        
        Args:
            asset_type: Type of asset to place
            buildable_mask: Boolean mask of buildable areas for this asset type
            slope_array: Slope data in degrees
            dem_array: Elevation data in meters
            transform: Rasterio affine transform
            cell_size_m: Cell size in meters
            placed_positions: List of already placed grid positions
            placed_footprints: List of already placed footprint polygons
            existing_assets: List of already placed assets
            candidate_positions: Optional pre-computed candidate positions (Poisson-disk)
            
        Returns:
            Best (row, col) position or None if no valid position found
        """
        height, width = slope_array.shape
        min_spacing = self.strategy_config.get("min_spacing_m", self.MIN_SPACING_M)
        # Ensure min_spacing_cells is at least 1 to avoid division by zero
        min_spacing_cells = max(1, int(min_spacing / cell_size_m))
        
        # Create exclusion mask from placed assets (cell-based for speed)
        exclusion_mask = np.zeros_like(buildable_mask)
        for r, c in placed_positions:
            r_min = max(0, r - min_spacing_cells)
            r_max = min(height, r + min_spacing_cells + 1)
            c_min = max(0, c - min_spacing_cells)
            c_max = min(width, c + min_spacing_cells + 1)
            exclusion_mask[r_min:r_max, c_min:c_max] = True
        
        # Get available positions
        available_mask = buildable_mask & ~exclusion_mask
        
        # Determine candidate positions from Poisson-disk or all available
        available_positions = np.argwhere(available_mask)
        
        if candidate_positions is not None and len(candidate_positions) > 0:
            # Filter Poisson-disk candidates to those still available
            filtered_list = []
            for pos in candidate_positions:
                if available_mask[pos[0], pos[1]]:
                    filtered_list.append(pos)
            if len(filtered_list) > 0:
                available_positions = np.array(filtered_list)
        
        if len(available_positions) == 0:
            return None
        
        # --- Substation placement: find flattest region centroid ---
        if asset_type == "substation" or len(existing_assets) == 0:
            return self._find_substation_position(
                available_positions=available_positions,
                available_mask=available_mask,
                slope_array=slope_array,
            )
        
        # --- Other assets: multi-factor scoring ---
        ref_asset = next(
            (a for a in existing_assets if a.asset_type == "substation"),
            existing_assets[0] if existing_assets else None
        )
        
        if ref_asset is None:
            idx = random.randint(0, len(available_positions) - 1)
            return tuple(available_positions[idx])
        
        ref_row = ref_asset.grid_row
        ref_col = ref_asset.grid_col
        
        # Compute individual scores for each candidate position
        rows = available_positions[:, 0]
        cols = available_positions[:, 1]
        
        # 1. Enhanced slope score with strong preference for flat terrain
        # Phase E: Aggressive scoring to push assets to flattest areas
        slopes = slope_array[rows, cols]
        max_slope = self.SLOPE_LIMITS.get(asset_type, 10.0)
        optimal_slope = self.SLOPE_OPTIMAL.get(asset_type, 5.0)
        
        # Use exponential decay - MUCH stronger penalty for higher slopes
        # Score = exp(-slope / optimal) gives ~0.37 at optimal, ~0.14 at 2x optimal
        slope_score = np.exp(-slopes / optimal_slope)
        
        # Additional hard penalty for slopes above optimal
        penalty = np.where(slopes > optimal_slope, 
                          (slopes - optimal_slope) / (max_slope - optimal_slope) * 0.3,
                          0)
        slope_score = np.clip(slope_score - penalty, 0, 1)
        
        # 2. Proximity score (closer to hub = higher score, but with distance cap)
        distances = np.sqrt((rows - ref_row) ** 2 + (cols - ref_col) ** 2)
        max_dist = np.max(distances) + 0.001
        # Phase E: Use softer proximity curve - don't penalize distant flat areas as much
        proximity_score = 1.0 - np.sqrt(distances / max_dist)  # Square root for softer falloff
        
        # 3. Suitability score (from pre-computed terrain analysis)
        if asset_type in self._suitability_scores:
            suitability = self._suitability_scores[asset_type][rows, cols]
            suitability_score = np.clip(suitability, 0, 1)
        else:
            # Phase E: If no suitability provided, derive from slope
            # This ensures terrain is always considered
            suitability_score = slope_score
        
        # 4. Aspect score for solar arrays (south-facing preferred)
        if asset_type == "solar_array" and self._aspect_array is not None:
            aspects = self._aspect_array[rows, cols]
            # South is 180°, score decreases with angular distance
            aspect_diff = np.abs(aspects - 180)
            aspect_diff = np.minimum(aspect_diff, 360 - aspect_diff)
            aspect_score = 1.0 - (aspect_diff / 180)
            # Flat areas (aspect < 0) get good score (they're flat!)
            aspect_score = np.where(aspects < 0, 0.8, aspect_score)
        else:
            aspect_score = np.ones(len(available_positions))
        
        # 5. Curvature penalty (if available) - penalize ridges/valleys
        curvature_score = np.ones(len(available_positions))
        if hasattr(self, '_curvature_array') and self._curvature_array is not None:
            curvatures = np.abs(self._curvature_array[rows, cols])
            # Penalize high curvature (ridges/valleys)
            curvature_score = 1.0 - np.clip(curvatures / 0.1, 0, 1)
        
        # Combine scores using strategy weights
        slope_weight = self.strategy_config.get("slope_weight", 0.65)
        proximity_weight = self.strategy_config.get("proximity_weight", 0.15)
        suitability_weight = self.strategy_config.get("suitability_weight", 0.20)
        
        # Normalize weights
        total_weight = slope_weight + proximity_weight + suitability_weight
        slope_weight /= total_weight
        proximity_weight /= total_weight
        suitability_weight /= total_weight
        
        # For solar, include aspect in suitability weight
        if asset_type == "solar_array":
            combined_suitability = 0.5 * suitability_score + 0.3 * aspect_score + 0.2 * curvature_score
        else:
            combined_suitability = 0.7 * suitability_score + 0.3 * curvature_score
        
        # Final combined score (higher = better)
        combined_score = (
            slope_weight * slope_score +
            proximity_weight * proximity_score +
            suitability_weight * combined_suitability
        )
        
        # Add small random noise to break ties and add variety
        combined_score += np.random.uniform(0, 0.005, size=len(combined_score))
        
        # Select best position
        best_idx = np.argmax(combined_score)
        return tuple(available_positions[best_idx])
    
    def _find_substation_position(
        self,
        available_positions: np.ndarray,
        available_mask: np.ndarray,
        slope_array: np.ndarray,
    ) -> Optional[tuple[int, int]]:
        """
        Find optimal substation position - MUST be on flattest terrain.
        
        Phase E: Enhanced to find the absolute flattest large area.
        Substations are critical infrastructure and need very level ground.
        """
        # Get slopes at all available positions
        rows = available_positions[:, 0]
        cols = available_positions[:, 1]
        slopes = slope_array[rows, cols]
        
        # Find the flattest 10% of positions
        slope_threshold = np.percentile(slopes, 10)
        flat_indices = np.where(slopes <= max(slope_threshold, 2.0))[0]
        
        if len(flat_indices) > 0:
            # Among the flattest positions, find the one closest to center of flat region
            flat_rows = rows[flat_indices]
            flat_cols = cols[flat_indices]
            centroid_row = np.mean(flat_rows)
            centroid_col = np.mean(flat_cols)
            
            # Pick the flat position closest to the centroid of flat area
            distances = np.sqrt(
                (flat_rows - centroid_row) ** 2 +
                (flat_cols - centroid_col) ** 2
            )
            best_flat_idx = flat_indices[np.argmin(distances)]
            
            logger.info(f"Substation: found flat area with slope <= {slope_threshold:.1f}°")
            return tuple(available_positions[best_flat_idx])
        
        # Fallback: just pick the absolute flattest position
        min_slope_idx = np.argmin(slopes)
        logger.warning(f"Substation: no flat area found, using min slope {slopes[min_slope_idx]:.1f}°")
        return tuple(available_positions[min_slope_idx])
    
    def _find_best_position(
        self,
        asset_type: str,
        buildable_mask: np.ndarray,
        slope_array: np.ndarray,
        dem_array: np.ndarray,
        transform: Affine,
        cell_size_m: float,
        placed_positions: list[tuple[int, int]],
        existing_assets: list[PlacedAsset],
    ) -> Optional[tuple[int, int]]:
        """
        Legacy method - delegates to enhanced version for backwards compatibility.
        """
        return self._find_best_position_enhanced(
            asset_type=asset_type,
            buildable_mask=buildable_mask,
            slope_array=slope_array,
            dem_array=dem_array,
            transform=transform,
            cell_size_m=cell_size_m,
            placed_positions=placed_positions,
            placed_footprints=[],
            existing_assets=existing_assets,
            candidate_positions=None,
        )
    
    def _select_asset_types(self, count: int) -> list[str]:
        """
        Select asset types based on configured weights.
        
        D-05: Adjusts weights based on strategy.
        """
        types = list(self.ASSET_CONFIGS.keys())
        
        # Get base weights from config
        base_weights = [self.ASSET_CONFIGS[t]["weight"] for t in types]
        
        # D-05: Adjust weights based on strategy
        solar_multiplier = self.strategy_config.get("solar_weight", 0.6) / 0.6  # Normalize to default
        
        weights = []
        for t, w in zip(types, base_weights):
            if t == "solar_array":
                weights.append(w * solar_multiplier)
            else:
                # Adjust other weights inversely
                weights.append(w / max(solar_multiplier, 0.5))
        
        # Normalize weights
        total = sum(weights)
        weights = [w / total for w in weights]
        
        return random.choices(types, weights=weights, k=count)
    
    def _generate_roads_terrain_aware(
        self,
        assets: list[PlacedAsset],
        slope_array: np.ndarray,
        transform: Affine,
        cell_size_m: float,
    ) -> list[PlacedRoad]:
        """
        Generate roads using slope-weighted pathfinding.
        
        Enhanced features (Phase E):
        - MST-based network topology (optional) for shorter total road length
        - Entry point integration for site access
        - Uses A* algorithm with slope-based cost function
        """
        if len(assets) < 2:
            return []
        
        roads = []
        
        # Find hub (substation or first asset)
        hub_asset = next(
            (a for a in assets if a.asset_type == "substation"),
            assets[0]
        )
        
        # Build cost surface from slope
        # Phase E: Enhanced cost surface with stronger slope penalties and allowance zones
        max_slope_for_road = np.degrees(np.arctan(self.MAX_ROAD_GRADE_PCT / 100))  # ~5.7° for 10%
        
        # Base cost: 1 + (slope / slope_limit)^3
        # This makes slopes below limit cheap, but cost skyrockets above it
        slope_ratio = slope_array / max_slope_for_road
        cost_surface = 1 + np.power(np.clip(slope_ratio, 0, 5), 3)
        
        # Curvature penalties (ridges/gullies)
        if getattr(self, '_curvature_array', None) is not None:
            curv = self._curvature_array
            # Ridge penalty (convex, >0): +2x surcharge for sharp ridges
            ridge_mask = curv > 0.05
            cost_surface[ridge_mask] *= (1 + curv[ridge_mask] * 20)  # Scale curvature to ~1-3x
            
            # Gully penalty (concave, <0): +1.5x surcharge
            gully_mask = curv < -0.05
            cost_surface[gully_mask] *= (1 + np.abs(curv[gully_mask]) * 10)

        # Allowance mask (reduces cost in designated zones, increases in avoidance zones)
        if getattr(self, '_allowance_mask', None) is not None:
            cost_surface *= self._allowance_mask
            
        # Make very steep slopes (>25°) finite but expensive (instead of infinite)
        # This allows crossing short steep sections if absolutely necessary
        cost_surface = np.where(
            slope_array > 25.0,
            10000.0,
            cost_surface
        )
        
        # Budget ceiling for pathfinding (equivalent to 500km of travel on flat ground)
        # This prevents infinite loops or extremely circuitous routes
        budget_ceiling = (500000.0 / cell_size_m) * 1.0  # 500km in cells
        
        # 1. Primary Spine: Entry -> Substation
        spine_roads = []
        if self._entry_point and hub_asset:
            try:
                start_row, start_col = rowcol(transform, self._entry_point.x, self._entry_point.y)
                height, width = cost_surface.shape
                
                if 0 <= start_row < height and 0 <= start_col < width:
                    spine_path, spine_cost = self._find_path_astar(
                        start=(start_row, start_col),
                        end=(hub_asset.grid_row, hub_asset.grid_col),
                        cost_surface=cost_surface,
                        budget_ceiling=budget_ceiling
                    )
                    
                    if spine_path:
                        spine_road = self._path_to_road(
                            path=spine_path,
                            cost=spine_cost,
                            name="Primary Spine",
                            road_class="spine",
                            transform=transform,
                            cell_size_m=cell_size_m,
                            slope_array=slope_array,
                        )
                        roads.append(spine_road)
                        spine_roads.append(spine_road)
                        logger.info(f"Generated spine road: {spine_road.length_m:.1f}m")
            except Exception as e:
                logger.warning(f"Failed to generate spine road: {e}")
        
        # Check if block layout was used - use corridor-based roads if so
        if self._block_layout_metadata:
            corridor_roads = self._generate_block_corridor_roads(
                assets=assets,
                hub_asset=hub_asset,
                cost_surface=cost_surface,
                slope_array=slope_array,
                transform=transform,
                cell_size_m=cell_size_m,
                budget_ceiling=budget_ceiling,
            )
            roads.extend(corridor_roads)
            logger.info(f"Generated {len(roads)} road segments (topology: block-corridor)")
            return roads
        
        # Check if we should use MST-based routing
        use_mst = self.strategy_config.get("use_mst_roads", False)
        
        if use_mst and len(assets) > 2:
            # Use Minimum Spanning Tree for road network
            mst_roads = self._generate_mst_roads(
                assets=assets,
                hub_asset=hub_asset,
                cost_surface=cost_surface,
                slope_array=slope_array,
                transform=transform,
                cell_size_m=cell_size_m,
                budget_ceiling=budget_ceiling,
                spine_roads=spine_roads,
            )
            roads.extend(mst_roads)
        else:
            # Use star topology (hub-and-spoke)
            star_roads = self._generate_star_roads(
                assets=assets,
                hub_asset=hub_asset,
                cost_surface=cost_surface,
                slope_array=slope_array,
                transform=transform,
                cell_size_m=cell_size_m,
                budget_ceiling=budget_ceiling,
            )
            roads.extend(star_roads)
        
        logger.info(f"Generated {len(roads)} road segments (topology: {'MST' if use_mst else 'star'})")
        return roads
    
    def _generate_star_roads(
        self,
        assets: list[PlacedAsset],
        hub_asset: PlacedAsset,
        cost_surface: np.ndarray,
        slope_array: np.ndarray,
        transform: Affine,
        cell_size_m: float,
        budget_ceiling: float = 50000.0,
    ) -> list[PlacedRoad]:
        """Generate roads using star (hub-and-spoke) topology."""
        roads = []
        other_assets = [a for a in assets if a is not hub_asset]
        
        for i, asset in enumerate(other_assets):
            road = self._create_road_segment(
                start_asset=hub_asset,
                end_asset=asset,
                cost_surface=cost_surface,
                slope_array=slope_array,
                transform=transform,
                cell_size_m=cell_size_m,
                road_name=f"Access Road {i + 1}",
                budget_ceiling=budget_ceiling,
            )
            if road:
                roads.append(road)
        
        return roads
    
    def _generate_block_corridor_roads(
        self,
        assets: list[PlacedAsset],
        hub_asset: PlacedAsset,
        cost_surface: np.ndarray,
        slope_array: np.ndarray,
        transform: Affine,
        cell_size_m: float,
        budget_ceiling: float = 50000.0,
    ) -> list[PlacedRoad]:
        """
        Generate roads using block corridor topology for structured layouts.
        
        Creates a grid-like road network:
        1. Main spine from entry point to center of block grid
        2. Row corridors connecting blocks in each row (east-west)
        3. Short spur roads from corridors to individual assets
        """
        roads = []
        meta = self._block_layout_metadata
        if not meta:
            return roads
        
        anchor_row, anchor_col = meta["anchor"]
        row_corridors = meta["row_corridors"]
        
        # 1. Main spine: Entry -> Anchor (center of block grid)
        if self._entry_point:
            try:
                entry_row, entry_col = rowcol(transform, self._entry_point.x, self._entry_point.y)
                height, width = cost_surface.shape
                
                if 0 <= entry_row < height and 0 <= entry_col < width:
                    spine_path, spine_cost = self._find_path_astar(
                        start=(entry_row, entry_col),
                        end=(anchor_row, anchor_col),
                        cost_surface=cost_surface,
                        budget_ceiling=budget_ceiling,
                    )
                    
                    if spine_path:
                        spine_road = self._path_to_road(
                            path=spine_path,
                            cost=spine_cost,
                            name="Main Corridor",
                            road_class="spine",
                            transform=transform,
                            cell_size_m=cell_size_m,
                            slope_array=slope_array,
                        )
                        roads.append(spine_road)
                        logger.info(f"Block corridor: Main spine {spine_road.length_m:.1f}m")
            except Exception as e:
                logger.warning(f"Block corridor: Failed to create main spine: {e}")
        
        # 2. Row corridors: Connect blocks within each row (east-west)
        for row_idx, row_blocks in enumerate(row_corridors):
            if len(row_blocks) < 2:
                continue
            
            # Sort blocks by column (east-west)
            sorted_blocks = sorted(row_blocks, key=lambda b: b[1])
            
            # Connect adjacent blocks in row
            for i in range(len(sorted_blocks) - 1):
                start_cell = sorted_blocks[i]
                end_cell = sorted_blocks[i + 1]
                
                try:
                    corridor_path, corridor_cost = self._find_path_astar(
                        start=start_cell,
                        end=end_cell,
                        cost_surface=cost_surface,
                        budget_ceiling=budget_ceiling,
                    )
                    
                    if corridor_path:
                        corridor_road = self._path_to_road(
                            path=corridor_path,
                            cost=corridor_cost,
                            name=f"Row {row_idx + 1} Corridor {i + 1}",
                            road_class="corridor",
                            transform=transform,
                            cell_size_m=cell_size_m,
                            slope_array=slope_array,
                        )
                        roads.append(corridor_road)
                except Exception as e:
                    logger.warning(f"Block corridor: Failed row {row_idx} segment {i}: {e}")
        
        # 3. Column corridors: Connect rows vertically (north-south)
        num_cols = meta.get("columns", 1)
        for col_idx in range(num_cols):
            # Gather block centers in this column
            col_blocks = []
            for row_idx, row_blocks in enumerate(row_corridors):
                if col_idx < len(row_blocks):
                    col_blocks.append(row_blocks[col_idx])
            
            if len(col_blocks) < 2:
                continue
            
            # Sort by row (north-south)
            sorted_col = sorted(col_blocks, key=lambda b: b[0])
            
            for i in range(len(sorted_col) - 1):
                start_cell = sorted_col[i]
                end_cell = sorted_col[i + 1]
                
                try:
                    col_path, col_cost = self._find_path_astar(
                        start=start_cell,
                        end=end_cell,
                        cost_surface=cost_surface,
                        budget_ceiling=budget_ceiling,
                    )
                    
                    if col_path:
                        col_road = self._path_to_road(
                            path=col_path,
                            cost=col_cost,
                            name=f"Column {col_idx + 1} Connector {i + 1}",
                            road_class="corridor",
                            transform=transform,
                            cell_size_m=cell_size_m,
                            slope_array=slope_array,
                        )
                        roads.append(col_road)
                except Exception as e:
                    logger.warning(f"Block corridor: Failed column {col_idx} segment {i}: {e}")
        
        # 4. Spur roads: Connect individual assets to nearest corridor node
        # Build set of corridor nodes (block centers)
        corridor_nodes = set(meta["block_centers"])
        
        for asset in assets:
            asset_cell = (asset.grid_row, asset.grid_col)
            
            # Skip if asset is already on a corridor node
            if asset_cell in corridor_nodes:
                continue
            
            # Find nearest corridor node
            min_dist = float('inf')
            nearest_node = None
            for node in corridor_nodes:
                dist = abs(asset_cell[0] - node[0]) + abs(asset_cell[1] - node[1])
                if dist < min_dist:
                    min_dist = dist
                    nearest_node = node
            
            if nearest_node is None or min_dist < 2:  # Skip very close assets
                continue
            
            try:
                spur_path, spur_cost = self._find_path_astar(
                    start=nearest_node,
                    end=asset_cell,
                    cost_surface=cost_surface,
                    budget_ceiling=budget_ceiling / 10,  # Lower budget for short spurs
                )
                
                if spur_path:
                    spur_road = self._path_to_road(
                        path=spur_path,
                        cost=spur_cost,
                        name=f"Spur to {asset.name}",
                        road_class="spur",
                        transform=transform,
                        cell_size_m=cell_size_m,
                        slope_array=slope_array,
                    )
                    roads.append(spur_road)
            except Exception as e:
                logger.debug(f"Block corridor: Failed spur to {asset.name}: {e}")
        
        logger.info(
            f"Block corridor roads: {len(roads)} segments "
            f"(spine + {len(row_corridors)} row corridors + {num_cols} col connectors + spurs)"
        )
        return roads
    
    def _generate_mst_roads(
        self,
        assets: list[PlacedAsset],
        hub_asset: PlacedAsset,
        cost_surface: np.ndarray,
        slope_array: np.ndarray,
        transform: Affine,
        cell_size_m: float,
        budget_ceiling: float = 50000.0,
        spine_roads: Optional[list[PlacedRoad]] = None,
    ) -> list[PlacedRoad]:
        """
        Generate roads using Minimum Spanning Tree topology.
        
        This minimizes total road length while ensuring all assets are connected.
        Uses Prim's algorithm with terrain-weighted distances.
        """
        roads = []
        n = len(assets)
        
        if n < 2:
            return roads
        
        # Build distance matrix (terrain-weighted)
        positions = np.array([[a.grid_row, a.grid_col] for a in assets])
        
        # Compute pairwise distances between assets
        dist_matrix = np.zeros((n, n))
        for i in range(n):
            for j in range(i + 1, n):
                # Euclidean distance in cells
                dist = np.sqrt(
                    (positions[i, 0] - positions[j, 0]) ** 2 +
                    (positions[i, 1] - positions[j, 1]) ** 2
                )
                # Add slope penalty (sample along straight line)
                r1, c1 = positions[i]
                r2, c2 = positions[j]
                num_samples = max(2, int(dist / 2))
                rows = np.linspace(r1, r2, num_samples).astype(int)
                cols = np.linspace(c1, c2, num_samples).astype(int)
                rows = np.clip(rows, 0, slope_array.shape[0] - 1)
                cols = np.clip(cols, 0, slope_array.shape[1] - 1)
                avg_slope = np.mean(slope_array[rows, cols])
                slope_penalty = 1 + (avg_slope / 10) ** 2
                
                dist_matrix[i, j] = dist * slope_penalty
                dist_matrix[j, i] = dist_matrix[i, j]
        
        # Find hub index
        hub_idx = next(i for i, a in enumerate(assets) if a is hub_asset)
        
        # Prim's algorithm
        # keys: min cost to connect to tree
        # parents: index of node to connect to (or -1 for spine)
        keys = [float('inf')] * n
        parents = [None] * n
        in_tree = [False] * n
        
        keys[hub_idx] = 0
        
        # Initialize with spine connections if available
        spine_connection_points = {}  # asset_idx -> (row, col) on spine
        
        if spine_roads:
            # Treat spine as part of the tree.
            # Any asset can connect to the spine if it's cheaper than connecting to hub
            # For simplicity, we'll assume spine geometry is available.
            # We need to find the "closest" point on the spine for each asset.
            # This is computationally expensive if we do full A*.
            # Approximation: find closest point on geometry, check slope penalty.
            
            spine_geom = unary_union([r.geometry for r in spine_roads])
            
            for i in range(n):
                if i == hub_idx:
                    continue
                    
                asset_pt = assets[i].position
                # Closest point on spine
                nearest_pt = spine_geom.interpolate(spine_geom.project(asset_pt))
                
                # Convert to grid
                try:
                    nr, nc = rowcol(transform, nearest_pt.x, nearest_pt.y)
                    ar, ac = positions[i]
                    
                    dist = np.sqrt((nr - ar)**2 + (nc - ac)**2)
                    # Basic slope penalty check (just endpoints and midpoint)
                    mr, mc = int((nr+ar)/2), int((nc+ac)/2)
                    
                    # Check bounds
                    if 0 <= nr < slope_array.shape[0] and 0 <= nc < slope_array.shape[1]:
                        avg_slope = (slope_array[ar, ac] + slope_array[nr, nc] + slope_array[mr, mc]) / 3
                        slope_penalty = 1 + (avg_slope / 10) ** 2
                        cost = dist * slope_penalty
                        
                        # Bias towards spine to create main arteries (0.8 factor)
                        cost *= 0.8
                        
                        if cost < keys[i]:
                            keys[i] = cost
                            parents[i] = -1  # Mark as connecting to spine
                            spine_connection_points[i] = (nr, nc)
                except Exception:
                    pass

        for _ in range(n):
            # Extract min
            u = -1
            min_val = float('inf')
            for i in range(n):
                if not in_tree[i] and keys[i] < min_val:
                    min_val = keys[i]
                    u = i
            
            if u == -1:
                break
                
            in_tree[u] = True
            
            # Create road if parent is defined
            parent = parents[u]
            if parent is not None:
                if parent == -1:
                    # Connect to spine
                    target_pos = spine_connection_points.get(u)
                    if target_pos:
                        # Create dummy asset for target
                        target_asset = PlacedAsset(
                            asset_type="spine_node", name="Spine",
                            position=Point(0,0), # Ignored by _create_road_segment if we passed coordinates, but we don't.
                            # Wait, _create_road_segment takes assets.
                            # I need to construct a temp asset or modify _create_road_segment.
                            # Easier: create a temporary asset object.
                            capacity_kw=0, grid_row=target_pos[0], grid_col=target_pos[1]
                        )
                        # Position point
                        tx, ty = xy(transform, target_pos[0], target_pos[1])
                        target_asset.position = Point(tx, ty)
                        
                        road = self._create_road_segment(
                            start_asset=target_asset, # From spine
                            end_asset=assets[u],      # To asset
                            cost_surface=cost_surface,
                            slope_array=slope_array,
                            transform=transform,
                            cell_size_m=cell_size_m,
                            road_name=f"Secondary Feed {u}",
                            budget_ceiling=budget_ceiling,
                        )
                        if road:
                            road.road_class = "secondary"
                            roads.append(road)
                else:
                    # Connect to another asset
                    road = self._create_road_segment(
                        start_asset=assets[parent],
                        end_asset=assets[u],
                        cost_surface=cost_surface,
                        slope_array=slope_array,
                        transform=transform,
                        cell_size_m=cell_size_m,
                        road_name=f"Access Road {u}",
                        budget_ceiling=budget_ceiling,
                    )
                    if road:
                        road.road_class = "tertiary"
                        roads.append(road)
            
            # Update neighbors
            for v in range(n):
                if not in_tree[v] and dist_matrix[u, v] < keys[v]:
                    keys[v] = dist_matrix[u, v]
                    parents[v] = u
        
        return roads
    
    def _path_to_road(
        self,
        path: list[tuple[int, int]],
        cost: float,
        name: str,
        road_class: str,
        transform: Affine,
        cell_size_m: float,
        slope_array: np.ndarray,
    ) -> PlacedRoad:
        """Convert a grid path to a PlacedRoad object with smoothing and stationing."""
        coords = []
        max_grade = 0.0

        for row, col in path:
            x, y = xy(transform, row, col)
            coords.append((x, y))
            grade = slope_array[row, col]
            max_grade = max(max_grade, grade)

        line = LineString(coords)

        # Smoothing (Douglas-Peucker)
        # Tolerance 1m. If geographic (degrees), convert 1m to degrees.
        is_geographic = abs(transform[0]) < 1.0
        tolerance = 1.0 if not is_geographic else 0.00001

        smoothed_line = line.simplify(tolerance, preserve_topology=True)

        length_factor = 111000 if is_geographic else 1.0
        length_m = smoothed_line.length * length_factor

        # Compute stationing
        stationing = []
        if hasattr(self, '_dem_array'):
            stationing = self._compute_stationing(smoothed_line, length_m, self._dem_array, transform)

        return PlacedRoad(
            name=name,
            geometry=smoothed_line,
            length_m=round(length_m, 1),
            width_m=5.0,
            max_grade_pct=round(np.tan(np.radians(max_grade)) * 100, 1),
            max_cumulative_cost=cost,
            road_class=road_class,
            stationing=stationing,
        )

    def _compute_stationing(
        self,
        line: LineString,
        length_m: float,
        dem_array: np.ndarray,
        transform: Affine,
        interval_m: float = 25.0
    ) -> list[dict]:
        """Compute stationing points along the road."""
        stations = []
        if length_m <= 0:
            return stations
            
        num_points = max(2, int(length_m / interval_m) + 1)
        
        for i in range(num_points):
            dist = i * interval_m
            if dist > length_m:
                dist = length_m
                
            # Get point along line (normalized distance 0-1)
            fraction = dist / length_m
            pt = line.interpolate(fraction, normalized=True)
            
            # Get elevation
            try:
                row, col = rowcol(transform, pt.x, pt.y)
                elev = 0.0
                if 0 <= row < dem_array.shape[0] and 0 <= col < dem_array.shape[1]:
                    elev = float(dem_array[row, col])
            except Exception:
                elev = 0.0
                
            stations.append({
                "station_m": round(dist, 1),
                "x": round(pt.x, 6),
                "y": round(pt.y, 6),
                "elevation_m": round(elev, 1),
            })
            
        # Calculate grades between stations
        for i in range(len(stations) - 1):
            s1 = stations[i]
            s2 = stations[i+1]
            dd = s2["station_m"] - s1["station_m"]
            dz = s2["elevation_m"] - s1["elevation_m"]
            grade = (dz / dd * 100) if dd > 0.1 else 0
            s1["grade_pct"] = round(grade, 1)
        
        if stations:
            stations[-1]["grade_pct"] = 0.0
            
        return stations
    
    def _create_road_segment(
        self,
        start_asset: PlacedAsset,
        end_asset: PlacedAsset,
        cost_surface: np.ndarray,
        slope_array: np.ndarray,
        transform: Affine,
        cell_size_m: float,
        road_name: str,
        budget_ceiling: float = 50000.0,
    ) -> Optional[PlacedRoad]:
        """Create a single road segment between two assets using A* pathfinding with retries."""
        
        for attempt in range(3):
            # Relax constraints on retries
            # Attempt 0: Strict (threshold 5000)
            # Attempt 1: Relaxed (threshold 10000)
            # Attempt 2: Very relaxed (threshold 20000)
            threshold = 5000.0 * (2 ** attempt)
            current_budget = budget_ceiling * (1 + attempt)
            
            path, cost = self._find_path_astar(
                start=(start_asset.grid_row, start_asset.grid_col),
                end=(end_asset.grid_row, end_asset.grid_col),
                cost_surface=cost_surface,
                budget_ceiling=current_budget,
                max_cost_threshold=threshold,
            )
            
            if path and len(path) >= 2:
                road = self._path_to_road(
                    path=path,
                    cost=cost,
                    name=road_name,
                    road_class="secondary" if "Access" in road_name else "tertiary",
                    transform=transform,
                    cell_size_m=cell_size_m,
                    slope_array=slope_array,
                )
                road.retry_count = attempt
                
                # Check KPIs
                flags = []
                if road.max_grade_pct > 10.0:
                    flags.append(f"Max grade {road.max_grade_pct:.1f}% > 10%")
                
                # Avg slope
                elevs = [p['elevation_m'] for p in road.stationing]
                if elevs:
                    total_climb = sum(abs(elevs[i+1]-elevs[i]) for i in range(len(elevs)-1))
                    avg_slope = (total_climb / road.length_m * 100) if road.length_m > 0 else 0
                    if avg_slope > 6.0:
                        flags.append(f"Avg slope {avg_slope:.1f}% > 6%")
                
                road.kpi_flags = flags
                return road
        
        # Fallback to direct line if A* fails
        logger.warning(f"A* failed for {road_name} after 3 attempts, using direct line")
        line = LineString([
            (start_asset.position.x, start_asset.position.y),
            (end_asset.position.x, end_asset.position.y)
        ])
        
        # Compute length in meters
        is_geographic = abs(transform[0]) < 1.0
        length_factor = 111000 if is_geographic else 1.0
        length_m = line.length * length_factor
        
        road = PlacedRoad(
            name=road_name,
            geometry=line,
            length_m=round(length_m, 1),
            width_m=5.0,
            road_class="tertiary",
            retry_count=3,
            failure_reason="Pathfinding failed",
            kpi_flags=["Pathfinding failed - using direct line"],
        )
        road.max_cumulative_cost = -1.0
        return road
    
    def _find_path_astar(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
        cost_surface: np.ndarray,
        max_iterations: int = 50000,
        budget_ceiling: float = 50000.0,
        max_cost_threshold: float = 5000.0,
    ) -> tuple[list[tuple[int, int]], float]:
        """
        Find lowest-cost path using A* algorithm with budget tracking.
            
        Returns:
            Tuple of (path, total_cost)
        """
        rows, cols = cost_surface.shape
        
        # Estimate average cost for heuristic scaling
        valid_costs = cost_surface[cost_surface < 100]
        avg_cost = np.median(valid_costs) if len(valid_costs) > 0 else 1.0
        
        # Heuristic: Euclidean distance scaled by average cost
        def heuristic(pos):
            dist = np.sqrt((pos[0] - end[0])**2 + (pos[1] - end[1])**2)
            return dist * avg_cost * 0.9  # Slightly underestimate for admissibility
        
        # Priority queue: (f_score, counter, g_score, position, path)
        counter = 0
        heap = [(heuristic(start), counter, 0, start, [start])]
        visited = set()
        iterations = 0
        
        # 8-connected neighbors
        neighbors = [(-1, 0), (1, 0), (0, -1), (0, 1),
                     (-1, -1), (-1, 1), (1, -1), (1, 1)]
        
        while heap and iterations < max_iterations:
            iterations += 1
            f_score, _, g_score, current, path = heapq.heappop(heap)
            
            if g_score > budget_ceiling:
                continue # Exceeded budget
            
            if current == end:
                logger.debug(f"A* found path in {iterations} iters, length {len(path)}, cost {g_score:.1f}")
                return path, g_score
            
            if current in visited:
                continue
            visited.add(current)
            
            for dr, dc in neighbors:
                nr, nc = current[0] + dr, current[1] + dc
                
                if 0 <= nr < rows and 0 <= nc < cols and (nr, nc) not in visited:
                    # Skip prohibitive cells entirely
                    if cost_surface[nr, nc] >= max_cost_threshold:
                        continue
                    
                    # Diagonal moves cost sqrt(2) times more
                    move_cost = 1.414 if (dr != 0 and dc != 0) else 1.0
                    step_cost = cost_surface[nr, nc] * move_cost
                    new_g = g_score + step_cost
                    new_f = new_g + heuristic((nr, nc))
                    
                    counter += 1
                    heapq.heappush(heap, (new_f, counter, new_g, (nr, nc), path + [(nr, nc)]))
        
        logger.warning(f"A* exhausted {iterations} iterations or budget from {start} to {end}")
        return [], 0.0
    
    def _compute_cut_fill(
        self,
        assets: list[PlacedAsset],
        roads: list[PlacedRoad],
        dem_array: np.ndarray,
        transform: Affine,
        cell_size_m: float,
    ) -> CutFillResult:
        """
        Compute cut/fill volumes for asset pads and road corridors.
        
        Enhanced (Phase E):
        - Calculates earthwork for both asset pads and road corridors
        - Reports separate volumes for assets vs roads
        - Includes net balance calculation
        """
        cell_area_m2 = cell_size_m ** 2
        total_cut = 0.0
        total_fill = 0.0
        per_asset = []
        
        height, width = dem_array.shape
        
        # --- Asset pad earthwork ---
        for asset in assets:
            config = self.ASSET_CONFIGS[asset.asset_type]
            pad_size_m = config["pad_size_m"]
            pad_size_cells = max(1, int(pad_size_m / cell_size_m))
            half_pad = pad_size_cells // 2
            
            row, col = asset.grid_row, asset.grid_col
            
            # Define pad extent
            r_min = max(0, row - half_pad)
            r_max = min(height, row + half_pad + 1)
            c_min = max(0, col - half_pad)
            c_max = min(width, col + half_pad + 1)
            
            # Get DEM within pad area
            pad_dem = dem_array[r_min:r_max, c_min:c_max]
            
            # Target elevation: use asset's elevation (center of pad)
            target_elev = asset.elevation_m
            
            # Calculate elevation differences
            dz = pad_dem - target_elev
            
            # Handle nodata
            valid_mask = pad_dem > -9000
            
            asset_cut = np.sum(dz[valid_mask & (dz > 0)]) * cell_area_m2
            asset_fill = np.sum(-dz[valid_mask & (dz < 0)]) * cell_area_m2
            
            total_cut += asset_cut
            total_fill += asset_fill
            
            per_asset.append({
                "asset_name": asset.name,
                "asset_type": asset.asset_type,
                "cut_m3": round(asset_cut, 1),
                "fill_m3": round(asset_fill, 1),
            })
        
        # --- Road corridor earthwork ---
        road_cut, road_fill, per_road = self._compute_road_earthwork(
            roads=roads,
            dem_array=dem_array,
            transform=transform,
            cell_size_m=cell_size_m,
        )
        
        logger.info(
            f"Cut/fill: assets cut={total_cut:.0f}m³, fill={total_fill:.0f}m³; "
            f"roads cut={road_cut:.0f}m³, fill={road_fill:.0f}m³"
        )
        
        return CutFillResult(
            cut_volume_m3=round(total_cut, 1),
            fill_volume_m3=round(total_fill, 1),
            road_cut_m3=round(road_cut, 1),
            road_fill_m3=round(road_fill, 1),
            per_asset=per_asset,
            per_road=per_road,
        )
    
    def _compute_road_earthwork(
        self,
        roads: list[PlacedRoad],
        dem_array: np.ndarray,
        transform: Affine,
        cell_size_m: float,
        road_width_m: float = 5.0,
    ) -> tuple[float, float, list[dict]]:
        """
        Compute cut/fill volumes for road corridors using buffer polygons.
        
        Calculates side-hill cut/fill by comparing ground elevation at each pixel
        in the corridor to the elevation of the nearest point on the centerline.
        """
        total_cut = 0.0
        total_fill = 0.0
        per_road = []
        
        from rasterio.features import rasterize
        height, width = dem_array.shape
        cell_area = cell_size_m ** 2
        
        for road in roads:
            if road.geometry is None or road.geometry.is_empty:
                continue
            
            # Skip extremely short roads
            if road.length_m < 1.0:
                continue
            
            # Create road corridor polygon
            # Buffer needs to be in coordinate units
            buffer_distance = road.width_m / 2.0
            if abs(transform[0]) < 1.0:
                # Convert meters to degrees (approx)
                buffer_distance /= 111000.0
                
            corridor = road.geometry.buffer(buffer_distance, cap_style=2) # Flat cap
            
            try:
                # Rasterize corridor to get mask
                mask = rasterize(
                    [(corridor, 1)],
                    out_shape=(height, width),
                    transform=transform,
                    fill=0,
                    dtype=np.uint8,
                ).astype(bool)
                
                # Get DEM pixels under road
                rows, cols = np.where(mask)
                if len(rows) == 0:
                    continue
            
                # Sample centerline densely for KDTree
                # Sampling interval: smaller of 1/2 cell size or 1m
                step = min(1.0, cell_size_m / 2.0)
                if abs(transform[0]) < 1.0:
                    step /= 111000.0
                
                # Generate sample points along centerline
                length_coord = road.geometry.length
                num_steps = int(length_coord / step) + 2
                sample_points = [road.geometry.interpolate(min(i * step, length_coord)) for i in range(num_steps)]
                
                # Get Ground Z for each sample point (Centerline Z)
                sample_coords = []
                sample_zs = []
                
                for p in sample_points:
                    sample_coords.append((p.x, p.y))
                    r, c = rowcol(transform, p.x, p.y)
                    z = 0.0
                    if 0 <= r < height and 0 <= c < width:
                        val = dem_array[r, c]
                        if val > -9000:
                            z = float(val)
                    sample_zs.append(z)
                
                # Build KDTree for 2D lookup
                if not sample_coords:
                    continue
            
                tree = cKDTree(sample_coords)
                
                # Get coordinates of all pixels in mask
                pixel_xs, pixel_ys = xy(transform, rows, cols)
                # xy returns tuple of lists/arrays. Ensure they are separate args to column_stack
                pixel_points = np.column_stack((pixel_xs, pixel_ys))
                
                # Find nearest centerline point for each pixel
                dists, indices = tree.query(pixel_points)
                
                # Target Z = Z of nearest centerline point (flat road cross-section)
                target_zs = np.array([sample_zs[i] for i in indices])
                
                # Actual Z = DEM at pixel
                actual_zs = dem_array[rows, cols]
                
                # Calculate volume
                diffs = actual_zs - target_zs
                valid = (actual_zs > -9000)
                
                road_cut = np.sum(diffs[valid & (diffs > 0)]) * cell_area
                road_fill = np.sum(-diffs[valid & (diffs < 0)]) * cell_area
                
                total_cut += road_cut
                total_fill += road_fill
                
                per_road.append({
                    "road_name": road.name,
                    "cut_m3": round(road_cut, 1),
                    "fill_m3": round(road_fill, 1),
                    "length_m": road.length_m
                })
                
            except Exception as e:
                logger.warning(f"Failed to compute earthwork for road {road.name}: {e}")
                continue
        
        return total_cut, total_fill, per_road
    
    @staticmethod
    def to_geojson_feature_collection(
        assets: list[PlacedAsset],
        roads: list[PlacedRoad],
        cut_fill: Optional[CutFillResult] = None,
    ) -> dict[str, Any]:
        """
        Convert assets and roads to a GeoJSON FeatureCollection.
        
        Returns a complete GeoJSON object for frontend display.
        Enhanced (Phase E) to include additional terrain metrics.
        """
        features = []
        
        # Add asset features with enhanced properties
        for asset in assets:
            feature = {
                "type": "Feature",
                "geometry": mapping(asset.position),
                "properties": {
                    "feature_type": "asset",
                    "asset_type": asset.asset_type,
                    "name": asset.name,
                    "capacity_kw": asset.capacity_kw,
                    "elevation_m": asset.elevation_m,
                    "slope_deg": asset.slope_deg,
                    "aspect_deg": asset.aspect_deg,
                    "suitability_score": asset.suitability_score,
                    "footprint_length_m": asset.footprint_length_m,
                    "footprint_width_m": asset.footprint_width_m,
                    "rotation_deg": asset.rotation_deg,
                },
            }
            features.append(feature)
        
        # Add road features
        for road in roads:
            feature = {
                "type": "Feature",
                "geometry": mapping(road.geometry),
                "properties": {
                    "feature_type": "road",
                    "name": road.name,
                    "length_m": road.length_m,
                    "width_m": road.width_m,
                    "max_grade_pct": road.max_grade_pct,
                    "road_class": road.road_class,
                    "stationing": road.stationing,
                    "kpi_flags": road.kpi_flags,
                    "retry_count": road.retry_count,
                    "failure_reason": road.failure_reason,
                    "cumulative_cost": road.max_cumulative_cost,
                },
            }
            features.append(feature)
        
        result = {
            "type": "FeatureCollection",
            "features": features,
        }
        
        # Add cut/fill summary as collection property (enhanced with road earthwork)
        if cut_fill:
            result["properties"] = {
                "cut_volume_m3": cut_fill.cut_volume_m3,
                "fill_volume_m3": cut_fill.fill_volume_m3,
                "road_cut_m3": cut_fill.road_cut_m3,
                "road_fill_m3": cut_fill.road_fill_m3,
                "total_cut_m3": cut_fill.total_cut_m3,
                "total_fill_m3": cut_fill.total_fill_m3,
                "net_balance_m3": cut_fill.net_balance_m3,
                "per_road_earthwork": cut_fill.per_road,
            }
        
        return result


class SimulatedAnnealingOptimizer:
    """
    Phase E: Local search optimization using simulated annealing.
    
    Refines initial layout placement by iteratively making small moves
    and accepting improvements (or occasional worse moves to escape local minima).
    
    Objectives (weighted):
    - Minimize total slope under assets
    - Minimize total road length
    - Maximize suitability scores
    - Balance cut/fill volumes
    """
    
    def __init__(
        self,
        initial_temp: float = 100.0,
        cooling_rate: float = 0.95,
        min_temp: float = 1.0,
        iterations_per_temp: int = 10,
    ):
        """
        Initialize the optimizer.
        
        Args:
            initial_temp: Starting temperature (higher = more exploration)
            cooling_rate: Temperature decay per iteration (0.9-0.99)
            min_temp: Stop when temperature drops below this
            iterations_per_temp: Moves to try at each temperature level
        """
        self.initial_temp = initial_temp
        self.cooling_rate = cooling_rate
        self.min_temp = min_temp
        self.iterations_per_temp = iterations_per_temp
    
    def optimize(
        self,
        assets: list[PlacedAsset],
        slope_array: np.ndarray,
        buildable_masks: dict[str, np.ndarray],
        transform: Affine,
        cell_size_m: float,
        suitability_scores: Optional[dict[str, np.ndarray]] = None,
        weights: Optional[dict[str, float]] = None,
    ) -> list[PlacedAsset]:
        """
        Optimize asset placement using simulated annealing.
        
        Args:
            assets: Initial asset placements
            slope_array: Slope data in degrees
            buildable_masks: Buildable area masks per asset type
            transform: Rasterio transform
            cell_size_m: Cell size in meters
            suitability_scores: Optional suitability score arrays
            weights: Optional objective weights
            
        Returns:
            Optimized list of PlacedAsset
        """
        if len(assets) < 2:
            return assets
        
        # Default weights
        weights = weights or {
            "slope": 0.3,
            "suitability": 0.3,
            "spacing": 0.2,
            "clustering": 0.2,
        }
        
        # Convert to mutable list of positions
        current_solution = [(a.grid_row, a.grid_col, a.asset_type) for a in assets]
        current_cost = self._evaluate_solution(
            current_solution, slope_array, buildable_masks, 
            suitability_scores, cell_size_m, weights
        )
        
        best_solution = current_solution.copy()
        best_cost = current_cost
        
        temperature = self.initial_temp
        height, width = slope_array.shape
        
        iterations = 0
        improvements = 0
        
        while temperature > self.min_temp:
            for _ in range(self.iterations_per_temp):
                iterations += 1
                
                # Generate neighbor solution (move one asset)
                neighbor = self._generate_neighbor(
                    current_solution, buildable_masks, height, width, cell_size_m
                )
                
                if neighbor is None:
                    continue
                
                neighbor_cost = self._evaluate_solution(
                    neighbor, slope_array, buildable_masks,
                    suitability_scores, cell_size_m, weights
                )
                
                # Accept or reject move
                delta = neighbor_cost - current_cost
                
                if delta < 0:
                    # Better solution - always accept
                    current_solution = neighbor
                    current_cost = neighbor_cost
                    improvements += 1
                    
                    if current_cost < best_cost:
                        best_solution = current_solution.copy()
                        best_cost = current_cost
                else:
                    # Worse solution - accept with probability based on temperature
                    acceptance_prob = math.exp(-delta / temperature)
                    if random.random() < acceptance_prob:
                        current_solution = neighbor
                        current_cost = neighbor_cost
            
            # Cool down
            temperature *= self.cooling_rate
        
        logger.info(
            f"Simulated annealing: {iterations} iterations, {improvements} improvements, "
            f"cost {best_cost:.2f} (initial: {current_cost:.2f})"
        )
        
        # Convert back to PlacedAsset list
        optimized_assets = []
        for i, (row, col, asset_type) in enumerate(best_solution):
            original = assets[i]
            x, y = xy(transform, row, col)
            
            optimized = PlacedAsset(
                asset_type=original.asset_type,
                name=original.name,
                position=Point(x, y),
                capacity_kw=original.capacity_kw,
                elevation_m=original.elevation_m,
                slope_deg=float(slope_array[row, col]),
                aspect_deg=original.aspect_deg,
                suitability_score=original.suitability_score,
                footprint_length_m=original.footprint_length_m,
                footprint_width_m=original.footprint_width_m,
                rotation_deg=original.rotation_deg,
                grid_row=row,
                grid_col=col,
            )
            optimized_assets.append(optimized)
        
        return optimized_assets
    
    def _evaluate_solution(
        self,
        solution: list[tuple[int, int, str]],
        slope_array: np.ndarray,
        buildable_masks: dict[str, np.ndarray],
        suitability_scores: Optional[dict[str, np.ndarray]],
        cell_size_m: float,
        weights: dict[str, float],
    ) -> float:
        """
        Evaluate a solution's cost (lower is better).
        
        Combines multiple objectives into a single scalar cost.
        """
        cost = 0.0
        
        # 1. Slope cost - sum of slopes at asset locations
        slope_cost = 0.0
        for row, col, asset_type in solution:
            slope_cost += slope_array[row, col]
        cost += weights.get("slope", 0.3) * slope_cost
        
        # 2. Suitability cost - inverse of suitability (lower suitability = higher cost)
        if suitability_scores:
            suit_cost = 0.0
            for row, col, asset_type in solution:
                if asset_type in suitability_scores:
                    suit_cost += (1.0 - suitability_scores[asset_type][row, col])
            cost += weights.get("suitability", 0.3) * suit_cost * 10  # Scale up
        
        # 3. Spacing cost - penalize assets too close together
        spacing_cost = 0.0
        min_spacing_cells = 15.0 / cell_size_m
        for i, (r1, c1, _) in enumerate(solution):
            for j, (r2, c2, _) in enumerate(solution):
                if i < j:
                    dist = math.sqrt((r1 - r2)**2 + (c1 - c2)**2)
                    if dist < min_spacing_cells:
                        spacing_cost += (min_spacing_cells - dist) ** 2
        cost += weights.get("spacing", 0.2) * spacing_cost
        
        # 4. Clustering cost - penalize spread-out layouts
        # (centroid distance)
        if len(solution) > 1:
            rows = [s[0] for s in solution]
            cols = [s[1] for s in solution]
            centroid_r = sum(rows) / len(rows)
            centroid_c = sum(cols) / len(cols)
            
            cluster_cost = sum(
                math.sqrt((r - centroid_r)**2 + (c - centroid_c)**2)
                for r, c, _ in solution
            ) / len(solution)
            cost += weights.get("clustering", 0.2) * cluster_cost * 0.1
        
        return cost
    
    def _generate_neighbor(
        self,
        solution: list[tuple[int, int, str]],
        buildable_masks: dict[str, np.ndarray],
        height: int,
        width: int,
        cell_size_m: float,
    ) -> Optional[list[tuple[int, int, str]]]:
        """
        Generate a neighbor solution by moving one asset.
        
        Returns None if no valid move is found.
        """
        # Pick random asset to move
        idx = random.randint(0, len(solution) - 1)
        row, col, asset_type = solution[idx]
        
        # Get buildable mask for this asset type
        mask = buildable_masks.get(asset_type, buildable_masks.get("solar_array"))
        
        # Try random moves
        move_distance = int(20 / cell_size_m)  # ~20m move
        
        for _ in range(10):  # Try up to 10 times
            dr = random.randint(-move_distance, move_distance)
            dc = random.randint(-move_distance, move_distance)
            
            new_row = row + dr
            new_col = col + dc
            
            # Check bounds
            if not (0 <= new_row < height and 0 <= new_col < width):
                continue
            
            # Check buildable
            if not mask[new_row, new_col]:
                continue
            
            # Check spacing from other assets
            min_spacing_cells = 10.0 / cell_size_m
            too_close = False
            for i, (r, c, _) in enumerate(solution):
                if i == idx:
                    continue
                dist = math.sqrt((new_row - r)**2 + (new_col - c)**2)
                if dist < min_spacing_cells:
                    too_close = True
                    break
            
            if too_close:
                continue
            
            # Valid move found
            neighbor = solution.copy()
            neighbor[idx] = (new_row, new_col, asset_type)
            return neighbor
        
        return None


def get_simulated_annealing_optimizer(
    initial_temp: float = 100.0,
    cooling_rate: float = 0.95,
) -> SimulatedAnnealingOptimizer:
    """Factory function to create optimizer with custom parameters."""
    return SimulatedAnnealingOptimizer(
        initial_temp=initial_temp,
        cooling_rate=cooling_rate,
    )
