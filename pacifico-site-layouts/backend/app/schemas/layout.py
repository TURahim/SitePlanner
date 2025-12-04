"""
Pydantic schemas for Layout API endpoints.

D-05: Added variant generation support with multiple optimization strategies.
Generation Profiles: Added support for different asset mixes (solar, gas+bess, wind, hybrid).
"""
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.config import get_settings
from app.services.generation_profiles import GenerationProfile, get_profile_info

# Get terrain default from config (environment-specific)
_settings = get_settings()


# =============================================================================
# D-05: Layout Variant Strategies
# =============================================================================


class LayoutStrategy(str, Enum):
    """Layout optimization strategies (D-05)."""
    BALANCED = "balanced"
    DENSITY = "density"
    LOW_EARTHWORK = "low_earthwork"
    CLUSTERED = "clustered"


class StrategyInfo(BaseModel):
    """Information about a layout strategy."""
    strategy: LayoutStrategy
    name: str
    description: str


# Strategy metadata for frontend
STRATEGY_INFO_LIST = [
    StrategyInfo(
        strategy=LayoutStrategy.BALANCED,
        name="Balanced",
        description="Balance capacity, earthwork, and access roads",
    ),
    StrategyInfo(
        strategy=LayoutStrategy.DENSITY,
        name="High Density",
        description="Maximize capacity per hectare",
    ),
    StrategyInfo(
        strategy=LayoutStrategy.LOW_EARTHWORK,
        name="Low Earthwork",
        description="Minimize grading and cut/fill volumes",
    ),
    StrategyInfo(
        strategy=LayoutStrategy.CLUSTERED,
        name="Clustered",
        description="Group assets tightly to minimize infrastructure",
    ),
]


class GenerateLayoutRequest(BaseModel):
    """Request schema for layout generation."""
    
    site_id: UUID = Field(..., description="ID of the site to generate layout for")
    target_capacity_kw: float = Field(
        default=1000.0,
        ge=100,
        le=5_000_000,
        description="Target total capacity in kW (supports up to 5 GW microgrids)",
    )
    use_terrain: bool = Field(
        default=_settings.use_terrain,  # From config: USE_TERRAIN env var
        description="Use terrain-aware placement (Phase B). Set False for dummy placement.",
    )
    dem_resolution_m: int = Field(
        default=10,
        ge=10,
        le=30,
        description="DEM resolution in meters (10 or 30). Only used if use_terrain=True.",
    )
    # Generation Profile: Asset mix selection
    generation_profile: GenerationProfile = Field(
        default=GenerationProfile.SOLAR_FARM,
        description="Generation profile determining asset mix (solar_farm, gas_bess, wind_hybrid, hybrid)",
    )
    # D-05: Variant generation options
    generate_variants: bool = Field(
        default=False,
        description="D-05: Generate multiple layout variants with different strategies",
    )
    variant_strategies: Optional[list[LayoutStrategy]] = Field(
        default=None,
        description="D-05: Strategies to use (defaults to all 4 if generate_variants=True)",
    )


# =============================================================================
# Generation Profiles
# =============================================================================


class ProfileInfo(BaseModel):
    """Information about a generation profile."""
    profile: str
    name: str
    description: str
    asset_types: list[str]
    has_block_layout: bool = False


class BlockLayoutInfo(BaseModel):
    """Information about structured block layout used in generation."""
    rows: int = Field(..., description="Number of block rows")
    columns: int = Field(..., description="Number of block columns")
    total_blocks: int = Field(..., description="Total number of blocks placed")
    profile_name: str = Field(..., description="Name of the generation profile used")


class ProfilesResponse(BaseModel):
    """Response for available generation profiles."""
    profiles: list[ProfileInfo]


class AssetResponse(BaseModel):
    """Response schema for an asset."""
    
    id: UUID
    asset_type: str
    name: Optional[str] = None
    capacity_kw: Optional[float] = None
    position: dict[str, Any] = Field(..., description="Position as GeoJSON Point")
    elevation_m: Optional[float] = Field(None, description="Ground elevation in meters")
    slope_deg: Optional[float] = Field(None, description="Terrain slope in degrees")
    footprint_length_m: Optional[float] = Field(None, description="Footprint length (N-S) in meters")
    footprint_width_m: Optional[float] = Field(None, description="Footprint width (E-W) in meters")
    # D-02: Per-asset cut/fill volumes (P1)
    cut_m3: Optional[float] = Field(None, description="Cut volume for asset pad grading (m³)")
    fill_m3: Optional[float] = Field(None, description="Fill volume for asset pad grading (m³)")
    # Phase E: Enhanced terrain metrics
    aspect_deg: Optional[float] = Field(None, description="Terrain aspect (slope direction) in degrees, 0-360 clockwise from north")
    suitability_score: Optional[float] = Field(None, description="Composite terrain suitability score (0-1, higher is better)")
    rotation_deg: Optional[float] = Field(None, description="Optimal footprint rotation in degrees")
    
    class Config:
        from_attributes = True


