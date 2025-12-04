"""
GIS Integration Service for Phase 5.

Provides a plugin-style GIS integration layer that can push final layouts to 
external GIS systems via their APIs. Starts as a stub with logging-only mode.

Supports:
- Pluggable provider pattern for different GIS backends
- Mock provider for testing
- Extensible to ArcGIS Online, Mapbox, and other GIS systems
"""
import logging
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


class GISProviderType(str, Enum):
    """Supported GIS provider types."""
    LOGGING = "logging"  # Stub: logs to console only
    ARCGIS_ONLINE = "arcgis_online"  # ArcGIS Online feature service
    MAPBOX = "mapbox"  # Mapbox data API
    GEOSERVER = "geoserver"  # GeoServer WFS-T
    MOCK = "mock"  # Mock provider for testing


@dataclass
class GISIntegrationConfig:
    """Configuration for GIS integration."""
    provider_type: GISProviderType
    enabled: bool = False
    endpoint_url: Optional[str] = None
    api_key: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    workspace_name: Optional[str] = None
    extra_params: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.extra_params is None:
            self.extra_params = {}


@dataclass
class GISPublishResult:
    """Result of publishing a layout to GIS."""
    success: bool
    provider_type: GISProviderType
    message: str
    external_id: Optional[str] = None  # ID assigned by external system
    url: Optional[str] = None  # URL to view in GIS system
    features_published: int = 0
    errors: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "success": self.success,
            "provider_type": self.provider_type.value,
            "message": self.message,
            "external_id": self.external_id,
            "url": self.url,
            "features_published": self.features_published,
            "errors": self.errors,
        }


class GISProvider(ABC):
    """Abstract base class for GIS providers."""
    
    def __init__(self, config: GISIntegrationConfig):
        """Initialize GIS provider with configuration."""
        self.config = config
        self.logger = logging.getLogger(f"gis.{self.__class__.__name__}")
    
    @abstractmethod
    def authenticate(self) -> bool:
        """Authenticate with the GIS service. Returns True if successful."""
        pass
    
    @abstractmethod
    def publish_layout(
        self,
        layout_id: str,
        layout_name: str,
        geojson_data: Dict[str, Any],
        metadata: Dict[str, Any] = None,
    ) -> GISPublishResult:
        """
        Publish a layout to the GIS service.
        
        Args:
            layout_id: Unique layout identifier
            layout_name: Human-readable layout name
            geojson_data: GeoJSON FeatureCollection with layout assets and roads
            metadata: Additional metadata to include in publication
        
        Returns:
            GISPublishResult with success status and details
        """
        pass
    
    @abstractmethod
    def get_published_layouts(self) -> List[Dict[str, Any]]:
        """Get list of previously published layouts."""
        pass
    
    @abstractmethod
    def delete_layout(self, external_id: str) -> bool:
        """Delete a published layout from the GIS service."""
        pass


class LoggingGISProvider(GISProvider):
    """
    Stub GIS provider that logs operations to console.
    
    Used for testing and when no external GIS system is configured.
    """
    
    def authenticate(self) -> bool:
        """Always returns True (no real auth)."""
        self.logger.info("Logging provider authenticated (stub)")
        return True
    
    def publish_layout(
        self,
        layout_id: str,
        layout_name: str,
        geojson_data: Dict[str, Any],
        metadata: Dict[str, Any] = None,
    ) -> GISPublishResult:
        """Log layout publication to console."""
        features_count = 0
        if "features" in geojson_data:
            features_count = len(geojson_data["features"])
        
        self.logger.info(
            f"PUBLISHING LAYOUT TO GIS:\n"
            f"  Layout ID: {layout_id}\n"
            f"  Layout Name: {layout_name}\n"
            f"  Features: {features_count}\n"
            f"  Metadata: {json.dumps(metadata or {}, indent=2)}"
        )
        
        # Log feature types
        if "features" in geojson_data:
            feature_types = {}
            for feature in geojson_data["features"]:
                props = feature.get("properties", {})
                ftype = props.get("type", "unknown")
                feature_types[ftype] = feature_types.get(ftype, 0) + 1
            
            self.logger.info(f"  Feature breakdown: {feature_types}")
        
        return GISPublishResult(
            success=True,
            provider_type=GISProviderType.LOGGING,
            message=f"Layout {layout_name} logged to console (stub mode)",
            external_id=f"logged-{layout_id}",
            features_published=features_count,
        )
    
    def get_published_layouts(self) -> List[Dict[str, Any]]:
        """Return empty list (stub)."""
        self.logger.info("Retrieving published layouts (stub - returns empty list)")
        return []
    
    def delete_layout(self, external_id: str) -> bool:
        """Log layout deletion to console."""
        self.logger.info(f"Deleting layout from GIS: {external_id} (stub)")
        return True


