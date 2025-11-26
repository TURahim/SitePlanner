/**
 * Layout Variants Components
 * 
 * D-05: UI for displaying and comparing layout variants
 * D-05-04: Side-by-side comparison view
 * D-05-06: Mark as preferred feature
 */
import { useState, useCallback } from 'react';
import type { 
  LayoutVariant, 
  VariantComparison, 
  LayoutVariantMetrics,
  LayoutStrategy 
} from '../types';
import './LayoutVariants.css';

interface VariantTabsProps {
  variants: LayoutVariant[];
  selectedStrategy: LayoutStrategy | null;
  onSelectVariant: (strategy: LayoutStrategy) => void;
  comparison: VariantComparison;
  preferredLayoutId?: string | null;
  onSetPreferred?: (layoutId: string) => void;
}

/**
 * Tab selector for choosing between layout variants
 */
export function VariantTabs({
  variants,
  selectedStrategy,
  onSelectVariant,
  comparison,
  preferredLayoutId,
  onSetPreferred,
}: VariantTabsProps) {
  const handlePreferredClick = useCallback((e: React.MouseEvent, layoutId: string) => {
    e.stopPropagation(); // Prevent tab selection
    if (onSetPreferred) {
      onSetPreferred(layoutId);
    }
  }, [onSetPreferred]);
  
  return (
    <div className="variant-tabs">
      <div className="variant-tabs-header">
        <h3>Layout Variants</h3>
        <span className="variant-count">{variants.length} options</span>
      </div>
      
      <div className="variant-tabs-list">
        {variants.map((variant) => {
          const isSelected = selectedStrategy === variant.strategy;
          const isPreferred = preferredLayoutId === variant.layout.id;
          const isBestCapacity = comparison.best_capacity_id === variant.layout.id;
          const isBestEarthwork = comparison.best_earthwork_id === variant.layout.id;
          const isBestRoads = comparison.best_road_network_id === variant.layout.id;
          
          return (
            <button
              key={variant.strategy}
              type="button"
              className={`variant-tab ${isSelected ? 'selected' : ''} ${isPreferred ? 'preferred' : ''}`}
              onClick={() => onSelectVariant(variant.strategy)}
            >
              <div className="variant-tab-header">
                <span className="variant-name">{variant.strategy_name}</span>
                {/* D-05-06: Preferred star button */}
                {onSetPreferred && (
                  <button
                    type="button"
                    className={`preferred-btn ${isPreferred ? 'is-preferred' : ''}`}
                    onClick={(e) => handlePreferredClick(e, variant.layout.id)}
                    title={isPreferred ? 'Preferred layout' : 'Mark as preferred'}
                  >
                    {isPreferred ? '★' : '☆'}
                  </button>
                )}
              </div>
              <div className="variant-badges">
                {isBestCapacity && (
                  <span className="badge badge-capacity" title="Best capacity">
                    ⚡
                  </span>
                )}
                {isBestEarthwork && (
                  <span className="badge badge-earthwork" title="Lowest earthwork">
                    🏔️
                  </span>
                )}
                {isBestRoads && (
                  <span className="badge badge-roads" title="Shortest roads">
                    🛤️
                  </span>
                )}
                {isPreferred && (
                  <span className="badge badge-preferred" title="Preferred layout">
                    ⭐
                  </span>
                )}
              </div>
              <span className="variant-capacity">
                {variant.layout.total_capacity_kw?.toLocaleString() || '—'} kW
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

interface ComparisonTableProps {
  comparison: VariantComparison;
  onSelectVariant: (layoutId: string) => void;
  preferredLayoutId?: string | null;
}

/**
 * Table comparing metrics across all variants
 */
export function ComparisonTable({
  comparison,
  onSelectVariant,
  preferredLayoutId,
}: ComparisonTableProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  
  const formatNumber = (num: number, decimals: number = 0) => {
    return num.toLocaleString('en-US', { 
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
  };
  
  const formatVolume = (m3: number) => {
    if (Math.abs(m3) >= 1000) {
      return `${formatNumber(m3 / 1000, 1)}k m³`;
    }
    return `${formatNumber(m3)} m³`;
  };
  
  const isBest = (metric: LayoutVariantMetrics, category: 'capacity' | 'earthwork' | 'roads') => {
    switch (category) {
      case 'capacity':
        return metric.layout_id === comparison.best_capacity_id;
      case 'earthwork':
        return metric.layout_id === comparison.best_earthwork_id;
      case 'roads':
        return metric.layout_id === comparison.best_road_network_id;
    }
  };
  
  return (
    <div className={`comparison-table-container ${isExpanded ? 'expanded' : ''}`}>
      <button 
        type="button"
        className="comparison-toggle"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <span>Compare Variants</span>
        <svg 
          viewBox="0 0 24 24" 
          fill="none" 
          stroke="currentColor" 
          strokeWidth="2"
          className={isExpanded ? 'rotated' : ''}
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>
      
      {isExpanded && (
        <div className="comparison-table-wrapper">
          <table className="comparison-table">
            <thead>
              <tr>
                <th>Metric</th>
                {comparison.metrics_table.map((m) => (
                  <th key={m.layout_id} className={preferredLayoutId === m.layout_id ? 'preferred-column' : ''}>
                    <button 
                      type="button"
                      className="variant-column-header"
                      onClick={() => onSelectVariant(m.layout_id)}
                    >
                      {m.strategy_name}
                      {preferredLayoutId === m.layout_id && <span className="preferred-star">★</span>}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Total Capacity</td>
                {comparison.metrics_table.map((m) => (
                  <td key={m.layout_id} className={`${isBest(m, 'capacity') ? 'best' : ''} ${preferredLayoutId === m.layout_id ? 'preferred-column' : ''}`}>
                    {formatNumber(m.total_capacity_kw)} kW
                    {isBest(m, 'capacity') && <span className="best-badge">★</span>}
                  </td>
                ))}
              </tr>
              <tr>
                <td>Assets</td>
                {comparison.metrics_table.map((m) => (
                  <td key={m.layout_id} className={preferredLayoutId === m.layout_id ? 'preferred-column' : ''}>{m.asset_count}</td>
                ))}
              </tr>
              <tr>
                <td>Road Length</td>
                {comparison.metrics_table.map((m) => (
                  <td key={m.layout_id} className={`${isBest(m, 'roads') ? 'best' : ''} ${preferredLayoutId === m.layout_id ? 'preferred-column' : ''}`}>
                    {formatNumber(m.road_length_m)} m
                    {isBest(m, 'roads') && <span className="best-badge">★</span>}
                  </td>
                ))}
              </tr>
              <tr>
                <td>Cut Volume</td>
                {comparison.metrics_table.map((m) => (
                  <td key={m.layout_id} className={preferredLayoutId === m.layout_id ? 'preferred-column' : ''}>{formatVolume(m.cut_volume_m3)}</td>
                ))}
              </tr>
              <tr>
                <td>Fill Volume</td>
                {comparison.metrics_table.map((m) => (
                  <td key={m.layout_id} className={preferredLayoutId === m.layout_id ? 'preferred-column' : ''}>{formatVolume(m.fill_volume_m3)}</td>
                ))}
              </tr>
              <tr>
                <td>Net Earthwork</td>
                {comparison.metrics_table.map((m) => (
                  <td key={m.layout_id} className={`${isBest(m, 'earthwork') ? 'best' : ''} ${preferredLayoutId === m.layout_id ? 'preferred-column' : ''}`}>
                    {m.net_earthwork_m3 >= 0 ? '+' : ''}{formatVolume(m.net_earthwork_m3)}
                    {isBest(m, 'earthwork') && <span className="best-badge">★</span>}
                  </td>
                ))}
              </tr>
              {comparison.metrics_table[0]?.capacity_per_hectare && (
                <tr>
                  <td>Capacity/ha</td>
                  {comparison.metrics_table.map((m) => (
                    <td key={m.layout_id} className={preferredLayoutId === m.layout_id ? 'preferred-column' : ''}>
                      {m.capacity_per_hectare ? formatNumber(m.capacity_per_hectare, 1) : '—'} kW/ha
                    </td>
                  ))}
                </tr>
              )}
            </tbody>
          </table>
          <div className="comparison-legend">
            <span className="legend-item">★ = Best in category</span>
            {preferredLayoutId && <span className="legend-item preferred-legend">★ Preferred</span>}
          </div>
        </div>
      )}
    </div>
  );
}

// =============================================================================
// D-05-04: Side-by-Side Comparison View
// =============================================================================

interface SideBySideCompareProps {
  variants: LayoutVariant[];
  comparison: VariantComparison;
  onClose: () => void;
  preferredLayoutId?: string | null;
}

/**
 * D-05-04: Side-by-side comparison panel for selecting two variants
 */
export function SideBySideCompare({
  variants,
  comparison,
  onClose,
  preferredLayoutId,
}: SideBySideCompareProps) {
  const [leftVariant, setLeftVariant] = useState<LayoutVariant | null>(variants[0] || null);
  const [rightVariant, setRightVariant] = useState<LayoutVariant | null>(variants[1] || null);
  
  const formatNumber = (num: number, decimals: number = 0) => {
    return num.toLocaleString('en-US', { 
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
  };
  
  const formatVolume = (m3: number) => {
    if (Math.abs(m3) >= 1000) {
      return `${formatNumber(m3 / 1000, 1)}k m³`;
    }
    return `${formatNumber(m3)} m³`;
  };
  
  const getMetrics = (variant: LayoutVariant | null) => {
    if (!variant) return null;
    return comparison.metrics_table.find(m => m.layout_id === variant.layout.id);
  };
  
  const leftMetrics = getMetrics(leftVariant);
  const rightMetrics = getMetrics(rightVariant);
  
  const compareValue = (left: number | undefined, right: number | undefined, higherIsBetter: boolean = true) => {
    if (left === undefined || right === undefined) return { left: '', right: '' };
    const diff = left - right;
    if (Math.abs(diff) < 0.01) return { left: '', right: '' };
    
    const betterClass = higherIsBetter 
      ? (diff > 0 ? 'better' : 'worse')
      : (diff < 0 ? 'better' : 'worse');
    const worseClass = higherIsBetter
      ? (diff < 0 ? 'better' : 'worse')
      : (diff > 0 ? 'better' : 'worse');
    
    return {
      left: betterClass,
      right: worseClass,
    };
  };
  
  return (
    <div className="side-by-side-overlay">
      <div className="side-by-side-modal">
        <div className="side-by-side-header">
          <h2>Compare Variants</h2>
          <button type="button" className="close-btn" onClick={onClose}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        
        <div className="side-by-side-selectors">
          <div className="variant-selector-dropdown">
            <label>Left Layout:</label>
            <select 
              value={leftVariant?.strategy || ''} 
              onChange={(e) => setLeftVariant(variants.find(v => v.strategy === e.target.value) || null)}
            >
              {variants.map(v => (
                <option key={v.strategy} value={v.strategy}>
                  {v.strategy_name}
                  {preferredLayoutId === v.layout.id ? ' ★' : ''}
                </option>
              ))}
            </select>
          </div>
          <div className="compare-vs">VS</div>
          <div className="variant-selector-dropdown">
            <label>Right Layout:</label>
            <select 
              value={rightVariant?.strategy || ''} 
              onChange={(e) => setRightVariant(variants.find(v => v.strategy === e.target.value) || null)}
            >
              {variants.map(v => (
                <option key={v.strategy} value={v.strategy}>
                  {v.strategy_name}
                  {preferredLayoutId === v.layout.id ? ' ★' : ''}
                </option>
              ))}
            </select>
          </div>
        </div>
        
        <div className="side-by-side-content">
          {/* Comparison Cards */}
          <div className="comparison-cards">
            <div className={`comparison-card ${preferredLayoutId === leftVariant?.layout.id ? 'preferred' : ''}`}>
              <h3>{leftVariant?.strategy_name || 'Select Layout'}</h3>
              {preferredLayoutId === leftVariant?.layout.id && <span className="preferred-badge">★ Preferred</span>}
              {leftMetrics && (
                <div className="metrics-list">
                  <div className={`metric-row ${compareValue(leftMetrics.total_capacity_kw, rightMetrics?.total_capacity_kw, true).left}`}>
                    <span className="metric-label">Capacity</span>
                    <span className="metric-value">{formatNumber(leftMetrics.total_capacity_kw)} kW</span>
                  </div>
                  <div className="metric-row">
                    <span className="metric-label">Assets</span>
                    <span className="metric-value">{leftMetrics.asset_count}</span>
                  </div>
                  <div className={`metric-row ${compareValue(leftMetrics.road_length_m, rightMetrics?.road_length_m, false).left}`}>
                    <span className="metric-label">Road Length</span>
                    <span className="metric-value">{formatNumber(leftMetrics.road_length_m)} m</span>
                  </div>
                  <div className={`metric-row ${compareValue(leftMetrics.cut_volume_m3, rightMetrics?.cut_volume_m3, false).left}`}>
                    <span className="metric-label">Cut Volume</span>
                    <span className="metric-value">{formatVolume(leftMetrics.cut_volume_m3)}</span>
                  </div>
                  <div className={`metric-row ${compareValue(leftMetrics.fill_volume_m3, rightMetrics?.fill_volume_m3, false).left}`}>
                    <span className="metric-label">Fill Volume</span>
                    <span className="metric-value">{formatVolume(leftMetrics.fill_volume_m3)}</span>
                  </div>
                  <div className={`metric-row ${compareValue(Math.abs(leftMetrics.net_earthwork_m3), Math.abs(rightMetrics?.net_earthwork_m3 || 0), false).left}`}>
                    <span className="metric-label">Net Earthwork</span>
                    <span className="metric-value">
                      {leftMetrics.net_earthwork_m3 >= 0 ? '+' : ''}{formatVolume(leftMetrics.net_earthwork_m3)}
                    </span>
                  </div>
                </div>
              )}
            </div>
            
            <div className={`comparison-card ${preferredLayoutId === rightVariant?.layout.id ? 'preferred' : ''}`}>
              <h3>{rightVariant?.strategy_name || 'Select Layout'}</h3>
              {preferredLayoutId === rightVariant?.layout.id && <span className="preferred-badge">★ Preferred</span>}
              {rightMetrics && (
                <div className="metrics-list">
                  <div className={`metric-row ${compareValue(leftMetrics?.total_capacity_kw, rightMetrics.total_capacity_kw, true).right}`}>
                    <span className="metric-label">Capacity</span>
                    <span className="metric-value">{formatNumber(rightMetrics.total_capacity_kw)} kW</span>
                  </div>
                  <div className="metric-row">
                    <span className="metric-label">Assets</span>
                    <span className="metric-value">{rightMetrics.asset_count}</span>
                  </div>
                  <div className={`metric-row ${compareValue(leftMetrics?.road_length_m, rightMetrics.road_length_m, false).right}`}>
                    <span className="metric-label">Road Length</span>
                    <span className="metric-value">{formatNumber(rightMetrics.road_length_m)} m</span>
                  </div>
                  <div className={`metric-row ${compareValue(leftMetrics?.cut_volume_m3, rightMetrics.cut_volume_m3, false).right}`}>
                    <span className="metric-label">Cut Volume</span>
                    <span className="metric-value">{formatVolume(rightMetrics.cut_volume_m3)}</span>
                  </div>
                  <div className={`metric-row ${compareValue(leftMetrics?.fill_volume_m3, rightMetrics.fill_volume_m3, false).right}`}>
                    <span className="metric-label">Fill Volume</span>
                    <span className="metric-value">{formatVolume(rightMetrics.fill_volume_m3)}</span>
                  </div>
                  <div className={`metric-row ${compareValue(Math.abs(leftMetrics?.net_earthwork_m3 || 0), Math.abs(rightMetrics.net_earthwork_m3), false).right}`}>
                    <span className="metric-label">Net Earthwork</span>
                    <span className="metric-value">
                      {rightMetrics.net_earthwork_m3 >= 0 ? '+' : ''}{formatVolume(rightMetrics.net_earthwork_m3)}
                    </span>
                  </div>
                </div>
              )}
            </div>
          </div>
          
          {/* Difference Summary */}
          {leftMetrics && rightMetrics && (
            <div className="difference-summary">
              <h4>Difference</h4>
              <div className="diff-grid">
                <div className="diff-item">
                  <span className="diff-label">Capacity</span>
                  <span className={`diff-value ${leftMetrics.total_capacity_kw > rightMetrics.total_capacity_kw ? 'positive' : leftMetrics.total_capacity_kw < rightMetrics.total_capacity_kw ? 'negative' : ''}`}>
                    {leftMetrics.total_capacity_kw - rightMetrics.total_capacity_kw >= 0 ? '+' : ''}
                    {formatNumber(leftMetrics.total_capacity_kw - rightMetrics.total_capacity_kw)} kW
                  </span>
                </div>
                <div className="diff-item">
                  <span className="diff-label">Road Length</span>
                  <span className={`diff-value ${leftMetrics.road_length_m < rightMetrics.road_length_m ? 'positive' : leftMetrics.road_length_m > rightMetrics.road_length_m ? 'negative' : ''}`}>
                    {leftMetrics.road_length_m - rightMetrics.road_length_m >= 0 ? '+' : ''}
                    {formatNumber(leftMetrics.road_length_m - rightMetrics.road_length_m)} m
                  </span>
                </div>
                <div className="diff-item">
                  <span className="diff-label">Net Earthwork</span>
                  <span className={`diff-value ${Math.abs(leftMetrics.net_earthwork_m3) < Math.abs(rightMetrics.net_earthwork_m3) ? 'positive' : Math.abs(leftMetrics.net_earthwork_m3) > Math.abs(rightMetrics.net_earthwork_m3) ? 'negative' : ''}`}>
                    {Math.abs(leftMetrics.net_earthwork_m3) - Math.abs(rightMetrics.net_earthwork_m3) >= 0 ? '+' : ''}
                    {formatVolume(Math.abs(leftMetrics.net_earthwork_m3) - Math.abs(rightMetrics.net_earthwork_m3))}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

interface VariantSelectorProps {
  variants: LayoutVariant[];
  selectedVariant: LayoutVariant | null;
  comparison: VariantComparison;
  onSelectVariant: (variant: LayoutVariant) => void;
  preferredLayoutId?: string | null;
  onSetPreferred?: (layoutId: string) => void;
}

/**
 * Combined variant selector with tabs, comparison, and side-by-side view
 */
export function VariantSelector({
  variants,
  selectedVariant,
  comparison,
  onSelectVariant,
  preferredLayoutId,
  onSetPreferred,
}: VariantSelectorProps) {
  const [showSideBySide, setShowSideBySide] = useState(false);
  
  const handleSelectByStrategy = (strategy: LayoutStrategy) => {
    const variant = variants.find(v => v.strategy === strategy);
    if (variant) {
      onSelectVariant(variant);
    }
  };
  
  const handleSelectByLayoutId = (layoutId: string) => {
    const variant = variants.find(v => v.layout.id === layoutId);
    if (variant) {
      onSelectVariant(variant);
    }
  };
  
  return (
    <div className="variant-selector">
      <VariantTabs
        variants={variants}
        selectedStrategy={selectedVariant?.strategy || null}
        onSelectVariant={handleSelectByStrategy}
        comparison={comparison}
        preferredLayoutId={preferredLayoutId}
        onSetPreferred={onSetPreferred}
      />
      
      <ComparisonTable
        comparison={comparison}
        onSelectVariant={handleSelectByLayoutId}
        preferredLayoutId={preferredLayoutId}
      />
      
      {/* D-05-04: Side-by-Side Compare Button */}
      <button
        type="button"
        className="side-by-side-btn"
        onClick={() => setShowSideBySide(true)}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="3" y="3" width="8" height="18" rx="1" />
          <rect x="13" y="3" width="8" height="18" rx="1" />
        </svg>
        Side-by-Side Compare
      </button>
      
      {/* D-05-04: Side-by-Side Modal */}
      {showSideBySide && (
        <SideBySideCompare
          variants={variants}
          comparison={comparison}
          onClose={() => setShowSideBySide(false)}
          preferredLayoutId={preferredLayoutId}
        />
      )}
    </div>
  );
}

