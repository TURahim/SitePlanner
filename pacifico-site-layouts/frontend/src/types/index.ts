/**
 * TypeScript type definitions for Pacifico Site Layouts
 */
import type { Polygon, Point, LineString, FeatureCollection } from 'geojson';

// =============================================================================
// Auth Types
// =============================================================================

export interface User {
  id: string;
  email: string;
  name?: string;
}

export interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}

// =============================================================================
// Site Types
// =============================================================================

export interface SiteListItem {
  id: string;
  name: string;
  area_m2: number;
  created_at: string;
}

export interface SiteListResponse {
  sites: SiteListItem[];
  total: number;
}

export interface Site {
  id: string;
  project_id?: string;
  name: string;
  area_m2: number;
  boundary: Polygon;
  created_at: string;
  updated_at: string;
}

export interface SiteUploadResponse {
  id: string;
  name: string;
  area_m2: number;
  boundary: Polygon;
  created_at: string;
}

// =============================================================================
// Layout Types
// =============================================================================

export type LayoutStatus = 'queued' | 'processing' | 'completed' | 'failed';

export interface Asset {
  id: string;
  asset_type: 'solar' | 'battery' | 'generator' | 'substation' | 'solar_array';
  name?: string;
  capacity_kw?: number;
  position: Point;
  elevation_m?: number;
  slope_deg?: number;
  footprint_length_m?: number;
  footprint_width_m?: number;
  // D-02: Per-asset cut/fill volumes (P1)
  cut_m3?: number;
  fill_m3?: number;
  // Phase E: Enhanced terrain metrics
  aspect_deg?: number;
  suitability_score?: number;
  rotation_deg?: number;
}

export interface Road {
  id: string;
  name?: string;
  length_m?: number;
  width_m?: number;
  geometry: LineString;
  max_grade_pct?: number;
}

export interface Layout {
  id: string;
  site_id: string;
  status: LayoutStatus;
  total_capacity_kw?: number;
  cut_volume_m3?: number;
  fill_volume_m3?: number;
  // Phase E: Enhanced earthwork metrics
  road_cut_m3?: number;
  road_fill_m3?: number;
  total_cut_m3?: number;
  total_fill_m3?: number;
  net_earthwork_m3?: number;
  error_message?: string;
  created_at: string;
  updated_at: string;
}

export interface LayoutDetail extends Layout {
  assets: Asset[];
  roads: Road[];
}

export interface LayoutGenerateResponse {
  layout: Layout;
  assets: Asset[];
  roads: Road[];
  geojson: FeatureCollection;
}

export interface LayoutListItem {
  id: string;
  site_id: string;
  status: LayoutStatus;
  total_capacity_kw?: number;
  created_at: string;
}

export interface LayoutListResponse {
  layouts: LayoutListItem[];
  total: number;
}

export interface GenerateLayoutRequest {
  site_id: string;
  target_capacity_kw?: number;
  use_terrain?: boolean;
  dem_resolution_m?: number;
}

// =============================================================================
// Phase C: Async Layout Generation Types
// =============================================================================

/**
 * Response when async layout generation is enabled (C-03)
 * Returns immediately with layout_id for polling
 */
export interface LayoutEnqueueResponse {
  layout_id: string;
  status: 'queued';
  message: string;
}

/**
 * Response from status polling endpoint (C-04)
 */
export interface LayoutStatusResponse {
  layout_id: string;
  status: LayoutStatus;
  error_message?: string;
  // Populated only when status is 'completed'
  total_capacity_kw?: number;
  asset_count?: number;
  road_length_m?: number;
  cut_volume_m3?: number;
  fill_volume_m3?: number;
}

/**
 * Union type for generate layout response
 * Can be either sync (full response) or async (enqueue response)
 */
export type GenerateLayoutResponseUnion = LayoutGenerateResponse | LayoutEnqueueResponse;

/**
 * Type guard to check if response is async (enqueue response)
 */
export function isAsyncLayoutResponse(
  response: GenerateLayoutResponseUnion
): response is LayoutEnqueueResponse {
  return 'message' in response && !('layout' in response);
}

// =============================================================================
// Export Types
// =============================================================================

/**
 * Available export formats
 * D-04-05: Added 'csv' format
 */
export type ExportFormat = 'geojson' | 'kmz' | 'pdf' | 'csv';

/**
 * Export response with download URL and metadata
 * D-04-06: Filename now includes site name and timestamp
 */
export interface ExportResponse {
  download_url: string;
  format: ExportFormat;
  /** D-04-06: Filename with site name, layout ID, and timestamp */
  filename: string;
  expires_in_seconds: number;
}

// =============================================================================
// Phase D: Terrain Visualization Types
// =============================================================================

/**
 * Elevation statistics for a site
 */
export interface ElevationStats {
  min_m: number;
  max_m: number;
  range_m: number;
  mean_m: number;
}

/**
 * Slope distribution bucket
 */
export interface SlopeDistributionBucket {
  range: string;
  min_deg: number;
  max_deg: number;
  percentage: number;
  area_m2: number;
}

/**
 * Slope statistics with distribution histogram
 */
export interface SlopeStats {
  min_deg: number;
  max_deg: number;
  mean_deg: number;
  distribution: SlopeDistributionBucket[];
}

/**
 * Buildable area statistics for an asset type
 */
export interface BuildableAreaStats {
  asset_type: string;
  max_slope_deg: number;
  area_m2: number;
  area_ha: number;
  percentage: number;
}

/**
 * Complete terrain analysis summary (D-01)
 */
