"""
Regulatory Data Integration Service.

Phase 2 (GAP Implementation): Service for fetching and integrating regulatory
and environmental constraint data into exclusion zones.

This service provides an abstraction layer for:
- Fetching regulatory datasets (FEMA flood zones, wetlands, etc.)
- Translating regulatory data into ExclusionZone records
- Supporting both mock data (for development) and real API integration (future)

Architecture:
- RegulatoryDataProvider: Abstract interface for data sources
- MockRegulatoryProvider: Static/mock data for development
- (Future) FEMAProvider, NWIProvider, etc.: Real API integrations
"""
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from shapely.geometry import Polygon, shape, mapping
from shapely.ops import unary_union

logger = logging.getLogger(__name__)


class RegulatoryLayerType(str, Enum):
    """Types of regulatory data layers that can be fetched."""
    
    # Environmental
    WETLAND = "wetland"                    # NWI wetlands
    FLOODPLAIN = "floodplain"              # FEMA flood zones
    WATER_BODY = "water_body"              # Lakes, rivers, streams
    SPECIES_HABITAT = "species_habitat"    # Protected species areas
    
    # Regulatory
    SETBACK = "setback"                    # Property line setbacks
    EASEMENT = "easement"                  # Utility easements
    RIGHT_OF_WAY = "right_of_way"          # Road/rail ROW
    
    # Infrastructure
    UTILITY_CORRIDOR = "utility_corridor"  # Power lines, pipelines
    EXISTING_STRUCTURE = "existing_structure"  # Buildings, roads


# Mapping from regulatory layer type to exclusion zone type
LAYER_TO_ZONE_TYPE = {
    RegulatoryLayerType.WETLAND: "environmental",
    RegulatoryLayerType.FLOODPLAIN: "environmental",
    RegulatoryLayerType.WATER_BODY: "environmental",
    RegulatoryLayerType.SPECIES_HABITAT: "environmental",
    RegulatoryLayerType.SETBACK: "regulatory",
    RegulatoryLayerType.EASEMENT: "regulatory",
    RegulatoryLayerType.RIGHT_OF_WAY: "regulatory",
    RegulatoryLayerType.UTILITY_CORRIDOR: "infrastructure",
    RegulatoryLayerType.EXISTING_STRUCTURE: "infrastructure",
}

# Default buffers and cost multipliers for each layer type
LAYER_DEFAULTS = {
    RegulatoryLayerType.WETLAND: {
        "buffer_m": 15.0,           # Wetland buffer
        "cost_multiplier": 100.0,   # Hard exclusion
        "description": "Wetland area - development prohibited",
    },
    RegulatoryLayerType.FLOODPLAIN: {
        "buffer_m": 0.0,
        "cost_multiplier": 50.0,    # Strong avoidance
        "description": "FEMA flood zone - avoid development",
    },
    RegulatoryLayerType.WATER_BODY: {
        "buffer_m": 30.0,           # Riparian buffer
        "cost_multiplier": 100.0,   # Hard exclusion
        "description": "Water body with riparian buffer",
    },
    RegulatoryLayerType.SPECIES_HABITAT: {
        "buffer_m": 50.0,           # Habitat buffer
        "cost_multiplier": 100.0,   # Hard exclusion
        "description": "Protected species habitat - development prohibited",
    },
    RegulatoryLayerType.SETBACK: {
        "buffer_m": 0.0,
        "cost_multiplier": 100.0,   # Hard exclusion
        "description": "Property setback requirement",
    },
    RegulatoryLayerType.EASEMENT: {
        "buffer_m": 5.0,
        "cost_multiplier": 100.0,   # Hard exclusion
        "description": "Utility or access easement",
    },
    RegulatoryLayerType.RIGHT_OF_WAY: {
        "buffer_m": 0.0,
        "cost_multiplier": 100.0,   # Hard exclusion
        "description": "Public right-of-way",
    },
    RegulatoryLayerType.UTILITY_CORRIDOR: {
        "buffer_m": 10.0,
        "cost_multiplier": 100.0,   # Hard exclusion
        "description": "Existing utility corridor",
    },
    RegulatoryLayerType.EXISTING_STRUCTURE: {
        "buffer_m": 5.0,
        "cost_multiplier": 100.0,   # Hard exclusion
        "description": "Existing structure or building",
    },
}


