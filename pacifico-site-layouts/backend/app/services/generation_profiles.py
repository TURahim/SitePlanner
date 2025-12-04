"""
Generation Profiles Configuration.

Defines different asset mixes for various project types:
- SOLAR_FARM: Traditional solar-heavy layout (default, backward compatible)
- GAS_BESS: Natural gas turbines + battery storage (for data center microgrids)
- WIND_HYBRID: Wind turbines with solar and storage
- HYBRID: Balanced mix of all generation types

Each profile specifies:
- Asset type weights (probability of selection)
- Capacity ranges per asset
- Footprint dimensions
- Slope limits
- Spacing requirements
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class GenerationProfile(str, Enum):
    """Available generation profiles for layout generation."""
    SOLAR_FARM = "solar_farm"          # Traditional solar + storage (default)
    GAS_BESS = "gas_bess"              # Gas turbines + battery storage
    WIND_HYBRID = "wind_hybrid"        # Wind + solar + storage
    HYBRID = "hybrid"                  # Balanced mix of all types


@dataclass
class AssetConfig:
    """Configuration for a single asset type."""
    capacity_range: tuple[float, float]  # (min_kw, max_kw)
    weight: float                         # Selection probability weight
    footprint: tuple[float, float]        # (length_m, width_m)
    pad_size_m: float                     # Grading pad size
    slope_limit_deg: float               # Maximum slope for placement
    optimal_slope_deg: float             # Preferred slope for scoring


@dataclass
class BlueprintAsset:
    """Asset within a block layout, positioned relative to block center."""
    asset_type: str
    offset_east_m: float = 0.0
    offset_north_m: float = 0.0


@dataclass
class BlockLayoutConfig:
    """Structured block layout configuration for repeating asset groups."""
    rows: int
    columns: int
    spacing_row_m: float     # North/South spacing between rows
    spacing_col_m: float     # East/West spacing between columns
    assets: list[BlueprintAsset] = field(default_factory=list)
    global_assets: list[BlueprintAsset] = field(default_factory=list)
    placement_description: str = ""


@dataclass
class ProfileConfig:
    """Complete configuration for a generation profile."""
    name: str
    description: str
    asset_configs: dict[str, AssetConfig]
    min_spacing_m: float = 15.0
    block_layout: BlockLayoutConfig | None = None
    
    def get_weights(self) -> dict[str, float]:
        """Get asset type weights for random selection."""
        return {k: v.weight for k, v in self.asset_configs.items()}
    
    def get_slope_limits(self) -> dict[str, float]:
        """Get slope limits by asset type."""
        return {k: v.slope_limit_deg for k, v in self.asset_configs.items()}


# =============================================================================
# Profile Definitions
# =============================================================================

SOLAR_FARM_PROFILE = ProfileConfig(
    name="Solar Farm",
    description="Traditional solar arrays with battery storage. Best for utility-scale solar projects.",
    min_spacing_m=15.0,
    asset_configs={
        "solar_array": AssetConfig(
            capacity_range=(100, 500),
            weight=0.60,
            footprint=(30, 20),
            pad_size_m=35,
            slope_limit_deg=10.0,
            optimal_slope_deg=5.0,
        ),
        "battery": AssetConfig(
            capacity_range=(50, 200),
            weight=0.20,
            footprint=(15, 10),
            pad_size_m=20,
            slope_limit_deg=4.0,
            optimal_slope_deg=2.0,
        ),
        "generator": AssetConfig(
            capacity_range=(100, 300),
            weight=0.10,
            footprint=(10, 8),
            pad_size_m=15,
            slope_limit_deg=5.0,
            optimal_slope_deg=3.0,
        ),
        "substation": AssetConfig(
            capacity_range=(500, 2000),
            weight=0.10,
            footprint=(20, 15),
            pad_size_m=25,
            slope_limit_deg=3.0,
            optimal_slope_deg=1.0,
        ),
    },
)

GAS_BESS_PROFILE = ProfileConfig(
    name="Gas + Battery Storage",
    description="Natural gas turbines with battery storage. Ideal for off-grid data centers and high-reliability microgrids.",
    min_spacing_m=25.0,  # Larger spacing for turbine blocks
    asset_configs={
        "gas_turbine": AssetConfig(
            capacity_range=(35_000, 50_000),  # 35-50 MW (Siemens SGT-800 class turbines)
            weight=0.50,
            footprint=(80, 60),  # Large turbine hall + cooling
            pad_size_m=100,
            slope_limit_deg=3.0,  # Very flat for turbine foundations
            optimal_slope_deg=1.0,
        ),
        "battery": AssetConfig(
            capacity_range=(25_000, 100_000),  # 25-100 MW BESS blocks
            weight=0.30,
            footprint=(50, 40),  # Large container arrays
            pad_size_m=60,
            slope_limit_deg=4.0,
            optimal_slope_deg=2.0,
        ),
        "substation": AssetConfig(
            capacity_range=(100_000, 500_000),  # Large substations for GW-scale
            weight=0.10,
            footprint=(60, 50),
            pad_size_m=80,
            slope_limit_deg=3.0,
            optimal_slope_deg=1.0,
        ),
        "control_center": AssetConfig(
            capacity_range=(0, 0),  # No generation capacity
            weight=0.05,
            footprint=(30, 20),
            pad_size_m=40,
            slope_limit_deg=3.0,
            optimal_slope_deg=1.0,
        ),
        "cooling_system": AssetConfig(
            capacity_range=(0, 0),  # Auxiliary equipment
            weight=0.05,
            footprint=(40, 30),
            pad_size_m=50,
            slope_limit_deg=4.0,
            optimal_slope_deg=2.0,
        ),
    },
    block_layout=BlockLayoutConfig(
        rows=2,
        columns=3,
        spacing_row_m=260.0,
        spacing_col_m=220.0,
        placement_description="Grid of turbine blocks aligned to site entry corridor.",
        assets=[
            BlueprintAsset(asset_type="gas_turbine", offset_east_m=0.0, offset_north_m=0.0),
            BlueprintAsset(asset_type="battery", offset_east_m=70.0, offset_north_m=0.0),
            BlueprintAsset(asset_type="cooling_system", offset_east_m=-70.0, offset_north_m=0.0),
        ],
        global_assets=[
            BlueprintAsset(asset_type="control_center", offset_east_m=0.0, offset_north_m=-250.0),
            BlueprintAsset(asset_type="substation", offset_east_m=0.0, offset_north_m=250.0),
        ],
    ),
)

WIND_HYBRID_PROFILE = ProfileConfig(
    name="Wind Hybrid",
    description="Wind turbines with solar and battery storage. Suitable for sites with good wind resources.",
    min_spacing_m=100.0,  # Large spacing for turbine wake effects
    asset_configs={
        "wind_turbine": AssetConfig(
            capacity_range=(2000, 5000),  # 2-5 MW per turbine
            weight=0.40,
            footprint=(60, 60),
            pad_size_m=80,
            slope_limit_deg=15.0,  # More tolerant to slope
            optimal_slope_deg=8.0,
        ),
        "solar_array": AssetConfig(
            capacity_range=(100, 500),
            weight=0.30,
            footprint=(30, 20),
            pad_size_m=35,
            slope_limit_deg=10.0,
            optimal_slope_deg=5.0,
        ),
        "battery": AssetConfig(
            capacity_range=(50, 200),
            weight=0.15,
            footprint=(15, 10),
            pad_size_m=20,
            slope_limit_deg=4.0,
            optimal_slope_deg=2.0,
        ),
        "substation": AssetConfig(
            capacity_range=(500, 2000),
            weight=0.15,
            footprint=(20, 15),
            pad_size_m=25,
            slope_limit_deg=3.0,
            optimal_slope_deg=1.0,
        ),
    },
)

HYBRID_PROFILE = ProfileConfig(
    name="Hybrid Mix",
    description="Balanced mix of solar, wind, gas, and storage. Maximum flexibility for diverse sites.",
    min_spacing_m=20.0,
    asset_configs={
        "solar_array": AssetConfig(
            capacity_range=(100, 500),
            weight=0.30,
            footprint=(30, 20),
            pad_size_m=35,
            slope_limit_deg=10.0,
            optimal_slope_deg=5.0,
        ),
        "wind_turbine": AssetConfig(
            capacity_range=(2000, 5000),
            weight=0.15,
            footprint=(60, 60),
            pad_size_m=80,
            slope_limit_deg=15.0,
            optimal_slope_deg=8.0,
        ),
        "gas_turbine": AssetConfig(
            capacity_range=(10_000, 50_000),
            weight=0.15,
            footprint=(50, 40),
            pad_size_m=60,
            slope_limit_deg=3.0,
            optimal_slope_deg=1.0,
        ),
        "battery": AssetConfig(
            capacity_range=(50, 500),
            weight=0.25,
            footprint=(20, 15),
            pad_size_m=25,
            slope_limit_deg=4.0,
            optimal_slope_deg=2.0,
        ),
        "substation": AssetConfig(
            capacity_range=(500, 2000),
            weight=0.15,
            footprint=(20, 15),
            pad_size_m=25,
            slope_limit_deg=3.0,
            optimal_slope_deg=1.0,
        ),
    },
)


# =============================================================================
# Profile Registry
# =============================================================================

PROFILES: dict[GenerationProfile, ProfileConfig] = {
    GenerationProfile.GAS_BESS: GAS_BESS_PROFILE,
    GenerationProfile.SOLAR_FARM: SOLAR_FARM_PROFILE,
    GenerationProfile.WIND_HYBRID: WIND_HYBRID_PROFILE,
    GenerationProfile.HYBRID: HYBRID_PROFILE,
}


def get_profile(profile: GenerationProfile) -> ProfileConfig:
    """Get the configuration for a generation profile."""
    return PROFILES[profile]


def get_profile_info() -> list[dict[str, Any]]:
    """Get metadata for all profiles (for API/frontend)."""
    return [
        {
            "profile": p.value,
            "name": config.name,
            "description": config.description,
            "asset_types": list(config.asset_configs.keys()),
            "has_block_layout": config.block_layout is not None,
        }
        for p, config in PROFILES.items()
    ]