class RoadResponse(BaseModel):
    """Response schema for a road."""
    
    id: UUID
    name: Optional[str] = None
    length_m: Optional[float] = None
    width_m: Optional[float] = Field(5.0, description="Road width in meters")
    geometry: dict[str, Any] = Field(..., description="Geometry as GeoJSON LineString")
    max_grade_pct: Optional[float] = Field(None, description="Maximum grade along road (%)")
    
    # Enhanced road metrics
    road_class: Optional[str] = Field(None, description="Road hierarchy class (spine, secondary, tertiary)")
    parent_segment_id: Optional[UUID] = Field(None, description="ID of the parent road segment")
    avg_grade_pct: Optional[float] = Field(None, description="Average grade (%)")
    max_cumulative_cost: Optional[float] = Field(None, description="Maximum cumulative cost to reach this segment")
    kpi_flags: Optional[dict[str, Any]] = Field(None, description="KPI flags raised for this road")
    stationing_json: Optional[dict[str, Any]] = Field(None, description="Detailed stationing data (chainage, elev, etc.)")
    
    class Config:
        from_attributes = True


class LayoutResponse(BaseModel):
    """Response schema for a layout."""
    
    id: UUID
    site_id: UUID
    status: str
    total_capacity_kw: Optional[float] = None
    cut_volume_m3: Optional[float] = None
    fill_volume_m3: Optional[float] = None
    # Phase E: Enhanced earthwork metrics
    road_cut_m3: Optional[float] = Field(None, description="Cut volume for road corridors (m³)")
    road_fill_m3: Optional[float] = Field(None, description="Fill volume for road corridors (m³)")
    total_cut_m3: Optional[float] = Field(None, description="Total cut volume including roads (m³)")
    total_fill_m3: Optional[float] = Field(None, description="Total fill volume including roads (m³)")
    net_earthwork_m3: Optional[float] = Field(None, description="Net earthwork balance (positive = excess cut)")
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class LayoutDetailResponse(LayoutResponse):
    """Detailed response including assets and roads."""
    
    assets: list[AssetResponse] = []
    roads: list[RoadResponse] = []


class LayoutGenerateResponse(BaseModel):
    """Response schema for layout generation."""
    
    layout: LayoutResponse
    assets: list[AssetResponse]
    roads: list[RoadResponse]
    geojson: dict[str, Any] = Field(
        ...,
        description="Complete layout as GeoJSON FeatureCollection",
    )
    block_layout_info: Optional[BlockLayoutInfo] = Field(
        None,
        description="Information about structured block layout, if used",
    )


class LayoutListItem(BaseModel):
    """Summary schema for layout listing."""
    
    id: UUID
    site_id: UUID
    status: str
    total_capacity_kw: Optional[float] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class LayoutListResponse(BaseModel):
    """Response schema for layout listing."""
    
    layouts: list[LayoutListItem]
    total: int


# =============================================================================
# Phase C: Async Layout Generation Schemas
# =============================================================================


class LayoutEnqueueResponse(BaseModel):
    """Response schema for layout generation job enqueue (C-03)."""
    
    layout_id: UUID = Field(..., description="ID of the queued layout")
    status: str = Field(
        default="queued",
        description="Initial status of the layout job"
    )
    message: str = Field(
        default="Layout generation job queued successfully",
        description="Confirmation message"
    )
    
    class Config:
        from_attributes = True


class LayoutGenerationStage(str, Enum):
    """Stages of layout generation for progress tracking (Phase 4 GAP)."""
    QUEUED = "queued"              # Job in queue
    FETCHING_DEM = "fetching_dem"  # Downloading DEM data
    COMPUTING_SLOPE = "computing_slope"  # Computing slope raster
    ANALYZING_TERRAIN = "analyzing_terrain"  # Terrain analysis (curvature, suitability)
    PLACING_ASSETS = "placing_assets"  # Asset placement
    GENERATING_ROADS = "generating_roads"  # Road network generation
    COMPUTING_EARTHWORK = "computing_earthwork"  # Cut/fill calculation
    FINALIZING = "finalizing"      # Saving to database
    COMPLETED = "completed"        # Done
    FAILED = "failed"              # Error