@dataclass
class RegulatoryFeature:
    """A single regulatory feature with geometry and metadata."""
    
    layer_type: RegulatoryLayerType
    geometry: Polygon  # Shapely polygon
    name: str
    source: str  # e.g., "FEMA", "NWI", "mock"
    source_id: Optional[str] = None  # ID from source system
    attributes: Optional[dict[str, Any]] = None  # Additional metadata
    
    def to_exclusion_zone_data(self) -> dict[str, Any]:
        """Convert to data suitable for creating an ExclusionZone."""
        defaults = LAYER_DEFAULTS.get(self.layer_type, {})
        zone_type = LAYER_TO_ZONE_TYPE.get(self.layer_type, "custom")
        
        return {
            "name": self.name,
            "zone_type": zone_type,
            "geometry": mapping(self.geometry),  # GeoJSON dict
            "buffer_m": defaults.get("buffer_m", 0.0),
            "cost_multiplier": defaults.get("cost_multiplier", 100.0),
            "description": defaults.get("description", f"{self.layer_type.value} constraint"),
        }


class RegulatoryDataProvider(ABC):
    """Abstract interface for regulatory data providers."""
    
    @abstractmethod
    async def fetch_features(
        self,
        boundary: Polygon,
        layer_types: Optional[list[RegulatoryLayerType]] = None,
    ) -> list[RegulatoryFeature]:
        """
        Fetch regulatory features within a boundary.
        
        Args:
            boundary: Site boundary polygon
            layer_types: Optional list of layer types to fetch (None = all)
            
        Returns:
            List of RegulatoryFeature objects
        """
        pass
    
    @abstractmethod
    def get_supported_layers(self) -> list[RegulatoryLayerType]:
        """Return list of layer types supported by this provider."""
        pass


class MockRegulatoryProvider(RegulatoryDataProvider):
    """
    Mock regulatory data provider for development and testing.
    
    Generates synthetic regulatory features based on the site boundary:
    - A simulated wetland in the corner
    - A simulated utility corridor across the site
    - A simulated setback around the perimeter
    """
    
    def get_supported_layers(self) -> list[RegulatoryLayerType]:
        """Return all layer types for mock data."""
        return [
            RegulatoryLayerType.WETLAND,
            RegulatoryLayerType.SETBACK,
            RegulatoryLayerType.UTILITY_CORRIDOR,
        ]
    
    async def fetch_features(
        self,
        boundary: Polygon,
        layer_types: Optional[list[RegulatoryLayerType]] = None,
    ) -> list[RegulatoryFeature]:
        """Generate mock regulatory features."""
        if not boundary.is_valid:
            boundary = boundary.buffer(0)
        
        features = []
        types_to_fetch = layer_types or self.get_supported_layers()
        
        bounds = boundary.bounds  # (minx, miny, maxx, maxy)
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        
        # Generate mock wetland in the northwest corner
        if RegulatoryLayerType.WETLAND in types_to_fetch:
            wetland_size = min(width, height) * 0.15  # 15% of smaller dimension
            wetland_center_x = bounds[0] + width * 0.2
            wetland_center_y = bounds[3] - height * 0.2
            
            # Create irregular polygon for wetland
            wetland_poly = Polygon([
                (wetland_center_x - wetland_size * 0.5, wetland_center_y - wetland_size * 0.3),
                (wetland_center_x - wetland_size * 0.3, wetland_center_y + wetland_size * 0.4),
                (wetland_center_x + wetland_size * 0.2, wetland_center_y + wetland_size * 0.5),
                (wetland_center_x + wetland_size * 0.6, wetland_center_y + wetland_size * 0.2),
                (wetland_center_x + wetland_size * 0.5, wetland_center_y - wetland_size * 0.4),
                (wetland_center_x + wetland_size * 0.1, wetland_center_y - wetland_size * 0.5),
            ])
            
            # Clip to boundary
            wetland_clipped = wetland_poly.intersection(boundary)
            if not wetland_clipped.is_empty and wetland_clipped.area > 0:
                features.append(RegulatoryFeature(
                    layer_type=RegulatoryLayerType.WETLAND,
                    geometry=wetland_clipped if isinstance(wetland_clipped, Polygon) else wetland_clipped.convex_hull,
                    name="Mock Wetland Area",
                    source="mock",
                    source_id="MOCK-WETLAND-001",
                    attributes={"wetland_type": "Palustrine Emergent", "acres": wetland_clipped.area * 111000**2 / 4047},
                ))
        
        # Generate mock utility corridor (diagonal across site)
        if RegulatoryLayerType.UTILITY_CORRIDOR in types_to_fetch:
            corridor_width = min(width, height) * 0.03  # 3% width
            
            # Create corridor from southwest to northeast
            from shapely.geometry import LineString
            corridor_line = LineString([
                (bounds[0] + width * 0.1, bounds[1] + height * 0.3),
                (bounds[2] - width * 0.3, bounds[3] - height * 0.1),
            ])
            
            # Buffer to create corridor polygon
            # Convert width to degrees (approximate)
            corridor_buffer_deg = corridor_width
            corridor_poly = corridor_line.buffer(corridor_buffer_deg)
            
            # Clip to boundary
            corridor_clipped = corridor_poly.intersection(boundary)
            if not corridor_clipped.is_empty and corridor_clipped.area > 0:
                features.append(RegulatoryFeature(
                    layer_type=RegulatoryLayerType.UTILITY_CORRIDOR,
                    geometry=corridor_clipped if isinstance(corridor_clipped, Polygon) else corridor_clipped.convex_hull,
                    name="Mock Power Line Easement",
                    source="mock",
                    source_id="MOCK-UTILITY-001",
                    attributes={"utility_type": "Overhead Power Line", "voltage_kv": 138},
                ))
        
        # Generate mock setback (perimeter buffer)
        if RegulatoryLayerType.SETBACK in types_to_fetch:
            setback_width = min(width, height) * 0.05  # 5% setback
            
            # Create setback as boundary minus interior
            interior = boundary.buffer(-setback_width)
            if interior.is_valid and not interior.is_empty:
                setback_ring = boundary.difference(interior)
                if not setback_ring.is_empty and setback_ring.area > 0:
                    # If it's a MultiPolygon, get the largest part
                    if setback_ring.geom_type == 'MultiPolygon':
                        setback_ring = max(setback_ring.geoms, key=lambda g: g.area)
                    
                    features.append(RegulatoryFeature(
                        layer_type=RegulatoryLayerType.SETBACK,
                        geometry=setback_ring,
                        name="Property Line Setback",
                        source="mock",
                        source_id="MOCK-SETBACK-001",
                        attributes={"setback_type": "Property Line", "distance_ft": setback_width * 111000 * 3.28084},
                    ))
        
        logger.info(f"MockRegulatoryProvider generated {len(features)} features")
        return features


