## Pacifico Site Layouts – GAP Implementation Plan (Nov 2025)

This document is a **self-contained implementation guide** for closing the gaps between:

- The Product Requirements Document (PRD) `PRD_Pacifico_Energy_Group_MVP_Site_Layouts_Use_code_and_open_source_data_to_.md`
- The current codebase under `pacifico-site-layouts/`

It is written so a **new agent or engineer** can execute work without needing prior conversation history.

---

## 1. High-Level Product Context

- **Goal**: Automatically generate terrain-aware site layouts for early-stage real estate due diligence:
  - Import KML/KMZ site boundaries.
  - Pull open terrain data (DEM), compute slope/aspect, and derive suitability metrics.
  - Auto-place core assets (solar arrays, batteries, generators, substations).
  - Generate road networks from site entry to major assets.
  - Estimate cut/fill volumes and export layouts (GeoJSON, KMZ, PDF, CSV).
- **Users**: Site planners, project managers, civil engineers, and executives at Pacifico Energy Group.

Current implementation is already **beyond a basic MVP** – it has a sophisticated terrain-aware generator and export stack, but there are gaps vs. the PRD, especially around regulatory integration, interactive editing, and UX.

---

## 2. Current Architecture (Concise Map)

### 2.1 Backend (FastAPI, async)

- **Core layout APIs** – `backend/app/api/layouts.py`
  - `POST /api/layouts/generate`: generate a single layout (dummy or terrain-aware, sync or async).
  - `POST /api/layouts/generate-variants`: generate multiple variants for different strategies.
  - `GET /api/layouts/{id}`: fetch full layout with assets & roads.
  - `GET /api/layouts/{id}/status`: poll async job status.
  - Uses:
    - `TerrainAwareLayoutGenerator` in `services/terrain_layout_generator.py`
    - `DummyLayoutGenerator` in `services/layout_generator.py`
    - `DEMService`, `SlopeService`, `TerrainAnalysisService`
    - Exclusion zones (`models/exclusion_zone.py`) via `_fetch_exclusion_zones`.

- **Export APIs** – `backend/app/api/exports.py`
  - `GET /api/layouts/{id}/export/geojson`
  - `GET /api/layouts/{id}/export/kmz`
  - `GET /api/layouts/{id}/export/pdf`
  - `GET /api/layouts/{id}/export/csv`
  - Use `ExportService` to upload artifacts to S3 and return presigned URLs.

- **Terrain & ingestion services**
  - `services/kml_parser.py`: parse `.kml`/`.kmz` to Shapely polygons for site boundaries.
  - `services/dem_service.py`: fetch DEM from USGS 3DEP via `py3dep`, cache in S3 and `TerrainCache`.
  - `services/slope_service.py`: compute slope rasters from DEM, cache in S3 and `TerrainCache`.
  - `services/terrain_analysis_service.py`: advanced terrain metrics and suitability scoring.
  - `services/terrain_visualization_service.py`: contours, buildable area, slope heatmaps, terrain summary.

- **Layout generator** – `services/terrain_layout_generator.py`
  - Asset placement:
    - Strategy-aware (`BALANCED`, `DENSITY`, `LOW_EARTHWORK`, `CLUSTERED`).
    - Poisson-disk candidate sampling, slope & suitability scoring, aspect-based rotation.
    - Exclusion zones and allowance masks.
  - Roads:
    - Cost surface from slope + curvature + allowance zones.
    - A* pathfinding with budget + retries + direct-line fallback.
    - Spine from entry point to substation; MST or star topology for the rest.
  - Earthwork:
    - Per-asset pad cut/fill; road corridor cut/fill via buffered corridors and KD-tree sampling.
  - Output:
    - `CutFillResult` with asset/road breakdown.
    - `to_geojson_feature_collection` for frontend consumption and exports.

### 2.2 Frontend (React + Vite)

- `frontend/src/App.tsx` – sets up routing and Cognito-based auth via Amplify.
- Main pages (high level):
  - `LandingPage`, `LoginPage`, `SignupPage`, `ProjectsPage`, `SiteDetailPage`.
- `SiteDetailPage`:
  - Shows individual site layouts and interacts with layout APIs (generation, polling, visualization).
  - Uses shared `Layout` component & map utilities (`lib/mapUtils.ts`) to visualize GeoJSON.
