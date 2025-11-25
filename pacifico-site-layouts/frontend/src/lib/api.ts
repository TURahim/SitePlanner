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
 * Download a file from a presigned URL
 * Opens the URL in a new tab or triggers download
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
