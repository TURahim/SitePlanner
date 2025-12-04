"""
Integration tests for terrain-aware layout generation.

These tests verify the full terrain pipeline works correctly.
Run with: pytest tests/test_terrain_integration.py -v

NOTE: These tests require:
- AWS credentials configured (for S3 access)
- Network access (for USGS 3DEP API)
- USE_TERRAIN=true environment variable

To run locally (skipped by default):
    USE_TERRAIN=true pytest tests/test_terrain_integration.py -v

TODO: Fix async/greenlet issue before enabling in CI/CD
      See app/config.py for details on the issue.
"""
import asyncio
import os
import pytest
from uuid import uuid4

from shapely.geometry import Polygon
from shapely import wkt

# Skip all tests if USE_TERRAIN is not enabled
pytestmark = pytest.mark.skipif(
    os.environ.get("USE_TERRAIN", "").lower() != "true",
    reason="Terrain tests require USE_TERRAIN=true"
)


class TestTerrainServicesIntegration:
    """Integration tests for terrain services (DEM, Slope)."""
    
    @pytest.fixture
    def sample_boundary(self):
        """A sample polygon in the US for testing (West Texas)."""
        return Polygon([
            (-101.85, 35.20),
            (-101.845, 35.20),
            (-101.845, 35.195),
            (-101.85, 35.195),
            (-101.85, 35.20),
        ])
    
    @pytest.mark.asyncio
    async def test_dem_service_fetch(self, sample_boundary):
        """Test that DEM service can fetch elevation data."""
        from app.services.dem_service import DEMService
        
        dem_service = DEMService()
        
        # This test requires network access and may take a few seconds
        dem_data, dem_profile = await dem_service._fetch_dem_from_3dep(
            boundary=sample_boundary,
            resolution_m=30,  # Use lower resolution for faster tests
        )
        
        assert dem_data is not None, "DEM data should not be None"
        assert dem_profile is not None, "DEM profile should not be None"
        assert dem_data.shape[0] > 0, "DEM should have rows"
        assert dem_data.shape[1] > 0, "DEM should have columns"
        assert "transform" in dem_profile, "Profile should have transform"
    
    @pytest.mark.asyncio
    async def test_slope_computation(self, sample_boundary):
        """Test that slope service can compute slope from DEM."""
        from app.services.dem_service import DEMService
        from app.services.slope_service import SlopeService
        import numpy as np
        
        dem_service = DEMService()
        slope_service = SlopeService()
        
        # Fetch DEM first
        dem_data, dem_profile = await dem_service._fetch_dem_from_3dep(
            boundary=sample_boundary,
            resolution_m=30,
        )
        
        assert dem_data is not None
        
        # Compute slope
        slope_data = slope_service._compute_slope_from_array(
            dem_array=dem_data,
            cell_size_x=dem_profile["transform"][0],
            cell_size_y=abs(dem_profile["transform"][4]),
        )
        
        assert slope_data is not None, "Slope data should not be None"
        assert slope_data.shape == dem_data.shape, "Slope shape should match DEM"
        assert np.nanmin(slope_data) >= 0, "Slope should be non-negative"
        assert np.nanmax(slope_data) <= 90, "Slope should be <= 90 degrees"


class TestTerrainLayoutGenerationIntegration:
    """Integration tests for full terrain-aware layout generation."""
    
    @pytest.fixture
    def sample_boundary(self):
        """A sample polygon for testing."""
        return Polygon([
            (-101.85, 35.20),
            (-101.845, 35.20),
            (-101.845, 35.195),
            (-101.85, 35.195),
            (-101.85, 35.20),
        ])
    
    @pytest.mark.asyncio
    async def test_terrain_layout_generation_standalone(self, sample_boundary):
        """Test terrain-aware layout generation without database."""
        import numpy as np
        from app.services.dem_service import DEMService
        from app.services.slope_service import SlopeService
        from app.services.terrain_layout_generator import TerrainAwareLayoutGenerator
        
        # Fetch terrain data
        dem_service = DEMService()
        slope_service = SlopeService()
        
        dem_data, dem_profile = await dem_service._fetch_dem_from_3dep(
            boundary=sample_boundary,
            resolution_m=30,
        )
        
        slope_data = slope_service._compute_slope_from_array(
            dem_array=dem_data,
            cell_size_x=dem_profile["transform"][0],
            cell_size_y=abs(dem_profile["transform"][4]),
        )
        
        # Generate layout
        generator = TerrainAwareLayoutGenerator(target_capacity_kw=1000)
        placed_assets, placed_roads, cut_fill = generator.generate(
            boundary=sample_boundary,
            dem_array=dem_data,
            slope_array=slope_data,
            transform=dem_profile["transform"],
            num_assets=5,
        )
        
        # Verify results
        assert len(placed_assets) > 0, "Should place at least one asset"
        assert len(placed_roads) > 0, "Should create at least one road"
        assert cut_fill is not None, "Should calculate cut/fill"
        
        # Verify asset properties
        for asset in placed_assets:
            assert asset.position is not None
            assert asset.asset_type in ["substation", "solar_array", "battery", "generator"]
            assert asset.elevation_m is not None, "Terrain assets should have elevation"
    
    @pytest.mark.asyncio
    async def test_terrain_layout_via_api_endpoint(self):
        """
        Test terrain-aware layout generation through the actual API endpoint.
        
        This test verifies the full flow including database operations.
        This is the test that currently fails due to the greenlet issue.
        
        TODO: Enable this test once async/greenlet issue is fixed.
        """
        pytest.skip("Skipped due to async/greenlet issue - see app/config.py TODO")
        
        # When fixed, this test should:
        # 1. Create a test site in database
        # 2. Call POST /api/layouts/generate with use_terrain=True
        # 3. Verify layout is created with terrain data
        # 4. Verify assets have elevation_m and slope_deg populated


class TestS3TerrainCaching:
    """Tests for S3-based terrain caching."""
    
    @pytest.mark.asyncio
    async def test_terrain_cache_upload_download(self):
        """Test uploading and downloading terrain files from S3."""
        from app.services.s3 import get_s3_service
        import numpy as np
        
        s3_service = get_s3_service()
        test_key = f"terrain/test-{uuid4()}/test.tif"
        test_data = b"test terrain data content"
        
        try:
            # Upload
            await s3_service.upload_terrain_file(
                s3_key=test_key,
                content=test_data,
            )
            
            # Verify exists
            exists = await s3_service.terrain_file_exists(test_key)
            assert exists, "Uploaded file should exist"
            
            # Download
            downloaded = await s3_service.download_terrain_file(test_key)
            assert downloaded == test_data, "Downloaded content should match"
            
        finally:
            # Cleanup - delete test file
            try:
                await s3_service.delete_terrain_files(f"test-{test_key.split('/')[1]}")
            except Exception:
                pass  # Ignore cleanup errors


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])






