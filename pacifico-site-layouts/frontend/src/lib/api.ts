/**
 * API client and service functions
 */
import axios from 'axios';
import { fetchAuthSession } from 'aws-amplify/auth';
import { config } from './config';
import type {
  Site,
  SiteListResponse,
  SiteUploadResponse,
  LayoutDetail,
  LayoutListResponse,
  GenerateLayoutRequest,
  ExportResponse,
  ExportFormat,
  LayoutStatusResponse,
  GenerateLayoutResponseUnion,
  // D-01: Terrain visualization types
  TerrainSummaryResponse,
  ContoursResponse,
  BuildableAreaResponse,
  SlopeHeatmapResponse,
  // D-03: Exclusion zone types
  ExclusionZone,
  ExclusionZoneCreateRequest,
  ExclusionZoneUpdateRequest,
  ExclusionZoneListResponse,
  ExclusionZoneTypesResponse,
  // D-05: Layout variant types
  LayoutStrategiesResponse,
  LayoutVariantsResponse,
  GenerateVariantsRequest,
  // D-05-06: Preferred layout types
  PreferredLayoutResponse,
} from '../types';

// =============================================================================
// Axios Instance
// =============================================================================

export const api = axios.create({
  baseURL: config.apiUrl,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth token to requests
api.interceptors.request.use(async (requestConfig) => {
  try {
    const session = await fetchAuthSession();
    const token = session.tokens?.idToken?.toString();
    if (token) {
      requestConfig.headers.Authorization = `Bearer ${token}`;
    }
  } catch {
    // Not authenticated - continue without token
  }
  return requestConfig;
});

// Handle 401 responses
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Redirect to login on auth failure
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// =============================================================================
// Sites API
// =============================================================================

/**
 * Get all sites for the current user
 */
export async function getSites(): Promise<SiteListResponse> {
  const response = await api.get<SiteListResponse>('/api/sites');
  return response.data;
}

/**
 * Get a single site by ID
 */
export async function getSite(siteId: string): Promise<Site> {
  const response = await api.get<Site>(`/api/sites/${siteId}`);
  return response.data;
}

/**
 * Upload a KML/KMZ file to create a new site
 */
export async function uploadSite(file: File): Promise<SiteUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);
  
  const response = await api.post<SiteUploadResponse>('/api/sites/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data;
}

/**
 * Delete a site
 */
export async function deleteSite(siteId: string): Promise<void> {
  await api.delete(`/api/sites/${siteId}`);
}

// =============================================================================
// Layouts API
// =============================================================================

/**
 * Generate a new layout for a site
 * 
 * In sync mode (default): Returns full LayoutGenerateResponse immediately
 * In async mode: Returns LayoutEnqueueResponse with layout_id for polling
 */
export async function generateLayout(
  request: GenerateLayoutRequest
): Promise<GenerateLayoutResponseUnion> {
  const response = await api.post<GenerateLayoutResponseUnion>('/api/layouts/generate', request);
  return response.data;
}

/**
 * Get layout generation status (C-04)
 * Used for polling when async layout generation is enabled
 */
export async function getLayoutStatus(layoutId: string): Promise<LayoutStatusResponse> {
  const response = await api.get<LayoutStatusResponse>(`/api/layouts/${layoutId}/status`);
  return response.data;
}

/**
 * Get a layout by ID with assets and roads
 */
export async function getLayout(layoutId: string): Promise<LayoutDetail> {
  const response = await api.get<LayoutDetail>(`/api/layouts/${layoutId}`);
  return response.data;
}

/**
 * Get all layouts for a site
 */
export async function getLayoutsForSite(siteId: string): Promise<LayoutListResponse> {
  const response = await api.get<LayoutListResponse>('/api/layouts', {
    params: { site_id: siteId },
  });
  return response.data;
}

/**
 * Delete a layout
 */
export async function deleteLayout(layoutId: string): Promise<void> {
  await api.delete(`/api/layouts/${layoutId}`);
}

// =============================================================================
// Export API
// =============================================================================

/**
 * Export a layout to the specified format
 * Returns a presigned URL for download
 */
export async function exportLayout(
  layoutId: string,
  format: ExportFormat
): Promise<ExportResponse> {
  const response = await api.get<ExportResponse>(
    `/api/layouts/${layoutId}/export/${format}`
  );
  return response.data;
}

/**
 * Export layout as GeoJSON
 */
export async function exportLayoutGeoJSON(layoutId: string): Promise<ExportResponse> {
  return exportLayout(layoutId, 'geojson');
}

/**
 * Export layout as KMZ (Google Earth)
 */
export async function exportLayoutKMZ(layoutId: string): Promise<ExportResponse> {
  return exportLayout(layoutId, 'kmz');
}

/**
 * Export layout as PDF report
 */
export async function exportLayoutPDF(layoutId: string): Promise<ExportResponse> {
  return exportLayout(layoutId, 'pdf');
}

/**
 * Export layout as CSV (tabular data)
 * D-04-05: New export format for spreadsheet analysis
 */
export async function exportLayoutCSV(layoutId: string): Promise<ExportResponse> {
  return exportLayout(layoutId, 'csv');
}

/**
 * Download a file from a presigned URL
 * D-04-06: Uses filename from export response for proper naming
 */
export function downloadFromUrl(url: string, filename?: string): void {
  const link = document.createElement('a');
  link.href = url;
  link.target = '_blank';
  if (filename) {
    link.download = filename;
  }
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

// =============================================================================
// Terrain API (D-01)
// =============================================================================

/**
 * Get terrain analysis summary for a site
 * Includes elevation, slope statistics and buildable area percentages
 */
export async function getTerrainSummary(siteId: string): Promise<TerrainSummaryResponse> {
  const response = await api.get<TerrainSummaryResponse>(
    `/api/sites/${siteId}/terrain/summary`
  );
  return response.data;
}

/**
 * Get contour lines for a site
 * Returns GeoJSON LineStrings at specified elevation intervals
 */
export async function getTerrainContours(
  siteId: string, 
  intervalM: number = 5
): Promise<ContoursResponse> {
  const response = await api.get<ContoursResponse>(
    `/api/sites/${siteId}/terrain/contours`,
    { params: { interval_m: intervalM } }
  );
  return response.data;
}

/**
 * Get buildable area polygons for a site
 * Returns areas where slope is within limits for specified asset type
 */
export async function getTerrainBuildableArea(
  siteId: string,
  assetType: string = 'solar_array',
  maxSlope?: number
): Promise<BuildableAreaResponse> {
  const response = await api.get<BuildableAreaResponse>(
    `/api/sites/${siteId}/terrain/buildable-area`,
    { params: { asset_type: assetType, max_slope: maxSlope } }
  );
  return response.data;
}

/**
 * Get slope heatmap polygons for a site
 * Returns colored zones by slope severity
 */
export async function getTerrainSlopeHeatmap(siteId: string): Promise<SlopeHeatmapResponse> {
  const response = await api.get<SlopeHeatmapResponse>(
    `/api/sites/${siteId}/terrain/slope-heatmap`
  );
  return response.data;
}

// =============================================================================
// Exclusion Zones API (D-03)
// =============================================================================

/**
 * Get available exclusion zone types
 * Returns types with colors and default buffers
 */
export async function getExclusionZoneTypes(): Promise<ExclusionZoneTypesResponse> {
  const response = await api.get<ExclusionZoneTypesResponse>(
    '/api/sites/exclusion-zone-types'
  );
  return response.data;
}

/**
 * Get all exclusion zones for a site
 */
export async function getExclusionZones(siteId: string): Promise<ExclusionZoneListResponse> {
  const response = await api.get<ExclusionZoneListResponse>(
    `/api/sites/${siteId}/exclusion-zones`
  );
  return response.data;
}

/**
 * Get a specific exclusion zone
 */
export async function getExclusionZone(siteId: string, zoneId: string): Promise<ExclusionZone> {
  const response = await api.get<ExclusionZone>(
    `/api/sites/${siteId}/exclusion-zones/${zoneId}`
  );
  return response.data;
}

/**
 * Create a new exclusion zone
 */
export async function createExclusionZone(
  siteId: string,
  zone: ExclusionZoneCreateRequest
): Promise<ExclusionZone> {
  const response = await api.post<ExclusionZone>(
    `/api/sites/${siteId}/exclusion-zones`,
    zone
  );
  return response.data;
}

/**
 * Update an existing exclusion zone
 */
export async function updateExclusionZone(
  siteId: string,
  zoneId: string,
  zone: ExclusionZoneUpdateRequest
): Promise<ExclusionZone> {
  const response = await api.put<ExclusionZone>(
    `/api/sites/${siteId}/exclusion-zones/${zoneId}`,
    zone
  );
  return response.data;
}

/**
 * Delete an exclusion zone
 */
export async function deleteExclusionZone(siteId: string, zoneId: string): Promise<void> {
  await api.delete(`/api/sites/${siteId}/exclusion-zones/${zoneId}`);
}

// =============================================================================
// Layout Variants API (D-05)
// =============================================================================

/**
 * Get available layout optimization strategies
 */
export async function getLayoutStrategies(): Promise<LayoutStrategiesResponse> {
  const response = await api.get<LayoutStrategiesResponse>('/api/layouts/strategies');
  return response.data;
}

/**
 * Generate multiple layout variants for comparison
 */
export async function generateLayoutVariants(
  request: GenerateVariantsRequest
): Promise<LayoutVariantsResponse> {
  const response = await api.post<LayoutVariantsResponse>(
    '/api/layouts/generate-variants',
    request
  );
  return response.data;
}

// =============================================================================
// Preferred Layout API (D-05-06)
// =============================================================================

/**
 * Get the preferred layout for a site
 */
export async function getPreferredLayout(siteId: string): Promise<PreferredLayoutResponse> {
  const response = await api.get<PreferredLayoutResponse>(
    `/api/sites/${siteId}/preferred-layout`
  );
  return response.data;
}

/**
 * Set or clear the preferred layout for a site
 * Pass null to clear the preferred layout
 */
export async function setPreferredLayout(
  siteId: string,
  layoutId: string | null
): Promise<PreferredLayoutResponse> {
  const response = await api.put<PreferredLayoutResponse>(
    `/api/sites/${siteId}/preferred-layout`,
    { layout_id: layoutId }
  );
  return response.data;
}
