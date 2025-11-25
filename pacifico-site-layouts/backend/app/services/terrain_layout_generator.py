"""
Terrain-aware layout generation service.

Generates layouts respecting terrain constraints including:
- Slope-based buildable area filtering
- Asset type-specific slope limits
- Minimum spacing enforcement
- Optimized road routing

Replaces DummyLayoutGenerator from Phase A with real terrain analysis.
"""
import heapq
import logging
import random
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID

import numpy as np
from rasterio.transform import Affine, rowcol, xy
from shapely.geometry import LineString, Point, Polygon, mapping
from shapely.ops import unary_union

logger = logging.getLogger(__name__)


@dataclass
class PlacedAsset:
    """Represents a placed asset with terrain information."""
    asset_type: str
    name: str
    position: Point
    capacity_kw: float
    elevation_m: float = 0.0
    slope_deg: float = 0.0
    footprint_length_m: float = 20.0
    footprint_width_m: float = 20.0
    # Grid position for cut/fill
    grid_row: int = 0
    grid_col: int = 0


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
    per_asset: list[dict] = field(default_factory=list)


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
    SLOPE_LIMITS = {
        "solar_array": 15.0,
        "battery": 5.0,
        "generator": 5.0,
        "substation": 5.0,
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
    
    # Minimum spacing between assets in meters
    MIN_SPACING_M = 15.0
    
    # Maximum road grade (percent)
    MAX_ROAD_GRADE_PCT = 10.0
    
    def __init__(self, target_capacity_kw: float = 1000.0):
        """
        Initialize the generator.
        
        Args:
            target_capacity_kw: Target total capacity in kW
        """
        self.target_capacity_kw = target_capacity_kw
    
    def generate(
        self,
        boundary: Polygon,
        dem_array: np.ndarray,
        slope_array: np.ndarray,
        transform: Affine,
        num_assets: int = 8,
    ) -> tuple[list[PlacedAsset], list[PlacedRoad], CutFillResult]:
        """
        Generate a terrain-aware layout.
        
        Args:
            boundary: Site boundary as Shapely Polygon
            dem_array: Elevation data (meters)
            slope_array: Slope data (degrees)
            transform: Rasterio affine transform
            num_assets: Target number of assets
            
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
            cell_size_m = cell_size_x * 111000
        else:
            cell_size_m = cell_size_x
        
        logger.info(f"Grid: {width}x{height}, cell size: {cell_size_m:.1f}m")
        
        # Create boundary mask
        boundary_mask = self._rasterize_boundary(boundary, transform, (height, width))
        
        # Create buildable masks for each asset type
        buildable_masks = {}
        for asset_type, max_slope in self.SLOPE_LIMITS.items():
            # Buildable where slope is below limit AND within boundary
            mask = (slope_array < max_slope) & (slope_array >= 0) & boundary_mask
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
        
        Strategy:
        1. Find flattest area for substation (centroid of flat region)
        2. Place batteries/generators near substation
        3. Fill remaining capacity with solar arrays
        """
        assets = []
        placed_positions = []  # Track placed asset grid positions
        
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
        
        # Place each asset
        for i, asset_type in enumerate(asset_types):
            buildable_mask = buildable_masks[asset_type]
            
            # Find best position for this asset
            position = self._find_best_position(
                asset_type=asset_type,
                buildable_mask=buildable_mask,
                slope_array=slope_array,
                dem_array=dem_array,
                transform=transform,
                cell_size_m=cell_size_m,
                placed_positions=placed_positions,
                existing_assets=assets,
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
            
            # Calculate capacity
            config = self.ASSET_CONFIGS[asset_type]
            base_capacity = random.uniform(*config["capacity_range"])
            scaled_capacity = base_capacity * (capacity_per_asset / 200)
            
            asset = PlacedAsset(
                asset_type=asset_type,
                name=f"{asset_type.replace('_', ' ').title()} {i + 1}",
                position=Point(x, y),
                capacity_kw=round(scaled_capacity, 1),
                elevation_m=round(elevation, 1),
                slope_deg=round(slope, 1),
                footprint_length_m=config["footprint"][0],
                footprint_width_m=config["footprint"][1],
                grid_row=row,
                grid_col=col,
            )
            assets.append(asset)
        
        logger.info(f"Placed {len(assets)} assets within terrain constraints")
        return assets
    
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
        Find the best position for an asset.
        
        For substations: find centroid of flattest region
        For others: prefer flat areas near existing infrastructure
        """
        height, width = slope_array.shape
        min_spacing_cells = int(self.MIN_SPACING_M / cell_size_m)
        
        # Create exclusion mask from placed assets
        exclusion_mask = np.zeros_like(buildable_mask)
        for r, c in placed_positions:
            r_min = max(0, r - min_spacing_cells)
            r_max = min(height, r + min_spacing_cells + 1)
            c_min = max(0, c - min_spacing_cells)
            c_max = min(width, c + min_spacing_cells + 1)
            exclusion_mask[r_min:r_max, c_min:c_max] = True
        
        # Available positions
        available_mask = buildable_mask & ~exclusion_mask
        available_positions = np.argwhere(available_mask)
        
        if len(available_positions) == 0:
            return None
        
        if asset_type == "substation" or len(existing_assets) == 0:
            # Find flattest region centroid
            flat_mask = available_mask & (slope_array < 3.0)
            if np.sum(flat_mask) > 0:
                flat_positions = np.argwhere(flat_mask)
                # Use centroid of flat region
                centroid_row = int(np.mean(flat_positions[:, 0]))
                centroid_col = int(np.mean(flat_positions[:, 1]))
                # Find nearest available position to centroid
                distances = np.sqrt(
                    (available_positions[:, 0] - centroid_row) ** 2 +
                    (available_positions[:, 1] - centroid_col) ** 2
                )
                best_idx = np.argmin(distances)
                return tuple(available_positions[best_idx])
            else:
                # No very flat area, use position with lowest slope
                slopes_at_available = slope_array[available_mask]
                min_slope_idx = np.argmin(slopes_at_available)
                return tuple(available_positions[min_slope_idx])
        else:
            # For other assets, prefer positions near existing assets
            # but still prioritize flatness
            
            # Get reference point (first asset or substation)
            ref_asset = next(
                (a for a in existing_assets if a.asset_type == "substation"),
                existing_assets[0] if existing_assets else None
            )
            
            if ref_asset:
                ref_row, ref_col = ref_asset.grid_row, ref_asset.grid_col
                
                # Score: lower slope + closer to reference
                slopes = slope_array[available_positions[:, 0], available_positions[:, 1]]
                distances = np.sqrt(
                    (available_positions[:, 0] - ref_row) ** 2 +
                    (available_positions[:, 1] - ref_col) ** 2
                )
                
                # Normalize and combine scores (lower is better)
                slope_score = slopes / (np.max(slopes) + 0.001)
                dist_score = distances / (np.max(distances) + 0.001)
                
                # Weight: 60% slope, 40% proximity
                combined_score = 0.6 * slope_score + 0.4 * dist_score
                
                best_idx = np.argmin(combined_score)
                return tuple(available_positions[best_idx])
            else:
                # Random from available
                idx = random.randint(0, len(available_positions) - 1)
                return tuple(available_positions[idx])
    
    def _select_asset_types(self, count: int) -> list[str]:
        """Select asset types based on configured weights."""
        types = list(self.ASSET_CONFIGS.keys())
        weights = [self.ASSET_CONFIGS[t]["weight"] for t in types]
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
        
        Uses A* algorithm with slope-based cost function.
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
        # Cost increases with slope, becomes prohibitive above max grade
        max_slope_for_road = np.degrees(np.arctan(self.MAX_ROAD_GRADE_PCT / 100))
        cost_surface = 1 + (slope_array / max_slope_for_road) ** 2
        cost_surface = np.where(
            slope_array > max_slope_for_road * 1.5,
            1000,  # Near-prohibitive
            cost_surface
        )
        
        # Connect each asset to hub
        other_assets = [a for a in assets if a is not hub_asset]
        
        for i, asset in enumerate(other_assets):
            path = self._find_path_astar(
                start=(hub_asset.grid_row, hub_asset.grid_col),
                end=(asset.grid_row, asset.grid_col),
                cost_surface=cost_surface,
            )
            
            if path:
                # Convert grid path to coordinates
                coords = []
                max_grade = 0.0
                for row, col in path:
                    x, y = xy(transform, row, col)
                    coords.append((x, y))
                    grade = slope_array[row, col]
                    max_grade = max(max_grade, grade)
                
                if len(coords) >= 2:
                    line = LineString(coords)
                    
                    # Calculate length in meters
                    length_m = len(path) * cell_size_m
                    
                    road = PlacedRoad(
                        name=f"Access Road {i + 1}",
                        geometry=line,
                        length_m=round(length_m, 1),
                        width_m=5.0,
                        max_grade_pct=round(np.tan(np.radians(max_grade)) * 100, 1),
                    )
                    roads.append(road)
            else:
                # Fallback to direct line if pathfinding fails
                line = LineString([
                    (hub_asset.position.x, hub_asset.position.y),
                    (asset.position.x, asset.position.y)
                ])
                length_deg = line.length
                length_m = length_deg * 111000
                
                road = PlacedRoad(
                    name=f"Access Road {i + 1}",
                    geometry=line,
                    length_m=round(length_m, 1),
                    width_m=5.0,
                )
                roads.append(road)
        
        logger.info(f"Generated {len(roads)} road segments")
        return roads
    
    def _find_path_astar(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
        cost_surface: np.ndarray,
        max_iterations: int = 10000,
    ) -> list[tuple[int, int]]:
        """
        Find lowest-cost path using A* algorithm.
        
        Args:
            start: Start position (row, col)
            end: End position (row, col)
            cost_surface: Cost array (higher = harder to traverse)
            max_iterations: Maximum search iterations
            
        Returns:
            List of (row, col) positions forming the path
        """
        rows, cols = cost_surface.shape
        
        # Heuristic: Euclidean distance
        def heuristic(pos):
            return np.sqrt((pos[0] - end[0])**2 + (pos[1] - end[1])**2)
        
        # Priority queue: (f_score, g_score, position, path)
        heap = [(heuristic(start), 0, start, [start])]
        visited = set()
        iterations = 0
        
        # 8-connected neighbors
        neighbors = [(-1, 0), (1, 0), (0, -1), (0, 1),
                     (-1, -1), (-1, 1), (1, -1), (1, 1)]
        
        while heap and iterations < max_iterations:
            iterations += 1
            f_score, g_score, current, path = heapq.heappop(heap)
            
            if current == end:
                return path
            
            if current in visited:
                continue
            visited.add(current)
            
            for dr, dc in neighbors:
                nr, nc = current[0] + dr, current[1] + dc
                
                if 0 <= nr < rows and 0 <= nc < cols and (nr, nc) not in visited:
                    # Diagonal moves cost sqrt(2) times more
                    move_cost = 1.414 if (dr != 0 and dc != 0) else 1.0
                    step_cost = cost_surface[nr, nc] * move_cost
                    new_g = g_score + step_cost
                    new_f = new_g + heuristic((nr, nc))
                    
                    heapq.heappush(heap, (new_f, new_g, (nr, nc), path + [(nr, nc)]))
        
        logger.warning(f"A* pathfinding did not find path in {iterations} iterations")
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
        Compute cut/fill volumes for asset pads.
        
        For each asset, calculates the volume of earth that needs to be
        cut (excavated) or filled to create a level pad.
        """
        cell_area_m2 = cell_size_m ** 2
        total_cut = 0.0
        total_fill = 0.0
        per_asset = []
        
        height, width = dem_array.shape
        
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
            # Positive dz = existing is higher than target = CUT
            # Negative dz = existing is lower than target = FILL
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
        
        logger.info(f"Cut/fill: cut={total_cut:.0f}m³, fill={total_fill:.0f}m³")
        
        return CutFillResult(
            cut_volume_m3=round(total_cut, 1),
            fill_volume_m3=round(total_fill, 1),
            per_asset=per_asset,
        )
    
    @staticmethod
    def to_geojson_feature_collection(
        assets: list[PlacedAsset],
        roads: list[PlacedRoad],
        cut_fill: Optional[CutFillResult] = None,
    ) -> dict[str, Any]:
        """
        Convert assets and roads to a GeoJSON FeatureCollection.
        
        Returns a complete GeoJSON object for frontend display.
        """
        features = []
        
        # Add asset features
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
                    "footprint_length_m": asset.footprint_length_m,
                    "footprint_width_m": asset.footprint_width_m,
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
        
        # Add cut/fill summary as collection property
        if cut_fill:
            result["properties"] = {
                "cut_volume_m3": cut_fill.cut_volume_m3,
                "fill_volume_m3": cut_fill.fill_volume_m3,
            }
        
        return result

