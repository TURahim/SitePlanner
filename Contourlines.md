Contour Line Implementation Bug Research Report
Executive Summary
This report documents the complete implementation of contour line visualization in the Pacifico Site Layouts application. It provides a roadmap for debugging contour-related issues by identifying all relevant files, data flow, and potential bug locations.
1. Architecture Overview
The contour line feature follows a client-server architecture:
┌─────────────────────────────────────────────────────────────────────────────┐│                              DATA FLOW                                       │├─────────────────────────────────────────────────────────────────────────────┤│                                                                              ││  Frontend (React)              Backend (FastAPI)             External        ││  ═══════════════              ═══════════════════          ══════════════   ││                                                                              ││  SiteDetailPage.tsx            terrain.py (API)             USGS 3DEP       ││       │                             │                           │           ││       │ GET /terrain/contours       │                           │           ││       ├─────────────────────────────►                           │           ││       │                             │                           │           ││       │                    terrain_visualization_service.py     │           ││       │                             │                           │           ││       │                    dem_service.py ◄─────────────────────┤           ││       │                             │ (fetch DEM if not cached)             ││       │                             │                           │           ││       │                    S3 Cache (GeoTIFF)                   │           ││       │                             │                           │           ││       │                    skimage.measure.find_contours()      │           ││       │                             │                           │           ││       ◄─────────────────────────────┤                           │           ││  GeoJSON Response                   │                           │           ││       │                             │                           │           ││  Leaflet GeoJSON render             │                           │           ││                                                                              │└─────────────────────────────────────────────────────────────────────────────┘
2. File Inventory
2.1 Backend Files
File	Purpose	Key Functions/Classes
backend/app/services/terrain_visualization_service.py	Core contour extraction logic	get_contours(), _extract_contour_at_elevation()
backend/app/api/terrain.py	API endpoint definition	get_contours() endpoint at /api/sites/{site_id}/terrain/contours
backend/app/schemas/terrain.py	Pydantic response schemas	ContoursResponse, ContourFeature
backend/app/services/dem_service.py	DEM data fetching/caching	get_dem_for_site(), get_dem_array()
backend/app/services/slope_service.py	Slope computation (dependency)	get_slope_for_site()
backend/app/services/s3.py	S3 caching operations	download_terrain_file(), upload_terrain_file()
2.2 Frontend Files
File	Purpose	Key Functions/Components
frontend/src/pages/SiteDetailPage.tsx	Map rendering & layer toggle	handleToggleTerrainLayer(), GeoJSON render at lines 1291-1312
frontend/src/pages/SiteDetailPage.css	Contour styling	.contour-tooltip, .contour-legend-line
frontend/src/lib/api.ts	API client	getTerrainContours() function
frontend/src/types/index.ts	TypeScript types	ContoursResponse, TerrainLayerType
3. Critical Code Sections
3.1 Backend: Contour Extraction Algorithm
File: backend/app/services/terrain_visualization_service.py
Lines 189-281: get_contours() method
async def get_contours(    self,    site_id: UUID,    db: AsyncSession,    boundary: Polygon,    interval_m: float = 5.0,) -> dict[str, Any]:
Key operations:
Fetches DEM from S3 cache (line 212-213)
Creates boundary mask (line 220)
Generates contour elevations at intervals (lines 238-241)
Calls _extract_contour_at_elevation() for each level (lines 245-271)
Clips contours to site boundary (lines 259-271)
Lines 283-320: _extract_contour_at_elevation() method - MOST LIKELY BUG LOCATION
def _extract_contour_at_elevation(    self,    dem: np.ndarray,    elevation: float,    transform: Affine,) -> list[list[tuple[float, float]]]:
This method:
Uses skimage.measure.find_contours() (line 298)
Converts pixel coordinates to geographic coordinates (lines 306-311)
⚠️ POTENTIAL BUG AREA - Coordinate Transform (lines 306-311):
for row, col in contour:    # Apply affine transform: x = a*col + b*row + c    x = transform[0] * col + transform[1] * row + transform[2]    y = transform[3] * col + transform[4] * row + transform[5]    coords.append((x, y))
This coordinate transformation from pixel space to geographic space is a common source of bugs:
Row/column order - find_contours returns (row, col) but affine expects different ordering
Affine transform indexing - The transform coefficients mapping may be incorrect
Coordinate system flipping - Y-axis often inverted between image and geographic coordinates
3.2 Backend: Boundary Mask Rasterization
Lines 541-559: _rasterize_boundary() method
def _rasterize_boundary(    self,    boundary: Polygon,    transform: Affine,    shape: tuple[int, int],) -> np.ndarray:
This creates a mask from the site boundary polygon. Bugs here could cause:
Contours appearing outside the site boundary
Empty contour results
Misaligned contours
3.3 Frontend: Contour Rendering
File: frontend/src/pages/SiteDetailPage.tsx
Lines 1291-1312: GeoJSON rendering of contours
{terrainLayers.has('contours') && contoursData && contoursData.features.map((feature, idx) => (  <GeoJSON    key={`contour-${idx}`}    data={feature as GeoJSON.Feature}    style={() => ({      color: '#8b5cf6',      weight: 1.5,      opacity: 0.7,    })}    onEachFeature={(feat, layer) => {      const elev = feat.properties?.elevation_m;      if (elev != null) {        layer.bindTooltip(`${elev.toFixed(0)}m`, {          permanent: false,          direction: 'auto',          className: 'contour-tooltip',        });      }    }}  />))}
Potential frontend bugs:
Key-based re-rendering issues (using index as key)
Tooltip not displaying for certain contours
GeoJSON parsing errors
3.4 Frontend: API Client
File: frontend/src/lib/api.ts
Lines 249-258: getTerrainContours() function
export async function getTerrainContours(  siteId: string,   intervalM: number = 5): Promise<ContoursResponse> {  const response = await api.get<ContoursResponse>(    `/api/sites/${siteId}/terrain/contours`,    { params: { interval_m: intervalM } }  );  return response.data;}
4. Potential Bug Categories
4.1 Coordinate System Issues (HIGHEST PROBABILITY)
Location: terrain_visualization_service.py, lines 306-311
Symptoms:
Contours appear in wrong location (shifted/rotated)
Contours appear mirrored
Contours don't align with site boundary
Investigation steps:
Check affine transform coefficients from DEM profile
Verify row/col vs x/y ordering in find_contours output
Compare contour coordinates to known elevation points
Test with a simple DEM (e.g., linear ramp) where expected contours are predictable
4.2 Empty/Missing Contours
Locations:
terrain_visualization_service.py, lines 227-236 (early return for invalid elevations)
terrain_visualization_service.py, lines 302-303 (skipping contours with <2 points)
terrain_visualization_service.py, lines 259-271 (boundary clipping)
Symptoms:
No contours returned
Partial contours missing
contour_count: 0 in response
Investigation steps:
Check DEM data validity (nodata values, NaN handling)
Verify elevation range calculation (min/max)
Check boundary intersection logic
Log contour counts before and after clipping
4.3 Performance Issues
Location: terrain_visualization_service.py, lines 245-271 (loop over elevations)
Symptoms:
Slow API response (>5s)
Timeout errors
High memory usage
Investigation steps:
Profile the loop over contour elevations
Check DEM array size
Consider caching computed contours
4.4 GeoJSON Format Issues
Locations:
terrain_visualization_service.py, lines 252-269 (feature construction)
schemas/terrain.py, lines 79-102 (ContoursResponse schema)
Symptoms:
Frontend parsing errors
Leaflet rendering failures
TypeScript type mismatches
Investigation steps:
Validate returned GeoJSON against spec
Check LineString vs MultiLineString handling
Verify properties are correctly attached
4.5 Frontend Rendering Issues
Location: SiteDetailPage.tsx, lines 1291-1312
Symptoms:
Contours don't appear on map
Tooltips not working
Layer toggle not responding
Investigation steps:
Check browser console for errors
Verify contoursData state is populated
Inspect Leaflet layer creation
Check CSS .contour-tooltip visibility
5. Dependencies
Backend Dependencies (check requirements.txt)
scikit-image - For measure.find_contours()
rasterio - For GeoTIFF handling and affine transforms
shapely - For geometry operations (LineString, clipping)
numpy - For array operations
py3dep - For USGS 3DEP data fetching
Frontend Dependencies (check package.json)
react-leaflet - For GeoJSON rendering
leaflet - Base mapping library
6. API Endpoint Details
GET /api/sites/{site_id}/terrain/contours
Parameters:
site_id (path): UUID of the site
interval_m (query, optional): Contour interval in meters (default: 5.0, range: 1-100)
Response Schema (ContoursResponse):
{  "site_id": "uuid",  "interval_m": 5.0,  "type": "FeatureCollection",  "features": [    {      "type": "Feature",      "geometry": {        "type": "LineString",  // or "MultiLineString"        "coordinates": [[lng, lat], ...]      },      "properties": {        "elevation_m": 123.0,        "type": "contour"      }    }  ],  "min_elevation_m": 100.0,  "max_elevation_m": 200.0,  "contour_count": 20}
7. Debugging Checklist
Backend Debugging
[ ] Add logging to _extract_contour_at_elevation() to trace coordinate transforms
[ ] Log DEM array shape and bounds before contour extraction
[ ] Log number of raw contours from find_contours() before filtering
[ ] Log contours before and after boundary clipping
[ ] Check for exceptions being silently caught (lines 270-271, 318-320)
Frontend Debugging
[ ] Add console logs in handleToggleTerrainLayer() to trace data loading
[ ] Inspect contoursData in React DevTools
[ ] Check network tab for API response
[ ] Verify GeoJSON structure matches Leaflet expectations
[ ] Test with a known-good GeoJSON to isolate rendering issues
Data Validation
[ ] Verify DEM is being correctly fetched and cached
[ ] Check DEM transform coefficients are correct
[ ] Validate elevation values are realistic for the site location
[ ] Compare boundary coordinates with contour coordinates
8. Quick Reference: Key Lines to Inspect
Issue Type	File	Lines
Coordinate transform bug	terrain_visualization_service.py	306-311
Contour extraction	terrain_visualization_service.py	296-316
Empty results	terrain_visualization_service.py	227-236, 302-303
Clipping issues	terrain_visualization_service.py	259-271
GeoJSON construction	terrain_visualization_service.py	252-269
API endpoint	terrain.py	123-175
Frontend rendering	SiteDetailPage.tsx	1291-1312
Frontend data fetching	SiteDetailPage.tsx	424-427
API client	api.ts	249-258
Type definitions	types/index.ts	259-267
9. Testing Recommendations
Unit test the _extract_contour_at_elevation() method with a known DEM
Integration test the full /terrain/contours endpoint
Visual test comparing rendered contours to expected elevations
Edge case test with flat terrain (no contours), steep terrain (many contours)
Boundary test with irregular site shapes to verify clipping