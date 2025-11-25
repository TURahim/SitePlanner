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
  asset_type: 'solar' | 'battery' | 'generator' | 'substation';
  name?: string;
  capacity_kw?: number;
  position: Point;
}

export interface Road {
  id: string;
  name?: string;
  length_m?: number;
  geometry: LineString;
}

export interface Layout {
  id: string;
  site_id: string;
  status: LayoutStatus;
  total_capacity_kw?: number;
  cut_volume_m3?: number;
  fill_volume_m3?: number;
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

export type ExportFormat = 'geojson' | 'kmz' | 'pdf';

export interface ExportResponse {
  download_url: string;
  format: ExportFormat;
  filename: string;
  expires_in_seconds: number;
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
