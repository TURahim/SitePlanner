/**
 * Projects dashboard - list and manage projects
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import './ProjectsPage.css';

// Placeholder data until API is connected
const PLACEHOLDER_PROJECTS = [
  { id: '1', name: 'Solar Farm Alpha', sites: 3, created: '2025-11-20' },
  { id: '2', name: 'Microgrid Beta', sites: 1, created: '2025-11-18' },
];

export function ProjectsPage() {
  const [showUploadModal, setShowUploadModal] = useState(false);

  return (
    <div className="projects-page">
      <div className="projects-header">
        <div>
          <h1>Projects</h1>
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

      {PLACEHOLDER_PROJECTS.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M3 7l6-4 6 4 6-4v14l-6 4-6-4-6 4V7z" />
              <path d="M9 3v14" />
              <path d="M15 7v14" />
            </svg>
          </div>
          <h2>No projects yet</h2>
          <p>Upload a KML or KMZ file to create your first site.</p>
          <button className="btn-primary" onClick={() => setShowUploadModal(true)}>
            Upload Site Boundary
          </button>
        </div>
      ) : (
        <div className="projects-grid">
          {PLACEHOLDER_PROJECTS.map((project) => (
            <Link to={`/sites/${project.id}`} key={project.id} className="project-card">
              <div className="project-preview">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1">
                  <rect x="3" y="3" width="18" height="18" rx="2" />
                  <path d="M3 9h18" />
                  <path d="M9 21V9" />
                </svg>
              </div>
              <div className="project-info">
                <h3>{project.name}</h3>
                <p>{project.sites} site{project.sites !== 1 ? 's' : ''}</p>
              </div>
            </Link>
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
        <div className="modal-overlay" onClick={() => setShowUploadModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Upload Site Boundary</h2>
              <button className="modal-close" onClick={() => setShowUploadModal(false)}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>
            <div className="upload-zone">
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
              <input type="file" accept=".kml,.kmz" />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

