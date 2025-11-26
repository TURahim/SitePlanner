/**
 * Site detail page with map and layout controls
 * 
 * Supports both sync and async layout generation (Phase C)
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { MapContainer, TileLayer, GeoJSON, Marker, Popup, useMap, FeatureGroup } from 'react-leaflet';
import { EditControl } from 'react-leaflet-draw';
import L from 'leaflet';
import type { FeatureCollection, Feature, Polygon } from 'geojson';
import 'leaflet-draw/dist/leaflet.draw.css';
import { 
  getSite, 
  generateLayout, 
  getLayoutsForSite, 
  deleteSite,
  exportLayoutGeoJSON,
  exportLayoutKMZ,
  exportLayoutPDF,
  exportLayoutCSV,
  downloadFromUrl,
  // D-01: Terrain visualization
  getTerrainSummary,
  getTerrainContours,
  getTerrainSlopeHeatmap,
  getTerrainBuildableArea,
  // D-05-06: Preferred layout
  getPreferredLayout,
  setPreferredLayout,
} from '../lib/api';
import { useLayoutPolling, formatElapsedTime } from '../hooks/useLayoutPolling';
import {
  ASSET_COLORS,
  calculateFootprintPolygon,
  getRoadGradeColor,
  formatCapacity,
  formatSlope,
  formatElevation,
  formatFootprint,
} from '../lib/mapUtils';
import { getAssetIconDataUrl } from '../components/AssetIcons';
import { ExclusionZonePanel } from '../components/ExclusionZonePanel';
import { VariantSelector } from '../components/LayoutVariants';
import { generateLayoutVariants } from '../lib/api';
import type { 
  Site, 
  LayoutGenerateResponse, 
  LayoutListItem, 
  Asset, 
  Road, 
  ExportFormat,
  // D-01: Terrain types
  TerrainSummaryResponse,
  ContoursResponse,
  SlopeHeatmapResponse,
  BuildableAreaResponse,
  TerrainLayerType,
  // D-03: Exclusion zone types
  ExclusionZone,
  // D-05: Layout variant types
  LayoutVariant,
  VariantComparison,
} from '../types';
import { isAsyncLayoutResponse } from '../types';
import 'leaflet/dist/leaflet.css';
import './SiteDetailPage.css';

// Fix Leaflet default marker icon issue
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png';
import markerIcon from 'leaflet/dist/images/marker-icon.png';
import markerShadow from 'leaflet/dist/images/marker-shadow.png';

// @ts-expect-error - Leaflet types don't include _getIconUrl
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
});

// Format asset type for display
function formatAssetType(type: string): string {
  const mapping: Record<string, string> = {
    solar_array: 'Solar Array',
    solar: 'Solar Array',
    battery: 'Battery Storage',
    generator: 'Generator',
    substation: 'Substation',
    transformer: 'Transformer',
    inverter: 'Inverter',
  };
  return mapping[type.toLowerCase()] || type.charAt(0).toUpperCase() + type.slice(1);
}

// D-02: Format volume with thousands separator
function formatVolume(volumeM3: number | null | undefined): string {
  if (volumeM3 == null || volumeM3 === 0) return '0 m³';
  return `${volumeM3.toLocaleString('en-US', { maximumFractionDigits: 0 })} m³`;
}

// Phase E: Convert aspect angle to cardinal direction
function getAspectDirection(aspectDeg: number): string {
  if (aspectDeg < 0) return 'Flat';
  const directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
  const index = Math.round(aspectDeg / 45) % 8;
  return `${directions[index]} (${aspectDeg.toFixed(0)}°)`;
}

// D-02: Determine earthwork status (Export = cut > fill, Import = fill > cut)
function getEarthworkStatus(cut: number | null | undefined, fill: number | null | undefined): {
  type: 'export' | 'import' | 'balanced';
  net: number;
} {
  const cutVal = cut ?? 0;
  const fillVal = fill ?? 0;
  const net = cutVal - fillVal;
  
  if (Math.abs(net) < 10) return { type: 'balanced', net: 0 }; // Within 10m³ tolerance
  return {
    type: net > 0 ? 'export' : 'import',
    net: Math.abs(net),
  };
}

// Custom marker icons for assets - uses SVG icon data URLs
function createAssetIcon(assetType: string): L.DivIcon {
  const iconUrl = getAssetIconDataUrl(assetType, 36);
  const colors = ASSET_COLORS[assetType] || ASSET_COLORS.solar;
  
  return L.divIcon({
    className: 'asset-marker',
    html: `
      <div class="asset-marker-container" style="
        width: 40px; 
        height: 40px; 
        display: flex;
        align-items: center;
        justify-content: center;
        background: white;
        border-radius: 8px;
        border: 2px solid ${colors.stroke};
        box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        transition: transform 0.15s ease, box-shadow 0.15s ease;
      ">
        <img src="${iconUrl}" alt="${assetType}" style="width: 28px; height: 28px;" />
      </div>
    `,
    iconSize: [40, 40],
    iconAnchor: [20, 20],
  });
}

// Component to fit map bounds to GeoJSON
function FitBounds({ geojson }: { geojson: FeatureCollection | null }) {
  const map = useMap();
  
  useEffect(() => {
    if (geojson) {
      const layer = L.geoJSON(geojson);
      const bounds = layer.getBounds();
      if (bounds.isValid()) {
        map.fitBounds(bounds, { padding: [50, 50] });
      }
    }
  }, [map, geojson]);
  
  return null;
}

export function SiteDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  
  // Site state
  const [site, setSite] = useState<Site | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Layout state
  const [layouts, setLayouts] = useState<LayoutListItem[]>([]);
  const [currentLayout, setCurrentLayout] = useState<LayoutGenerateResponse | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [targetCapacity, setTargetCapacity] = useState(1000);
  const [generationError, setGenerationError] = useState<string | null>(null);
  
  // Phase C: Async polling state
  const {
    status: pollingStatus,
    isPolling,
    startPolling,
    stopPolling,
    elapsedTime,
    layoutData: polledLayoutData,
  } = useLayoutPolling({
    interval: 2000, // Poll every 2 seconds
    onComplete: (status) => {
      console.log('Layout completed:', status);
      // Refresh layouts list
      if (id) fetchLayouts(id);
    },
    onError: (err) => {
      setGenerationError(err);
      setIsGenerating(false);
    },
  });
  
  // Export state
  const [exportingFormat, setExportingFormat] = useState<ExportFormat | null>(null);
  
  // D-01: Terrain layer state
  const [terrainLayers, setTerrainLayers] = useState<Set<TerrainLayerType>>(new Set());
  const [terrainLoading, setTerrainLoading] = useState<Set<TerrainLayerType>>(new Set());
  const [terrainSummary, setTerrainSummary] = useState<TerrainSummaryResponse | null>(null);
  const [contoursData, setContoursData] = useState<ContoursResponse | null>(null);
  const [slopeHeatmapData, setSlopeHeatmapData] = useState<SlopeHeatmapResponse | null>(null);
  const [buildableAreaData, setBuildableAreaData] = useState<BuildableAreaResponse | null>(null);
  
  // Map ref for imperative access
  const mapRef = useRef<L.Map | null>(null);
  
  // D-03: Exclusion zone state
  const [exclusionZones, setExclusionZones] = useState<ExclusionZone[]>([]);
  const [isDrawingZone, setIsDrawingZone] = useState(false);
  const [drawnPolygon, setDrawnPolygon] = useState<Polygon | null>(null);
  const featureGroupRef = useRef<L.FeatureGroup | null>(null);
  
  // D-05: Layout variants state
  const [layoutVariants, setLayoutVariants] = useState<LayoutVariant[] | null>(null);
  const [variantComparison, setVariantComparison] = useState<VariantComparison | null>(null);
  const [selectedVariant, setSelectedVariant] = useState<LayoutVariant | null>(null);
  const [isGeneratingVariants, setIsGeneratingVariants] = useState(false);
  
  // D-05-06: Preferred layout state
  const [preferredLayoutId, setPreferredLayoutId] = useState<string | null>(null);
  
  // When polled layout data arrives, convert it to display format
  useEffect(() => {
    if (polledLayoutData && pollingStatus?.status === 'completed') {
      // Convert LayoutDetail to LayoutGenerateResponse format for display
      const layoutResponse: LayoutGenerateResponse = {
        layout: {
          id: polledLayoutData.id,
          site_id: polledLayoutData.site_id,
          status: polledLayoutData.status,
          total_capacity_kw: polledLayoutData.total_capacity_kw,
          cut_volume_m3: polledLayoutData.cut_volume_m3,
          fill_volume_m3: polledLayoutData.fill_volume_m3,
          error_message: polledLayoutData.error_message,
          created_at: polledLayoutData.created_at,
          updated_at: polledLayoutData.updated_at,
        },
        assets: polledLayoutData.assets,
        roads: polledLayoutData.roads,
        geojson: {
          type: 'FeatureCollection',
          features: [],
        },
      };
      setCurrentLayout(layoutResponse);
      setIsGenerating(false);
    }
  }, [polledLayoutData, pollingStatus]);

  // Fetch site data on mount
  useEffect(() => {
    if (id) {
      fetchSite(id);
      fetchLayouts(id);
      fetchPreferredLayout(id);
    }
  }, [id]);
  
  // D-05-06: Fetch preferred layout
  async function fetchPreferredLayout(siteId: string) {
    try {
      const response = await getPreferredLayout(siteId);
      setPreferredLayoutId(response.preferred_layout_id);
    } catch (err) {
      console.error('Failed to fetch preferred layout:', err);
      // Not critical - continue without preferred
    }
  }

  async function fetchSite(siteId: string) {
    try {
      setIsLoading(true);
      setError(null);
      const data = await getSite(siteId);
      setSite(data);
    } catch (err) {
      setError('Failed to load site. It may not exist or you may not have access.');
      console.error('Failed to fetch site:', err);
    } finally {
      setIsLoading(false);
    }
  }

  async function fetchLayouts(siteId: string) {
    try {
      const response = await getLayoutsForSite(siteId);
      setLayouts(response.layouts);
    } catch (err) {
      console.error('Failed to fetch layouts:', err);
    }
  }

  const handleGenerateLayout = async () => {
    if (!id) return;
    
    try {
      setIsGenerating(true);
      setGenerationError(null);
      setCurrentLayout(null);
      
      const response = await generateLayout({
        site_id: id,
        target_capacity_kw: targetCapacity,
      });
      
      // Check if async response (Phase C)
      if (isAsyncLayoutResponse(response)) {
        // Async mode: Start polling for status
        console.log('Async layout generation started:', response.layout_id);
        startPolling(response.layout_id);
      } else {
        // Sync mode: Layout is ready immediately
        setCurrentLayout(response);
        setIsGenerating(false);
        // Refresh layouts list
        fetchLayouts(id);
      }
    } catch (err) {
      console.error('Failed to generate layout:', err);
      setGenerationError('Failed to generate layout. Please try again.');
      setIsGenerating(false);
    }
  };
  
  const handleCancelGeneration = () => {
    stopPolling();
    setIsGenerating(false);
    setGenerationError(null);
  };

  const handleDeleteSite = async () => {
    if (!site) return;
    
    if (!confirm(`Are you sure you want to delete "${site.name}"? This will also delete all layouts and cannot be undone.`)) {
      return;
    }
    
    try {
      await deleteSite(site.id);
      navigate('/projects');
    } catch (err) {
      console.error('Failed to delete site:', err);
      alert('Failed to delete site. Please try again.');
    }
  };

  const handleExport = async (format: ExportFormat) => {
    if (!currentLayout) return;
    
    try {
      setExportingFormat(format);
      
      let response;
      switch (format) {
        case 'geojson':
          response = await exportLayoutGeoJSON(currentLayout.layout.id);
          break;
        case 'kmz':
          response = await exportLayoutKMZ(currentLayout.layout.id);
          break;
        case 'pdf':
          response = await exportLayoutPDF(currentLayout.layout.id);
          break;
        case 'csv':
          response = await exportLayoutCSV(currentLayout.layout.id);
          break;
      }
      
      // D-04-06: Download with proper filename from response
      downloadFromUrl(response.download_url, response.filename);
    } catch (err) {
      console.error(`Failed to export ${format}:`, err);
      alert(`Failed to export ${format.toUpperCase()}. Please try again.`);
    } finally {
      setExportingFormat(null);
    }
  };

  // D-01: Toggle terrain layer
  const handleToggleTerrainLayer = async (layer: TerrainLayerType) => {
    if (!id) return;
    
    const newLayers = new Set(terrainLayers);
    
    if (newLayers.has(layer)) {
      // Turn off layer
      newLayers.delete(layer);
      setTerrainLayers(newLayers);
      return;
    }
    
    // Turn on layer - fetch data if needed
    newLayers.add(layer);
    setTerrainLayers(newLayers);
    
    // Check if we need to fetch data
    const needsFetch = (
      (layer === 'contours' && !contoursData) ||
      (layer === 'slopeHeatmap' && !slopeHeatmapData) ||
      (layer === 'buildableArea' && !buildableAreaData)
    );
    
    if (!needsFetch) return;
    
    // Set loading state
    setTerrainLoading(prev => new Set(prev).add(layer));
    
    try {
      // Fetch terrain summary if not already loaded
      if (!terrainSummary) {
        const summary = await getTerrainSummary(id);
        setTerrainSummary(summary);
      }
      
      // Fetch specific layer data
      switch (layer) {
        case 'contours':
          const contours = await getTerrainContours(id, 5);
          setContoursData(contours);
          break;
        case 'slopeHeatmap':
          const heatmap = await getTerrainSlopeHeatmap(id);
          setSlopeHeatmapData(heatmap);
          break;
        case 'buildableArea':
          const buildable = await getTerrainBuildableArea(id, 'solar_array');
          setBuildableAreaData(buildable);
          break;
      }
    } catch (err) {
      console.error(`Failed to load ${layer} data:`, err);
      // Remove layer on error
      setTerrainLayers(prev => {
        const next = new Set(prev);
        next.delete(layer);
        return next;
      });
    } finally {
      setTerrainLoading(prev => {
        const next = new Set(prev);
        next.delete(layer);
        return next;
      });
    }
  };

  const formatArea = (areaM2: number): string => {
    const hectares = areaM2 / 10000;
    if (hectares >= 1) {
      return `${hectares.toFixed(1)} ha`;
    }
    return `${areaM2.toLocaleString()} m²`;
  };
  
  // D-03: Exclusion zone handlers
  const handleStartDrawing = useCallback(() => {
    setIsDrawingZone(true);
  }, []);
  
  const handleCancelDrawing = useCallback(() => {
    setIsDrawingZone(false);
    setDrawnPolygon(null);
    // Clear any drawn shapes from the feature group
    if (featureGroupRef.current) {
      featureGroupRef.current.clearLayers();
    }
  }, []);
  
  const handlePolygonCreated = useCallback((e: { layer: L.Layer }) => {
    const layer = e.layer as L.Polygon;
    const geoJSON = layer.toGeoJSON();
    
    if (geoJSON.geometry.type === 'Polygon') {
      setDrawnPolygon(geoJSON.geometry as Polygon);
    }
    
    setIsDrawingZone(false);
  }, []);
  
  const handlePolygonSaved = useCallback(() => {
    setDrawnPolygon(null);
    // Clear the feature group
    if (featureGroupRef.current) {
      featureGroupRef.current.clearLayers();
    }
  }, []);
  
  const handleZonesChange = useCallback((zones: ExclusionZone[]) => {
    setExclusionZones(zones);
  }, []);
  
  // D-05: Generate layout variants handler
  const handleGenerateVariants = async () => {
    if (!id) return;
    
    try {
      setIsGeneratingVariants(true);
      setGenerationError(null);
      setCurrentLayout(null);
      setLayoutVariants(null);
      setVariantComparison(null);
      setSelectedVariant(null);
      
      const response = await generateLayoutVariants({
        site_id: id,
        target_capacity_kw: targetCapacity,
      });
      
      setLayoutVariants(response.variants);
      setVariantComparison(response.comparison);
      
      // Auto-select the first (balanced) variant
      if (response.variants.length > 0) {
        setSelectedVariant(response.variants[0]);
        // Convert to LayoutGenerateResponse format for display
        const firstVariant = response.variants[0];
        setCurrentLayout({
          layout: firstVariant.layout,
          assets: firstVariant.assets,
          roads: firstVariant.roads,
          geojson: firstVariant.geojson,
        });
      }
      
      // Refresh layouts list
      fetchLayouts(id);
    } catch (err) {
      console.error('Failed to generate variants:', err);
      setGenerationError('Failed to generate layout variants. Please try again.');
    } finally {
      setIsGeneratingVariants(false);
    }
  };
  
  // D-05: Select a variant handler
  const handleSelectVariant = useCallback((variant: LayoutVariant) => {
    setSelectedVariant(variant);
    setCurrentLayout({
      layout: variant.layout,
      assets: variant.assets,
      roads: variant.roads,
      geojson: variant.geojson,
    });
  }, []);
  
  // D-05-06: Set preferred layout handler
  const handleSetPreferred = useCallback(async (layoutId: string) => {
    if (!id) return;
    
    try {
      // Toggle: if already preferred, clear it; otherwise set it
      const newPreferredId = preferredLayoutId === layoutId ? null : layoutId;
      const response = await setPreferredLayout(id, newPreferredId);
      setPreferredLayoutId(response.preferred_layout_id);
    } catch (err) {
      console.error('Failed to set preferred layout:', err);
      // Show a brief notification (could use toast)
      alert('Failed to update preferred layout');
    }
  }, [id, preferredLayoutId]);

  // Create GeoJSON for the site boundary
  const boundaryGeoJSON: FeatureCollection | null = site ? {
    type: 'FeatureCollection',
    features: [{
      type: 'Feature',
      properties: { name: site.name },
      geometry: site.boundary,
    }],
  } : null;

  // Style for the boundary polygon
  const boundaryStyle = {
    color: '#1B1464',
    weight: 3,
    fillColor: '#3A80C6',
    fillOpacity: 0.15,
  };

  // Style function for roads - varies by grade
  const getRoadStyle = (road: Road) => {
    const gradeColor = getRoadGradeColor(road.max_grade_pct);
    const width = Math.max(4, (road.width_m ?? 5) * 0.8);
    return {
      color: gradeColor,
      weight: width,
      opacity: 0.85,
      lineCap: 'round' as const,
      lineJoin: 'round' as const,
    };
  };

  if (isLoading) {
    return (
      <div className="site-detail-page">
        <aside className="site-sidebar">
          <div className="loading-state">
            <div className="loading-spinner" />
            <p>Loading site...</p>
          </div>
        </aside>
        <div className="map-container">
          <div className="map-placeholder">
            <div className="loading-spinner" />
          </div>
        </div>
      </div>
    );
  }

  if (error || !site) {
    return (
      <div className="site-detail-page">
        <aside className="site-sidebar">
          <div className="sidebar-header">
            <Link to="/projects" className="back-link">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="15 18 9 12 15 6" />
              </svg>
              Back to Sites
            </Link>
          </div>
          <div className="error-state">
            <p>{error || 'Site not found'}</p>
            <Link to="/projects" className="btn-back">Return to Sites</Link>
          </div>
        </aside>
        <div className="map-container">
          <div className="map-placeholder">
            <p>Unable to load site</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="site-detail-page">
      <aside className="site-sidebar">
        <div className="sidebar-header">
          <Link to="/projects" className="back-link">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="15 18 9 12 15 6" />
            </svg>
            Back to Sites
          </Link>
        </div>

        <div className="site-info">
          <h1>{site.name}</h1>
          <div className="site-stats">
            <div className="stat">
              <span className="stat-value">{formatArea(site.area_m2)}</span>
              <span className="stat-label">Area</span>
            </div>
            <div className="stat">
              <span className="stat-value">{layouts.length}</span>
              <span className="stat-label">Layouts</span>
            </div>
          </div>
        </div>

        <div className="sidebar-section">
          <h2>Generate Layout</h2>
          <p>Create an optimized asset layout for this site.</p>
          
          <div className="form-group">
            <label htmlFor="capacity">Target Capacity (kW)</label>
            <input
              id="capacity"
              type="number"
              value={targetCapacity}
              onChange={(e) => setTargetCapacity(Number(e.target.value))}
              min={100}
              max={100000}
              step={100}
              disabled={isGenerating || isPolling}
            />
          </div>

          {/* Error message */}
          {generationError && (
            <div className="generation-error">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              <span>{generationError}</span>
            </div>
          )}

          {/* Processing state (Phase C async) */}
          {(isGenerating || isPolling) && pollingStatus && (
            <div className="processing-state">
              <div className="processing-header">
                <div className="processing-spinner" />
                <span className="processing-status">
                  {pollingStatus.status === 'queued' && 'Queued...'}
                  {pollingStatus.status === 'processing' && 'Processing...'}
                </span>
              </div>
              <div className="processing-details">
                <span className="elapsed-time">
                  Elapsed: {formatElapsedTime(elapsedTime)}
                </span>
                <span className="processing-hint">
                  {pollingStatus.status === 'queued' 
                    ? 'Waiting for worker...' 
                    : 'Generating terrain-aware layout...'}
                </span>
              </div>
              <div className="processing-progress">
                <div 
                  className="progress-bar" 
                  style={{ 
                    width: pollingStatus.status === 'queued' ? '15%' : '60%',
                    transition: 'width 0.5s ease-out'
                  }} 
                />
              </div>
              <button 
                className="btn-cancel" 
                onClick={handleCancelGeneration}
                type="button"
              >
                Cancel
              </button>
            </div>
          )}

          {/* Generate buttons - hidden when processing */}
          {!isPolling && !isGenerating && !isGeneratingVariants && (
            <div className="generate-buttons">
              <button
                className="btn-generate"
                onClick={handleGenerateLayout}
                disabled={isGenerating}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
                </svg>
                Generate Layout
              </button>
              
              {/* D-05: Generate variants button */}
              <button
                className="btn-generate-variants"
                onClick={handleGenerateVariants}
                disabled={isGeneratingVariants}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="3" y="3" width="7" height="7" />
                  <rect x="14" y="3" width="7" height="7" />
                  <rect x="3" y="14" width="7" height="7" />
                  <rect x="14" y="14" width="7" height="7" />
                </svg>
                Compare Variants
              </button>
            </div>
          )}
          
          {/* D-05: Generating variants state */}
          {isGeneratingVariants && (
            <div className="processing-state">
              <div className="processing-header">
                <div className="processing-spinner" />
                <span className="processing-status">Generating variants...</span>
              </div>
              <div className="processing-details">
                <span className="processing-hint">
                  Creating 4 layout variants with different optimization strategies
                </span>
              </div>
              <div className="processing-progress">
                <div className="progress-bar" style={{ width: '50%' }} />
              </div>
            </div>
          )}
        </div>
        
        {/* D-05: Variant Selector (when variants are available) */}
        {layoutVariants && layoutVariants.length > 0 && variantComparison && (
          <div className="sidebar-section variant-section">
            <VariantSelector
              variants={layoutVariants}
              selectedVariant={selectedVariant}
              comparison={variantComparison}
              onSelectVariant={handleSelectVariant}
              preferredLayoutId={preferredLayoutId}
              onSetPreferred={handleSetPreferred}
            />
          </div>
        )}

        {/* D-01: Terrain Layers Section */}
        <div className="sidebar-section terrain-layers-section">
          <h2>Map Layers</h2>
          <p>Toggle terrain visualization layers on the map.</p>
          
          <div className="terrain-layers">
            {/* Slope Heatmap Toggle */}
            <button
              type="button"
              className={`terrain-layer-toggle ${terrainLayers.has('slopeHeatmap') ? 'active' : ''} ${terrainLoading.has('slopeHeatmap') ? 'loading' : ''}`}
              onClick={() => handleToggleTerrainLayer('slopeHeatmap')}
            >
              <div className="terrain-checkbox">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              </div>
              <div className="terrain-layer-info">
                <div className="terrain-layer-name">Slope Heatmap</div>
                <div className="terrain-layer-desc">Show slope severity by color</div>
              </div>
              {terrainLoading.has('slopeHeatmap') && (
                <div className="terrain-loading-indicator" />
              )}
            </button>
            
            {/* Contours Toggle */}
            <button
              type="button"
              className={`terrain-layer-toggle ${terrainLayers.has('contours') ? 'active' : ''} ${terrainLoading.has('contours') ? 'loading' : ''}`}
              onClick={() => handleToggleTerrainLayer('contours')}
            >
              <div className="terrain-checkbox">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              </div>
              <div className="terrain-layer-info">
                <div className="terrain-layer-name">Contour Lines</div>
                <div className="terrain-layer-desc">Elevation contours at 5m intervals</div>
              </div>
              {terrainLoading.has('contours') && (
                <div className="terrain-loading-indicator" />
              )}
            </button>
            
            {/* Buildable Area Toggle */}
            <button
              type="button"
              className={`terrain-layer-toggle ${terrainLayers.has('buildableArea') ? 'active' : ''} ${terrainLoading.has('buildableArea') ? 'loading' : ''}`}
              onClick={() => handleToggleTerrainLayer('buildableArea')}
            >
              <div className="terrain-checkbox">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              </div>
              <div className="terrain-layer-info">
                <div className="terrain-layer-name">Buildable Area</div>
                <div className="terrain-layer-desc">Areas suitable for solar arrays</div>
              </div>
              {terrainLoading.has('buildableArea') && (
                <div className="terrain-loading-indicator" />
              )}
            </button>
          </div>
          
          {/* Terrain Legend */}
          {terrainLayers.size > 0 && (
            <div className="terrain-legend">
              {terrainLayers.has('slopeHeatmap') && slopeHeatmapData && (
                <>
                  <h4>Slope Legend</h4>
                  <div className="slope-legend-items">
                    {slopeHeatmapData.legend.map((item) => (
                      <div key={item.class} className="slope-legend-item">
                        <span className="slope-legend-color" style={{ backgroundColor: item.color }} />
                        <span className="slope-legend-label">{item.label}</span>
                      </div>
                    ))}
                  </div>
                </>
              )}
              
              {terrainLayers.has('contours') && (
                <>
                  <h4>Contours</h4>
                  <div className="contour-legend-item">
                    <span className="contour-legend-line" />
                    <span className="slope-legend-label">5m elevation intervals</span>
                  </div>
                </>
              )}
              
              {terrainLayers.has('buildableArea') && (
                <>
                  <h4>Buildable Area</h4>
                  <div className="buildable-legend-item">
                    <span className="buildable-legend-swatch" />
                    <span className="slope-legend-label">Slope &lt;15° (Solar suitable)</span>
                  </div>
                </>
              )}
            </div>
          )}
          
          {/* Terrain Summary */}
          {terrainSummary && terrainLayers.size > 0 && (
            <div className="terrain-summary">
              <div className="terrain-summary-grid">
                <div className="terrain-stat">
                  <span className="terrain-stat-label">Elevation Range</span>
                  <span className="terrain-stat-value">
                    {terrainSummary.elevation.min_m.toFixed(0)}–{terrainSummary.elevation.max_m.toFixed(0)} m
                  </span>
                </div>
                <div className="terrain-stat">
                  <span className="terrain-stat-label">Avg Slope</span>
                  <span className="terrain-stat-value">{terrainSummary.slope.mean_deg.toFixed(1)}°</span>
                </div>
                <div className="terrain-summary-divider" />
                <div className="slope-distribution">
                  <div className="slope-distribution-label">Slope Distribution</div>
                  <div className="slope-distribution-bars">
                    {terrainSummary.slope.distribution.map((bucket, idx) => {
                      const colorClass = ['very-gentle', 'gentle', 'moderate', 'steep'][idx] || 'steep';
                      return (
                        <div
                          key={bucket.range}
                          className={`slope-bar ${colorClass}`}
                          style={{ width: `${bucket.percentage}%` }}
                          title={`${bucket.range}: ${bucket.percentage.toFixed(1)}%`}
                        />
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* D-03: Exclusion Zones Section */}
        <div className="sidebar-section exclusion-zones-section">
          <ExclusionZonePanel
            siteId={id || ''}
            isDrawing={isDrawingZone}
            onStartDrawing={handleStartDrawing}
            onCancelDrawing={handleCancelDrawing}
            onZonesChange={handleZonesChange}
            drawnPolygon={drawnPolygon}
            onPolygonSaved={handlePolygonSaved}
          />
        </div>

        {currentLayout && (
          <div className="sidebar-section layout-results">
            <h2>Layout Results</h2>
            <div className="layout-stats">
              <div className="layout-stat">
                <span className="stat-value">{currentLayout.assets.length}</span>
                <span className="stat-label">Assets</span>
              </div>
              <div className="layout-stat">
                <span className="stat-value">{currentLayout.layout.total_capacity_kw?.toFixed(0) || '—'}</span>
                <span className="stat-label">kW Total</span>
              </div>
              <div className="layout-stat">
                <span className="stat-value">{currentLayout.roads.length}</span>
                <span className="stat-label">Roads</span>
              </div>
            </div>
            
            {/* D-02: Cut/Fill Volume Display */}
            {(currentLayout.layout.cut_volume_m3 != null || currentLayout.layout.fill_volume_m3 != null) && (
              <div className="earthwork-section">
                <h3>Earthwork Estimate</h3>
                <div className="earthwork-stats">
                  <div className="earthwork-stat cut">
                    <div className="earthwork-icon">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M12 19V5M5 12l7-7 7 7"/>
                      </svg>
                    </div>
                    <div className="earthwork-info">
                      <span className="earthwork-value">{formatVolume(currentLayout.layout.cut_volume_m3)}</span>
                      <span className="earthwork-label">Cut</span>
                    </div>
                  </div>
                  <div className="earthwork-stat fill">
                    <div className="earthwork-icon">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M12 5v14M5 12l7 7 7-7"/>
                      </svg>
                    </div>
                    <div className="earthwork-info">
                      <span className="earthwork-value">{formatVolume(currentLayout.layout.fill_volume_m3)}</span>
                      <span className="earthwork-label">Fill</span>
                    </div>
                  </div>
                </div>
                
                {/* Net Earthwork Indicator */}
                {(() => {
                  const status = getEarthworkStatus(
                    currentLayout.layout.cut_volume_m3, 
                    currentLayout.layout.fill_volume_m3
                  );
                  return (
                    <div className={`earthwork-net ${status.type}`}>
                      <span className="earthwork-net-label">Net:</span>
                      <span className="earthwork-net-value">{formatVolume(status.net)}</span>
                      <span className={`earthwork-net-badge ${status.type}`}>
                        {status.type === 'export' && 'EXPORT'}
                        {status.type === 'import' && 'IMPORT'}
                        {status.type === 'balanced' && 'BALANCED'}
                      </span>
                    </div>
                  );
                })()}
                
                <div className="earthwork-hint">
                  <svg viewBox="0 0 24 24" fill="currentColor" width="14" height="14">
                    <circle cx="12" cy="12" r="10"/>
                    <path d="M12 16v-4M12 8h.01" stroke="white" strokeWidth="2" strokeLinecap="round"/>
                  </svg>
                  <span>Estimated grading for flat asset pads</span>
                </div>
              </div>
            )}
            
            <div className="legend">
              <h3>Asset Types</h3>
              <div className="legend-items">
                {Object.entries(ASSET_COLORS).map(([type, colors]) => (
                  <div key={type} className="legend-item">
                    <span 
                      className="legend-swatch" 
                      style={{ 
                        backgroundColor: colors.fill,
                        borderColor: colors.stroke,
                      }} 
                    />
                    <span className="legend-label">{formatAssetType(type)}</span>
                  </div>
                ))}
              </div>
              
              <h3 className="legend-subtitle">Road Grade</h3>
              <div className="legend-items road-legend">
                <div className="legend-item">
                  <span className="legend-line easy" />
                  <span className="legend-label">&lt; 5% (Easy)</span>
                </div>
                <div className="legend-item">
                  <span className="legend-line moderate" />
                  <span className="legend-label">5-10% (Moderate)</span>
                </div>
                <div className="legend-item">
                  <span className="legend-line steep" />
                  <span className="legend-label">&gt; 10% (Steep)</span>
                </div>
              </div>
            </div>
          </div>
        )}

        <div className="sidebar-section">
          <h2>Export Layout</h2>
          <div className="export-buttons">
            <button 
              className="btn-export" 
              disabled={!currentLayout || exportingFormat !== null}
              onClick={() => handleExport('geojson')}
            >
              {exportingFormat === 'geojson' ? (
                <><span className="spinner-small" /> Exporting...</>
              ) : (
                <>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                    <polyline points="14 2 14 8 20 8" />
                    <line x1="16" y1="13" x2="8" y2="13" />
                    <line x1="16" y1="17" x2="8" y2="17" />
                  </svg>
                  GeoJSON
                </>
              )}
            </button>
            <button 
              className="btn-export" 
              disabled={!currentLayout || exportingFormat !== null}
              onClick={() => handleExport('kmz')}
            >
              {exportingFormat === 'kmz' ? (
                <><span className="spinner-small" /> Exporting...</>
              ) : (
                <>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
                    <circle cx="12" cy="12" r="10" />
                    <line x1="2" y1="12" x2="22" y2="12" />
                    <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
                  </svg>
                  KMZ
                </>
              )}
            </button>
            <button 
              className="btn-export" 
              disabled={!currentLayout || exportingFormat !== null}
              onClick={() => handleExport('pdf')}
            >
              {exportingFormat === 'pdf' ? (
                <><span className="spinner-small" /> Exporting...</>
              ) : (
                <>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                    <polyline points="14 2 14 8 20 8" />
                    <line x1="16" y1="13" x2="8" y2="13" />
                    <line x1="16" y1="17" x2="8" y2="17" />
                    <polyline points="10 9 9 9 8 9" />
                  </svg>
                  PDF Report
                </>
              )}
            </button>
            {/* D-04-05: CSV export button */}
            <button 
              className="btn-export" 
              disabled={!currentLayout || exportingFormat !== null}
              onClick={() => handleExport('csv')}
            >
              {exportingFormat === 'csv' ? (
                <><span className="spinner-small" /> Exporting...</>
              ) : (
                <>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                    <polyline points="14 2 14 8 20 8" />
                    <line x1="8" y1="13" x2="16" y2="13" />
                    <line x1="8" y1="17" x2="12" y2="17" />
                  </svg>
                  CSV Data
                </>
              )}
            </button>
          </div>
          {!currentLayout && (
            <p className="export-hint">Generate a layout first to enable exports.</p>
          )}
        </div>

        <div className="sidebar-section danger-zone">
          <h2>Danger Zone</h2>
          <button className="btn-delete" onClick={handleDeleteSite}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="3 6 5 6 21 6" />
              <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
            </svg>
            Delete Site
          </button>
        </div>
      </aside>

      <div className="map-container">
        <MapContainer
          center={[0, 0]}
          zoom={2}
          style={{ height: '100%', width: '100%' }}
          ref={mapRef}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          
          {/* Fit map to boundary */}
          <FitBounds geojson={boundaryGeoJSON} />
          
          {/* Site boundary */}
          {boundaryGeoJSON && (
            <GeoJSON 
              data={boundaryGeoJSON} 
              style={boundaryStyle}
              onEachFeature={(feature, layer) => {
                layer.bindPopup(`<strong>${feature.properties?.name || 'Site Boundary'}</strong>`);
              }}
            />
          )}
          
          {/* D-03: Exclusion Zones Layer */}
          {exclusionZones.map((zone) => (
            <GeoJSON
              key={zone.id}
              data={{
                type: 'Feature',
                properties: { 
                  name: zone.name, 
                  zone_type: zone.zone_type,
                  buffer_m: zone.buffer_m,
                },
                geometry: zone.geometry,
              } as Feature}
              style={() => ({
                fillColor: zone.color,
                fillOpacity: 0.3,
                color: zone.color,
                weight: 2,
                opacity: 0.8,
                dashArray: '5, 5',
              })}
              onEachFeature={(feature, layer) => {
                layer.bindPopup(`
                  <div class="exclusion-zone-popup">
                    <strong>${feature.properties?.name}</strong>
                    <div class="popup-zone-type">${feature.properties?.zone_type}</div>
                    ${feature.properties?.buffer_m > 0 ? `<div class="popup-buffer">Buffer: ${feature.properties.buffer_m}m</div>` : ''}
                  </div>
                `);
              }}
            />
          ))}
          
          {/* D-03: Leaflet Draw Controls for creating exclusion zones */}
          <FeatureGroup ref={featureGroupRef}>
            {isDrawingZone && (
              <EditControl
                position="topright"
                onCreated={handlePolygonCreated}
                draw={{
                  rectangle: false,
                  circle: false,
                  circlemarker: false,
                  marker: false,
                  polyline: false,
                  polygon: {
                    allowIntersection: false,
                    drawError: {
                      color: '#ef4444',
                      message: 'Polygon cannot intersect itself',
                    },
                    shapeOptions: {
                      color: '#3b82f6',
                      fillColor: '#3b82f6',
                      fillOpacity: 0.3,
                    },
                  },
                }}
                edit={{
                  edit: false,
                  remove: false,
                }}
              />
            )}
          </FeatureGroup>
          
          {/* D-01: Slope Heatmap Layer */}
          {terrainLayers.has('slopeHeatmap') && slopeHeatmapData && slopeHeatmapData.features.map((feature, idx) => (
            <GeoJSON
              key={`slope-${idx}`}
              data={feature as GeoJSON.Feature}
              style={() => ({
                fillColor: feature.properties?.color || '#888',
                fillOpacity: 0.5,
                color: feature.properties?.color || '#888',
                weight: 0.5,
                opacity: 0.7,
              })}
            />
          ))}
          
          {/* D-01: Buildable Area Layer */}
          {terrainLayers.has('buildableArea') && buildableAreaData && buildableAreaData.features.map((feature, idx) => (
            <GeoJSON
              key={`buildable-${idx}`}
              data={feature as GeoJSON.Feature}
              style={() => ({
                fillColor: '#22c55e',
                fillOpacity: 0.25,
                color: '#16a34a',
                weight: 2,
                opacity: 0.8,
                dashArray: '5, 5',
              })}
            />
          ))}
          
          {/* D-01: Contour Lines Layer */}
          {terrainLayers.has('contours') && contoursData && contoursData.features.map((feature, idx) => (
            <GeoJSON
              key={`contour-${idx}`}
              data={feature as GeoJSON.Feature}
              style={() => ({
                color: '#8b5cf6',
                weight: 1.5,
                opacity: 0.7,
              })}
              onEachFeature={(feat, layer) => {
                const elev = feat.properties?.elevation_m;
                if (elev != null) {
                  layer.bindTooltip(`${elev.toFixed(0)}m`, {
                    permanent: false,
                    direction: 'auto',
                    className: 'contour-tooltip',
                  });
                }
              }}
            />
          ))}
          
          {/* Roads from layout - rendered with grade-based coloring */}
          {currentLayout?.roads.map((road: Road) => (
            <GeoJSON
              key={road.id}
              data={{
                type: 'Feature',
                properties: { 
                  name: road.name, 
                  length_m: road.length_m,
                  width_m: road.width_m,
                  max_grade_pct: road.max_grade_pct,
                },
                geometry: road.geometry,
              } as Feature}
              style={() => getRoadStyle(road)}
              onEachFeature={(feature, layer) => {
                const props = feature.properties;
                const gradeText = props?.max_grade_pct != null 
                  ? `${props.max_grade_pct.toFixed(1)}%` 
                  : '—';
                const gradeClass = props?.max_grade_pct != null
                  ? props.max_grade_pct < 5 ? 'easy' : props.max_grade_pct <= 10 ? 'moderate' : 'steep'
                  : 'unknown';
                layer.bindPopup(`
                  <div class="road-popup">
                    <strong>${props?.name || 'Access Road'}</strong>
                    <div class="popup-stats">
                      <div class="popup-stat">
                        <span class="popup-label">Length</span>
                        <span class="popup-value">${props?.length_m?.toFixed(0) || '—'} m</span>
                      </div>
                      <div class="popup-stat">
                        <span class="popup-label">Width</span>
                        <span class="popup-value">${props?.width_m?.toFixed(1) || '5.0'} m</span>
                      </div>
                      <div class="popup-stat">
                        <span class="popup-label">Max Grade</span>
                        <span class="popup-value grade-${gradeClass}">${gradeText}</span>
                      </div>
                    </div>
                  </div>
                `);
              }}
            />
          ))}
          
          {/* Asset footprints from layout - rendered as polygons */}
          {currentLayout?.assets.map((asset: Asset) => {
            const coords = asset.position.coordinates;
            const [lng, lat] = coords;
            const colors = ASSET_COLORS[asset.asset_type] || ASSET_COLORS.solar;
            
            // Calculate footprint polygon if dimensions available
            const hasFootprint = asset.footprint_length_m && asset.footprint_width_m;
            const footprintCoords = hasFootprint
              ? calculateFootprintPolygon(
                  lat, lng,
                  asset.footprint_length_m!,
                  asset.footprint_width_m!
                )
              : null;
            
            return (
              <React.Fragment key={asset.id}>
                {/* Footprint polygon */}
                {footprintCoords && (
                  <GeoJSON
                    data={{
                      type: 'Feature',
                      properties: { id: asset.id },
                      geometry: {
                        type: 'Polygon',
                        coordinates: [footprintCoords.map(([lat, lng]) => [lng, lat])],
                      },
                    } as Feature}
                    style={{
                      fillColor: colors.fill,
                      fillOpacity: 0.6,
                      color: colors.stroke,
                      weight: 2,
                      opacity: 0.9,
                    }}
                    eventHandlers={{
                      mouseover: (e) => {
                        e.target.setStyle({
                          fillOpacity: 0.8,
                          weight: 3,
                        });
                      },
                      mouseout: (e) => {
                        e.target.setStyle({
                          fillOpacity: 0.6,
                          weight: 2,
                        });
                      },
                    }}
                  />
                )}
                
                {/* Asset marker with icon */}
                <Marker
                  position={[lat, lng]}
                  icon={createAssetIcon(asset.asset_type)}
                >
                  <Popup>
                    <div className="asset-popup">
                      <div className="asset-popup-header">
                        <strong>{asset.name || formatAssetType(asset.asset_type)}</strong>
                        <span className="asset-type-badge" style={{ 
                          backgroundColor: colors.fill,
                          color: colors.text,
                          border: `1px solid ${colors.stroke}`,
                        }}>
                          {formatAssetType(asset.asset_type)}
                        </span>
                      </div>
                      <div className="popup-stats">
                        <div className="popup-stat">
                          <span className="popup-label">Capacity</span>
                          <span className="popup-value">{formatCapacity(asset.capacity_kw)}</span>
                        </div>
                        {hasFootprint && (
                          <div className="popup-stat">
                            <span className="popup-label">Footprint</span>
                            <span className="popup-value">{formatFootprint(asset.footprint_length_m, asset.footprint_width_m)}</span>
                          </div>
                        )}
                        {asset.elevation_m != null && (
                          <div className="popup-stat">
                            <span className="popup-label">Elevation</span>
                            <span className="popup-value">{formatElevation(asset.elevation_m)}</span>
                          </div>
                        )}
                        {asset.slope_deg != null && (
                          <div className="popup-stat">
                            <span className="popup-label">Slope</span>
                            <span className="popup-value">{formatSlope(asset.slope_deg)}</span>
                          </div>
                        )}
                        {/* D-02: Per-asset grading */}
                        {(asset.cut_m3 != null || asset.fill_m3 != null) && (
                          <div className="popup-stat grading-stat">
                            <span className="popup-label">Grading</span>
                            <span className="popup-value grading-value">
                              <span className="grading-cut" title="Cut volume">
                                ↑{formatVolume(asset.cut_m3)}
                              </span>
                              <span className="grading-separator">/</span>
                              <span className="grading-fill" title="Fill volume">
                                ↓{formatVolume(asset.fill_m3)}
                              </span>
                            </span>
                          </div>
                        )}
                        {/* Phase E: Enhanced terrain metrics */}
                        {asset.suitability_score != null && (
                          <div className="popup-stat">
                            <span className="popup-label">Suitability</span>
                            <span className="popup-value" style={{
                              color: asset.suitability_score >= 0.7 ? '#22c55e' : 
                                     asset.suitability_score >= 0.4 ? '#eab308' : '#ef4444'
                            }}>
                              {(asset.suitability_score * 100).toFixed(0)}%
                            </span>
                          </div>
                        )}
                        {asset.aspect_deg != null && asset.aspect_deg >= 0 && (
                          <div className="popup-stat">
                            <span className="popup-label">Aspect</span>
                            <span className="popup-value">
                              {getAspectDirection(asset.aspect_deg)}
                            </span>
                          </div>
                        )}
                        {asset.rotation_deg != null && asset.rotation_deg !== 0 && (
                          <div className="popup-stat">
                            <span className="popup-label">Rotation</span>
                            <span className="popup-value">{asset.rotation_deg}°</span>
                          </div>
                        )}
                      </div>
                    </div>
                  </Popup>
                </Marker>
              </React.Fragment>
            );
          })}
        </MapContainer>
      </div>
    </div>
  );
}
