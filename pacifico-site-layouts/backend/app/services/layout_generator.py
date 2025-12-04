"""
Layout generation service.

For MVP Phase A, generates dummy asset placement within site boundaries.
Phase B will implement terrain-aware placement.
"""
import logging
import random
from dataclasses import dataclass
from typing import Any

from shapely.geometry import LineString, Point, Polygon, mapping
from shapely.ops import unary_union

logger = logging.getLogger(__name__)


@dataclass
class PlacedAsset:
    """Represents a placed asset."""
    asset_type: str
    name: str
    position: Point
    capacity_kw: float
    footprint_length_m: float = 20.0
    footprint_width_m: float = 20.0


@dataclass
class PlacedRoad:
    """Represents a placed road."""
    name: str
    geometry: LineString
    length_m: float
    width_m: float = 5.0


class DummyLayoutGenerator:
    """
    Generates dummy layouts with random asset placement.
    
    For Phase A MVP - places assets in a grid pattern within the site boundary.
    Does not consider terrain or other constraints.
    """
    
    # Asset type configurations
    ASSET_CONFIGS = {
        "solar_array": {
            "capacity_range": (100, 500),  # kW per unit
            "weight": 0.6,  # Probability weight
            "footprint": (30, 20),  # length x width in meters
        },
        "battery": {
            "capacity_range": (50, 200),
            "weight": 0.2,
            "footprint": (15, 10),
        },
        "generator": {
            "capacity_range": (100, 300),
            "weight": 0.15,
            "footprint": (10, 8),
        },
        "substation": {
            "capacity_range": (500, 2000),
            "weight": 0.05,
            "footprint": (20, 15),
        },
        "wind_turbine": {
            "capacity_range": (1000, 5000),  # Phase 5: kW per turbine
            "weight": 0.0,  # Not selected by default
            "footprint": (60, 60),
        },
    }
    
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
        num_assets: int = 8,
    ) -> tuple[list[PlacedAsset], list[PlacedRoad]]:
        """
        Generate a dummy layout within the given boundary.
        
        Args:
            boundary: Site boundary as Shapely Polygon
            num_assets: Number of assets to place (default: 8)
            
        Returns:
            Tuple of (assets, roads) lists
        """
        if not boundary.is_valid:
            boundary = boundary.buffer(0)
        
        # Generate asset positions using grid within bbox
        assets = self._place_assets(boundary, num_assets)
        
        # Generate roads connecting assets
        roads = self._generate_roads(assets)
        
        return assets, roads
    
    def _place_assets(self, boundary: Polygon, num_assets: int) -> list[PlacedAsset]:
        """
        Place assets in a grid pattern within the boundary.
        
        Uses the bounding box to create a grid, then filters points
        that fall within the actual polygon.
        """
        assets = []
        
        # Get bounding box
        minx, miny, maxx, maxy = boundary.bounds
        
        # Calculate grid spacing to get approximately num_assets points
        width = maxx - minx
        height = maxy - miny
        
        # Estimate grid size (add buffer for points outside polygon)
        target_points = int(num_assets * 1.5)
        grid_size = max(2, int((target_points ** 0.5)))
        
        dx = width / (grid_size + 1)
        dy = height / (grid_size + 1)
        
        # Generate grid points
        candidate_points = []
        for i in range(1, grid_size + 1):
            for j in range(1, grid_size + 1):
                x = minx + i * dx
                y = miny + j * dy
                point = Point(x, y)
                
                # Check if point is inside polygon
                if boundary.contains(point):
                    candidate_points.append(point)
        
        # If we have too few points, try random placement
        attempts = 0
        while len(candidate_points) < num_assets and attempts < 100:
            x = random.uniform(minx, maxx)
            y = random.uniform(miny, maxy)
            point = Point(x, y)
            
            if boundary.contains(point):
                # Check minimum distance from existing points
                min_dist = min(
                    (point.distance(p) for p in candidate_points),
                    default=float('inf')
                )
                if min_dist > dx * 0.5:  # At least half grid spacing
                    candidate_points.append(point)
            
            attempts += 1
        
        # Select assets up to num_assets
        selected_points = candidate_points[:num_assets]
        
        # Assign asset types based on weights
        asset_types = self._select_asset_types(len(selected_points))
        
        # Calculate capacity per asset to reach target
        capacity_per_asset = self.target_capacity_kw / max(len(selected_points), 1)
        
        # Create placed assets
        for i, (point, asset_type) in enumerate(zip(selected_points, asset_types)):
            config = self.ASSET_CONFIGS[asset_type]
            
            # Randomize capacity within type's range, scaled to target
            base_capacity = random.uniform(*config["capacity_range"])
            scaled_capacity = base_capacity * (capacity_per_asset / 200)  # Normalize
            
            asset = PlacedAsset(
                asset_type=asset_type,
                name=f"{asset_type.replace('_', ' ').title()} {i + 1}",
                position=point,
                capacity_kw=round(scaled_capacity, 1),
                footprint_length_m=config["footprint"][0],
                footprint_width_m=config["footprint"][1],
            )
            assets.append(asset)
        
        logger.info(f"Placed {len(assets)} assets within boundary")
        return assets
    
    def _select_asset_types(self, count: int) -> list[str]:
        """
        Select asset types based on configured weights.
        
        Ensures at least one substation if count >= 3.
        """
        types = list(self.ASSET_CONFIGS.keys())
        weights = [self.ASSET_CONFIGS[t]["weight"] for t in types]
        
        # Random selection based on weights
        selected = random.choices(types, weights=weights, k=count)
        
        # Ensure at least one substation for larger layouts
        if count >= 3 and "substation" not in selected:
            selected[0] = "substation"
        
        return selected
    
    def _generate_roads(self, assets: list[PlacedAsset]) -> list[PlacedRoad]:
        """
        Generate simple roads connecting assets.
        
        Creates a main road connecting all assets in sequence,
        optimizing for shorter total distance.
        """
        if len(assets) < 2:
            return []
        
        roads = []
        
        # Find the substation (or first asset) as the hub
        hub_asset = next(
            (a for a in assets if a.asset_type == "substation"),
            assets[0]
        )
        
        # Sort other assets by distance from hub
        other_assets = [a for a in assets if a is not hub_asset]
        other_assets.sort(key=lambda a: hub_asset.position.distance(a.position))
        
        # Create a road from hub to each asset (star topology)
        # This is simpler than optimal routing but works for dummy data
        for i, asset in enumerate(other_assets):
            # Create LineString from hub to this asset
            line = LineString([hub_asset.position, asset.position])
            
            # Calculate length (approximate, in degrees - real length would need projection)
            # For dummy data, we'll estimate based on coordinate difference
            length_deg = line.length
            # Rough conversion: 1 degree ≈ 111km at equator
            # This is very approximate but fine for dummy data
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
    
    @staticmethod
    def to_geojson_feature_collection(
        assets: list[PlacedAsset],
        roads: list[PlacedRoad],
    ) -> dict[str, Any]:
        """
        Convert assets and roads to a GeoJSON FeatureCollection.
        
        Returns a complete GeoJSON object ready for frontend display.
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
                },
            }
            features.append(feature)
        
        return {
            "type": "FeatureCollection",
            "features": features,
        }

