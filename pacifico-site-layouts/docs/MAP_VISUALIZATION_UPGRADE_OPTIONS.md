# Map Visualization Upgrade Options

**Research Document: Upgrading from Simple Markers to Rich Graphical Representations**

---

## Table of Contents

1. [Current State Analysis](#current-state-analysis)
2. [Upgrade Options Overview](#upgrade-options-overview)
3. [Option 1: SVG Footprint Rectangles](#option-1-svg-footprint-rectangles)
4. [Option 2: Custom SVG Icons with Detail](#option-2-custom-svg-icons-with-detail)
5. [Option 3: Canvas-Based Rendering](#option-3-canvas-based-rendering)
6. [Option 4: 3D Visualization with Deck.gl](#option-4-3d-visualization-with-deckgl)
7. [Option 5: Vector Tiles with MapLibre GL](#option-5-vector-tiles-with-maplibre-gl)
8. [Comparison Matrix](#comparison-matrix)
9. [Recommended Approach](#recommended-approach)
10. [Implementation Roadmap](#implementation-roadmap)

---

## Current State Analysis

### What We Have Now

**Assets:**
- Rendered as simple colored circles (24px diameter)
- Created using Leaflet's `L.divIcon` with inline CSS
- Color-coded by type (solar=amber, battery=blue, generator=red, substation=purple)
- Popup shows basic info on click

**Roads:**
- Rendered as simple orange lines (4px width)
- Using Leaflet's `GeoJSON` component
- No styling variation based on grade or type

**Data Available (But Unused):**
```typescript
// Backend sends this for each asset:
{
  position: { type: "Point", coordinates: [lng, lat] },
  footprint_length_m: 30,  // ← NOT USED
  footprint_width_m: 20,   // ← NOT USED
  elevation_m: 150,        // ← NOT USED
  slope_deg: 3.2,          // ← NOT USED
}
```

### Current Limitations

| Issue | Impact |
|-------|--------|
| **No footprint visualization** | Can't see actual equipment size/orientation |
| **No terrain context** | Can't visualize elevation or slope |
| **Generic appearance** | Looks like any mapping app, not a specialized tool |
| **No equipment detail** | Can't distinguish a 500kW solar array from a 100kW one |
| **Limited interactivity** | Only basic popups, no hover effects |
| **No road width** | Roads shown as hairlines regardless of actual width |

---

## Upgrade Options Overview

| Option | Visual Quality | Performance | Complexity | Best For |
|--------|---------------|-------------|------------|----------|
| **1. SVG Footprints** | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ (Medium) | Quick win, actual sizes |
| **2. Custom SVG Icons** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ (Medium) | Industry look |
| **3. Canvas Rendering** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ (High) | Large sites (100+ assets) |
| **4. 3D with Deck.gl** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ (Very High) | Wow factor, elevation viz |
| **5. MapLibre GL** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ (Very High) | Complete rebuild |

---

## Option 1: SVG Footprint Rectangles

### Concept
Instead of showing a dot at the asset center, draw the **actual footprint rectangle** at the correct scale and position.

### Visual Example
```
Current:          Proposed:
    ●                 ┌─────────┐
   (dot)              │ SOLAR   │  ← 30m × 20m rectangle
                      │  ARRAY  │
                      └─────────┘
```

### How It Works

1. **Convert footprint to polygon:**
   - Take center point (lat, lng)
   - Use footprint_length_m × footprint_width_m
   - Calculate corner coordinates using geodesic math
   - Account for rotation/orientation (future enhancement)

2. **Render as GeoJSON polygon:**
   - Style with semi-transparent fill
   - Add border matching asset color
   - Include icon/label at center

### Technical Approach

**Frontend calculation:**
```
Given:
  - Center: (lat, lng)
  - Length: 30m (north-south)
  - Width: 20m (east-west)

Calculate corners using:
  - 1 degree latitude ≈ 111,000 meters
  - 1 degree longitude ≈ 111,000 × cos(latitude) meters

Result: 4 corner coordinates forming a rectangle
```

**Leaflet rendering:**
- Use `L.rectangle()` or `L.polygon()` for each asset
- Apply custom styles per asset type
- Add center marker with icon overlay

### Pros
- ✅ Shows true equipment scale
- ✅ Works with existing Leaflet setup
- ✅ Minimal new dependencies
- ✅ Uses data already available from backend
- ✅ Good performance (simple polygons)

### Cons
- ❌ Rectangles only (no complex shapes)
- ❌ No orientation/rotation support initially
- ❌ Still 2D (no height representation)
- ❌ Manual coordinate math required

### Effort Estimate
- **Development:** 2-3 days
- **Dependencies:** None (pure Leaflet)
- **Risk:** Low

---

## Option 2: Custom SVG Icons with Detail

### Concept
Replace simple colored dots with **detailed SVG icons** that represent each equipment type visually.

### Visual Examples

**Solar Array:**
```svg
┌─────────────────┐
│ ▓▓▓▓ ▓▓▓▓ ▓▓▓▓ │  ← Panel rows
│ ▓▓▓▓ ▓▓▓▓ ▓▓▓▓ │
│ ▓▓▓▓ ▓▓▓▓ ▓▓▓▓ │
└─────────────────┘
     500 kW
```

**Battery Storage:**
```svg
  ┌─────────────┐
  │ ┌──┐ ┌──┐   │  ← Container with battery modules
  │ │██│ │██│   │
  │ │██│ │██│   │
  │ └──┘ └──┘   │
  └─────────────┘
      200 kW
```

**Generator:**
```svg
    ╔═══════╗
    ║ ▄▄▄▄▄ ║  ← Engine housing
    ║ █████ ║
    ║ ◉◉◉◉◉ ║  ← Exhaust vents
    ╚═══════╝
      150 kW
```

**Substation:**
```svg
      ┌─┐
    ╔═╧═╧═╗
    ║ ┌─┐ ║  ← Transformer
    ║ │█│ ║
    ║ └─┘ ║
    ╚═════╝
     2 MW
```

### How It Works

1. **Create detailed SVG files** for each asset type
2. **Size dynamically** based on capacity (larger capacity = larger icon)
3. **Add capacity labels** below/inside icons
4. **Color variations** for status (normal, selected, warning)
5. **Use Leaflet's `L.divIcon`** with embedded SVG

### Technical Approach

**Icon sizing formula:**
```
Base size: 32px (for minimum capacity)
Scale factor: 1 + (capacity / max_capacity) × 0.5
Final size: base_size × scale_factor

Example:
  - 100kW solar: 32px × 1.1 = 35px
  - 500kW solar: 32px × 1.5 = 48px
```

**Implementation:**
- Create SVG sprites or inline SVG components
- Pass capacity to icon generator function
- Apply CSS transforms for hover/selection states

### Pros
- ✅ Professional, industry-standard look
- ✅ Immediately recognizable equipment types
- ✅ Scalable to show relative sizes
- ✅ Good hover/interaction potential
- ✅ Works with existing Leaflet

### Cons
- ❌ Requires design work for each icon
- ❌ Icons don't show true footprint scale
- ❌ May look cluttered with many assets
- ❌ Orientation still not represented

### Effort Estimate
- **Development:** 3-4 days
- **Design:** 1-2 days for SVG icons
- **Dependencies:** None
- **Risk:** Low

---

## Option 3: Canvas-Based Rendering

### Concept
Replace DOM-based markers with **canvas drawing** for better performance with large numbers of assets.

### How It Works

Leaflet can use either:
- **SVG renderer** (default) — Each element is a DOM node
- **Canvas renderer** — All elements drawn on a single canvas

### Technical Approach

**Enable canvas renderer:**
```javascript
// In MapContainer props
<MapContainer preferCanvas={true}>
```

**Custom canvas markers:**
- Use `L.circleMarker` (inherently canvas-compatible)
- Or create custom `L.Canvas` extension for complex shapes

**Drawing logic:**
```javascript
drawAsset(ctx, asset) {
  ctx.fillStyle = ASSET_COLORS[asset.type];
  
  // Draw footprint rectangle
  ctx.fillRect(x, y, width, height);
  
  // Draw icon on top
  ctx.drawImage(assetIcon, x, y);
  
  // Draw label
  ctx.fillText(`${asset.capacity_kw} kW`, x, y + height);
}
```

### Pros
- ✅ Excellent performance (1000+ assets)
- ✅ Smooth pan/zoom
- ✅ Full control over rendering
- ✅ Can combine with WebGL for effects

### Cons
- ❌ No native DOM events (must implement hit detection)
- ❌ More complex code
- ❌ Harder to style with CSS
- ❌ Accessibility challenges

### When to Use
- Sites with **100+ assets**
- Mobile devices with limited resources
- Animated visualizations

### Effort Estimate
- **Development:** 4-5 days
- **Dependencies:** None (built into Leaflet)
- **Risk:** Medium (custom hit detection logic)

---

## Option 4: 3D Visualization with Deck.gl

### Concept
Add a **3D layer** showing assets with height, creating an immersive visualization that shows elevation context.

### Visual Example
```
                    ╔═══╗
            ┌───┐   ║   ║  ← Substation (tallest)
    ┌───────┴───┴───╨───╨────────┐
    │                            │  ← Site boundary at terrain level
    │   ▓▓▓▓▓▓▓▓     ████████   │
    │   ▓▓▓▓▓▓▓▓     ████████   │  ← Solar arrays (low height)
    │   ▓▓▓▓▓▓▓▓     ████████   │
    └────────────────────────────┘
    
    [Perspective view showing terrain + equipment heights]
```

### How It Works

**Deck.gl** is Uber's WebGL-powered visualization library:

1. **Replace Leaflet map** with deck.gl + basemap
2. **Use `PolygonLayer`** for asset footprints with extrusion (height)
3. **Use `PathLayer`** for roads with width
4. **Add `TerrainLayer`** for elevation visualization
5. **Integrate with React** using `@deck.gl/react`

### Technical Approach

**Asset layer:**
```javascript
new PolygonLayer({
  data: assets,
  getPolygon: d => d.footprintCoords,
  getFillColor: d => ASSET_COLORS_RGB[d.type],
  getElevation: d => d.elevation_m,
  extruded: true,
  getHeight: d => ASSET_HEIGHTS[d.type],  // Solar: 3m, Substation: 10m
  pickable: true,
})
```

**Terrain layer:**
```javascript
new TerrainLayer({
  elevationData: '/api/terrain/{site_id}/dem.png',  // Encoded elevation
  texture: '/api/terrain/{site_id}/hillshade.png',
  meshMaxError: 4.0,
})
```

### Pros
- ✅ Stunning 3D visuals
- ✅ Shows terrain elevation context
- ✅ Equipment heights visible
- ✅ Smooth 60fps interactions
- ✅ Industry-leading for geospatial viz

### Cons
- ❌ **Major rewrite** — replaces Leaflet entirely
- ❌ Steeper learning curve
- ❌ Requires terrain data in specific formats
- ❌ Higher GPU requirements
- ❌ More complex popup/interaction handling

### Data Requirements
- DEM converted to height-encoded PNG or terrain tiles
- Pre-computed footprint polygons from backend
- Asset height metadata

### Effort Estimate
- **Development:** 2-3 weeks
- **Dependencies:** `deck.gl`, `@deck.gl/react`, `@deck.gl/geo-layers`
- **Backend changes:** Terrain tile endpoint
- **Risk:** High (complete map library swap)

---

## Option 5: Vector Tiles with MapLibre GL

### Concept
Replace Leaflet + raster tiles with **MapLibre GL JS** for vector-based rendering, enabling smooth zoom, rotation, and pitch.

### How It Works

**MapLibre GL** is an open-source fork of Mapbox GL:

1. **Replace react-leaflet** with `react-map-gl` (MapLibre version)
2. **Use vector basemaps** (OpenMapTiles, Maptiler, or self-hosted)
3. **Add custom layers** for assets and roads as GeoJSON sources
4. **Style with JSON** using Mapbox style spec
5. **Enable 3D terrain** with built-in terrain support

### Technical Approach

**Map setup:**
```javascript
import Map from 'react-map-gl/maplibre';

<Map
  mapStyle="https://tiles.example.com/style.json"
  terrain={{ source: 'terrain', exaggeration: 1.5 }}
>
  <Source id="assets" type="geojson" data={assetsGeoJSON}>
    <Layer
      type="fill-extrusion"
      paint={{
        'fill-extrusion-color': ['get', 'color'],
        'fill-extrusion-height': ['get', 'height'],
        'fill-extrusion-base': ['get', 'elevation'],
      }}
    />
  </Source>
</Map>
```

### Pros
- ✅ Vector rendering = crisp at all zoom levels
- ✅ Built-in 3D terrain support
- ✅ Smooth rotation and pitch
- ✅ Better mobile performance than Leaflet
- ✅ Powerful styling language

### Cons
- ❌ **Complete rewrite** of map component
- ❌ Need vector tile source (cost or self-host)
- ❌ Different interaction patterns
- ❌ Steeper learning curve
- ❌ Some features require Mapbox account

### Effort Estimate
- **Development:** 2-3 weeks
- **Dependencies:** `react-map-gl`, `maplibre-gl`
- **Infrastructure:** Vector tile server or paid service
- **Risk:** High (architecture change)

---

## Comparison Matrix

| Criteria | Option 1 (Footprints) | Option 2 (SVG Icons) | Option 3 (Canvas) | Option 4 (Deck.gl) | Option 5 (MapLibre) |
|----------|----------------------|---------------------|-------------------|-------------------|---------------------|
| **Development Time** | 2-3 days | 3-4 days | 4-5 days | 2-3 weeks | 2-3 weeks |
| **Visual Quality** | Good | Very Good | Good | Excellent | Excellent |
| **Shows True Scale** | ✅ Yes | ❌ No | ✅ Yes | ✅ Yes | ✅ Yes |
| **3D Capability** | ❌ No | ❌ No | ❌ No | ✅ Yes | ✅ Yes |
| **Terrain Viz** | ❌ No | ❌ No | ❌ No | ✅ Yes | ✅ Yes |
| **Performance (100+ assets)** | Good | Good | Excellent | Very Good | Very Good |
| **Mobile Performance** | Good | Good | Excellent | Fair | Very Good |
| **Architecture Change** | None | None | Minor | Major | Major |
| **New Dependencies** | None | None | None | deck.gl (~2MB) | maplibre-gl (~1MB) |
| **Risk Level** | Low | Low | Medium | High | High |

---

## Recommended Approach

### Phased Implementation Strategy

#### Phase 1: Quick Wins (Week 1)
**Implement Options 1 + 2 together**

1. **Add footprint rectangles** for all assets
   - Shows true equipment scale
   - Immediate visual improvement
   - Low risk, uses existing Leaflet

2. **Create custom SVG icons** to overlay on footprints
   - Solar: Panel array pattern
   - Battery: Container with modules
   - Generator: Engine symbol
   - Substation: Transformer symbol

3. **Enhance roads**
   - Show actual width (5m default)
   - Color-code by grade (green < 5%, yellow 5-10%, red > 10%)

**Deliverable:** Professional 2D layout visualization

---

#### Phase 2: Polish (Week 2)
**Enhance interactivity and details**

1. **Hover effects**
   - Highlight asset on hover
   - Show detailed tooltip with all metadata

2. **Selection state**
   - Click to select asset
   - Show sidebar with full details
   - Allow editing (future)

3. **Dynamic sizing**
   - Scale footprints accurately at all zoom levels
   - Hide details when zoomed out, show when zoomed in

4. **Legend improvements**
   - Add visual legend with actual icons
   - Show scale reference ("This rectangle = 30m × 20m")

**Deliverable:** Interactive, informative visualization

---

#### Phase 3: Future Consideration (Later)
**Evaluate 3D if there's demand**

Only consider Options 4 or 5 if:
- Users specifically request 3D/terrain visualization
- Competitive pressure requires it
- Performance issues arise with Leaflet at scale

**Note:** The 2D approach from Phases 1-2 will serve 90% of use cases. 3D adds complexity without proportional value for early-stage feasibility studies.

---

## Implementation Roadmap

### Week 1: Foundation

| Day | Task |
|-----|------|
| 1 | Create utility function to convert point + dimensions → polygon |
| 1 | Update Asset interface to include footprint dimensions |
| 2 | Implement footprint polygon rendering in Leaflet |
| 2 | Add styling (fill, stroke) per asset type |
| 3 | Design and create SVG icons for 4 asset types |
| 3 | Implement icon overlay at footprint center |
| 4 | Enhance roads with width rendering |
| 4 | Add grade-based color coding for roads |
| 5 | Testing and polish |

### Week 2: Interactivity

| Day | Task |
|-----|------|
| 1 | Implement hover states for assets |
| 1 | Create detailed tooltip component |
| 2 | Add click-to-select functionality |
| 2 | Build asset detail sidebar/panel |
| 3 | Implement zoom-level-based detail hiding |
| 3 | Add scale reference to map |
| 4 | Update legend with new visual style |
| 4 | Mobile responsive testing |
| 5 | Final polish and documentation |

---

## Technical Notes for Implementation

### Footprint Polygon Calculation

```
Input:
  center = (lat, lng)
  length_m = 30 (north-south dimension)
  width_m = 20 (east-west dimension)

Constants:
  METERS_PER_DEGREE_LAT = 111,319
  meters_per_degree_lng = 111,319 × cos(lat)

Calculation:
  half_length_deg = (length_m / 2) / METERS_PER_DEGREE_LAT
  half_width_deg = (width_m / 2) / meters_per_degree_lng

Corners (counter-clockwise from SW):
  SW = (lat - half_length_deg, lng - half_width_deg)
  SE = (lat - half_length_deg, lng + half_width_deg)
  NE = (lat + half_length_deg, lng + half_width_deg)
  NW = (lat + half_length_deg, lng - half_width_deg)
```

### Suggested Libraries (If Needed)

| Purpose | Library | Notes |
|---------|---------|-------|
| Geodesic calculations | `@turf/turf` | Already popular, well-maintained |
| SVG in React | Native JSX | No library needed |
| Tooltips | `react-tooltip` or custom | Leaflet popups may suffice |
| Color utilities | `chroma-js` | For gradient calculations |

### Asset Type Visual Specifications

| Type | Fill Color | Border | Icon | Label Position |
|------|------------|--------|------|----------------|
| Solar | `#fef3c7` (amber-50) | `#f59e0b` | Panel grid | Bottom center |
| Battery | `#dbeafe` (blue-100) | `#3b82f6` | Container | Bottom center |
| Generator | `#fee2e2` (red-100) | `#ef4444` | Engine | Bottom center |
| Substation | `#ede9fe` (violet-100) | `#8b5cf6` | Transformer | Bottom center |

---

## Summary

**Recommended path:** Start with **Options 1 + 2** (footprint rectangles + custom SVG icons) for immediate improvement with minimal risk. This provides:

- True-to-scale equipment visualization
- Professional, industry-appropriate appearance  
- Excellent performance
- No architecture changes
- 2 weeks to complete

**Defer 3D visualization** (Options 4/5) until there's clear user demand. The complexity and risk don't justify the visual benefit for early-stage site planning.

---

*Document version: 1.0*  
*Created: November 25, 2025*  
*Author: Pacifico Engineering Team*