class RegulatoryService:
    """
    Main service for regulatory data integration.
    
    Coordinates data fetching from providers and creates exclusion zones.
    """
    
    def __init__(self, provider: Optional[RegulatoryDataProvider] = None):
        """
        Initialize the service.
        
        Args:
            provider: Data provider to use (defaults to MockRegulatoryProvider)
        """
        self.provider = provider or MockRegulatoryProvider()
    
    async def sync_regulatory_data(
        self,
        site_id: UUID,
        boundary: Polygon,
        layer_types: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch regulatory data and prepare exclusion zone records.
        
        Args:
            site_id: Site ID to associate zones with
            boundary: Site boundary polygon
            layer_types: Optional list of layer type strings to fetch
            
        Returns:
            List of exclusion zone data dicts ready for DB insertion
        """
        # Convert string layer types to enum
        enum_types = None
        if layer_types:
            enum_types = []
            for lt in layer_types:
                try:
                    enum_types.append(RegulatoryLayerType(lt))
                except ValueError:
                    logger.warning(f"Unknown layer type: {lt}")
        
        # Fetch features from provider
        features = await self.provider.fetch_features(boundary, enum_types)
        
        # Convert to exclusion zone data
        zone_data_list = []
        for feature in features:
            zone_data = feature.to_exclusion_zone_data()
            zone_data["site_id"] = site_id
            zone_data_list.append(zone_data)
        
        logger.info(f"Regulatory sync for site {site_id}: {len(zone_data_list)} zones prepared")
        return zone_data_list
    
    def get_available_layers(self) -> list[dict[str, Any]]:
        """
        Get information about available regulatory layers.
        
        Returns:
            List of layer info dicts with type, name, description
        """
        supported = self.provider.get_supported_layers()
        
        layers = []
        for layer_type in supported:
            defaults = LAYER_DEFAULTS.get(layer_type, {})
            layers.append({
                "type": layer_type.value,
                "name": layer_type.value.replace("_", " ").title(),
                "zone_type": LAYER_TO_ZONE_TYPE.get(layer_type, "custom"),
                "default_buffer_m": defaults.get("buffer_m", 0.0),
                "default_cost_multiplier": defaults.get("cost_multiplier", 100.0),
                "description": defaults.get("description", ""),
            })
        
        return layers


# Singleton instance
_regulatory_service: Optional[RegulatoryService] = None


def get_regulatory_service() -> RegulatoryService:
    """Get the singleton RegulatoryService instance."""
    global _regulatory_service
    if _regulatory_service is None:
        # In future, could configure provider based on environment
        _regulatory_service = RegulatoryService()
    return _regulatory_service

