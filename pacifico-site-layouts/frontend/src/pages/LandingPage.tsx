/**
 * Landing page - public home page with product info
 */
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import './LandingPage.css';

export function LandingPage() {
  const { isAuthenticated, demoLogin } = useAuth();
  const navigate = useNavigate();
  const [isDemoLoading, setIsDemoLoading] = useState(false);
  const [demoError, setDemoError] = useState<string | null>(null);

  const handleDemoLogin = async () => {
    setIsDemoLoading(true);
    setDemoError(null);
    try {
      await demoLogin();
      navigate('/projects');
    } catch (err) {
      setDemoError(err instanceof Error ? err.message : 'Failed to start demo');
    } finally {
      setIsDemoLoading(false);
    }
  };

  return (
    <div className="landing-page">
      <section className="hero">
        <div className="hero-bg">
          <div className="grid-overlay" />
        </div>
        <div className="hero-content">
          <h1 className="hero-title">
            Site Layouts,
            <br />
            <span className="accent">Automated</span>
          </h1>
          <p className="hero-subtitle">
            AI-powered geospatial planning for DG, microgrids, and data centers.
            Upload a boundary, get a terrain-optimized layout in minutes.
          </p>
          <div className="hero-actions">
            {isAuthenticated ? (
              <Link to="/projects" className="btn-hero-primary">
                Go to Dashboard
              </Link>
            ) : (
              <>
                <button
                  onClick={handleDemoLogin}
                  className="btn-hero-demo"
                  disabled={isDemoLoading}
                >
                  {isDemoLoading ? 'Loading Demo...' : '🚀 Try Demo'}
                </button>
                <Link to="/signup" className="btn-hero-primary">
                  Start Free
                </Link>
                <Link to="/login" className="btn-hero-secondary">
                  Sign In
                </Link>
              </>
            )}
          </div>
          {demoError && (
            <p className="demo-error">{demoError}</p>
          )}
        </div>
      </section>

      <section className="features">
        <div className="features-grid">
          <div className="feature-card">
            <div className="feature-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z" />
                <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
                <line x1="12" y1="22.08" x2="12" y2="12" />
              </svg>
            </div>
            <h3>Terrain Analysis</h3>
            <p>Automatic DEM fetching with slope and aspect computation for optimal placement.</p>
          </div>

          <div className="feature-card">
            <div className="feature-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <circle cx="12" cy="12" r="10" />
                <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76" />
              </svg>
            </div>
            <h3>Smart Placement</h3>
            <p>Heuristic algorithms place assets where they work best—flat for batteries, angled for solar.</p>
          </div>

          <div className="feature-card">
            <div className="feature-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="16" y1="13" x2="8" y2="13" />
                <line x1="16" y1="17" x2="8" y2="17" />
              </svg>
            </div>
            <h3>Export Anywhere</h3>
            <p>Download layouts as GeoJSON, KMZ, or professional PDF reports.</p>
          </div>
        </div>
      </section>

      <footer className="landing-footer">
        <p>© 2025 Microgrid Layout AI</p>
      </footer>
    </div>
  );
}

