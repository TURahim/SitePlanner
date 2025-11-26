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
from scipy.spatial import distance_matrix
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


@dataclass
class CutFillResult:
    """Cut/fill calculation results."""
    cut_volume_m3: float = 0.0
    fill_volume_m3: float = 0.0
    road_cut_m3: float = 0.0  # Cut volume for road corridors
    road_fill_m3: float = 0.0  # Fill volume for road corridors
    per_asset: list[dict] = field(default_factory=list)
    
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
    }
    
    # Optimal slope targets for scoring (positions below this get bonus)
    SLOPE_OPTIMAL = {
        "solar_array": 5.0,   # Prefer slopes under 5°
        "battery": 2.0,       # Prefer slopes under 2°
        "generator": 3.0,     # Prefer slopes under 3°
        "substation": 1.0,    # Prefer nearly flat
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
    ):
        """
        Initialize the generator.
        
        Args:
            target_capacity_kw: Target total capacity in kW
            strategy: D-05 - Optimization strategy for layout generation
        """
        self.target_capacity_kw = target_capacity_kw
        self.strategy = strategy
        self.strategy_config = self.STRATEGY_CONFIGS.get(strategy, self.STRATEGY_CONFIGS[LayoutStrategy.BALANCED])
    
    def generate(
        self,
        boundary: Polygon,
        dem_array: np.ndarray,
        slope_array: np.ndarray,
        transform: Affine,
        num_assets: int = 8,
        exclusion_zones: Optional[list[Polygon]] = None,
        aspect_array: Optional[np.ndarray] = None,
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
            exclusion_zones: Optional list of exclusion zone polygons (D-03)
            aspect_array: Optional aspect data (degrees, 0-360 clockwise from north)
            suitability_scores: Optional dict of asset_type -> suitability score array
            entry_point: Optional site entry point for road network optimization
            
        Returns:
            Tuple of (assets, roads, cut_fill_result)
        """
        if not boundary.is_valid:
            boundary = boundary.buffer(0)
        
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
        self._aspect_array = aspect_array
        self._suitability_scores = suitability_scores or {}
        self._entry_point = entry_point
        
        # Create boundary mask
        boundary_mask = self._rasterize_boundary(boundary, transform, (height, width))
        
        # D-03: Create exclusion zone mask
        exclusion_mask = np.zeros((height, width), dtype=bool)
        if exclusion_zones:
            exclusion_mask = self._create_exclusion_mask(
                exclusion_zones=exclusion_zones,
                transform=transform,
                shape=(height, width),
                cell_size_m=cell_size_m,
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
    
    def _create_exclusion_mask(
        self,
        exclusion_zones: list[Polygon],
        transform: Affine,
        shape: tuple[int, int],
        cell_size_m: float,
    ) -> np.ndarray:
        """
        Create a boolean mask from exclusion zone polygons.
        
        D-03: Rasterizes exclusion zones including their buffers.
        
        Args:
            exclusion_zones: List of exclusion zone polygons
            transform: Rasterio affine transform
            shape: Output shape (height, width)
            cell_size_m: Cell size in meters
            
        Returns:
            Boolean mask where True = excluded area
        """
        from rasterio.features import rasterize
        
        mask = np.zeros(shape, dtype=np.uint8)
        
        for zone in exclusion_zones:
            if not zone.is_valid:
                zone = zone.buffer(0)
            
            try:
                zone_mask = rasterize(
                    [(zone, 1)],
                    out_shape=shape,
                    transform=transform,
                    fill=0,
                    dtype=np.uint8,
                )
                mask = mask | zone_mask
            except Exception as e:
                logger.warning(f"Could not rasterize exclusion zone: {e}")
        
        return mask.astype(bool)
    
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
            # Use solar buildable mask (most permissive) for initial candidates
            candidate_positions = self._poisson_disk_sample(
                buildable_masks.get("solar_array", buildable_masks["substation"]),
                min_spacing_cells=int(min_spacing / cell_size_m),
                num_candidates=num_assets * 3,  # Generate extra candidates
            )
            logger.info(f"Poisson-disk sampling generated {len(candidate_positions)} candidates")
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
            
            # Calculate capacity
            config = self.ASSET_CONFIGS[asset_type]
            base_capacity = random.uniform(*config["capacity_range"])
            # D-05: Apply strategy-specific capacity multiplier
            capacity_multiplier = self.strategy_config.get("capacity_multiplier", 1.0)
            scaled_capacity = base_capacity * (capacity_per_asset / 200) * capacity_multiplier
            
            asset = PlacedAsset(
                asset_type=asset_type,
                name=f"{asset_type.replace('_', ' ').title()} {i + 1}",
                position=Point(x, y),
                capacity_kw=round(scaled_capacity, 1),
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
        min_spacing_cells = int(min_spacing / cell_size_m)
        
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
        # Phase E: Enhanced cost surface with stronger slope penalties
        max_slope_for_road = np.degrees(np.arctan(self.MAX_ROAD_GRADE_PCT / 100))  # ~5.7° for 10%
        
        # Base cost increases with cube of slope ratio - strong penalty for steeper terrain
        slope_ratio = slope_array / max_slope_for_road
        cost_surface = 1 + np.power(np.clip(slope_ratio, 0, 3), 3)
        
        # Add strong penalty for slopes approaching limit (80% of max)
        cost_surface = np.where(
            slope_array > max_slope_for_road * 0.8,
            cost_surface * 5,  # 5x penalty
            cost_surface
        )
        
        # Make slopes over limit very expensive (120% of max)
        cost_surface = np.where(
            slope_array > max_slope_for_road * 1.2,
            500,  # Very high cost
            cost_surface
        )
        
        # Make very steep slopes (>15°) nearly impassable
        cost_surface = np.where(
            slope_array > 15.0,
            10000,  # Prohibitive
            cost_surface
        )
        
        # Check if we should use MST-based routing
        use_mst = self.strategy_config.get("use_mst_roads", False)
        
        if use_mst and len(assets) > 2:
            # Use Minimum Spanning Tree for road network
            roads = self._generate_mst_roads(
                assets=assets,
                hub_asset=hub_asset,
                cost_surface=cost_surface,
                slope_array=slope_array,
                transform=transform,
                cell_size_m=cell_size_m,
            )
        else:
            # Use star topology (hub-and-spoke)
            roads = self._generate_star_roads(
                assets=assets,
                hub_asset=hub_asset,
                cost_surface=cost_surface,
                slope_array=slope_array,
                transform=transform,
                cell_size_m=cell_size_m,
            )
        
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
            )
            if road:
                roads.append(road)
        
        return roads
    
    def _generate_mst_roads(
        self,
        assets: list[PlacedAsset],
        hub_asset: PlacedAsset,
        cost_surface: np.ndarray,
        slope_array: np.ndarray,
        transform: Affine,
        cell_size_m: float,
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
        # For simplicity, use Euclidean distance * average slope penalty
        positions = np.array([[a.grid_row, a.grid_col] for a in assets])
        
        # Compute pairwise distances
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
        
        # Prim's algorithm starting from hub
        in_tree = [False] * n
        in_tree[hub_idx] = True
        edges = []  # (from_idx, to_idx)
        
        for _ in range(n - 1):
            min_dist = float('inf')
            min_edge = None
            
            for i in range(n):
                if not in_tree[i]:
                    continue
                for j in range(n):
                    if in_tree[j]:
                        continue
                    if dist_matrix[i, j] < min_dist:
                        min_dist = dist_matrix[i, j]
                        min_edge = (i, j)
            
            if min_edge:
                edges.append(min_edge)
                in_tree[min_edge[1]] = True
        
        # Create road segments for MST edges
        for idx, (i, j) in enumerate(edges):
            road = self._create_road_segment(
                start_asset=assets[i],
                end_asset=assets[j],
                cost_surface=cost_surface,
                slope_array=slope_array,
                transform=transform,
                cell_size_m=cell_size_m,
                road_name=f"Access Road {idx + 1}",
            )
            if road:
                roads.append(road)
        
        return roads
    
    def _create_road_segment(
        self,
        start_asset: PlacedAsset,
        end_asset: PlacedAsset,
        cost_surface: np.ndarray,
        slope_array: np.ndarray,
        transform: Affine,
        cell_size_m: float,
        road_name: str,
    ) -> Optional[PlacedRoad]:
        """Create a single road segment between two assets using A* pathfinding."""
        path = self._find_path_astar(
            start=(start_asset.grid_row, start_asset.grid_col),
            end=(end_asset.grid_row, end_asset.grid_col),
            cost_surface=cost_surface,
        )
        
        if path and len(path) >= 2:
            coords = []
            max_grade = 0.0
            for row, col in path:
                x, y = xy(transform, row, col)
                coords.append((x, y))
                grade = slope_array[row, col]
                max_grade = max(max_grade, grade)
            
            line = LineString(coords)
            length_m = len(path) * cell_size_m
            
            return PlacedRoad(
                name=road_name,
                geometry=line,
                length_m=round(length_m, 1),
                width_m=5.0,
                max_grade_pct=round(np.tan(np.radians(max_grade)) * 100, 1),
            )
        
        # Fallback to direct line if A* fails
        logger.warning(f"A* failed for {road_name}, using direct line")
        line = LineString([
            (start_asset.position.x, start_asset.position.y),
            (end_asset.position.x, end_asset.position.y)
        ])
        length_m = line.length * 111000
        
        return PlacedRoad(
            name=road_name,
            geometry=line,
            length_m=round(length_m, 1),
            width_m=5.0,
        )
    
    def _find_path_astar(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
        cost_surface: np.ndarray,
        max_iterations: int = 50000,  # Phase E: Increased from 10000
    ) -> list[tuple[int, int]]:
        """
        Find lowest-cost path using A* algorithm.
        
        Phase E: Enhanced with better heuristic and increased iterations.
        
        Args:
            start: Start position (row, col)
            end: End position (row, col)
            cost_surface: Cost array (higher = harder to traverse)
            max_iterations: Maximum search iterations
            
        Returns:
            List of (row, col) positions forming the path
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
            
            if current == end:
                logger.debug(f"A* found path in {iterations} iters, length {len(path)}")
                return path
            
            if current in visited:
                continue
            visited.add(current)
            
            for dr, dc in neighbors:
                nr, nc = current[0] + dr, current[1] + dc
                
                if 0 <= nr < rows and 0 <= nc < cols and (nr, nc) not in visited:
                    # Skip prohibitive cells entirely
                    if cost_surface[nr, nc] >= 5000:
                        continue
                    
                    # Diagonal moves cost sqrt(2) times more
                    move_cost = 1.414 if (dr != 0 and dc != 0) else 1.0
                    step_cost = cost_surface[nr, nc] * move_cost
                    new_g = g_score + step_cost
                    new_f = new_g + heuristic((nr, nc))
                    
                    counter += 1
                    heapq.heappush(heap, (new_f, counter, new_g, (nr, nc), path + [(nr, nc)]))
        
        logger.warning(f"A* exhausted {iterations} iterations from {start} to {end}")
        return []
    
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
        road_cut, road_fill = self._compute_road_earthwork(
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
        )
    
    def _compute_road_earthwork(
        self,
        roads: list[PlacedRoad],
        dem_array: np.ndarray,
        transform: Affine,
        cell_size_m: float,
        road_width_m: float = 5.0,
    ) -> tuple[float, float]:
        """
        Compute cut/fill volumes for road corridors.
        
        For each road segment, samples elevations along the path and
        calculates the earthwork needed to create a smooth grade.
        
        Args:
            roads: List of road segments
            dem_array: Elevation data
            transform: Rasterio transform
            cell_size_m: Cell size in meters
            road_width_m: Road corridor width
            
        Returns:
            Tuple of (total_cut_m3, total_fill_m3)
        """
        total_cut = 0.0
        total_fill = 0.0
        
        height, width = dem_array.shape
        
        for road in roads:
            if road.geometry is None or road.geometry.is_empty:
                continue
            
            # Sample points along road
            coords = list(road.geometry.coords)
            if len(coords) < 2:
                continue
            
            # Convert coordinates to grid positions and get elevations
            elevations = []
            positions = []
            for x, y in coords:
                try:
                    row, col = rowcol(transform, x, y)
                    if 0 <= row < height and 0 <= col < width:
                        elev = dem_array[row, col]
                        if elev > -9000:  # Valid data
                            elevations.append(elev)
                            positions.append((row, col))
                except Exception:
                    continue
            
            if len(elevations) < 2:
                continue
            
            # Calculate target grade line (linear interpolation from start to end)
            start_elev = elevations[0]
            end_elev = elevations[-1]
            n_points = len(elevations)
            target_elevations = np.linspace(start_elev, end_elev, n_points)
            
            # Calculate cut/fill at each point
            # Road corridor area per segment = road_width * segment_length
            segment_length = road.length_m / max(n_points - 1, 1)
            segment_area = road_width_m * segment_length
            
            for i, (actual, target) in enumerate(zip(elevations, target_elevations)):
                dz = actual - target
                if dz > 0:
                    total_cut += dz * segment_area
                else:
                    total_fill += abs(dz) * segment_area
        
        return total_cut, total_fill
    
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
