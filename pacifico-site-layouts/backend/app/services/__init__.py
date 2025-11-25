"""
Business logic services for Pacifico Site Layouts.
"""
# Phase A services
from app.services.kml_parser import KMLParser, KMLParseError
from app.services.layout_generator import DummyLayoutGenerator
from app.services.s3 import S3Service, get_s3_service

# Phase B services - Terrain processing
from app.services.dem_service import DEMService, get_dem_service
from app.services.slope_service import SlopeService, get_slope_service
from app.services.terrain_layout_generator import (
    TerrainAwareLayoutGenerator,
    PlacedAsset,
    PlacedRoad,
    CutFillResult,
)
from app.services.export_service import ExportService, get_export_service

__all__ = [
    # Phase A
    "KMLParser",
    "KMLParseError",
    "S3Service",
    "get_s3_service",
    "DummyLayoutGenerator",
    # Phase B - Terrain
    "DEMService",
    "get_dem_service",
    "SlopeService",
    "get_slope_service",
    "TerrainAwareLayoutGenerator",
    "PlacedAsset",
    "PlacedRoad",
    "CutFillResult",
    # Phase B - Exports
    "ExportService",
    "get_export_service",
]