export interface TerrainSummaryResponse {
  site_id: string;
  dem_source: string;
  dem_resolution_m: number;
  elevation: ElevationStats;
  slope: SlopeStats;
  buildable_area: BuildableAreaStats[];
  total_area_m2: number;
  total_area_ha: number;
}

/**
 * Contour lines as GeoJSON FeatureCollection (D-01)
 */
export interface ContoursResponse {
  site_id: string;
  interval_m: number;
  type: 'FeatureCollection';
  features: GeoJSON.Feature[];
  min_elevation_m: number;
  max_elevation_m: number;
  contour_count: number;
}

/**
 * Buildable area polygons (D-01)
 */
export interface BuildableAreaResponse {
  site_id: string;
  asset_type: string;
  max_slope_deg: number;
  type: 'FeatureCollection';
  features: GeoJSON.Feature[];
  buildable_area_m2: number;
  buildable_area_ha: number;
  buildable_percentage: number;
}

/**
 * Slope heatmap legend item
 */
export interface SlopeHeatmapLegendItem {
  class: string;
  label: string;
  color: string;
  min_deg: number;
  max_deg: number;
}

/**
 * Slope heatmap as colored polygons (D-01)
 */
export interface SlopeHeatmapResponse {
  site_id: string;
  type: 'FeatureCollection';
  features: GeoJSON.Feature[];
  legend: SlopeHeatmapLegendItem[];
}

/**
 * Available terrain layer types
 */
export type TerrainLayerType = 'contours' | 'slopeHeatmap' | 'buildableArea';

// =============================================================================
// Phase D-05: Layout Variants Types
// =============================================================================

/**
 * Layout optimization strategies (D-05)
 */
export type LayoutStrategy = 
  | 'balanced' 
  | 'density' 
  | 'low_earthwork' 
  | 'clustered';

/**
 * Strategy information
 */
export interface StrategyInfo {
  strategy: LayoutStrategy;
  name: string;
  description: string;
}

/**
 * Metrics for a single layout variant
 */
export interface LayoutVariantMetrics {
  layout_id: string;
  strategy: LayoutStrategy;
  strategy_name: string;
  total_capacity_kw: number;
  asset_count: number;
  road_length_m: number;
  cut_volume_m3: number;
  fill_volume_m3: number;
  net_earthwork_m3: number;
  capacity_per_hectare?: number;
}

/**
 * Comparison analysis across variants
 */
export interface VariantComparison {
  best_capacity_id: string;
  best_earthwork_id: string;
  best_road_network_id: string;
  metrics_table: LayoutVariantMetrics[];
}

/**
 * Single variant in a multi-variant response
 */
export interface LayoutVariant {
  strategy: LayoutStrategy;
  strategy_name: string;
  layout: Layout;
  assets: Asset[];
  roads: Road[];
  geojson: FeatureCollection;
}

/**
 * Response for multi-variant layout generation
 */
export interface LayoutVariantsResponse {
  site_id: string;
  variants: LayoutVariant[];
  comparison: VariantComparison;
}

/**
 * Response for available layout strategies
 */
export interface LayoutStrategiesResponse {
  strategies: StrategyInfo[];
}

/**
 * Request to set preferred layout (D-05-06)
 */
export interface SetPreferredLayoutRequest {
  layout_id: string | null;
}

/**
 * Response for preferred layout operations (D-05-06)
 */
export interface PreferredLayoutResponse {
  site_id: string;
  preferred_layout_id: string | null;
  message: string;
}

/**
 * Request for generating layout variants
 */
export interface GenerateVariantsRequest {
  site_id: string;
  target_capacity_kw?: number;
  use_terrain?: boolean;
  dem_resolution_m?: number;
  generate_variants?: boolean;
  variant_strategies?: LayoutStrategy[];
}

// =============================================================================
// Phase D-03: Exclusion Zone Types
// =============================================================================

/**
 * Exclusion zone types
 */
export type ExclusionZoneType = 
  | 'environmental' 
  | 'regulatory' 
  | 'infrastructure' 
  | 'safety' 
  | 'custom';

/**
 * Exclusion zone type metadata
 */
export interface ExclusionZoneTypeInfo {
  type: ExclusionZoneType;
  label: string;
  color: string;
  default_buffer_m: number;
  description: string;
}

/**
 * Exclusion zone response from API
 */
export interface ExclusionZone {
  id: string;
  site_id: string;
  name: string;
  zone_type: ExclusionZoneType;
  geometry: Polygon;
  buffer_m: number;
  description?: string;
  area_m2?: number;
  color: string;
  created_at: string;
  updated_at: string;
}

/**
 * Request to create an exclusion zone
 */
export interface ExclusionZoneCreateRequest {
  name: string;
  zone_type: ExclusionZoneType;
  geometry: Polygon;
  buffer_m?: number;
  description?: string;
}

/**
 * Request to update an exclusion zone
 */
export interface ExclusionZoneUpdateRequest {
  name?: string;
  zone_type?: ExclusionZoneType;
  geometry?: Polygon;
  buffer_m?: number;
  description?: string;
}

/**
 * List response for exclusion zones
 */
export interface ExclusionZoneListResponse {
  zones: ExclusionZone[];
  total: number;
  site_id: string;
}

/**
 * Response for available zone types
 */
export interface ExclusionZoneTypesResponse {
  types: ExclusionZoneTypeInfo[];
}

// =============================================================================
// Project Types (for future use)
// =============================================================================

export interface Project {
  id: string;
  name: string;
  description?: string;
  created_at: string;
  updated_at: string;
}
