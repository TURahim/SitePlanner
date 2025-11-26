/**
 * Exclusion Zone Panel Component
 * 
 * D-03: Provides UI for managing exclusion zones including:
 * - Drawing new zones on the map
 * - Listing existing zones
 * - Editing zone properties
 * - Deleting zones
 */
import React, { useState, useEffect, useCallback } from 'react';
import type { Polygon } from 'geojson';
import { 
  getExclusionZones, 
  getExclusionZoneTypes,
  createExclusionZone, 
  updateExclusionZone,
  deleteExclusionZone,
} from '../lib/api';
import type { 
  ExclusionZone, 
  ExclusionZoneType, 
  ExclusionZoneTypeInfo,
  ExclusionZoneCreateRequest,
} from '../types';
import './ExclusionZonePanel.css';

interface ExclusionZonePanelProps {
  siteId: string;
  isDrawing: boolean;
  onStartDrawing: () => void;
  onCancelDrawing: () => void;
  onZonesChange: (zones: ExclusionZone[]) => void;
  drawnPolygon: Polygon | null;
  onPolygonSaved: () => void;
}

interface ZoneModalProps {
  isOpen: boolean;
  mode: 'create' | 'edit';
  zone?: ExclusionZone;
  zoneTypes: ExclusionZoneTypeInfo[];
  polygon?: Polygon;
  onSave: (data: {
    name: string;
    zone_type: ExclusionZoneType;
    buffer_m: number;
    description: string;
  }) => void;
  onCancel: () => void;
  isSaving: boolean;
}

