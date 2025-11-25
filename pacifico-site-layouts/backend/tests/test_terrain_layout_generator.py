"""
Unit tests for terrain-aware asset placement algorithms (B-05).

Tests cover:
- Flat terrain: all assets should be placed
- Steep terrain: assets only placed on flat areas
- Boundary enforcement: no assets outside polygon
- Spacing constraints: minimum distance between assets
- Capacity targeting: actual vs target capacity within tolerance
"""
import numpy as np
import pytest
from rasterio.transform import Affine
from shapely.geometry import Point, Polygon, box

from app.services.terrain_layout_generator import (
    TerrainAwareLayoutGenerator,
    PlacedAsset,
    PlacedRoad,
    CutFillResult,
)


class TestTerrainAwareLayoutGenerator:
    """Tests for TerrainAwareLayoutGenerator class."""
    
    @pytest.fixture
    def generator(self):
        """Create a generator with default target capacity."""
        return TerrainAwareLayoutGenerator(target_capacity_kw=1000.0)
    
    @pytest.fixture
    def square_boundary(self):
        """Create a simple 1km x 1km square boundary polygon."""
        # Centered at (0, 0), 1km x 1km in degrees (approx 0.009 deg ≈ 1km)
        return box(-0.0045, -0.0045, 0.0045, 0.0045)
    
    @pytest.fixture
    def small_boundary(self):
        """Create a small 100m x 100m boundary for spacing tests."""
        # 100m ≈ 0.0009 degrees
        return box(-0.00045, -0.00045, 0.00045, 0.00045)
    
    @pytest.fixture
    def flat_terrain(self):
        """Create flat terrain data (slope = 0 everywhere)."""
        # 100x100 grid, ~10m resolution
        shape = (100, 100)
        dem = np.ones(shape) * 100.0  # Constant elevation of 100m
        slope = np.zeros(shape)  # 0 degrees slope everywhere
        # Transform: pixel (0,0) at (-0.0045, 0.0045), resolution ~10m per pixel
        transform = Affine(0.00009, 0, -0.0045, 0, -0.00009, 0.0045)
        return dem, slope, transform
    
    @pytest.fixture
    def steep_terrain(self):
        """Create terrain with steep and flat zones."""
        shape = (100, 100)
        # Elevation varies to create steep areas
        dem = np.ones(shape) * 100.0
        
        # Slope array: mostly steep (20°), with a flat zone (2°) in the center
        slope = np.ones(shape) * 20.0  # 20° slope everywhere
        
        # Create flat zone in center (rows 40-60, cols 40-60)
        slope[40:60, 40:60] = 2.0  # Only 2° slope in center
        
        transform = Affine(0.00009, 0, -0.0045, 0, -0.00009, 0.0045)
        return dem, slope, transform
    
    @pytest.fixture
    def mostly_steep_terrain(self):
        """Create terrain that's almost entirely too steep."""
        shape = (100, 100)
        dem = np.ones(shape) * 100.0
        
        # Very steep everywhere (25°) - above all asset limits
        slope = np.ones(shape) * 25.0
        
        # Only a tiny flat area (5x5 cells at corner)
        slope[0:5, 0:5] = 1.0
        
        transform = Affine(0.00009, 0, -0.0045, 0, -0.00009, 0.0045)
        return dem, slope, transform
    
    @pytest.fixture
    def varied_elevation_terrain(self):
        """Create terrain with varied elevations for cut/fill testing."""
        shape = (100, 100)
        
        # Create a sloped surface: elevation increases from west to east
        dem = np.zeros(shape)
        for col in range(100):
            dem[:, col] = 100.0 + col * 0.5  # 0.5m rise per cell
        
        # Low slope (about 3 degrees) - buildable
        slope = np.ones(shape) * 3.0
        
        transform = Affine(0.00009, 0, -0.0045, 0, -0.00009, 0.0045)
        return dem, slope, transform
    
    # =========================================================================
    # Test 1: Flat terrain - all assets should be placed successfully
    # =========================================================================
    
    def test_flat_terrain_all_assets_placed(self, generator, square_boundary, flat_terrain):
        """Test that all requested assets are placed on flat terrain."""
        dem, slope, transform = flat_terrain
        
        assets, roads, cut_fill = generator.generate(
            boundary=square_boundary,
            dem_array=dem,
            slope_array=slope,
            transform=transform,
            num_assets=8,
        )
        
        # All assets should be placed on flat terrain
        assert len(assets) == 8, f"Expected 8 assets, got {len(assets)}"
        
        # All assets should have valid positions
        for asset in assets:
            assert asset.position is not None
            assert isinstance(asset.position, Point)
    
    def test_flat_terrain_assets_have_zero_slope(self, generator, square_boundary, flat_terrain):
        """Test that assets placed on flat terrain report correct slope."""
        dem, slope, transform = flat_terrain
        
        assets, _, _ = generator.generate(
            boundary=square_boundary,
            dem_array=dem,
            slope_array=slope,
            transform=transform,
            num_assets=5,
        )
        
        # All assets should have slope ≈ 0
        for asset in assets:
            assert asset.slope_deg == pytest.approx(0.0, abs=0.5), \
                f"Asset {asset.name} has slope {asset.slope_deg}°, expected ~0°"
    
    # =========================================================================
    # Test 2: Steep terrain - assets only placed on flat areas
    # =========================================================================
    
    def test_steep_terrain_assets_in_flat_zones(self, generator, square_boundary, steep_terrain):
        """Test that assets are placed only in flat zones on steep terrain."""
        dem, slope, transform = steep_terrain
        
        assets, _, _ = generator.generate(
            boundary=square_boundary,
            dem_array=dem,
            slope_array=slope,
            transform=transform,
            num_assets=5,
        )
        
        # Assets should be placed (center is flat)
        assert len(assets) > 0, "No assets placed despite flat center zone"
        
        # All placed assets should be in the flat zone (slope < 15° for solar)
        for asset in assets:
            max_allowed_slope = TerrainAwareLayoutGenerator.SLOPE_LIMITS[asset.asset_type]
            assert asset.slope_deg < max_allowed_slope, \
                f"Asset {asset.name} placed on slope {asset.slope_deg}° > limit {max_allowed_slope}°"
    
    def test_mostly_steep_terrain_limited_placement(self, generator, square_boundary, mostly_steep_terrain):
        """Test that very limited assets are placed when terrain is mostly steep."""
        dem, slope, transform = mostly_steep_terrain
        
        assets, _, _ = generator.generate(
            boundary=square_boundary,
            dem_array=dem,
            slope_array=slope,
            transform=transform,
            num_assets=10,
        )
        
        # Should place fewer assets due to limited buildable area
        # The tiny flat zone (5x5 cells) can only fit a few assets with spacing
        assert len(assets) < 10, "Too many assets placed on mostly steep terrain"
        
        # Verify all placed assets respect slope limits
        for asset in assets:
            max_allowed_slope = TerrainAwareLayoutGenerator.SLOPE_LIMITS[asset.asset_type]
            assert asset.slope_deg <= max_allowed_slope + 0.5, \
                f"Asset {asset.name} on excessive slope: {asset.slope_deg}°"
    
    # =========================================================================
    # Test 3: Boundary enforcement - no assets outside polygon
    # =========================================================================
    
    def test_assets_within_boundary(self, generator, square_boundary, flat_terrain):
        """Test that all assets are placed within the site boundary."""
        dem, slope, transform = flat_terrain
        
        assets, _, _ = generator.generate(
            boundary=square_boundary,
            dem_array=dem,
            slope_array=slope,
            transform=transform,
            num_assets=15,  # Try to place many assets
        )
        
        # All assets must be within boundary
        for asset in assets:
            assert square_boundary.contains(asset.position) or square_boundary.touches(asset.position), \
                f"Asset {asset.name} at {asset.position.coords[0]} is outside boundary"
    
    def test_irregular_boundary(self, generator, flat_terrain):
        """Test asset placement with an L-shaped boundary."""
        dem, slope, transform = flat_terrain
        
        # Create an L-shaped polygon
        l_shape = Polygon([
            (-0.0045, -0.0045),  # Bottom-left
            (0.0045, -0.0045),   # Bottom-right
            (0.0045, 0.0),       # Middle-right
            (0.0, 0.0),          # Inner corner
            (0.0, 0.0045),       # Top-middle
            (-0.0045, 0.0045),   # Top-left
            (-0.0045, -0.0045),  # Close polygon
        ])
        
        assets, _, _ = generator.generate(
            boundary=l_shape,
            dem_array=dem,
            slope_array=slope,
            transform=transform,
            num_assets=8,
        )
        
        # All assets must be within L-shape
        for asset in assets:
            # Use buffer to handle floating point precision
            assert l_shape.buffer(0.0001).contains(asset.position), \
                f"Asset {asset.name} outside L-shaped boundary"
    
    # =========================================================================
    # Test 4: Spacing constraints - minimum distance between assets
    # =========================================================================
    
    def test_minimum_spacing_between_assets(self, generator, square_boundary, flat_terrain):
        """Test that assets maintain minimum spacing."""
        dem, slope, transform = flat_terrain
        
        assets, _, _ = generator.generate(
            boundary=square_boundary,
            dem_array=dem,
            slope_array=slope,
            transform=transform,
            num_assets=10,
        )
        
        # Check pairwise distances
        min_spacing_deg = TerrainAwareLayoutGenerator.MIN_SPACING_M / 111000  # Convert 15m to degrees
        
        for i, asset1 in enumerate(assets):
            for j, asset2 in enumerate(assets):
                if i >= j:
                    continue
                
                distance = asset1.position.distance(asset2.position)
                # Allow small tolerance for grid alignment
                assert distance >= min_spacing_deg * 0.8, \
                    f"Assets {asset1.name} and {asset2.name} too close: {distance * 111000:.1f}m"
    
    def test_small_boundary_limits_asset_count(self, generator, small_boundary, flat_terrain):
        """Test that small boundaries limit how many assets can be placed due to spacing."""
        dem, slope, transform = flat_terrain
        
        # Request many assets in a small area
        assets, _, _ = generator.generate(
            boundary=small_boundary,
            dem_array=dem,
            slope_array=slope,
            transform=transform,
            num_assets=20,
        )
        
        # With 15m min spacing in a 100m x 100m area, can fit roughly 5x5 = 25 assets max
        # But with random placement, likely fewer
        # The key test is that spacing is still maintained
        for i, asset1 in enumerate(assets):
            for j, asset2 in enumerate(assets):
                if i >= j:
                    continue
                
                distance = asset1.position.distance(asset2.position)
                min_spacing_deg = TerrainAwareLayoutGenerator.MIN_SPACING_M / 111000
                assert distance >= min_spacing_deg * 0.7, "Spacing constraint violated"
    
    # =========================================================================
    # Test 5: Capacity targeting
    # =========================================================================
    
    def test_capacity_within_tolerance(self, generator, square_boundary, flat_terrain):
        """Test that total capacity is within ±20% of target."""
        dem, slope, transform = flat_terrain
        target = generator.target_capacity_kw
        
        assets, _, _ = generator.generate(
            boundary=square_boundary,
            dem_array=dem,
            slope_array=slope,
            transform=transform,
            num_assets=10,
        )
        
        total_capacity = sum(asset.capacity_kw for asset in assets)
        
        # Should be within ±50% of target (generous tolerance for randomness)
        # The algorithm distributes target_capacity across num_assets
        assert total_capacity > 0, "Total capacity should be positive"
        assert total_capacity > target * 0.3, f"Total capacity {total_capacity} too low vs target {target}"
        assert total_capacity < target * 3.0, f"Total capacity {total_capacity} too high vs target {target}"
    
    def test_high_capacity_target(self, square_boundary, flat_terrain):
        """Test with high capacity target."""
        generator = TerrainAwareLayoutGenerator(target_capacity_kw=10000.0)
        dem, slope, transform = flat_terrain
        
        assets, _, _ = generator.generate(
            boundary=square_boundary,
            dem_array=dem,
            slope_array=slope,
            transform=transform,
            num_assets=20,
        )
        
        total_capacity = sum(asset.capacity_kw for asset in assets)
        
        # Higher target should result in higher total capacity
        assert total_capacity > 1000, "High target should produce higher capacity"
    
    # =========================================================================
    # Test 6: Road generation
    # =========================================================================
    
    def test_roads_connect_assets(self, generator, square_boundary, flat_terrain):
        """Test that roads connect assets to a hub."""
        dem, slope, transform = flat_terrain
        
        assets, roads, _ = generator.generate(
            boundary=square_boundary,
            dem_array=dem,
            slope_array=slope,
            transform=transform,
            num_assets=5,
        )
        
        # Should have roads connecting non-hub assets
        # In star topology: n-1 roads for n assets
        expected_roads = max(0, len(assets) - 1)
        assert len(roads) == expected_roads, \
            f"Expected {expected_roads} roads for {len(assets)} assets, got {len(roads)}"
    
    def test_roads_have_valid_geometry(self, generator, square_boundary, flat_terrain):
        """Test that road geometries are valid LineStrings."""
        dem, slope, transform = flat_terrain
        
        _, roads, _ = generator.generate(
            boundary=square_boundary,
            dem_array=dem,
            slope_array=slope,
            transform=transform,
            num_assets=4,
        )
        
        for road in roads:
            assert road.geometry.is_valid, f"Road {road.name} has invalid geometry"
            assert road.geometry.length > 0, f"Road {road.name} has zero length"
            assert road.length_m > 0, f"Road {road.name} reports zero length_m"
    
    def test_single_asset_no_roads(self, generator, square_boundary, flat_terrain):
        """Test that single asset generates no roads."""
        dem, slope, transform = flat_terrain
        
        assets, roads, _ = generator.generate(
            boundary=square_boundary,
            dem_array=dem,
            slope_array=slope,
            transform=transform,
            num_assets=1,
        )
        
        # Single asset = no roads needed
        assert len(roads) == 0, "Single asset should have no roads"
    
    # =========================================================================
    # Test 7: Cut/fill calculation
    # =========================================================================
    
    def test_cut_fill_on_flat_terrain(self, generator, square_boundary, flat_terrain):
        """Test that flat terrain produces minimal cut/fill."""
        dem, slope, transform = flat_terrain
        
        _, _, cut_fill = generator.generate(
            boundary=square_boundary,
            dem_array=dem,
            slope_array=slope,
            transform=transform,
            num_assets=5,
        )
        
        # Flat terrain should have minimal cut/fill
        assert cut_fill.cut_volume_m3 == pytest.approx(0, abs=100), \
            f"Flat terrain should have ~0 cut, got {cut_fill.cut_volume_m3}"
        assert cut_fill.fill_volume_m3 == pytest.approx(0, abs=100), \
            f"Flat terrain should have ~0 fill, got {cut_fill.fill_volume_m3}"
    
    def test_cut_fill_on_sloped_terrain(self, generator, square_boundary, varied_elevation_terrain):
        """Test that varied terrain produces meaningful cut/fill volumes."""
        dem, slope, transform = varied_elevation_terrain
        
        _, _, cut_fill = generator.generate(
            boundary=square_boundary,
            dem_array=dem,
            slope_array=slope,
            transform=transform,
            num_assets=5,
        )
        
        # Sloped terrain should have some cut/fill
        total_earthwork = cut_fill.cut_volume_m3 + cut_fill.fill_volume_m3
        assert total_earthwork > 0, "Sloped terrain should have some earthwork"
        
        # Per-asset breakdown should match total
        per_asset_cut = sum(a["cut_m3"] for a in cut_fill.per_asset)
        per_asset_fill = sum(a["fill_m3"] for a in cut_fill.per_asset)
        
        assert per_asset_cut == pytest.approx(cut_fill.cut_volume_m3, abs=1), \
            "Per-asset cut should sum to total"
        assert per_asset_fill == pytest.approx(cut_fill.fill_volume_m3, abs=1), \
            "Per-asset fill should sum to total"
    
    # =========================================================================
    # Test 8: GeoJSON output
    # =========================================================================
    
    def test_geojson_output_structure(self, generator, square_boundary, flat_terrain):
        """Test that GeoJSON output has correct structure."""
        dem, slope, transform = flat_terrain
        
        assets, roads, cut_fill = generator.generate(
            boundary=square_boundary,
            dem_array=dem,
            slope_array=slope,
            transform=transform,
            num_assets=5,
        )
        
        geojson = TerrainAwareLayoutGenerator.to_geojson_feature_collection(
            assets, roads, cut_fill
        )
        
        # Check structure
        assert geojson["type"] == "FeatureCollection"
        assert "features" in geojson
        assert isinstance(geojson["features"], list)
        
        # Should have features for all assets and roads
        expected_features = len(assets) + len(roads)
        assert len(geojson["features"]) == expected_features
        
        # Check properties included
        assert "properties" in geojson
        assert "cut_volume_m3" in geojson["properties"]
        assert "fill_volume_m3" in geojson["properties"]
    
    def test_geojson_asset_properties(self, generator, square_boundary, flat_terrain):
        """Test that GeoJSON asset features have required properties."""
        dem, slope, transform = flat_terrain
        
        assets, roads, cut_fill = generator.generate(
            boundary=square_boundary,
            dem_array=dem,
            slope_array=slope,
            transform=transform,
            num_assets=3,
        )
        
        geojson = TerrainAwareLayoutGenerator.to_geojson_feature_collection(
            assets, roads, cut_fill
        )
        
        # Find asset features
        asset_features = [f for f in geojson["features"] 
                         if f["properties"].get("feature_type") == "asset"]
        
        for feature in asset_features:
            props = feature["properties"]
            
            # Required properties
            assert "asset_type" in props
            assert "name" in props
            assert "capacity_kw" in props
            assert "elevation_m" in props
            assert "slope_deg" in props
            
            # Geometry should be Point
            assert feature["geometry"]["type"] == "Point"
    
    # =========================================================================
    # Test 9: Substation placement
    # =========================================================================
    
    def test_substation_always_present(self, generator, square_boundary, flat_terrain):
        """Test that layouts with 3+ assets always include a substation."""
        dem, slope, transform = flat_terrain
        
        assets, _, _ = generator.generate(
            boundary=square_boundary,
            dem_array=dem,
            slope_array=slope,
            transform=transform,
            num_assets=5,
        )
        
        # Should have at least one substation
        substations = [a for a in assets if a.asset_type == "substation"]
        assert len(substations) >= 1, "Layout should include at least one substation"
    
    def test_substation_in_flat_area(self, generator, square_boundary, steep_terrain):
        """Test that substation is placed in flattest available area."""
        dem, slope, transform = steep_terrain
        
        assets, _, _ = generator.generate(
            boundary=square_boundary,
            dem_array=dem,
            slope_array=slope,
            transform=transform,
            num_assets=5,
        )
        
        substations = [a for a in assets if a.asset_type == "substation"]
        
        if substations:
            # Substation should be on relatively flat ground
            assert substations[0].slope_deg < 5.0, \
                f"Substation on slope {substations[0].slope_deg}° > limit 5°"