- There is **no current interactive asset-drag/edit feature** in the frontend.

### 2.3 Infra

- Terraform in `infra/terraform/` for AWS (S3, CloudFront, SQS, etc.).
- Backend worker (`backend/app/worker.py`) consumes SQS messages to do async layout generation.

---

## 3. PRD vs. Implementation – Key GAP Summary

From the PRD:

- **P0 (must-have)** items (import KML/KMZ, terrain metrics, auto-placement with exclusions, road networks, cut/fill + reports) are **functionally implemented**.
- Largest gaps lie in **P1/P2 and non-functional requirements**:

1. **Regulatory & environmental constraints (dynamic)**
   - Today: generic exclusion zones with buffers & multipliers; no automatic ingestion from regulatory APIs.
2. **User-defined asset placement adjustments**
   - Today: assets are fully algorithmic; no per-asset edit endpoints or UI to move/snap assets and recompute local impacts.
3. **Real-time visualization of layout changes**
   - Today: generate → wait → show result; no streaming progress or live layout updates during edit operations.
4. **Compliance modeling**
   - Today: engineering-informed constraints (slope limits, road grades) but not explicitly mapped to codes/jurisdictions.
5. **Alternative assets & GIS integration**
   - Support for solar/generator/battery/substation but not wind etc.; exports are GIS-compatible but no direct GIS API integration.

The following implementation plan focuses on closing the **highest-value gaps** while respecting the existing architecture.

---

## 4. Implementation Plan – Phased Roadmap

### Phase 1 – Document & Expose Existing Capabilities ✅ COMPLETE

**Goal:** Make current behavior explicit and easier to consume, without major new features. This also de-risks later changes.

**Completed (Nov 26, 2025):**

1. ✅ **Updated internal docs**
   - `docs/LAYOUT_GENERATION_EXPLAINED.md` - Comprehensive 357-line guide covering:
     - Multi-tier road network architecture
     - Asset placement algorithm with strategy configs
     - Slope limits per asset type (Solar 10°, Battery 4°, Generator 5°, Substation 3°)
     - Road pathfinding with A* algorithm and 3-tier retry logic
     - Cut/fill calculation methodology
     - Exclusion zone processing
     - All 4 export formats with examples
     - Full API reference
   - `docs/ARCHITECTURE_OVERVIEW.md` - New 300+ line system architecture document covering:
     - High-level component diagram with all services
     - Complete directory structure mapping
     - Data flow for both sync and async generation paths
     - Technology stack with rationale
     - Database schema overview
     - Configuration reference with all environment variables

2. ✅ **Frontend wiring confirmed**
   - `SiteDetailPage.tsx` verified to properly:
     - Call `POST /api/layouts/generate` and `GET /api/layouts/{id}/status`
     - Retrieve exports via `/export/geojson`, `/export/kmz`, `/export/pdf`, `/export/csv`
     - Render layout GeoJSON via Leaflet map component
     - Display terrain overlays (contours, slope heatmap, buildable areas)
     - Manage exclusion zones with drawing UI
     - Compare layout variants with strategy selector
   - Clear entry points identified for Phase 3 asset editing

**Deliverables:** ✅
- Updated docs that accurately describe generator and exports
- Clear entry points in frontend for future UX enhancements

---

### Phase 2 – Regulatory & Environmental Constraints Integration ✅ COMPLETE

**Goal:** Move from manual exclusion-zone definition to **dynamic regulatory/environmental constraints**, aligned with PRD P1.

**Completed (Nov 26, 2025):**

#### 2.1 Data Model & API Extensions ✅
- ✅ `ExclusionZone` model extended with `zone_type` (environmental, regulatory, infrastructure, safety, custom)
- ✅ Typed defaults configuration in `ZONE_TYPE_DEFAULTS` mapping with:
  - Default buffers (0m-25m depending on type)
  - Cost multipliers (1.0-100.0)
  - Display colors and descriptions
- ✅ New endpoints implemented:
  - `GET /api/sites/regulatory-layers` - Lists available regulatory layers (9 types)
  - `POST /api/sites/{site_id}/regulatory-sync` - Auto-populate exclusion zones from regulatory data

