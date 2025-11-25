"""
KML/KMZ file parsing service.

Extracts polygon geometries from KML and KMZ files for site boundary import.
"""
import io
import logging
import zipfile
from typing import Optional

from fastkml import kml
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.geometry.base import BaseGeometry

logger = logging.getLogger(__name__)


class KMLParseError(Exception):
    """Raised when KML/KMZ parsing fails."""
    pass


class KMLParser:
    """
    Parser for KML and KMZ files.
    
    Extracts the first Polygon or MultiPolygon geometry from the file.
    """
    
    ALLOWED_EXTENSIONS = {".kml", ".kmz"}
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
    
    @classmethod
    def parse(cls, content: bytes, filename: str) -> tuple[Polygon | MultiPolygon, Optional[str]]:
        """
        Parse KML/KMZ file content and extract the first polygon geometry.
        
        Args:
            content: Raw file bytes
            filename: Original filename (used to determine file type)
            
        Returns:
            Tuple of (geometry, name) where geometry is a Shapely Polygon/MultiPolygon
            and name is the feature name from KML (or None)
            
        Raises:
            KMLParseError: If parsing fails or no polygon is found
        """
        # Validate file size
        if len(content) > cls.MAX_FILE_SIZE:
            raise KMLParseError(f"File exceeds maximum size of {cls.MAX_FILE_SIZE // (1024*1024)}MB")
        
        # Determine file type and extract KML content
        ext = cls._get_extension(filename)
        if ext not in cls.ALLOWED_EXTENSIONS:
            raise KMLParseError(f"Invalid file type. Allowed: {', '.join(cls.ALLOWED_EXTENSIONS)}")
        
        try:
            if ext == ".kmz":
                kml_content = cls._extract_kmz(content)
            else:
                kml_content = content
        except Exception as e:
            raise KMLParseError(f"Failed to read file: {e}")
        
        # Parse KML content
        return cls._parse_kml(kml_content)
    
    @classmethod
    def _get_extension(cls, filename: str) -> str:
        """Get lowercase file extension."""
        return "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    
    @classmethod
    def _extract_kmz(cls, content: bytes) -> bytes:
        """
        Extract KML from KMZ (ZIP) archive.
        
        KMZ files are ZIP archives containing a doc.kml file (or similar).
        """
        try:
            with zipfile.ZipFile(io.BytesIO(content), "r") as zf:
                # Find the main KML file
                kml_files = [n for n in zf.namelist() if n.lower().endswith(".kml")]
                
                if not kml_files:
                    raise KMLParseError("No KML file found in KMZ archive")
                
                # Prefer doc.kml if present, otherwise use first KML file
                main_kml = next(
                    (f for f in kml_files if f.lower() == "doc.kml"),
                    kml_files[0]
                )
                
                return zf.read(main_kml)
                
        except zipfile.BadZipFile:
            raise KMLParseError("Invalid KMZ file: not a valid ZIP archive")
    
    @classmethod
    def _parse_kml(cls, content: bytes) -> tuple[Polygon | MultiPolygon, Optional[str]]:
        """
        Parse KML content and extract first polygon geometry.
        
        Uses fastkml to parse the KML structure and extract geometries.
        """
        try:
            # Parse KML document
            k = kml.KML()
            k.from_string(content)
            
            # Recursively search for polygon features
            geometry, name = cls._find_polygon(k)
            
            if geometry is None:
                raise KMLParseError("No polygon geometry found in KML file")
            
            # Validate the geometry
            if not geometry.is_valid:
                # Try to fix invalid geometry
                geometry = geometry.buffer(0)
                if not geometry.is_valid:
                    raise KMLParseError("Invalid polygon geometry that could not be repaired")
            
            # Ensure it's a Polygon or MultiPolygon
            if isinstance(geometry, Polygon):
                return geometry, name
            elif isinstance(geometry, MultiPolygon):
                return geometry, name
            else:
                raise KMLParseError(f"Expected Polygon or MultiPolygon, got {type(geometry).__name__}")
                
        except KMLParseError:
            raise
        except Exception as e:
            logger.exception(f"KML parsing error: {e}")
            raise KMLParseError(f"Failed to parse KML: {e}")
    
    @classmethod
    def _find_polygon(
        cls,
        element,
        depth: int = 0
    ) -> tuple[Optional[BaseGeometry], Optional[str]]:
        """
        Recursively search KML element tree for polygon geometry.
        
        Returns the first Polygon or MultiPolygon found.
        """
        if depth > 20:  # Prevent infinite recursion
            return None, None
        
        # Check if this element has geometry
        geometry = getattr(element, "geometry", None)
        if geometry is not None:
            geom = shape(geometry)
            if isinstance(geom, (Polygon, MultiPolygon)):
                name = getattr(element, "name", None)
                return geom, name
        
        # Search in features (Documents, Folders, Placemarks)
        features = getattr(element, "features", None)
        if features:
            try:
                for feature in features:
                    geom, name = cls._find_polygon(feature, depth + 1)
                    if geom is not None:
                        return geom, name
            except TypeError:
                # features might not be iterable in some cases
                pass
        
        return None, None
    
    @staticmethod
    def geometry_to_wkt(geometry: BaseGeometry) -> str:
        """Convert Shapely geometry to WKT string."""
        return geometry.wkt
    
    @staticmethod
    def geometry_to_geojson(geometry: BaseGeometry) -> dict:
        """Convert Shapely geometry to GeoJSON dict."""
        import json
        from shapely.geometry import mapping
        return mapping(geometry)

