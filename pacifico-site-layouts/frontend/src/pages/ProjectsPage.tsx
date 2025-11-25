/**
 * Projects dashboard - list and manage sites
 */
import { useState, useEffect, useCallback, type ChangeEvent, type DragEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { getSites, uploadSite, deleteSite } from '../lib/api';
import type { SiteListItem } from '../types';
import './ProjectsPage.css';

export function ProjectsPage() {
  const [sites, setSites] = useState<SiteListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  
  const navigate = useNavigate();

  // Fetch sites on mount
  useEffect(() => {
    fetchSites();
  }, []);

  async function fetchSites() {
    try {
      setIsLoading(true);
      setError(null);
      const response = await getSites();
      setSites(response.sites);
    } catch (err) {
      setError('Failed to load sites. Please try again.');
      console.error('Failed to fetch sites:', err);
    } finally {
      setIsLoading(false);
    }
  }

  const handleFileUpload = useCallback(async (file: File) => {
    // Validate file type
    const validTypes = ['.kml', '.kmz'];
    const ext = file.name.toLowerCase().slice(file.name.lastIndexOf('.'));
    if (!validTypes.includes(ext)) {
      setUploadError('Invalid file type. Please upload a KML or KMZ file.');
      return;
    }

    // Validate file size (10MB max)
    const maxSize = 10 * 1024 * 1024;
    if (file.size > maxSize) {
      setUploadError('File too large. Maximum size is 10MB.');
      return;
    }

    try {
      setIsUploading(true);
      setUploadError(null);
      const response = await uploadSite(file);
      setShowUploadModal(false);
      // Navigate to the new site
      navigate(`/sites/${response.id}`);
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 
        'Failed to upload file. Please try again.';
      setUploadError(errorMessage);
      console.error('Upload failed:', err);
    } finally {
      setIsUploading(false);
    }
  }, [navigate]);

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      handleFileUpload(file);
    }
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) {
      handleFileUpload(file);
    }
  };

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDeleteSite = async (siteId: string, siteName: string) => {
    if (!confirm(`Are you sure you want to delete "${siteName}"? This cannot be undone.`)) {
      return;
    }
    
    try {
      await deleteSite(siteId);
      setSites(sites.filter(s => s.id !== siteId));
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

  const formatDate = (dateStr: string): string => {
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  if (isLoading) {
    return (
      <div className="projects-page">
        <div className="loading-state">
          <div className="loading-spinner" />
          <p>Loading sites...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="projects-page">
      <div className="projects-header">
        <div>
          <h1>Sites</h1>
          <p>Manage your site layout projects</p>
        </div>
        <button className="btn-new-project" onClick={() => setShowUploadModal(true)}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          New Site
        </button>
      </div>

      {error && (
        <div className="error-banner">
          <p>{error}</p>
          <button onClick={fetchSites}>Retry</button>
        </div>
      )}

      {sites.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M3 7l6-4 6 4 6-4v14l-6 4-6-4-6 4V7z" />
              <path d="M9 3v14" />
              <path d="M15 7v14" />
            </svg>
          </div>
          <h2>No sites yet</h2>
          <p>Upload a KML or KMZ file to create your first site.</p>
          <button className="btn-primary" onClick={() => setShowUploadModal(true)}>
            Upload Site Boundary
          </button>
        </div>
      ) : (
        <div className="projects-grid">
          {sites.map((site) => (
            <div key={site.id} className="project-card">
              <Link to={`/sites/${site.id}`} className="project-card-link">
                <div className="project-preview">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1">
                    <path d="M3 7l6-4 6 4 6-4v14l-6 4-6-4-6 4V7z" />
                    <path d="M9 3v14" />
                    <path d="M15 7v14" />
                  </svg>
                </div>
                <div className="project-info">
                  <h3>{site.name}</h3>
                  <p>{formatArea(site.area_m2)} · {formatDate(site.created_at)}</p>
                </div>
              </Link>
              <button 
                className="btn-delete-site"
                onClick={(e) => {
                  e.preventDefault();
                  handleDeleteSite(site.id, site.name);
                }}
                title="Delete site"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="3 6 5 6 21 6" />
                  <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                </svg>
              </button>
            </div>
          ))}
          
          <button className="project-card add-card" onClick={() => setShowUploadModal(true)}>
            <div className="add-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="12" y1="5" x2="12" y2="19" />
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
            </div>
            <span>Add New Site</span>
          </button>
        </div>
      )}

      {showUploadModal && (
        <div className="modal-overlay" onClick={() => !isUploading && setShowUploadModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Upload Site Boundary</h2>
              <button 
                className="modal-close" 
                onClick={() => setShowUploadModal(false)}
                disabled={isUploading}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>
            
            {uploadError && (
              <div className="upload-error">
                {uploadError}
              </div>
            )}
            
            <div 
              className={`upload-zone ${isDragging ? 'dragging' : ''} ${isUploading ? 'uploading' : ''}`}
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
            >
              {isUploading ? (
                <>
                  <div className="upload-spinner" />
                  <p className="upload-text">Uploading...</p>
                  <p className="upload-hint">Please wait while we process your file</p>
                </>
              ) : (
                <>
                  <div className="upload-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
                      <polyline points="17 8 12 3 7 8" />
                      <line x1="12" y1="3" x2="12" y2="15" />
                    </svg>
                  </div>
                  <p className="upload-text">
                    Drag and drop a <strong>KML</strong> or <strong>KMZ</strong> file
                  </p>
                  <p className="upload-hint">or click to browse (max 10MB)</p>
                  <input 
                    type="file" 
                    accept=".kml,.kmz"
                    onChange={handleFileChange}
                    disabled={isUploading}
                  />
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
