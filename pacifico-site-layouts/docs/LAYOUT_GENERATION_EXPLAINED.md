# Layout Generation – Architecture & Algorithms

> Last updated: November 2025

This document explains the terrain-aware layout generation system, covering architecture, algorithms, and configuration options.

---

## 1. Architecture Overview

### 1.1 Core Services

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Layout Generation Flow                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────┐    ┌──────────────┐    ┌────────────────────────────┐  │
│  │ API Layer   │ -> │ DEM Service  │ -> │ TerrainAwareLayoutGenerator│  │
│  │ (layouts.py)│    │              │    │                            │  │
│  └─────────────┘    │ Slope Service│    │ - Asset Placement          │  │
│                     │              │    │ - Road Generation          │  │
│                     │ Terrain      │    │ - Cut/Fill Calculation     │  │
│                     │ Analysis     │    │                            │  │
│                     └──────────────┘    └────────────────────────────┘  │
│                                                                          │
│  ┌─────────────┐    ┌──────────────┐    ┌────────────────────────────┐  │
│  │ Export Svc  │    │ SQS Worker   │    │ ExclusionZone Model        │  │
│  │ (PDF/KMZ/   │    │ (async jobs) │    │ (constraints)              │  │
│  │  GeoJSON)   │    │              │    │                            │  │
│  └─────────────┘    └──────────────┘    └────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Service Responsibilities

| Service | File | Purpose |
|---------|------|---------|
| **Layout API** | `api/layouts.py` | POST `/generate`, `/generate-variants`, GET `/{id}`, `/{id}/status` |
| **Export API** | `api/exports.py` | GeoJSON, KMZ, PDF, CSV exports with S3 presigned URLs |
| **DEM Service** | `services/dem_service.py` | Fetch DEM from USGS 3DEP via `py3dep`, cache in S3 |
| **Slope Service** | `services/slope_service.py` | Compute slope rasters from DEM, cache results |
| **Terrain Analysis** | `services/terrain_analysis_service.py` | Curvature, aspect, roughness, suitability scoring |
| **Terrain Viz** | `services/terrain_visualization_service.py` | Contours, buildable area polygons, slope heatmaps |
| **Layout Generator** | `services/terrain_layout_generator.py` | Core algorithm: placement, roads, earthwork |
| **KML Parser** | `services/kml_parser.py` | Parse `.kml`/`.kmz` to Shapely polygons |

---

## 2. Layout Generation Pipeline

### 2.1 Request Flow

1. **API receives request** (`POST /api/layouts/generate`)
   - Validates site ownership and boundary
   - Determines sync vs async mode (config: `ENABLE_ASYNC_LAYOUT_GENERATION`)

2. **Terrain data acquisition**
   - DEM fetched via `DEMService.get_dem_for_site()` (10m or 30m resolution)
   - Slope computed via `SlopeService.get_slope_for_site()`
   - Enhanced metrics via `TerrainAnalysisService.analyze_terrain()`:
     - Aspect (slope direction)
     - Curvature (concavity/convexity)
     - Plan curvature
     - Surface roughness

3. **Suitability scoring**
   - Per-asset-type suitability arrays computed
   - Considers slope, curvature, roughness weights per asset type

4. **Exclusion zones fetched**
   - `_fetch_exclusion_zones()` retrieves zones with:
     - Hard exclusions (cost_multiplier >= 100)
     - Allowances (cost_multiplier < 1.0 reduces pathfinding cost)
     - Buffers applied in degrees

5. **Layout generation** (`TerrainAwareLayoutGenerator.generate()`)
   - Asset placement with terrain constraints
   - Road network generation with A* pathfinding
   - Cut/fill volume calculation

6. **Response assembly**
   - GeoJSON feature collection created
   - Asset and road records persisted to DB
   - Response returned (or status updated for async)

---

## 3. Asset Placement Algorithm

### 3.1 Slope Limits by Asset Type

| Asset Type | Max Slope | Optimal Slope | Notes |
|------------|-----------|---------------|-------|
| Solar Array | 10° | 5° | Trackers work best on gentler slopes |
| Battery | 4° | 2° | BESS needs level ground |
| Generator | 5° | 3° | Equipment requires flat pads |
| Substation | 3° | 1° | Critical infrastructure, must be very level |