# Stage progress percentages for progress bar
STAGE_PROGRESS = {
    LayoutGenerationStage.QUEUED: 0,
    LayoutGenerationStage.FETCHING_DEM: 10,
    LayoutGenerationStage.COMPUTING_SLOPE: 25,
    LayoutGenerationStage.ANALYZING_TERRAIN: 40,
    LayoutGenerationStage.PLACING_ASSETS: 55,
    LayoutGenerationStage.GENERATING_ROADS: 70,
    LayoutGenerationStage.COMPUTING_EARTHWORK: 85,
    LayoutGenerationStage.FINALIZING: 95,
    LayoutGenerationStage.COMPLETED: 100,
    LayoutGenerationStage.FAILED: -1,
}


class LayoutStatusResponse(BaseModel):
    """Response schema for layout status polling (C-04, enhanced Phase 4 GAP)."""
    
    layout_id: UUID = Field(..., description="ID of the layout")
    status: str = Field(
        ...,
        description="Current status: queued, processing, completed, or failed"
    )
    error_message: Optional[str] = Field(
        None,
        description="Error message if status is 'failed'"
    )
    
    # Phase 4 (GAP): Progress tracking
    stage: Optional[str] = Field(
        None,
        description="Current generation stage (e.g., 'fetching_dem', 'placing_assets')"
    )
    progress_pct: Optional[int] = Field(
        None,
        ge=0,
        le=100,
        description="Progress percentage (0-100)"
    )
    stage_message: Optional[str] = Field(
        None,
        description="Human-readable message about current stage"
    )
    
    # Populated only when status is 'completed'
    total_capacity_kw: Optional[float] = Field(None, description="Total capacity in kW")
    asset_count: Optional[int] = Field(None, description="Number of assets placed")
    road_length_m: Optional[float] = Field(None, description="Total road length in meters")
    cut_volume_m3: Optional[float] = Field(None, description="Cut volume in cubic meters")
    fill_volume_m3: Optional[float] = Field(None, description="Fill volume in cubic meters")
    
    class Config:
        from_attributes = True


# =============================================================================
# D-05: Layout Variants Schemas
# =============================================================================


class LayoutVariantMetrics(BaseModel):
    """Metrics for a single layout variant (D-05)."""
    
    layout_id: UUID
    strategy: LayoutStrategy
    strategy_name: str
    total_capacity_kw: float
    asset_count: int
    road_length_m: float
    cut_volume_m3: float
    fill_volume_m3: float
    net_earthwork_m3: float = Field(..., description="cut - fill (positive = export)")
    capacity_per_hectare: Optional[float] = Field(None, description="kW per hectare")


class VariantComparison(BaseModel):
    """
    Comparison analysis across variants (D-05).
    
    Identifies which variant is "best" for each metric category.
    """
    
    best_capacity_id: UUID = Field(..., description="Variant with highest total capacity")
    best_earthwork_id: UUID = Field(..., description="Variant with lowest net earthwork")
    best_road_network_id: UUID = Field(..., description="Variant with shortest total roads")
    metrics_table: list[LayoutVariantMetrics] = Field(
        ..., description="Metrics for each variant in comparison table"
    )


class LayoutVariantResponse(BaseModel):
    """
    Single variant in a multi-variant response (D-05).
    
    Includes the strategy used and full layout data.
    """
    
    strategy: LayoutStrategy
    strategy_name: str
    layout: LayoutResponse
    assets: list[AssetResponse]
    roads: list[RoadResponse]
    geojson: dict[str, Any]


class LayoutVariantsResponse(BaseModel):
    """
    Response for multi-variant layout generation (D-05).
    
    Contains multiple layout variants with comparison analysis.
    """
    
    site_id: UUID
    variants: list[LayoutVariantResponse]
    comparison: VariantComparison
    
    class Config:
        from_attributes = True


class LayoutStrategiesResponse(BaseModel):
    """Response for available layout strategies (D-05)."""
    
    strategies: list[StrategyInfo]


# =============================================================================
# Phase 3 (GAP): Asset Manipulation Schemas
# =============================================================================


