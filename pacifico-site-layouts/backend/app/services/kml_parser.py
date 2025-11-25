"""
KML/KMZ file parsing service.

Extracts polygon geometries from KML and KMZ files for site boundary import.
"""
import io
import logging
import re
import zipfile
import xml.etree.ElementTree as ET
from typing import Optional

from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry

logger = logging.getLogger(__name__)


class KMLParseError(Exception):
    """Raised when KML/KMZ parsing fails."""
    pass


class KMLParser:
    """
    Parser for KML and KMZ files.
    
    Extracts the first Polygon or MultiPolygon geometry from the file.
    Uses direct XML parsing for reliability across different KML versions.
    """
    
    ALLOWED_EXTENSIONS = {".kml", ".kmz"}
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
    
    # KML namespace
    KML_NS = {"kml": "http://www.opengis.net/kml/2.2"}
    
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
        Parse KML content and extract first polygon geometry using ElementTree.
        """
        try:
            # Parse XML
            root = ET.fromstring(content)
            
            # Handle namespace - KML files typically have a namespace
            # Extract namespace from root tag if present
            ns_match = re.match(r'\{(.+?)\}', root.tag)
            ns = {"kml": ns_match.group(1)} if ns_match else cls.KML_NS
            
            # Find all Placemark elements
            placemarks = root.findall(".//kml:Placemark", ns)
            if not placemarks:
                # Try without namespace (some KML files don't use it)
                placemarks = root.findall(".//Placemark")
            
            for placemark in placemarks:
                # Get placemark name
                name_elem = placemark.find("kml:name", ns)
                if name_elem is None:
                    name_elem = placemark.find("name")
                name = name_elem.text if name_elem is not None else None
                
                # Find Polygon element
                polygon_elem = placemark.find(".//kml:Polygon", ns)
                if polygon_elem is None:
                    polygon_elem = placemark.find(".//Polygon")
                
                if polygon_elem is not None:
                    geometry = cls._parse_polygon(polygon_elem, ns)
                    if geometry is not None:
                        return geometry, name
            
            raise KMLParseError("No polygon geometry found in KML file")
                
        except KMLParseError:
            raise
        except ET.ParseError as e:
            raise KMLParseError(f"Invalid XML: {e}")
        except Exception as e:
            logger.exception(f"KML parsing error: {e}")
            raise KMLParseError(f"Failed to parse KML: {e}")
    
    @classmethod
    def _parse_polygon(cls, polygon_elem, ns: dict) -> Optional[Polygon]:
        """
        Parse a KML Polygon element into a Shapely Polygon.
        """
        # Find outer boundary coordinates
        outer_boundary = polygon_elem.find(".//kml:outerBoundaryIs//kml:coordinates", ns)
        if outer_boundary is None:
            outer_boundary = polygon_elem.find(".//outerBoundaryIs//coordinates")
        
        if outer_boundary is None or not outer_boundary.text:
            return None
        
        # Parse coordinates
        exterior_coords = cls._parse_coordinates(outer_boundary.text)
        if len(exterior_coords) < 4:
            return None
        
        # Find inner boundaries (holes)
        holes = []
        inner_boundaries = polygon_elem.findall(".//kml:innerBoundaryIs//kml:coordinates", ns)
        if not inner_boundaries:
            inner_boundaries = polygon_elem.findall(".//innerBoundaryIs//coordinates")
        
        for inner in inner_boundaries:
            if inner.text:
                hole_coords = cls._parse_coordinates(inner.text)
                if len(hole_coords) >= 4:
                    holes.append(hole_coords)
        
        # Create Shapely Polygon
        try:
            polygon = Polygon(exterior_coords, holes if holes else None)
            
            # Validate and repair if needed
            if not polygon.is_valid:
                polygon = polygon.buffer(0)
            
            return polygon if polygon.is_valid else None
        except Exception as e:
            logger.warning(f"Failed to create polygon: {e}")
            return None
    
    @classmethod
    def _parse_coordinates(cls, coord_text: str) -> list[tuple[float, float]]:
        """
        Parse KML coordinate string into list of (lon, lat) tuples.
        
        KML format: "lon,lat,alt lon,lat,alt ..."
        """
        coords = []
        # Split by whitespace and parse each coordinate tuple
        for coord_str in coord_text.strip().split():
            parts = coord_str.strip().split(",")
            if len(parts) >= 2:
                try:
                    lon = float(parts[0])
                    lat = float(parts[1])
                    coords.append((lon, lat))
                except ValueError:
                    continue
        return coords
    
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

