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
