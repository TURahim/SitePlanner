
import sys
import os

# Add the backend directory to sys.path so we can import app modules
sys.path.append(os.path.join(os.getcwd(), 'pacifico-site-layouts/backend'))

try:
    from app.services.kml_parser import KMLParser
except ImportError as e:
    print(f"ImportError: {e}")
    sys.exit(1)

kml_path = 'pacifico-site-layouts/test-files/testsitereal.kml'

try:
    with open(kml_path, 'rb') as f:
        content = f.read()
        
    print(f"Read {len(content)} bytes from {kml_path}")
    
    geometry, name = KMLParser.parse(content, 'testsitereal.kml')
    
    print(f"Successfully parsed KML.")
    print(f"Name: {name}")
    print(f"Geometry Type: {geometry.geom_type}")
    if geometry.geom_type == 'Polygon':
        print(f"Exterior points: {len(geometry.exterior.coords)}")
        print(f"Bounds: {geometry.bounds}")
    
except Exception as e:
    print(f"Error parsing KML: {e}")
    import traceback
    traceback.print_exc()