class MockGISProvider(GISProvider):
    """
    Mock GIS provider for testing.
    
    Simulates a real GIS backend with in-memory storage.
    """
    
    # Class-level storage for mock layouts
    _published_layouts: Dict[str, Dict[str, Any]] = {}
    
    def authenticate(self) -> bool:
        """Mock authentication."""
        self.logger.info("Mock GIS provider authenticated")
        return True
    
    def publish_layout(
        self,
        layout_id: str,
        layout_name: str,
        geojson_data: Dict[str, Any],
        metadata: Dict[str, Any] = None,
    ) -> GISPublishResult:
        """Store layout in mock storage."""
        features_count = 0
        if "features" in geojson_data:
            features_count = len(geojson_data["features"])
        
        external_id = f"mock-{layout_id}"
        
        # Store in mock storage
        MockGISProvider._published_layouts[external_id] = {
            "layout_id": layout_id,
            "layout_name": layout_name,
            "geojson": geojson_data,
            "metadata": metadata or {},
            "features_count": features_count,
        }
        
        self.logger.info(
            f"Mock GIS: Published layout {layout_name} "
            f"with {features_count} features (ID: {external_id})"
        )
        
        return GISPublishResult(
            success=True,
            provider_type=GISProviderType.MOCK,
            message=f"Layout published to mock GIS",
            external_id=external_id,
            features_published=features_count,
        )
    
    def get_published_layouts(self) -> List[Dict[str, Any]]:
        """Return all mock published layouts."""
        self.logger.info(f"Retrieving {len(MockGISProvider._published_layouts)} mock layouts")
        return list(MockGISProvider._published_layouts.values())
    
    def delete_layout(self, external_id: str) -> bool:
        """Delete from mock storage."""
        if external_id in MockGISProvider._published_layouts:
            del MockGISProvider._published_layouts[external_id]
            self.logger.info(f"Mock GIS: Deleted layout {external_id}")
            return True
        return False
    
    @classmethod
    def clear_all(cls):
        """Clear all mock data (for testing)."""
        cls._published_layouts.clear()


class GISIntegrationService:
    """
    Service for managing GIS integrations.
    
    Provides a unified interface for publishing layouts to various GIS backends.
    Supports plugin-style provider pattern for extensibility.
    """
    
    def __init__(self, config: GISIntegrationConfig):
        """Initialize GIS integration service."""
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.provider: Optional[GISProvider] = None
        
        # Initialize provider based on config
        if config.enabled:
            self._init_provider()
    
    def _init_provider(self):
        """Initialize the appropriate GIS provider based on config."""
        provider_type = self.config.provider_type
        
        if provider_type == GISProviderType.LOGGING:
            self.provider = LoggingGISProvider(self.config)
        elif provider_type == GISProviderType.MOCK:
            self.provider = MockGISProvider(self.config)
        elif provider_type == GISProviderType.ARCGIS_ONLINE:
            # Future: Implement ArcGIS Online provider
            self.logger.warning("ArcGIS Online provider not yet implemented")
            self.provider = LoggingGISProvider(self.config)
        elif provider_type == GISProviderType.GEOSERVER:
            # Future: Implement GeoServer WFS-T provider
            self.logger.warning("GeoServer provider not yet implemented")
            self.provider = LoggingGISProvider(self.config)
        else:
            self.logger.error(f"Unknown GIS provider type: {provider_type}")
            self.provider = LoggingGISProvider(self.config)
        
        # Authenticate
        if not self.provider.authenticate():
            self.logger.error("Failed to authenticate with GIS provider")
    
    def is_enabled(self) -> bool:
        """Check if GIS integration is enabled."""
        return self.config.enabled and self.provider is not None
    
    def publish_layout(
        self,
        layout_id: str,
        layout_name: str,
        geojson_data: Dict[str, Any],
        metadata: Dict[str, Any] = None,
    ) -> GISPublishResult:
        """
        Publish a layout to the configured GIS system.
        
        Args:
            layout_id: Unique layout identifier
            layout_name: Human-readable layout name
            geojson_data: GeoJSON FeatureCollection with layout
            metadata: Additional metadata to include
        
        Returns:
            GISPublishResult with success status
        """
        if not self.is_enabled():
            return GISPublishResult(
                success=False,
                provider_type=self.config.provider_type,
                message="GIS integration is not enabled",
            )
        
        try:
            result = self.provider.publish_layout(
                layout_id, layout_name, geojson_data, metadata
            )
            self.logger.info(f"Successfully published layout: {result.message}")
            return result
        except Exception as e:
            self.logger.error(f"Failed to publish layout: {str(e)}", exc_info=True)
            return GISPublishResult(
                success=False,
                provider_type=self.config.provider_type,
                message=f"Error publishing layout: {str(e)}",
                errors=[str(e)],
            )
    
    def get_published_layouts(self) -> List[Dict[str, Any]]:
        """Get all previously published layouts."""
        if not self.is_enabled():
            return []
        
        try:
            return self.provider.get_published_layouts()
        except Exception as e:
            self.logger.error(f"Failed to retrieve layouts: {str(e)}", exc_info=True)
            return []
    
    def delete_layout(self, external_id: str) -> bool:
        """Delete a published layout from the GIS system."""
        if not self.is_enabled():
            return False
        
        try:
            return self.provider.delete_layout(external_id)
        except Exception as e:
            self.logger.error(f"Failed to delete layout: {str(e)}", exc_info=True)
            return False


def get_gis_integration_service(
    provider_type: str = "logging",
    enabled: bool = False,
    endpoint_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> GISIntegrationService:
    """
    Factory function to create a GIS integration service.
    
    Args:
        provider_type: Type of GIS provider ('logging', 'mock', 'arcgis_online', etc.)
        enabled: Whether GIS integration is enabled
        endpoint_url: API endpoint URL for the GIS service
        api_key: API key for the GIS service
    
    Returns:
        GISIntegrationService instance
    """
    try:
        ptype = GISProviderType(provider_type.lower())
    except ValueError:
        logger.warning(f"Unknown GIS provider '{provider_type}', using LOGGING")
        ptype = GISProviderType.LOGGING
    
    config = GISIntegrationConfig(
        provider_type=ptype,
        enabled=enabled,
        endpoint_url=endpoint_url,
        api_key=api_key,
    )
    
    return GISIntegrationService(config)

