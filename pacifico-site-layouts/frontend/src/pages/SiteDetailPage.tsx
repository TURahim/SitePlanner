/**
 * Site detail page with map and layout controls
 */
import { useState, useEffect, useRef } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { MapContainer, TileLayer, GeoJSON, Marker, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import type { FeatureCollection, Feature } from 'geojson';
import { getSite, generateLayout, getLayoutsForSite, deleteSite } from '../lib/api';
import type { Site, LayoutGenerateResponse, LayoutListItem, Asset, Road } from '../types';
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

// Asset type colors
const ASSET_COLORS: Record<string, string> = {
  solar: '#f59e0b',      // amber
  battery: '#3b82f6',    // blue
  generator: '#ef4444',  // red
  substation: '#8b5cf6', // purple
};

// Custom marker icons for assets
function createAssetIcon(assetType: string): L.DivIcon {
  const color = ASSET_COLORS[assetType] || '#6b7280';
  return L.divIcon({
    className: 'asset-marker',
    html: `<div style="background-color: ${color}; width: 24px; height: 24px; border-radius: 50%; border: 3px solid white; box-shadow: 0 2px 6px rgba(0,0,0,0.3);"></div>`,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
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
  
  // Map ref for imperative access
  const mapRef = useRef<L.Map | null>(null);

  // Fetch site data on mount
  useEffect(() => {
    if (id) {
      fetchSite(id);
      fetchLayouts(id);
    }
  }, [id]);

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
      const response = await generateLayout({
        site_id: id,
        target_capacity_kw: targetCapacity,
      });
      setCurrentLayout(response);
      // Refresh layouts list
      fetchLayouts(id);
    } catch (err) {
      console.error('Failed to generate layout:', err);
      alert('Failed to generate layout. Please try again.');
    } finally {
      setIsGenerating(false);
    }
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

  const formatArea = (areaM2: number): string => {
    const hectares = areaM2 / 10000;
    if (hectares >= 1) {
      return `${hectares.toFixed(1)} ha`;
    }
    return `${areaM2.toLocaleString()} m²`;
  };

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

  // Style for roads
  const roadStyle = {
    color: '#f59e0b',
    weight: 4,
    opacity: 0.8,
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
            />
          </div>

          <button
            className="btn-generate"
            onClick={handleGenerateLayout}
            disabled={isGenerating}
          >
            {isGenerating ? (
              <>
                <span className="spinner" />
                Generating...
              </>
            ) : (
              <>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
                </svg>
                Generate Layout
              </>
            )}
          </button>
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
            
            <div className="legend">
              <h3>Asset Legend</h3>
              <div className="legend-items">
                {Object.entries(ASSET_COLORS).map(([type, color]) => (
                  <div key={type} className="legend-item">
                    <span className="legend-dot" style={{ backgroundColor: color }} />
                    <span className="legend-label">{type.charAt(0).toUpperCase() + type.slice(1)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        <div className="sidebar-section">
          <h2>Export</h2>
          <div className="export-buttons">
            <button className="btn-export" disabled={!currentLayout}>
              GeoJSON
            </button>
            <button className="btn-export" disabled={!currentLayout}>
              KMZ
            </button>
            <button className="btn-export" disabled={!currentLayout}>
              PDF
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
          
          {/* Roads from layout */}
          {currentLayout?.roads.map((road: Road) => (
            <GeoJSON
              key={road.id}
              data={{
                type: 'Feature',
                properties: { name: road.name, length_m: road.length_m },
                geometry: road.geometry,
              } as Feature}
              style={roadStyle}
              onEachFeature={(feature, layer) => {
                const props = feature.properties;
                layer.bindPopup(`
                  <strong>${props?.name || 'Road'}</strong><br/>
                  Length: ${props?.length_m?.toFixed(0) || '—'} m
                `);
              }}
            />
          ))}
          
          {/* Asset markers from layout */}
          {currentLayout?.assets.map((asset: Asset) => {
            const coords = asset.position.coordinates;
            return (
              <Marker
                key={asset.id}
                position={[coords[1], coords[0]]}
                icon={createAssetIcon(asset.asset_type)}
              >
                <Popup>
                  <strong>{asset.name || asset.asset_type}</strong><br/>
                  Type: {asset.asset_type}<br/>
                  Capacity: {asset.capacity_kw?.toFixed(0) || '—'} kW
                </Popup>
              </Marker>
            );
          })}
        </MapContainer>
      </div>
    </div>
  );
}
