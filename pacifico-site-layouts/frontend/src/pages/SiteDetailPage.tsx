/**
 * Site detail page with map and layout controls
 */
import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import './SiteDetailPage.css';

// Placeholder until map integration
export function SiteDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [isGenerating, setIsGenerating] = useState(false);

  // Placeholder site data
  const site = {
    id,
    name: 'Solar Farm Alpha',
    area_m2: 150000,
    created_at: '2025-11-20T10:30:00Z',
  };

  const handleGenerateLayout = () => {
    setIsGenerating(true);
    // TODO: Call API to generate layout
    setTimeout(() => setIsGenerating(false), 2000);
  };

  return (
    <div className="site-detail-page">
      <aside className="site-sidebar">
        <div className="sidebar-header">
          <Link to="/projects" className="back-link">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="15 18 9 12 15 6" />
            </svg>
            Back to Projects
          </Link>
        </div>

        <div className="site-info">
          <h1>{site.name}</h1>
          <div className="site-stats">
            <div className="stat">
              <span className="stat-value">
                {(site.area_m2 / 10000).toFixed(1)} ha
              </span>
              <span className="stat-label">Area</span>
            </div>
            <div className="stat">
              <span className="stat-value">—</span>
              <span className="stat-label">Layouts</span>
            </div>
          </div>
        </div>

        <div className="sidebar-section">
          <h2>Generate Layout</h2>
          <p>Create an optimized asset layout based on terrain analysis.</p>
          
          <div className="form-group">
            <label htmlFor="capacity">Target Capacity (kW)</label>
            <input
              id="capacity"
              type="number"
              defaultValue={1000}
              min={100}
              max={100000}
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

        <div className="sidebar-section">
          <h2>Export</h2>
          <div className="export-buttons">
            <button className="btn-export" disabled>
              GeoJSON
            </button>
            <button className="btn-export" disabled>
              KMZ
            </button>
            <button className="btn-export" disabled>
              PDF
            </button>
          </div>
          <p className="export-hint">Generate a layout first to enable exports.</p>
        </div>
      </aside>

      <div className="map-container">
        <div className="map-placeholder">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M3 7l6-4 6 4 6-4v14l-6 4-6-4-6 4V7z" />
            <path d="M9 3v14" />
            <path d="M15 7v14" />
          </svg>
          <p>Map will appear here</p>
          <span>Leaflet integration coming in A-13</span>
        </div>
      </div>
    </div>
  );
}