// Zone Modal Component
function ZoneModal({ 
  isOpen, 
  mode, 
  zone, 
  zoneTypes, 
  onSave, 
  onCancel, 
  isSaving 
}: ZoneModalProps) {
  const [name, setName] = useState('');
  const [zoneType, setZoneType] = useState<ExclusionZoneType>('custom');
  const [bufferM, setBufferM] = useState(0);
  const [description, setDescription] = useState('');
  
  // Reset form when modal opens
  useEffect(() => {
    if (isOpen) {
      if (mode === 'edit' && zone) {
        setName(zone.name);
        setZoneType(zone.zone_type);
        setBufferM(zone.buffer_m);
        setDescription(zone.description || '');
      } else {
        setName('');
        setZoneType('custom');
        setBufferM(0);
        setDescription('');
      }
    }
  }, [isOpen, mode, zone]);
  
  // Update buffer when zone type changes
  useEffect(() => {
    if (mode === 'create') {
      const typeInfo = zoneTypes.find(t => t.type === zoneType);
      if (typeInfo) {
        setBufferM(typeInfo.default_buffer_m);
      }
    }
  }, [zoneType, zoneTypes, mode]);
  
  if (!isOpen) return null;
  
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave({
      name: name.trim() || `${zoneType.charAt(0).toUpperCase() + zoneType.slice(1)} Zone`,
      zone_type: zoneType,
      buffer_m: bufferM,
      description: description.trim(),
    });
  };
  
  const selectedTypeInfo = zoneTypes.find(t => t.type === zoneType);
  
  return (
    <div className="zone-modal-overlay" onClick={onCancel}>
      <div className="zone-modal" onClick={e => e.stopPropagation()}>
        <div className="zone-modal-header">
          <h3>{mode === 'create' ? 'Add Exclusion Zone' : 'Edit Exclusion Zone'}</h3>
          <button type="button" className="zone-modal-close" onClick={onCancel}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        
        <form onSubmit={handleSubmit}>
          <div className="zone-modal-body">
            {/* Zone Type Selection */}
            <div className="form-group">
              <label>Zone Type</label>
              <div className="zone-type-grid">
                {zoneTypes.map((type) => (
                  <button
                    key={type.type}
                    type="button"
                    className={`zone-type-option ${zoneType === type.type ? 'selected' : ''}`}
                    onClick={() => setZoneType(type.type as ExclusionZoneType)}
                  >
                    <span 
                      className="zone-type-color" 
                      style={{ backgroundColor: type.color }}
                    />
                    <span className="zone-type-label">{type.label}</span>
                    <span className="zone-type-desc">{type.description}</span>
                  </button>
                ))}
              </div>
            </div>
            
            {/* Zone Name */}
            <div className="form-group">
              <label htmlFor="zone-name">Zone Name</label>
              <input
                id="zone-name"
                type="text"
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder={`${selectedTypeInfo?.label || 'Exclusion'} Zone`}
                maxLength={255}
              />
            </div>
            
            {/* Buffer Distance */}
            <div className="form-group">
              <label htmlFor="zone-buffer">
                Buffer Distance (m)
                <span className="form-hint">
                  Additional setback around zone boundary
                </span>
              </label>
              <input
                id="zone-buffer"
                type="number"
                value={bufferM}
                onChange={e => setBufferM(Number(e.target.value))}
                min={0}
                max={1000}
                step={5}
              />
            </div>
            
            {/* Description */}
            <div className="form-group">
              <label htmlFor="zone-description">Description (optional)</label>
              <textarea
                id="zone-description"
                value={description}
                onChange={e => setDescription(e.target.value)}
                placeholder="Notes about this exclusion zone..."
                rows={2}
                maxLength={1000}
              />
            </div>
          </div>
          
          <div className="zone-modal-footer">
            <button 
              type="button" 
              className="btn-cancel" 
              onClick={onCancel}
              disabled={isSaving}
            >
              Cancel
            </button>
            <button 
              type="submit" 
              className="btn-save"
              disabled={isSaving}
            >
              {isSaving ? (
                <>
                  <span className="spinner-small" />
                  Saving...
                </>
              ) : (
                mode === 'create' ? 'Add Zone' : 'Save Changes'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export function ExclusionZonePanel({
  siteId,
  isDrawing,
  onStartDrawing,
  onCancelDrawing,
  onZonesChange,
  drawnPolygon,
  onPolygonSaved,
}: ExclusionZonePanelProps) {
  const [zones, setZones] = useState<ExclusionZone[]>([]);
  const [zoneTypes, setZoneTypes] = useState<ExclusionZoneTypeInfo[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Modal state
  const [modalOpen, setModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState<'create' | 'edit'>('create');
  const [editingZone, setEditingZone] = useState<ExclusionZone | undefined>();
  const [isSaving, setIsSaving] = useState(false);
  
  // Expanded zone (for details view)
  const [expandedZoneId, setExpandedZoneId] = useState<string | null>(null);
  
  // Fetch zone types on mount
  useEffect(() => {
    async function fetchTypes() {
      try {
        const response = await getExclusionZoneTypes();
        setZoneTypes(response.types);
      } catch (err) {
        console.error('Failed to fetch zone types:', err);
      }
    }
    fetchTypes();
  }, []);
  
  // Fetch zones when siteId changes
  useEffect(() => {
    if (siteId) {
      fetchZones();
    }
  }, [siteId]);
  
  // Open modal when polygon is drawn
  useEffect(() => {
    if (drawnPolygon) {
      setModalMode('create');
      setEditingZone(undefined);
      setModalOpen(true);
    }
  }, [drawnPolygon]);
  
  const fetchZones = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const response = await getExclusionZones(siteId);
      setZones(response.zones);
      onZonesChange(response.zones);
    } catch (err) {
      console.error('Failed to fetch exclusion zones:', err);
      setError('Failed to load exclusion zones');
    } finally {
      setIsLoading(false);
    }
  }, [siteId, onZonesChange]);
  
  const handleSaveZone = async (data: {
    name: string;
    zone_type: ExclusionZoneType;
    buffer_m: number;
    description: string;
  }) => {
    try {
      setIsSaving(true);
      
      if (modalMode === 'create' && drawnPolygon) {
        const request: ExclusionZoneCreateRequest = {
          name: data.name,
          zone_type: data.zone_type,
          geometry: drawnPolygon,
          buffer_m: data.buffer_m,
          description: data.description || undefined,
        };
        await createExclusionZone(siteId, request);
        onPolygonSaved();
      } else if (modalMode === 'edit' && editingZone) {
        await updateExclusionZone(siteId, editingZone.id, {
          name: data.name,
          zone_type: data.zone_type,
          buffer_m: data.buffer_m,
          description: data.description || undefined,
        });
      }
      
      setModalOpen(false);
      await fetchZones();
    } catch (err) {
      console.error('Failed to save zone:', err);
      alert('Failed to save exclusion zone. Please try again.');
    } finally {
      setIsSaving(false);
    }
  };
  
  const handleEditZone = (zone: ExclusionZone) => {
    setEditingZone(zone);
    setModalMode('edit');
    setModalOpen(true);
  };
  
  const handleDeleteZone = async (zone: ExclusionZone) => {
    if (!confirm(`Delete "${zone.name}"? This cannot be undone.`)) return;
    
    try {
      await deleteExclusionZone(siteId, zone.id);
      await fetchZones();
    } catch (err) {
      console.error('Failed to delete zone:', err);
      alert('Failed to delete exclusion zone. Please try again.');
    }
  };
  
  const handleCancelModal = () => {
    setModalOpen(false);
    if (modalMode === 'create') {
      onCancelDrawing();
    }
  };
  
  const formatArea = (areaM2: number | undefined): string => {
    if (!areaM2) return '—';
    const hectares = areaM2 / 10000;
    if (hectares >= 1) {
      return `${hectares.toFixed(2)} ha`;
    }
    return `${areaM2.toLocaleString()} m²`;
  };
  
  return (
    <div className="exclusion-zone-panel">
      <div className="panel-header">
        <h2>Exclusion Zones</h2>
        <span className="zone-count">{zones.length}</span>
      </div>
      
      <p className="panel-description">
        Define areas where assets cannot be placed. The layout generator will respect these constraints.
      </p>
      
      {/* Drawing Controls */}
      {isDrawing ? (
        <div className="drawing-state">
          <div className="drawing-indicator">
            <div className="drawing-pulse" />
            <span>Draw a polygon on the map</span>
          </div>
          <p className="drawing-hint">
            Click to add points. Double-click or click the first point to finish.
          </p>
          <button 
            type="button" 
            className="btn-cancel-draw"
            onClick={onCancelDrawing}
          >
            Cancel Drawing
          </button>
        </div>
      ) : (
        <button 
          type="button" 
          className="btn-add-zone"
          onClick={onStartDrawing}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5 12 2" />
            <line x1="12" y1="22" x2="12" y2="15.5" />
            <polyline points="22 8.5 12 15.5 2 8.5" />
            <line x1="12" y1="2" x2="12" y2="15.5" />
          </svg>
          Add Exclusion Zone
        </button>
      )}
      
      {/* Zones List */}
      <div className="zones-list">
        {isLoading ? (
          <div className="zones-loading">
            <div className="spinner-small" />
            <span>Loading zones...</span>
          </div>
        ) : error ? (
          <div className="zones-error">{error}</div>
        ) : zones.length === 0 ? (
          <div className="zones-empty">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5 12 2" />
              <line x1="12" y1="22" x2="12" y2="15.5" />
            </svg>
            <p>No exclusion zones defined</p>
            <p className="zones-empty-hint">
              Draw zones to mark areas where assets cannot be placed.
            </p>
          </div>
        ) : (
          zones.map((zone) => {
            const typeInfo = zoneTypes.find(t => t.type === zone.zone_type);
            const isExpanded = expandedZoneId === zone.id;
            
            return (
              <div 
                key={zone.id} 
                className={`zone-item ${isExpanded ? 'expanded' : ''}`}
              >
                <button 
                  type="button"
                  className="zone-item-header"
                  onClick={() => setExpandedZoneId(isExpanded ? null : zone.id)}
                >
                  <span 
                    className="zone-color" 
                    style={{ backgroundColor: zone.color }}
                  />
                  <div className="zone-info">
                    <span className="zone-name">{zone.name}</span>
                    <span className="zone-type">{typeInfo?.label || zone.zone_type}</span>
                  </div>
                  <svg 
                    className="zone-expand-icon" 
                    viewBox="0 0 24 24" 
                    fill="none" 
                    stroke="currentColor" 
                    strokeWidth="2"
                  >
                    <polyline points="6 9 12 15 18 9" />
                  </svg>
                </button>
                
                {isExpanded && (
                  <div className="zone-details">
                    <div className="zone-stats">
                      <div className="zone-stat">
                        <span className="zone-stat-label">Area</span>
                        <span className="zone-stat-value">{formatArea(zone.area_m2)}</span>
                      </div>
                      <div className="zone-stat">
                        <span className="zone-stat-label">Buffer</span>
                        <span className="zone-stat-value">{zone.buffer_m}m</span>
                      </div>
                    </div>
                    {zone.description && (
                      <p className="zone-description">{zone.description}</p>
                    )}
                    <div className="zone-actions">
                      <button 
                        type="button"
                        className="btn-zone-action edit"
                        onClick={() => handleEditZone(zone)}
                      >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                          <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                        </svg>
                        Edit
                      </button>
                      <button 
                        type="button"
                        className="btn-zone-action delete"
                        onClick={() => handleDeleteZone(zone)}
                      >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <polyline points="3 6 5 6 21 6" />
                          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                        </svg>
                        Delete
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
      
      {/* Zone Modal */}
      <ZoneModal
        isOpen={modalOpen}
        mode={modalMode}
        zone={editingZone}
        zoneTypes={zoneTypes}
        polygon={drawnPolygon || undefined}
        onSave={handleSaveZone}
        onCancel={handleCancelModal}
        isSaving={isSaving}
      />
    </div>
  );
}