#### 2.2 Regulatory Data Integration ✅
- ✅ **`RegulatoryService` abstraction** (`backend/app/services/regulatory_service.py`):
  - `RegulatoryDataProvider` - Abstract interface for pluggable providers
  - `MockRegulatoryProvider` - Generates synthetic regulatory features:
    - Wetlands (15m buffer, hard exclusion)
    - Utility corridors (3% site width buffer, hard exclusion)
    - Property setbacks (5% perimeter buffer, hard exclusion)
  - Support for 9 layer types with automatic zone type mapping
  
- ✅ **Mock integration complete**
  - Provider generates contextually-appropriate features based on site boundary
  - Automatic clipping to site boundary
  - Attributes preserved in ExclusionZone descriptions
  
- ✅ **Real API hooks designed**
  - Service interface ready for FEMA flood data integration
  - Support for NWI wetlands API
  - Extensible to any GeoJSON-based regulatory API

**Deliverables:** ✅
- Extended `ExclusionZone` semantics with typed categories
- `RegulatoryService` with provider pattern for future real data sources
- `POST /api/sites/{id}/regulatory-sync` endpoint with auto zone population
- Layout generation already uses `_fetch_exclusion_zones` which now includes auto-synced zones

---

### Phase 3 – User-Defined Asset Adjustments & Local Recompute ✅ COMPLETE

**Goal:** Allow users to **manually adjust assets** post-generation and locally recompute roads and cut/fill, closing a big P1 gap and supporting real engineer workflows.

**Completed (Nov 26, 2025):**

#### 3.1 Backend – New Asset Manipulation APIs ✅

1. ✅ **Move asset endpoint**
   - `PATCH /api/layouts/{layout_id}/assets/{asset_id}` with:
     - New `position` (GeoJSON Point with [lng, lat])
     - Optional `recompute_local` flag for terrain metrics
   - Validation:
     - New position must be within site boundary
     - New position cannot be in hard exclusion zones (cost_multiplier >= 100)
     - Warnings generated for soft exclusion zones
     - Slope, elevation, suitability re-evaluated at new position
     - Warnings if slope exceeds asset type limits
   - Response includes asset details and validation warnings

2. ✅ **Recompute roads endpoint**
   - `POST /api/layouts/{layout_id}/roads/recompute` (Option A implemented)
   - Regenerates **all** road segments using current asset positions:
     - Uses `TerrainAwareLayoutGenerator._generate_roads_terrain_aware`
     - Deletes existing roads and creates new ones
     - Reapplies MST or star topology based on original strategy
     - Includes entry point integration for primary spine
   - Response includes updated roads, total length, road count

3. ✅ **Recompute earthwork endpoint**
   - `POST /api/layouts/{layout_id}/earthwork/recompute`
   - Re-runs `_compute_cut_fill` with:
     - Current asset positions and footprints
     - Current road geometries (if `include_roads=true`)
     - Existing DEM and terrain transform
   - Updates layout-level cut/fill and per-asset/road breakdowns
   - Response includes cut/fill totals and net balance

#### 3.2 Schemas & Frontend Types ✅
- ✅ Added Pydantic schemas for all 3 endpoints (request/response)
- ✅ Added TypeScript interfaces in frontend types
- ✅ Ready for frontend drag-and-drop implementation (future iteration)

**Deliverables:** ✅
- Complete CRUD-like API for asset moves and recompute operations
- Comprehensive validation and error handling
- Ready for frontend drag-and-drop UI enhancement
- Foundation for Phase 3b: Undo/revert functionality

---

### Phase 4 – Real-Time Progress & Layout Visualization ✅ COMPLETE

**Goal:** Improve perceived responsiveness and transparency by surfacing **layout generation progress** and frequent state updates.

**Completed (Nov 26, 2025):**

1. ✅ **Enhanced job status tracking**
   - Extended `LayoutStatusResponse` with progress fields:
     - `stage` - Current generation stage (queued, fetching_dem, computing_slope, analyzing_terrain, placing_assets, generating_roads, computing_earthwork, finalizing, completed, failed)
     - `progress_pct` - Progress percentage (0-100)
     - `stage_message` - Human-readable stage description
   - Created `LayoutGenerationStage` enum with 10 distinct stages
   - Added `STAGE_PROGRESS` mapping for automatic progress calculation

