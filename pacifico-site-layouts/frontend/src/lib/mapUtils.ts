/**
 * Map utilities for footprint calculations and styling
 */
import type { LatLngTuple } from 'leaflet';

// =============================================================================
// Constants
// =============================================================================

const METERS_PER_DEGREE_LAT = 111319;

// Asset type colors - matching brand guidelines
export const ASSET_COLORS: Record<string, { fill: string; stroke: string; text: string }> = {
  solar_array: { 
    fill: '#fef3c7', // amber-50
    stroke: '#f59e0b', // amber-500
    text: '#92400e', // amber-800
  },
  solar: { 
    fill: '#fef3c7',
    stroke: '#f59e0b',
    text: '#92400e',
  },
  battery: { 
    fill: '#dbeafe', // blue-100
    stroke: '#3b82f6', // blue-500
    text: '#1e40af', // blue-800
  },
  generator: { 
    fill: '#fee2e2', // red-100
    stroke: '#ef4444', // red-500
    text: '#991b1b', // red-800
  },
  substation: { 
    fill: '#ede9fe', // violet-100
    stroke: '#8b5cf6', // violet-500
    text: '#5b21b6', // violet-800
  },
  // New asset types for gas_bess and hybrid profiles
  gas_turbine: {
    fill: '#fef2f2', // red-50
    stroke: '#dc2626', // red-600
    text: '#7f1d1d', // red-900
  },
  wind_turbine: {
    fill: '#ecfdf5', // emerald-50
    stroke: '#10b981', // emerald-500
    text: '#064e3b', // emerald-900
  },
  control_center: {
    fill: '#f0fdf4', // green-50
    stroke: '#22c55e', // green-500
    text: '#14532d', // green-900
  },
  cooling_system: {
    fill: '#f0f9ff', // sky-50
    stroke: '#0ea5e9', // sky-500
    text: '#0c4a6e', // sky-900
  },
};

// Road grade thresholds for color coding
export const ROAD_GRADE_COLORS = {
  easy: '#22c55e',    // green - <5%
  moderate: '#f59e0b', // amber - 5-10%
  steep: '#ef4444',    // red - >10%
};

// =============================================================================
// Footprint Polygon Calculation
// =============================================================================

/**
 * Convert a center point + dimensions to polygon coordinates
 * 
 * @param centerLat - Latitude of center point
 * @param centerLng - Longitude of center point
 * @param lengthM - Footprint length in meters (north-south dimension)
 * @param widthM - Footprint width in meters (east-west dimension)
 * @returns Array of [lat, lng] coordinates forming the polygon (5 points, closed)
 */
export function calculateFootprintPolygon(
  centerLat: number,
  centerLng: number,
  lengthM: number,
  widthM: number
): LatLngTuple[] {
  // Calculate degrees offset
  const halfLengthDeg = (lengthM / 2) / METERS_PER_DEGREE_LAT;
  const metersPerDegreeLng = METERS_PER_DEGREE_LAT * Math.cos((centerLat * Math.PI) / 180);
  const halfWidthDeg = (widthM / 2) / metersPerDegreeLng;

  // Calculate corners (counter-clockwise from SW)
  const sw: LatLngTuple = [centerLat - halfLengthDeg, centerLng - halfWidthDeg];
  const se: LatLngTuple = [centerLat - halfLengthDeg, centerLng + halfWidthDeg];
  const ne: LatLngTuple = [centerLat + halfLengthDeg, centerLng + halfWidthDeg];
  const nw: LatLngTuple = [centerLat + halfLengthDeg, centerLng - halfWidthDeg];

  // Return closed polygon
  return [sw, se, ne, nw, sw];
}

/**
 * Get the appropriate color for a road based on its grade
 */
export function getRoadGradeColor(gradePct: number | undefined): string {
  if (gradePct === undefined || gradePct === null) {
    return ROAD_GRADE_COLORS.moderate; // Default to moderate if unknown
  }
  if (gradePct < 5) {
    return ROAD_GRADE_COLORS.easy;
  }
  if (gradePct <= 10) {
    return ROAD_GRADE_COLORS.moderate;
  }
  return ROAD_GRADE_COLORS.steep;
}

/**
 * Calculate pixel width for road based on meters and zoom level
 * This provides a minimum visible width while respecting proportions
 */
export function getRoadWidth(widthM: number | undefined, _zoom: number): number {
  const baseWidth = widthM ?? 5;
  // Minimum 4px, max 12px, scale with zoom
  return Math.min(12, Math.max(4, baseWidth * 0.8));
}

/**
 * Normalize asset type (backend uses 'solar_array', frontend used 'solar')
 */
export function normalizeAssetType(type: string): string {
  if (type === 'solar_array') return 'solar_array';
  return type;
}

/**
 * Format capacity display
 */
export function formatCapacity(capacityKw: number | undefined): string {
  if (capacityKw === undefined || capacityKw === null) return '—';
  if (capacityKw >= 1000) {
    return `${(capacityKw / 1000).toFixed(1)} MW`;
  }
  return `${capacityKw.toFixed(0)} kW`;
}

/**
 * Format slope display
 */
export function formatSlope(slopeDeg: number | undefined): string {
  if (slopeDeg === undefined || slopeDeg === null) return '—';
  return `${slopeDeg.toFixed(1)}°`;
}

/**
 * Format elevation display
 */
export function formatElevation(elevationM: number | undefined): string {
  if (elevationM === undefined || elevationM === null) return '—';
  return `${elevationM.toFixed(0)} m`;
}

/**
 * Format footprint dimensions
 */
export function formatFootprint(lengthM: number | undefined, widthM: number | undefined): string {
  if (!lengthM || !widthM) return '—';
  return `${lengthM.toFixed(0)}m × ${widthM.toFixed(0)}m`;
}





