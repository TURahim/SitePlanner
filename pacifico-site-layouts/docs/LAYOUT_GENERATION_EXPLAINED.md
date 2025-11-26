# How Layout Generation Works

**A Plain-English Guide to Pacifico's Asset Placement & Road Routing Algorithms**

---

## Table of Contents

1. [Overview](#overview)
2. [Generation Modes](#generation-modes)
3. [Step 1: Getting Terrain Data](#step-1-getting-terrain-data)
4. [Step 2: Computing Terrain Metrics](#step-2-computing-terrain-metrics)
5. [Step 3: Placing Assets](#step-3-placing-assets)
6. [Step 4: Generating Roads](#step-4-generating-roads)
7. [Step 5: Calculating Cut/Fill Volumes](#step-5-calculating-cutfill-volumes)
8. [Layout Strategies (D-05)](#layout-strategies-d-05)
9. [Exclusion Zones (D-03)](#exclusion-zones-d-03)
10. [Async Processing (Phase C)](#async-processing-phase-c)
11. [Why We Chose These Approaches](#why-we-chose-these-approaches)
12. [Configuration Reference](#configuration-reference)

---

## Overview

When you click "Generate Layout" in Pacifico, the system automatically:

1. **Gets elevation data** for your site from USGS satellites
2. **Calculates terrain metrics** (slope, aspect, curvature, roughness)
3. **Computes suitability scores** for each asset type
4. **Places infrastructure** using intelligent heuristics respecting terrain constraints
5. **Routes access roads** between all equipment, preferring flatter paths
6. **Estimates earthwork** (cut/fill volumes for pads and road corridors)

The entire process typically takes 5-30 seconds depending on site size and whether terrain data is cached.

---

## Generation Modes

### Mode 1: Dummy Layout (Fast, No Terrain)
- Used for quick testing or when terrain data isn't available
- Places assets in a simple grid pattern
- Roads are straight lines between assets
- **Good for:** Quick prototyping, demos, areas without USGS coverage

### Mode 2: Terrain-Aware Layout (Production)
- Uses real elevation data from USGS 3DEP
- Computes comprehensive terrain analysis (slope, aspect, curvature, roughness)
- Places assets only on sufficiently flat ground with optimal orientation
- Roads follow paths that avoid steep slopes using A* pathfinding
- Calculates actual earthwork volumes for pads and road corridors
- **Good for:** Real site planning, feasibility studies, cost estimation

### Mode 3: Layout Variants (D-05)
- Generates multiple layouts with different optimization strategies
- Allows comparison across metrics (capacity, earthwork, road length)
- Returns "best" variant for each category
- **Good for:** Trade-off analysis, stakeholder presentations

---

## Step 1: Getting Terrain Data

### What We Fetch
We download a **Digital Elevation Model (DEM)** — essentially a grid of elevation values covering your site.

```
Example: A 500m × 500m site at 10m resolution = 50 × 50 grid = 2,500 elevation points
```

### Where It Comes From
**USGS 3DEP (3D Elevation Program)** — Free, high-quality elevation data covering the entire United States.

| Resolution | Accuracy | Coverage |
|------------|----------|----------|
| 10 meters  | ±1-2m vertical | Most of US |
| 30 meters  | ±3-5m vertical | All of US |

### How Caching Works
Elevation data is cached in Amazon S3 to avoid re-downloading:

```
First layout for Site X:  ~15-30 seconds (downloads DEM)
Second layout for Site X: ~2-5 seconds (uses cached data)
```

**Cache location:** `s3://pacifico-layouts-dev-site-outputs/terrain/{site_id}/dem.tif`

The `TerrainCache` database table tracks cached terrain files by site and terrain type (elevation, slope).

### Why USGS 3DEP?
| Consideration | USGS 3DEP | Alternative (Google/Bing) |
|---------------|-----------|---------------------------|
| Cost | Free | $0.005-0.01 per request |
| Coverage | US only | Global |
| Resolution | 10-30m | 10-30m |
| Reliability | Excellent | API rate limits |
| License | Public domain | Commercial restrictions |

For US sites, USGS 3DEP is the clear winner. For international sites, SRTM (NASA's free global elevation data) can be added as a fallback.

---

## Step 2: Computing Terrain Metrics

### Enhanced Terrain Analysis (Phase E)

Beyond basic slope, we compute multiple terrain derivatives:

| Metric | Description | Use |
|--------|-------------|-----|
| **Slope** | Steepness in degrees | Primary placement constraint |
| **Aspect** | Direction slope faces (0-360°) | Solar panel orientation |
| **Profile Curvature** | Convexity/concavity | Drainage, stability |
| **Plan Curvature** | Water flow convergence | Drainage design |
| **Roughness** | Local terrain variability | Construction difficulty |

### How Slope & Aspect Are Calculated

We use **Horn's method** (Sobel-like 3×3 kernels) for better accuracy than simple gradients:

```python
# dz/dx kernel (weighted differences)
kernel_x = [
    [-1, 0, 1],
    [-2, 0, 2],
    [-1, 0, 1]
] / (8 × cell_size)

# Similar for dz/dy
# Slope = arctan(√(dx² + dy²))
# Aspect = arctan2(-dzdx, dzdy) → converted to 0-360°
```

### Visual Example

```
Elevation Grid (meters):         Calculated Slope (degrees):
┌────┬────┬────┐                 ┌────┬────┬────┐
│100 │102 │105 │                 │ 3° │ 5° │ 6° │
├────┼────┼────┤        →        ├────┼────┼────┤
│101 │103 │108 │                 │ 4° │ 7° │ 9° │
├────┼────┼────┤                 ├────┼────┼────┤
│100 │105 │115 │                 │ 6° │ 10°│ 14°│
└────┴────┴────┘                 └────┴────┴────┘
```

### DEM Smoothing

Before computing derivatives, we apply **Gaussian smoothing** (sigma=1.0) to reduce DEM noise:

```python
# Reduces artifacts from sensor noise / data compression
dem_smooth = gaussian_filter(dem, sigma=1.0)
```

### Composite Suitability Scoring

Each cell gets a suitability score (0-1) combining:

| Component | Weight | Description |
|-----------|--------|-------------|
| Slope | 65% | Primary factor - exponential decay above optimal |
| Curvature | 15% | Penalty for ridges/valleys |
| Aspect | 10% | South-facing preferred for solar |
| Roughness | 10% | Penalty for irregular terrain |

```python
suitability = (
    0.65 * slope_score +
    0.10 * aspect_score +
    0.15 * curvature_score +
    0.10 * roughness_score
)
```

---

## Step 3: Placing Assets

### Asset Types & Slope Limits

Different equipment has different terrain requirements (Phase E tightened limits):

| Asset Type | Max Slope | Optimal Slope | Why |
|------------|-----------|---------------|-----|
| **Substation** | 3° | 1° | Critical infrastructure, must be very level |
| **Battery Storage** | 4° | 2° | Heavy containers need flat, stable pads |
| **Generator** | 5° | 3° | Engines require level mounting |
| **Solar Array** | 10° | 5° | Tracking systems work best on gentler slopes |

### The Placement Algorithm

We use a **multi-factor scoring heuristic** with intelligent prioritization:

```
1. FIRST: Place substation at the flattest spot
   └─ Find flattest 10% of cells
   └─ Pick the centroid of this flat region
   
2. THEN: Place batteries & generators near substation
   └─ Score each candidate: slope + proximity + suitability
   └─ Use exponential decay for slope scoring
   
3. FINALLY: Fill remaining capacity with solar arrays
   └─ Consider aspect (prefer south-facing)
   └─ Apply optimal rotation based on terrain
```

### Poisson-Disk Sampling (Phase E)

For better spatial distribution, we use **Poisson-disk sampling** instead of random candidate selection:

```
Benefits:
- Uniform distribution (no clustering)
- Respects minimum spacing naturally
- More realistic industrial layouts
```

```python
# Generate well-distributed candidates
candidates = poisson_disk_sample(
    buildable_mask,
    min_spacing_cells=15m / cell_size,
    num_candidates=num_assets * 3,  # Extra candidates for selection
)
```

### Enhanced Scoring (Phase E)

Each candidate position is scored using:

```python
# Exponential decay for slope (MUCH stronger preference for flat)
slope_score = exp(-slope / optimal_slope)

# Additional penalty above optimal
if slope > optimal:
    penalty = (slope - optimal) / (max - optimal) * 0.3
    slope_score -= penalty

# Softer proximity curve
proximity_score = 1 - sqrt(distance / max_distance)

# Combine with strategy-specific weights
combined = (
    slope_weight * slope_score +
    proximity_weight * proximity_score +
    suitability_weight * combined_suitability
)
```

### Footprint Geometry & Rotation

Assets have **true rectangular footprints** with rotation:

```python
@dataclass
class PlacedAsset:
    footprint_length_m: float = 20.0
    footprint_width_m: float = 20.0
    rotation_deg: float = 0.0  # Optimal orientation
    
    @property
    def footprint_polygon(self) -> Polygon:
        """Get the actual footprint as a rotated rectangle."""
        rect = box(-half_l, -half_w, half_l, half_w)
        if self.rotation_deg != 0:
            rect = rotate(rect, self.rotation_deg)
        return translate(rect, self.position.x, self.position.y)
```

Solar arrays are rotated based on terrain aspect:
- South-facing slopes (180°) → panels face south (optimal)
- East/West slopes → panels rotated 90° to align

### Spacing Enforcement

All assets must be at least **10-20 meters apart** (varies by strategy):

| Strategy | Min Spacing |
|----------|-------------|
| Balanced | 15m |
| High Density | 10m |
| Low Earthwork | 20m |
| Clustered | 12m |

### Buildable Area Analysis

Before placement, we calculate what percentage of the site is buildable:

```
Example output:
  substation: 15.2% buildable (slope < 3°)
  battery:    18.7% buildable (slope < 4°)
  generator:  23.5% buildable (slope < 5°)
  solar:      58.3% buildable (slope < 10°)
```

---

## Step 4: Generating Roads

### Road Network Topology

We support two topologies:

**Star Topology (Hub-and-Spoke)**
```
        [Solar 1]
             \
              \
[Battery] ----[Substation]---- [Generator]
              /
             /
        [Solar 2]
```

**MST Topology (Minimum Spanning Tree)** — Phase E
```
[Solar 1]---[Battery]
              |
        [Substation]
              |
[Solar 2]---[Generator]
```

MST minimizes total road length while ensuring all assets are connected.

### A* Pathfinding Algorithm

Instead of straight lines, we use **A* (A-star) pathfinding** to find routes that avoid steep slopes:

```
How A* works:

1. Start at hub asset
2. Look at all neighboring cells (8-connected)
3. Score each: cost = (distance traveled) + (estimated remaining distance)
4. Expand the cheapest option
5. Repeat until destination reached
```

### Enhanced Cost Surface (Phase E)

The cost to traverse a cell depends on slope with **aggressive penalties**:

```python
# Base cost with cubic scaling
slope_ratio = slope / max_grade
cost = 1 + slope_ratio³

# 5x penalty for slopes > 80% of max
if slope > max_grade * 0.8:
    cost *= 5

# 500x for slopes > 120% of max
if slope > max_grade * 1.2:
    cost = 500

# Nearly impassable for >15°
if slope > 15:
    cost = 10000
```

| Slope | Cost Multiplier | Effect |
|-------|-----------------|--------|
| 0° (flat) | 1.0x | Preferred |
| 3° | ~1.3x | Acceptable |
| 5.7° (10% grade) | ~2x | Limit approach |
| 8° | ~500x | Nearly prohibited |
| 15°+ | 10000x | Impassable |

### MST Road Generation (Phase E)

When `use_mst_roads=True`, we use **Prim's algorithm**:

```python
1. Build distance matrix with slope-weighted penalties
2. Start from hub (substation)
3. Greedily add cheapest edge to unconnected asset
4. Repeat until all assets connected
```

This typically reduces total road length by 15-30% compared to star topology.

### Road Grade Reporting

For each road segment, we report the **maximum grade percentage**:

```
Access Road 1: 127.3m, max grade 4.2%
Access Road 2: 89.5m, max grade 7.8%
```

---

## Step 5: Calculating Cut/Fill Volumes

### What Is Cut/Fill?

When you build on uneven ground, you need to either:
- **Cut** (excavate) — remove dirt from high spots
- **Fill** (backfill) — add dirt to low spots

The goal is a **level pad** for each piece of equipment.

### Asset Pad Earthwork

For each asset:

```
1. Define a grading pad (square area around the asset)
   - Substation: 25m × 25m
   - Battery: 20m × 20m
   - Generator: 15m × 15m
   - Solar: 35m × 35m

2. Set target elevation = elevation at asset center

3. For each cell in the pad:
   If existing_elevation > target: CUT (remove dirt)
   If existing_elevation < target: FILL (add dirt)

4. Volume = elevation_difference × cell_area
```

### Road Corridor Earthwork (Phase E)

We now calculate cut/fill for **road corridors** too:

```python
def compute_road_earthwork():
    for road in roads:
        # Sample elevations along road centerline
        # Calculate target grade (linear from start to end)
        # Compute cut/fill per segment
        # Area = road_width × segment_length
```

### Enhanced CutFillResult

```python
@dataclass
class CutFillResult:
    cut_volume_m3: float      # Asset pad cut
    fill_volume_m3: float     # Asset pad fill
    road_cut_m3: float        # Road corridor cut
    road_fill_m3: float       # Road corridor fill
    per_asset: list[dict]     # Per-asset breakdown
    
    @property
    def total_cut_m3(self):
        return self.cut_volume_m3 + self.road_cut_m3
    
    @property
    def net_balance_m3(self):
        """Positive = excess cut (export), Negative = need import"""
        return self.total_cut_m3 - self.total_fill_m3
```

### Cost Implications

Cut/fill volumes directly impact construction cost:

| Volume | Typical Cost | Time |
|--------|--------------|------|
| 100 m³ | $500-1,500 | 1 day |
| 1,000 m³ | $5,000-15,000 | 1 week |
| 10,000 m³ | $50,000-150,000 | 1 month |

---

## Layout Strategies (D-05)

### Four Optimization Strategies

Generate multiple layouts with different objectives using `/api/layouts/generate-variants`:

| Strategy | Objective | Trade-offs |
|----------|-----------|------------|
| **Balanced** | Balance all metrics | Good all-around |
| **High Density** | Maximize kW/hectare | May increase earthwork |
| **Low Earthwork** | Minimize cut/fill | May reduce capacity |
| **Clustered** | Group assets tightly | Minimizes infrastructure |

### Strategy-Specific Configurations

```python
STRATEGY_CONFIGS = {
    "balanced": {
        "min_spacing_m": 15.0,
        "slope_weight": 0.65,
        "proximity_weight": 0.15,
        "capacity_multiplier": 1.0,
        "use_poisson_disk": True,
        "use_mst_roads": True,
    },
    "density": {
        "min_spacing_m": 10.0,
        "slope_weight": 0.50,
        "capacity_multiplier": 1.3,  # Higher capacity per asset
        "solar_weight": 0.8,         # More solar arrays
    },
    "low_earthwork": {
        "min_spacing_m": 20.0,
        "slope_weight": 0.80,        # Strong flat preference
        "capacity_multiplier": 0.8,
    },
    "clustered": {
        "min_spacing_m": 12.0,
        "proximity_weight": 0.40,    # Cluster near hub
        "use_poisson_disk": False,   # Grid-like for clusters
    },
}
```

### Comparison Analysis

The variant response includes comparison data:

```json
{
  "comparison": {
    "best_capacity_id": "uuid-of-density-variant",
    "best_earthwork_id": "uuid-of-low-earthwork-variant",
    "best_road_network_id": "uuid-of-mst-variant",
    "metrics_table": [...]
  }
}
```

---

## Exclusion Zones (D-03)

### What Are Exclusion Zones?

User-defined areas where assets **cannot** be placed:

| Zone Type | Default Buffer | Color | Examples |
|-----------|----------------|-------|----------|
| Environmental | 0m | Blue | Wetlands, water bodies |
| Regulatory | 0m | Red | Setbacks, easements |
| Infrastructure | 10m | Orange | Existing utilities |
| Safety | 25m | Yellow | Noise/emissions buffers |
| Custom | 0m | Gray | User-defined |

### How They're Applied

```python
# D-03: Create exclusion mask from polygons
exclusion_mask = np.zeros((height, width), dtype=bool)
for zone in exclusion_zones:
    if zone.buffer_m > 0:
        zone = zone.buffer(buffer_deg)  # Apply buffer
    exclusion_mask |= rasterize(zone)

# Buildable = within boundary AND not excluded AND slope OK
buildable = boundary_mask & ~exclusion_mask & (slope < max_slope)
```

### Drawing Exclusion Zones

The frontend uses **Leaflet Draw** for polygon creation:
1. User draws polygon on map
2. Selects zone type from modal
3. Zone saved via POST `/api/exclusion-zones`
4. Next layout generation respects the zone

---

## Async Processing (Phase C)

### Why Async?

For large sites, layout generation can take 30+ seconds. Async processing:
- Returns immediately with a job ID
- Processes in background worker
- Frontend polls for status

### SQS Job Queue

```
┌─────────┐     ┌─────────┐     ┌──────────┐
│ Frontend│────▶│ FastAPI │────▶│ SQS Queue│
└─────────┘     └─────────┘     └──────────┘
                                      │
                                      ▼
                               ┌──────────┐
                               │ Worker   │
                               │ Container│
                               └──────────┘
```

### Status Polling

```
POST /api/layouts/generate  →  { "layout_id": "uuid", "status": "queued" }
GET /api/layouts/{id}/status  →  { "status": "processing" }
GET /api/layouts/{id}/status  →  { "status": "completed", "total_capacity_kw": 1234 }
```

### Enable Async Mode

```bash
# In environment or terraform.tfvars
ENABLE_ASYNC_LAYOUT_GENERATION=true
```

---

## Why We Chose These Approaches

### Design Principles

1. **Speed over perfection** — A good answer in 5 seconds beats a perfect answer in 5 minutes
2. **Graceful degradation** — If terrain data fails, fall back to dummy placement
3. **Cache everything** — Never fetch the same data twice
4. **Transparent constraints** — Report why assets couldn't be placed

### Trade-offs Made

| Decision | What We Chose | Alternative | Why |
|----------|---------------|-------------|-----|
| DEM source | USGS 3DEP | Commercial APIs | Free, reliable, sufficient quality |
| Slope calculation | Horn's method | Simple gradient | Better accuracy for rough terrain |
| Asset placement | Multi-factor scoring | Genetic algorithm | Speed, predictability |
| Road routing | A* pathfinding | Simple lines | Better routes, avoids steep terrain |
| Road topology | Star + MST option | Fixed topology | Flexibility for different strategies |
| Cut/fill method | Per-cell volume | Full grading model | Fast approximation, sufficient accuracy |

### What's Not Included (Yet)

Potential future enhancements:

- **Flood zone avoidance** — Integrate FEMA flood maps
- **Geotechnical constraints** — Soil bearing capacity, bedrock depth
- **Utility corridors** — Route power lines along roads
- **Vegetation clearing** — Estimate tree removal costs
- **Access point optimization** — Optimal site entrance location
- **Simulated annealing** — Local search optimization (code exists, not yet integrated)

---

## Configuration Reference

### Slope Limits (degrees)

```python
SLOPE_LIMITS = {
    "solar_array": 10.0,   # Reduced from 15° - trackers work best on gentler slopes
    "battery": 4.0,        # Reduced from 5° - BESS needs level ground
    "generator": 5.0,      # Kept at 5° - generators need flat pads
    "substation": 3.0,     # Reduced from 5° - critical infrastructure
}

SLOPE_OPTIMAL = {
    "solar_array": 5.0,    # Prefer slopes under 5°
    "battery": 2.0,        # Prefer slopes under 2°
    "generator": 3.0,      # Prefer slopes under 3°
    "substation": 1.0,     # Prefer nearly flat
}
```

### Asset Configurations

```python
ASSET_CONFIGS = {
    "solar_array": {
        "capacity_range": (100, 500),  # kW per unit
        "weight": 0.6,                  # 60% of assets
        "footprint": (30, 20),          # meters
        "pad_size_m": 35,               # grading pad
    },
    "battery": {
        "capacity_range": (50, 200),
        "weight": 0.2,                  # 20% of assets
        "footprint": (15, 10),
        "pad_size_m": 20,
    },
    "generator": {
        "capacity_range": (100, 300),
        "weight": 0.15,                 # 15% of assets
        "footprint": (10, 8),
        "pad_size_m": 15,
    },
    "substation": {
        "capacity_range": (500, 2000),
        "weight": 0.05,                 # 5% of assets (1 per layout)
        "footprint": (20, 15),
        "pad_size_m": 25,
    },
}
```

### Road Parameters

```python
MIN_SPACING_M = 15.0        # Default minimum distance between assets
MAX_ROAD_GRADE_PCT = 10.0   # Maximum acceptable road grade (~5.7°)
ROAD_WIDTH_M = 5.0          # Standard access road width
```

### Terrain Analysis Parameters

```python
DEFAULT_RESOLUTION_M = 10    # 10m resolution (highest available)
BUFFER_DEGREES = 0.001       # ~100m buffer around site boundary
SMOOTHING_SIGMA = 1.0        # Gaussian smoothing for DEM noise reduction
```

### Suitability Scoring Weights

```python
SuitabilityConfig = {
    "slope_weight": 0.65,       # Primary factor
    "aspect_weight": 0.10,      # For solar orientation
    "curvature_weight": 0.15,   # Penalize ridges/valleys
    "roughness_weight": 0.10,   # Penalize irregular terrain
    "max_curvature": 0.1,       # Max acceptable curvature
    "max_roughness": 5.0,       # Max acceptable roughness
}
```

---

## Summary

Pacifico's layout generation combines:

1. **Free government elevation data** (USGS 3DEP) with S3 caching
2. **Comprehensive terrain analysis** (slope, aspect, curvature, roughness)
3. **Composite suitability scoring** for intelligent asset placement
4. **Poisson-disk sampling** for better spatial distribution
5. **A* pathfinding** with slope-weighted cost surface
6. **MST road optimization** for shorter networks
7. **Complete earthwork estimation** (pads + road corridors)
8. **Multiple layout strategies** for trade-off analysis
9. **Exclusion zone support** for user-defined constraints
10. **Async processing** for large sites

The result is a realistic, terrain-aware site layout in under 30 seconds — giving developers actionable feasibility data without expensive manual surveys.

---

*Document version: 2.0*  
*Last updated: November 26, 2025*  
*Author: Pacifico Engineering Team*