### 3.2 Asset Configuration

```python
ASSET_CONFIGS = {
    "solar_array": {
        "capacity_range": (100, 500),  # kW per unit
        "weight": 0.6,                  # Selection probability
        "footprint": (30, 20),          # meters (length x width)
        "pad_size_m": 35,               # Grading pad size
    },
    "battery": {
        "capacity_range": (50, 200),
        "weight": 0.2,
        "footprint": (15, 10),
        "pad_size_m": 20,
    },
    # ... generator, substation
}
```

### 3.3 Placement Strategies (D-05)

| Strategy | Spacing | Slope Weight | Proximity Weight | Description |
|----------|---------|--------------|------------------|-------------|
| **Balanced** | 15m | 0.65 | 0.15 | Default: balance capacity, earthwork, access |
| **Density** | 10m | 0.50 | 0.15 | Maximize kW/ha, may increase earthwork |
| **Low Earthwork** | 20m | 0.80 | 0.05 | Minimize cut/fill, may reduce capacity |
| **Clustered** | 12m | 0.45 | 0.40 | Group assets tightly, minimize roads |

### 3.4 Placement Process

1. **Substation placed first** at flattest region centroid
2. **Poisson-disk sampling** generates well-distributed candidates (if enabled)
3. **Multi-factor scoring** for each candidate position:
   - Slope score: `exp(-slope / optimal_slope)` with penalty above optimal
   - Proximity score: Distance to hub (softer falloff with sqrt)
   - Suitability score: Pre-computed terrain suitability
   - Aspect score: South-facing preferred for solar
   - Curvature score: Penalizes ridges/valleys

4. **Optimal rotation** computed from terrain aspect (solar arrays align perpendicular to slope)

---

## 4. Road Network Generation

### 4.1 Multi-Tier Road Hierarchy

| Tier | Class | Purpose |
|------|-------|---------|
| Primary | `spine` | Site entry point → Substation |
| Secondary | `secondary` | MST connections biased toward spine |
| Tertiary | `tertiary` | Local connections for remote assets |

### 4.2 Cost Surface

The A* pathfinding uses a cost surface derived from:

```python
# Base cost from slope
slope_ratio = slope_array / max_slope_for_road  # ~5.7° for 10% grade
cost_surface = 1 + np.power(np.clip(slope_ratio, 0, 5), 3)

# Curvature penalties
cost_surface[ridges] *= (1 + curvature * 20)    # Ridge penalty
cost_surface[gullies] *= (1 + abs(curvature) * 10)  # Gully penalty

# Allowance zones (reduces cost where permitted)
cost_surface *= allowance_mask

# Steep slopes (>25°) get very high but finite cost
cost_surface[slope > 25] = 10000.0
```

### 4.3 A* Pathfinding

- **Heuristic**: Euclidean distance × median cost × 0.9 (slightly admissible)
- **Budget ceiling**: 500km equivalent travel on flat ground
- **8-connected neighbors** with diagonal moves costing √2×
- **3 retry levels** with progressively relaxed thresholds:
  - Attempt 0: threshold 5000
  - Attempt 1: threshold 10000
  - Attempt 2: threshold 20000
- **Fallback**: Direct line if all pathfinding fails

### 4.4 MST vs Star Topology

- **MST (Minimum Spanning Tree)**: Used for BALANCED, DENSITY, CLUSTERED
  - Prim's algorithm with terrain-weighted distances
  - Spine connections biased (0.8× cost factor)
  - Minimizes total road length

- **Star (Hub-and-Spoke)**: Used for LOW_EARTHWORK
  - Direct connections from hub to each asset
  - May be shorter for sparse layouts

### 4.5 Path Optimization

- **Douglas-Peucker smoothing**: ~1m tolerance (0.00001° for geographic CRS)
- **Stationing**: Points generated every 25m with:
  - Station distance (m)
  - X, Y coordinates
  - Elevation (m)
  - Grade (%) between stations

---

## 5. Earthwork Calculation

### 5.1 Asset Pad Earthwork

For each asset:
1. Define pad extent based on `pad_size_m` config
2. Extract DEM within pad area
3. Target elevation = asset center elevation
4. Calculate volume: `dz * cell_area_m²`
   - Positive dz = cut (remove material)
   - Negative dz = fill (add material)

