Implementation Plan
Phase Alignment: Read both docs/LAYOUT_GENERATION_EXPLAINED.md and terrainlayoutupdate.md. Audited the current pipeline across app/services/terrain_layout_generator.py, app/api/layouts.py, terrain_analysis_service.py, exports, and the React SiteDetailPage to understand how terrain data, routing, and deliverables are assembled today.
1. Data Inputs & Schema Prep
Extend sites table/model/schema/API to store a gate/easement point (entry_point geometry plus metadata) so the generator receives an explicit starting node. Surface CRUD in app/api/sites.py, expose through frontend/src/lib/api.ts, and add UI affordances on SiteDetailPage to place/move that marker.
Introduce an “earthwork allowance” overlay: either a dedicated table (e.g. site_cost_overlays) or a lighter-weight extension of ExclusionZone with a cost_multiplier field. Server-side we’ll rasterize these polygons similar to exclusion_zones; client-side we need a draw tool and persistence.
Add road-level KPI columns (avg_grade_pct, max_cumulative_cost, kpi_flags, stationing_json) plus layout-level aggregates. Wire up Alembic migrations, SQLAlchemy models, and Pydantic response classes.
2. Raster Validation & Mask Construction (Phase 1)
In TerrainAwareLayoutGenerator.generate, normalize DEM/slope inputs: detect nodata pockets, interpolate/fill (e.g. with scipy.ndimage.distance_transform_edt), and clamp slopes per plan.
Store full TerrainMetrics on the generator (_curvature_array, _plan_curvature_array, _roughness_array) so curvature penalties can be applied during road scoring.
Rasterize the new allowance polygons into a mask that marks low-cost corridors; persist in the generator to influence cost.
3. Cost Surface & Budget Normalization
Replace the current cube-based cost surface with the spec’d formula cost = 1 + (slope / slope_limit)^3, apply curvature surcharges (convex ridges +2×, concave gullies +1.5×), and multiply by 0.6 wherever the allowance mask is true. Keep a finite but high (10⁴) cost for slopes >25° instead of infinite.
Implement a budget ceiling equivalent to 500 km of travel: during _find_path_astar/Dijkstra we’ll track cumulative cost (cost-per-cell × cell_size) and abort with a structured error once the budget is exceeded. Log and persist the max cumulative cost per road for auditability.
4. Multi-Tier Road Network Logic (Phase 2)
Primary spine: map the entry point to raster indices and run weighted Dijkstra to the substation (respecting exclusion masks). Generate a PlacedRoad marked as primary_spine.
Secondary feeds: update _generate_mst_roads to bias Prim’s algorithm toward connecting nodes already on the spine (e.g. weight edges by dist * hub_bias). Once the edge set is chosen, still run A* for each edge to obtain a terrain-following geometry.
Tertiary spurs: identify assets >300 m from any spine/secondary road vertex and run capped-length A* from that road to the asset. Skip or flag assets that cannot be connected within the cap.
Update road naming/metadata (road_class, parent_segment_id) so downstream exports can distinguish classes.
5. Path Smoothing, Corridor Offsets & Earthwork
Convert each raster path into meters (local UTM or pyproj), run Douglas–Peucker with a 1 m tolerance, then sample at fixed intervals for grade/elevation.
Derive 5 m corridor polygons via left/right offsets and pass them into a revamped _compute_road_earthwork, which now returns per-road cut/fill plus overall totals. Store the per-road breakdown in CutFillResult and surface it through the API.
Compute stationing every 25 m (chainage, lat/lon, elev, grade) and attach to road properties for GeoJSON/CAD exports.
6. Failover Handling & KPI Gates
Enhance _create_road_segment to retry up to three times, relaxing penalties by 10 % increments before falling back to a straight line. Capture the retry count and reason in the PlacedRoad.
After all segments are built, enforce KPIs: verify max_grade_pct ≤ 10, average slope ≤ 6 %, and ensure no sampled point traverses exclusion zones or >15° slopes. Failures either trigger rerouting or set kpi_flags for manual review.
Feed these KPIs back into LayoutResponse (overall status plus flag list) and into logging/monitoring.
7. Outputs & QA Deliverables (Phase 3)
Update GeoJSON generation to include new road metadata (class, stationing, cumulative cost, flags, per-road earthwork). The frontend map can style roads based on these properties.
Extend ExportService:
Add a CAD/DXF exporter (e.g. via ezdxf) that emits polylines with station labels every 25 m.
Enhance PDF exports with grade profiles, KPI tables, and per-road earthwork summaries.
Continue KMZ/GeoJSON exports but embed the new attributes.
Add a “stress test” step: re-evaluate each route with the cost surface multiplied by 2 to confirm feasibility, store the pass/fail result, and surface it to the user.
Provide an imagery/LiDAR overlay toggle on the map (even if it’s just switching to a satellite basemap) to satisfy the “overlay routes on LiDAR/imagery” review requirement.
8. Frontend Enhancements
Update TypeScript types and API helpers for new fields (entry point, allowance overlays, road KPI data, CAD export URL, etc.).
On SiteDetailPage, add controls for:
Setting the entry point (draggable marker) and saving it.
Drawing allowance polygons and assigning a cost multiplier.
Displaying route KPIs, flags, per-road earthwork, and stress-test status.
Initiating the new CAD export alongside existing GeoJSON/KMZ/PDF/CSV buttons.
Highlight flagged roads on the map (e.g. red outline for manual-review items) and surface KPI badges in the layout summary/variant comparison components.
9. Testing & Documentation
Expand unit tests (tests/test_terrain_layout_generator.py) to cover nodata filling, entry-point routing, tiered road creation, KPI enforcement, and stationing output.
Add integration tests (possibly skipped in CI like the existing terrain tests) to verify the CAD export and KPIs when connected to real DEM data.
Refresh docs/LAYOUT_GENERATION_EXPLAINED.md plus add a shorter “Terrain-Aware Road Optimization” playbook summarizing the new behavior, KPIs, and configuration knobs.
Update the /memory artifacts (PROJECT_BRIEF.md, ACTIVE_CONTEXT.md, etc.) once the implementation lands to keep long-lived collaborators aligned.
This plan keeps code untouched while detailing how to thread the roadmap requirements through backend services, database schema, exports, and the frontend experience. Let me know if you want to dive deeper into any specific step before we start implementing.