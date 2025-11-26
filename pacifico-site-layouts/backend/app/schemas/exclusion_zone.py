"""
Pydantic schemas for Exclusion Zone API endpoints.

Phase D-03: Schemas for creating, updating, and retrieving exclusion zones.
"""
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ExclusionZoneType(str, Enum):
    """Exclusion zone types matching the model."""
    ENVIRONMENTAL = "environmental"
    REGULATORY = "regulatory"
    INFRASTRUCTURE = "infrastructure"
    SAFETY = "safety"
    CUSTOM = "custom"


class ExclusionZoneTypeInfo(BaseModel):
    """Information about an exclusion zone type."""
    type: str
    label: str
    color: str
    default_buffer_m: float
    description: str


# Zone type metadata for frontend
ZONE_TYPE_INFO = [
    ExclusionZoneTypeInfo(
        type="environmental",
        label="Environmental",
        color="#3b82f6",
        default_buffer_m=0,
        description="Wetlands, water bodies, protected areas",
    ),
    ExclusionZoneTypeInfo(
        type="regulatory",
        label="Regulatory",
        color="#ef4444",
        default_buffer_m=0,
        description="Setbacks, easements, ROW",
    ),
    ExclusionZoneTypeInfo(
        type="infrastructure",
        label="Infrastructure",
        color="#f97316",
        default_buffer_m=10,
        description="Existing utilities, buildings",
    ),
    ExclusionZoneTypeInfo(
        type="safety",
        label="Safety",
        color="#eab308",
        default_buffer_m=25,
        description="Generator noise/emissions buffer",
    ),
    ExclusionZoneTypeInfo(
        type="custom",
        label="Custom",
        color="#6b7280",
        default_buffer_m=0,
        description="User-defined constraints",
    ),
]


class ExclusionZoneCreate(BaseModel):
    """Request schema for creating an exclusion zone."""
    
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Name of the exclusion zone",
    )
    zone_type: ExclusionZoneType = Field(
        default=ExclusionZoneType.CUSTOM,
        description="Type of exclusion zone",
    )
    geometry: dict[str, Any] = Field(
        ...,
        description="GeoJSON Polygon geometry",
    )
    buffer_m: float = Field(
        default=0.0,
        ge=0,
        le=1000,
        description="Additional buffer around geometry in meters",
    )
    cost_multiplier: float = Field(
        default=1.0,
        ge=0.0,
        le=100.0,
        description="Cost multiplier for pathfinding (1.0 = neutral)",
    )
    description: Optional[str] = Field(
        None,
        max_length=1000,
        description="Optional description of the zone",
    )
    
    @field_validator("geometry")
    @classmethod
    def validate_geometry(cls, v: dict) -> dict:
        """Validate that geometry is a valid GeoJSON Polygon."""
        if not isinstance(v, dict):
            raise ValueError("Geometry must be a GeoJSON object")
        
        geom_type = v.get("type")
        if geom_type != "Polygon":
            raise ValueError(f"Geometry must be a Polygon, got {geom_type}")
        
        coords = v.get("coordinates")
        if not coords or not isinstance(coords, list):
            raise ValueError("Polygon must have coordinates")
        
        # Basic validation: outer ring should have at least 4 points (closed polygon)
        if len(coords) < 1 or len(coords[0]) < 4:
            raise ValueError("Polygon must have at least 4 coordinates (closed ring)")
        
        return v


class ExclusionZoneUpdate(BaseModel):
    """Request schema for updating an exclusion zone."""
    
    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="Name of the exclusion zone",
    )
    zone_type: Optional[ExclusionZoneType] = Field(
        None,
        description="Type of exclusion zone",
    )
    geometry: Optional[dict[str, Any]] = Field(
        None,
        description="GeoJSON Polygon geometry",
    )
    buffer_m: Optional[float] = Field(
        None,
        ge=0,
        le=1000,
        description="Additional buffer around geometry in meters",
    )
    cost_multiplier: Optional[float] = Field(
        None,
        ge=0.0,
        le=100.0,
        description="Cost multiplier for pathfinding",
    )
    description: Optional[str] = Field(
        None,
        max_length=1000,
        description="Optional description of the zone",
    )
    
    @field_validator("geometry")
    @classmethod
    def validate_geometry(cls, v: Optional[dict]) -> Optional[dict]:
        """Validate geometry if provided."""
        if v is None:
            return v
        
        if not isinstance(v, dict):
            raise ValueError("Geometry must be a GeoJSON object")
        
        geom_type = v.get("type")
        if geom_type != "Polygon":
            raise ValueError(f"Geometry must be a Polygon, got {geom_type}")
        
        coords = v.get("coordinates")
        if not coords or not isinstance(coords, list):
            raise ValueError("Polygon must have coordinates")
        
        if len(coords) < 1 or len(coords[0]) < 4:
            raise ValueError("Polygon must have at least 4 coordinates (closed ring)")
        
        return v


class ExclusionZoneResponse(BaseModel):
    """Response schema for an exclusion zone."""
    
    id: UUID
    site_id: UUID
    name: str
    zone_type: str
    geometry: dict[str, Any] = Field(..., description="GeoJSON Polygon geometry")
    buffer_m: float
    cost_multiplier: float = Field(..., description="Cost multiplier for pathfinding")
    description: Optional[str]
    area_m2: Optional[float]
    color: str = Field(..., description="Display color for this zone type")
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class ExclusionZoneListResponse(BaseModel):
    """Response schema for listing exclusion zones."""
    
    zones: list[ExclusionZoneResponse]
    total: int
    site_id: UUID


class ExclusionZoneTypesResponse(BaseModel):
    """Response schema for listing available zone types."""
    
    types: list[ExclusionZoneTypeInfo]