### 5.2 Road Corridor Earthwork

1. **Buffer road geometry** by road width (default 5m)
2. **Rasterize corridor** to identify affected pixels
3. **Sample centerline** densely for KDTree lookup
4. **For each pixel in corridor**:
   - Find nearest centerline point
   - Target Z = centerline elevation (flat road cross-section)
   - Calculate cut/fill from DEM difference

### 5.3 Output Structure

```python
@dataclass
class CutFillResult:
    cut_volume_m3: float       # Asset pad cut
    fill_volume_m3: float      # Asset pad fill
    road_cut_m3: float         # Road corridor cut
    road_fill_m3: float        # Road corridor fill
    per_asset: list[dict]      # Per-asset breakdown
    per_road: list[dict]       # Per-road breakdown

    @property
    def net_balance_m3(self) -> float:
        """Positive = excess cut (export), negative = need import"""
        return self.total_cut_m3 - self.total_fill_m3
```

---

## 6. Exclusion Zones

### 6.1 Zone Types

| Type | Color | Default Buffer | Use Case |
|------|-------|----------------|----------|
| Environmental | Blue | 0m | Wetlands, water bodies, protected areas |
| Regulatory | Red | 0m | Setbacks, easements, ROW |
| Infrastructure | Orange | 10m | Existing utilities, buildings |
| Safety | Yellow | 25m | Generator noise/emissions buffer |
| Custom | Gray | 0m | User-defined constraints |

### 6.2 Zone Processing

- **Hard exclusions**: `cost_multiplier >= 100` → assets cannot be placed
- **Allowances**: `cost_multiplier < 1.0` → reduced pathfinding cost
- **Penalties**: `1.0 < cost_multiplier < 100` → increased pathfinding cost

---

## 7. Export Formats

| Format | Content | Service Method |
|--------|---------|----------------|
| **GeoJSON** | Complete layout with all properties | `ExportService.generate_geojson()` |
| **KMZ** | Google Earth compatible with styles | `ExportService.generate_kmz()` |
| **PDF** | Summary report with statistics | `ExportService.generate_pdf()` |
| **CSV** | Tabular asset/road data | `ExportService.generate_csv()` |

All exports:
- Upload to S3 with 1-hour expiry
- Return presigned download URL
- Include site and layout metadata

---

## 8. API Reference

### 8.1 Layout Generation

```
POST /api/layouts/generate
{
  "site_id": "uuid",
  "target_capacity_kw": 1000,
  "use_terrain": true,
  "dem_resolution_m": 10
}
```

### 8.2 Variant Generation (D-05)

```
POST /api/layouts/generate-variants
{
  "site_id": "uuid",
  "target_capacity_kw": 1000,
  "variant_strategies": ["balanced", "density", "low_earthwork", "clustered"]
}
```

### 8.3 Status Polling (Async)

```
GET /api/layouts/{layout_id}/status
→ { "status": "processing", "progress_pct": 60, "stage": "roads" }
```

### 8.4 Exports

```
GET /api/layouts/{id}/export/geojson
GET /api/layouts/{id}/export/kmz
GET /api/layouts/{id}/export/pdf
GET /api/layouts/{id}/export/csv
→ { "download_url": "https://s3...", "filename": "layout_xxx.ext" }
```

---

## 9. Configuration

### 9.1 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_TERRAIN` | `true` | Enable terrain-aware placement |
| `ENABLE_ASYNC_LAYOUT_GENERATION` | `false` | Use SQS worker for generation |
| `AWS_S3_BUCKET_NAME` | — | S3 bucket for DEM/slope cache and exports |
| `DEM_CACHE_TTL_DAYS` | `30` | DEM cache duration |

### 9.2 Terrain Limits

```python
MAX_ROAD_GRADE_PCT = 10.0  # Maximum road grade percentage
MIN_SPACING_M = 15.0       # Minimum asset spacing (varies by strategy)
```

---

## 10. Future Enhancements

See `gapimplement.md` for the phased roadmap:

- **Phase 2**: Regulatory data integration (auto-populate exclusion zones)
- **Phase 3**: Interactive asset editing with local recompute
- **Phase 4**: Real-time progress tracking with stage indicators
- **Phase 5**: Compliance rules engine, additional asset types, GIS integration