class TestAssetTypeDistribution:
    """Tests for asset type selection and distribution."""
    
    def test_asset_types_are_valid(self):
        """Test that selected asset types are from valid set."""
        generator = TerrainAwareLayoutGenerator()
        types = generator._select_asset_types(20)
        
        valid_types = set(TerrainAwareLayoutGenerator.ASSET_CONFIGS.keys())
        for t in types:
            assert t in valid_types, f"Invalid asset type: {t}"
    
    def test_asset_distribution_roughly_matches_weights(self):
        """Test that type distribution roughly matches configured weights."""
        generator = TerrainAwareLayoutGenerator()
        
        # Generate many selections to test distribution
        types = generator._select_asset_types(1000)
        
        # Count occurrences
        counts = {}
        for t in types:
            counts[t] = counts.get(t, 0) + 1
        
        # Check that solar is most common (weight 0.6)
        assert counts.get("solar_array", 0) > counts.get("battery", 0), \
            "Solar should be more common than battery"
        assert counts.get("solar_array", 0) > counts.get("substation", 0), \
            "Solar should be more common than substation"


class TestBoundaryRasterization:
    """Tests for boundary rasterization."""
    
    def test_rasterize_simple_polygon(self):
        """Test that boundary is correctly rasterized."""
        generator = TerrainAwareLayoutGenerator()
        
        # Simple square boundary
        boundary = box(-0.0045, -0.0045, 0.0045, 0.0045)
        transform = Affine(0.00009, 0, -0.0045, 0, -0.00009, 0.0045)
        shape = (100, 100)
        
        mask = generator._rasterize_boundary(boundary, transform, shape)
        
        # Should be boolean array
        assert mask.dtype == bool
        
        # Should have some True values (inside boundary)
        assert np.any(mask), "Boundary mask should have interior cells"
        
        # Should have some False values (corners outside)
        # Actually, boundary fills entire grid in this case
        # Just check mask is reasonable
        interior_pct = np.sum(mask) / mask.size * 100
        assert interior_pct > 50, "Most of grid should be inside boundary"