2. ✅ **Database model updates**
   - Added columns to `Layout` model:
     - `stage: String` - Current generation stage
     - `progress_pct: Integer` - Progress percentage
     - `stage_message: String` - Human-readable status message
   - Created migration `006_layout_progress_tracking.py` with auto-migration for existing records
   - Status endpoint updated to return progress info during generation

3. ✅ **Frontend enhancements**
   - Updated `LayoutStatusResponse` TypeScript interface with progress fields
   - Enhanced `SiteDetailPage.tsx` progress indicator:
     - Progress bar now shows actual `progress_pct` instead of fixed percentages
     - Stage-specific messages displayed (e.g., "Downloading elevation data...", "Placing assets...")
     - Percentage display in progress section
     - Elapsed time continues to show during generation
   - `useLayoutPolling.ts` hook already configured for polling progress updates

4. ✅ **Optional Phase 4b – Streaming preparation**
   - Service layer designed to support future WebSocket/SSE endpoints
   - Status tracking in database enables real-time updates in future
   - Frontend ready for connection to streaming endpoints

**Deliverables:** ✅
- Enriched `/status` payload with stage tracking
- UI progress indicators with stage-specific messages
- Database migration completed
- Full frontend integration
- Foundation ready for WebSocket enhancement (Phase 4b)

---

### Phase 5 – Compliance & Advanced Assets (P2 / Longer-Term)

**Goal:** Incrementally align with P2 ambitions while keeping scope manageable.

1. **Compliance modeling**
   - Introduce a basic **rules engine** module that expresses constraints such as:
     - max slopes by road class and asset type,
     - minimum distances to boundary or sensitive zones,
     - basic code-like rules (e.g., min pad size for substations).
   - Rules can initially mirror existing parameters (slope limits, MAX_ROAD_GRADE_PCT) with explicit configuration, then be extended per jurisdiction.

2. **Alternative asset types**
   - Add `wind_turbine` or other types to:
     - `ASSET_CONFIGS` in `terrain_layout_generator.py`,
     - suitability configs in `terrain_analysis_service.py`,
     - frontend type handling and legends.
   - Implement distinct spacing and road-connection rules for these new assets.

3. **GIS integration (beyond exports)**
   - Design a plugin-style `GISIntegrationService` that:
     - can push final layouts to external GIS systems via their APIs,
     - starts as a stub with logging-only mode.

**Deliverables:**
- Configurable rules layer, linked to existing constraints.
- Extended asset catalog and updated generator logic.
- Pluggable GIS integration abstraction (even if no production API is wired yet).

---

## 5. Completion Summary

**✅ PHASES 1-4 COMPLETED (Nov 26, 2025) — All core GAP items delivered**

### Delivery Timeline
- **Phase 1** (Documentation): 2 comprehensive guides covering architecture and generation algorithms
- **Phase 2** (Regulatory Integration): Extensible RegulatoryService with mock provider, 2 new API endpoints
- **Phase 3** (Asset Manipulation): 3 new endpoints for asset moves and recomputation, with validation
- **Phase 4** (Progress Tracking): Database model, schema, and frontend integration for 10-stage generation pipeline

### Code Statistics
- **New files**: 3 (regulatory_service.py, ARCHITECTURE_OVERVIEW.md, 006_layout_progress_tracking.py migration)
- **Updated files**: 8 (README.md, gapimplement.md, layouts.py, sites.py, layout.py models/schemas, SiteDetailPage.tsx, types/index.ts)
- **New API endpoints**: 5 (regulatory-layers, regulatory-sync, move-asset, recompute-roads, recompute-earthwork)
- **New database fields**: 3 (stage, progress_pct, stage_message)
- **Frontend enhancements**: Progress bar with stage-specific messages

### PRD Alignment
- **P0 (must-have)**: ✅ All core features from PRD implemented and working
- **P1 (high-priority)**: ✅ Regulatory integration (Phase 2), asset editing (Phase 3), progress tracking (Phase 4) now available
- **P2 (nice-to-have)**: Ready for Phase 5 (compliance rules, additional assets, GIS integration)

**Next Steps (Phase 5 - Future Work):**
- Compliance rules engine for jurisdiction-specific constraints
- Additional asset types (wind turbines, etc.)
- Direct GIS system integration
- WebSocket streaming for real-time progress (Phase 4b)
- Undo/reset asset changes functionality

All phases are shippable and testable in isolation. The system is now significantly closer to full PRD alignment.