class AssetMoveRequest(BaseModel):
    """Request schema for moving an asset (Phase 3 GAP)."""
    
    position: dict = Field(
        ...,
        description="New position as GeoJSON Point {type: 'Point', coordinates: [lng, lat]}",
    )
    recompute_local: bool = Field(
        default=True,
        description="Re-evaluate slope and suitability at new position",
    )
    
    @property
    def longitude(self) -> float:
        """Extract longitude from GeoJSON position."""
        coords = self.position.get("coordinates", [0, 0])
        return coords[0] if len(coords) >= 2 else 0.0
    
    @property
    def latitude(self) -> float:
        """Extract latitude from GeoJSON position."""
        coords = self.position.get("coordinates", [0, 0])
        return coords[1] if len(coords) >= 2 else 0.0


class AssetMoveResponse(BaseModel):
    """Response schema for asset move (Phase 3 GAP)."""
    
    asset: AssetResponse
    message: str
    warnings: list[str] = Field(default_factory=list, description="Validation warnings")


class RecomputeRoadsRequest(BaseModel):
    """Request schema for recomputing roads (Phase 3 GAP)."""
    
    dem_resolution_m: int = Field(
        default=10,
        ge=10,
        le=30,
        description="DEM resolution for terrain data",
    )


class RecomputeRoadsResponse(BaseModel):
    """Response schema for roads recompute (Phase 3 GAP)."""
    
    layout_id: UUID
    roads: list[RoadResponse]
    road_count: int
    total_length_m: float
    message: str


class RecomputeEarthworkRequest(BaseModel):
    """Request schema for recomputing earthwork (Phase 3 GAP)."""
    
    include_roads: bool = Field(
        default=True,
        description="Include road corridor earthwork in calculation",
    )


class RecomputeEarthworkResponse(BaseModel):
    """Response schema for earthwork recompute (Phase 3 GAP)."""
    
    layout_id: UUID
    cut_volume_m3: float
    fill_volume_m3: float
    road_cut_m3: Optional[float] = None
    road_fill_m3: Optional[float] = None
    net_earthwork_m3: float
    per_asset: list[dict] = Field(default_factory=list)
    message: str


# =============================================================================
# Phase 5: Compliance Rules & Advanced Assets
# =============================================================================


class ComplianceRuleRequest(BaseModel):
    """Request to add/update a compliance rule."""
    
    rule_id: str = Field(..., description="Unique rule identifier")
    rule_type: str = Field(..., description="Type of rule (e.g., max_slope, min_spacing)")
    asset_type: Optional[str] = Field(None, description="Asset type this rule applies to (None = all)")
    value: float = Field(..., description="Rule limit value")
    unit: str = Field(..., description="Unit of measurement (e.g., 'degrees', 'meters')")
    description: str = Field(..., description="Human-readable rule description")
    enabled: bool = Field(default=True, description="Whether rule is enabled")


class ComplianceRuleResponse(BaseModel):
    """Response for a compliance rule."""
    
    rule_id: str
    rule_type: str
    jurisdiction: str
    asset_type: Optional[str]
    value: float
    unit: str
    description: str
    enabled: bool


class ComplianceViolation(BaseModel):
    """A single compliance violation."""
    
    rule_id: str
    rule_type: str
    asset_type: Optional[str]
    message: str
    severity: str  # "error" or "warning"
    actual_value: float
    limit_value: float


class ComplianceCheckRequest(BaseModel):
    """Request to check compliance for a layout."""
    
    jurisdiction: str = Field(default="default", description="Jurisdiction code")


class ComplianceCheckResponse(BaseModel):
    """Response from compliance check."""
    
    layout_id: UUID
    is_compliant: bool
    violations_count: int
    warnings_count: int
    violations: list[ComplianceViolation] = Field(default_factory=list)
    warnings: list[ComplianceViolation] = Field(default_factory=list)
    checked_rules_count: int


class GetComplianceRulesRequest(BaseModel):
    """Request to get compliance rules for a jurisdiction."""
    
    jurisdiction: str = Field(default="default", description="Jurisdiction code")
    enabled_only: bool = Field(default=True, description="Return only enabled rules")


class GetComplianceRulesResponse(BaseModel):
    """Response with compliance rules for a jurisdiction."""
    
    jurisdiction: str
    total_rules: int
    rules: list[ComplianceRuleResponse]


class GISPublishRequest(BaseModel):
    """Request to publish layout to GIS system."""
    
    provider_type: str = Field(
        default="logging",
        description="GIS provider type (logging, mock, arcgis_online, etc.)",
    )
    include_metadata: bool = Field(
        default=True,
        description="Include layout metadata in GIS publish",
    )


class GISPublishResponse(BaseModel):
    """Response from GIS publish operation."""
    
    success: bool
    provider_type: str
    message: str
    external_id: Optional[str] = None
    url: Optional[str] = None
    features_published: int
    errors: list[str] = Field(default_factory=list)

