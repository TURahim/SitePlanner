/**
 * TypeScript type definitions
 */
import type { Polygon, Point, LineString } from 'geojson';

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

export interface Project {
  id: string;
  name: string;
  description?: string;
  created_at: string;
  updated_at: string;
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

export interface Layout {
  id: string;
  site_id: string;
  status: 'queued' | 'processing' | 'completed' | 'failed';
  total_capacity_kw?: number;
  cut_volume_m3?: number;
  fill_volume_m3?: number;
  created_at: string;
  updated_at: string;
}

export interface Asset {
  id: string;
  layout_id: string;
  type: 'solar' | 'battery' | 'generator' | 'substation';
  capacity_kw: number;
  position: Point;
}

export interface Road {
  id: string;
  layout_id: string;
  length_m: number;
  geometry: LineString;
}

