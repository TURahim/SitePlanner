/**
 * SVG Icons for asset types
 * 
 * These icons represent different infrastructure equipment types
 * for the map visualization.
 */
import React from 'react';

interface IconProps {
  size?: number;
  color?: string;
  className?: string;
}

/**
 * Solar Array Icon - Panel grid pattern
 */
export const SolarArrayIcon: React.FC<IconProps> = ({ 
  size = 32, 
  color = '#f59e0b',
  className 
}) => (
  <svg 
    width={size} 
    height={size} 
    viewBox="0 0 32 32" 
    fill="none" 
    className={className}
    xmlns="http://www.w3.org/2000/svg"
  >
    {/* Panel frame */}
    <rect x="2" y="6" width="28" height="20" rx="2" fill="currentColor" fillOpacity="0.15" stroke={color} strokeWidth="1.5"/>
    
    {/* Solar panel grid - 3x2 pattern */}
    <g stroke={color} strokeWidth="1">
      {/* Vertical lines */}
      <line x1="12" y1="6" x2="12" y2="26"/>
      <line x1="20" y1="6" x2="20" y2="26"/>
      {/* Horizontal line */}
      <line x1="2" y1="16" x2="30" y2="16"/>
    </g>
    
    {/* Panel cells pattern */}
    <g fill={color} fillOpacity="0.3">
      <rect x="3" y="7" width="8" height="8" rx="0.5"/>
      <rect x="13" y="7" width="6" height="8" rx="0.5"/>
      <rect x="21" y="7" width="8" height="8" rx="0.5"/>
      <rect x="3" y="17" width="8" height="8" rx="0.5"/>
      <rect x="13" y="17" width="6" height="8" rx="0.5"/>
      <rect x="21" y="17" width="8" height="8" rx="0.5"/>
    </g>
    
    {/* Sun symbol */}
    <circle cx="26" cy="4" r="3" fill="#fbbf24" stroke="#f59e0b" strokeWidth="0.5"/>
    <g stroke="#f59e0b" strokeWidth="0.75">
      <line x1="26" y1="0" x2="26" y2="1"/>
      <line x1="29" y1="1" x2="28.5" y2="1.5"/>
      <line x1="30" y1="4" x2="29" y2="4"/>
    </g>
  </svg>
);

/**
 * Battery Storage Icon - Container with battery modules
 */
export const BatteryIcon: React.FC<IconProps> = ({ 
  size = 32, 
  color = '#3b82f6',
  className 
}) => (
  <svg 
    width={size} 
    height={size} 
    viewBox="0 0 32 32" 
    fill="none" 
    className={className}
    xmlns="http://www.w3.org/2000/svg"
  >
    {/* Container outline */}
    <rect x="2" y="8" width="28" height="18" rx="2" fill="currentColor" fillOpacity="0.15" stroke={color} strokeWidth="1.5"/>
    
    {/* Battery terminals */}
    <rect x="5" y="4" width="4" height="4" rx="1" fill={color}/>
    <rect x="23" y="4" width="4" height="4" rx="1" fill={color}/>
    
    {/* Battery modules */}
    <g fill={color} fillOpacity="0.6">
      <rect x="5" y="11" width="6" height="12" rx="1"/>
      <rect x="13" y="11" width="6" height="12" rx="1"/>
      <rect x="21" y="11" width="6" height="12" rx="1"/>
    </g>
    
    {/* Charge level indicators */}
    <g fill={color}>
      <rect x="6" y="18" width="4" height="4" rx="0.5"/>
      <rect x="14" y="16" width="4" height="6" rx="0.5"/>
      <rect x="22" y="14" width="4" height="8" rx="0.5"/>
    </g>
    
    {/* Lightning bolt */}
    <path d="M16 1 L14 5 L17 5 L15 9 L18 4 L15 4 L16 1" fill="#fbbf24" stroke={color} strokeWidth="0.5"/>
  </svg>
);

/**
 * Generator Icon - Engine with exhaust
 */
export const GeneratorIcon: React.FC<IconProps> = ({ 
  size = 32, 
  color = '#ef4444',
  className 
}) => (
  <svg 
    width={size} 
    height={size} 
    viewBox="0 0 32 32" 
    fill="none" 
    className={className}
    xmlns="http://www.w3.org/2000/svg"
  >
    {/* Generator housing */}
    <rect x="4" y="10" width="24" height="16" rx="2" fill="currentColor" fillOpacity="0.15" stroke={color} strokeWidth="1.5"/>
    
    {/* Engine block */}
    <rect x="6" y="13" width="12" height="10" rx="1" fill={color} fillOpacity="0.4"/>
    
    {/* Cylinder heads */}
    <g fill={color}>
      <rect x="7" y="14" width="4" height="3" rx="0.5"/>
      <rect x="12" y="14" width="4" height="3" rx="0.5"/>
    </g>
    
    {/* Control panel */}
    <rect x="20" y="13" width="6" height="10" rx="1" fill={color} fillOpacity="0.3" stroke={color} strokeWidth="0.5"/>
    
    {/* Control panel indicators */}
    <circle cx="23" cy="15.5" r="1" fill="#22c55e"/>
    <circle cx="23" cy="18.5" r="1" fill="#fbbf24"/>
    <rect x="21" y="20" width="4" height="2" rx="0.5" fill={color}/>
    
    {/* Exhaust pipe */}
    <rect x="1" y="12" width="3" height="4" rx="1" fill={color}/>
    
    {/* Exhaust fumes */}
    <g fill={color} fillOpacity="0.3">
      <circle cx="0" cy="10" r="2"/>
      <circle cx="-2" cy="8" r="1.5"/>
      <circle cx="1" cy="6" r="1"/>
    </g>
    
    {/* Base/skid */}
    <rect x="2" y="26" width="28" height="3" rx="1" fill={color} fillOpacity="0.6"/>
  </svg>
);

/**
 * Substation Icon - Transformer with power lines
 */
export const SubstationIcon: React.FC<IconProps> = ({ 
  size = 32, 
  color = '#8b5cf6',
  className 
}) => (
  <svg 
    width={size} 
    height={size} 
    viewBox="0 0 32 32" 
    fill="none" 
    className={className}
    xmlns="http://www.w3.org/2000/svg"
  >
    {/* Base platform */}
    <rect x="2" y="26" width="28" height="4" rx="1" fill={color} fillOpacity="0.4"/>
    
    {/* Transformer body */}
    <rect x="8" y="12" width="16" height="14" rx="2" fill="currentColor" fillOpacity="0.15" stroke={color} strokeWidth="1.5"/>
    
    {/* Transformer fins/cooling */}
    <g fill={color} fillOpacity="0.3">
      <rect x="5" y="14" width="3" height="10" rx="0.5"/>
      <rect x="24" y="14" width="3" height="10" rx="0.5"/>
    </g>
    
    {/* Transformer core symbol */}
    <g stroke={color} strokeWidth="1.5">
      {/* Primary coil */}
      <path d="M12 15 C10 15, 10 17, 12 17 C10 17, 10 19, 12 19 C10 19, 10 21, 12 21 C10 21, 10 23, 12 23"/>
      {/* Secondary coil */}
      <path d="M20 15 C22 15, 22 17, 20 17 C22 17, 22 19, 20 19 C22 19, 22 21, 20 21 C22 21, 22 23, 20 23"/>
    </g>
    
    {/* Bushings/insulators */}
    <g fill={color}>
      <rect x="10" y="6" width="3" height="6" rx="1"/>
      <rect x="19" y="6" width="3" height="6" rx="1"/>
    </g>
    
    {/* Power lines from top */}
    <g stroke={color} strokeWidth="1">
      <line x1="11.5" y1="2" x2="11.5" y2="6"/>
      <line x1="20.5" y1="2" x2="20.5" y2="6"/>
    </g>
    
    {/* Connection nodes */}
    <g fill={color}>
      <circle cx="11.5" cy="2" r="1.5"/>
      <circle cx="20.5" cy="2" r="1.5"/>
    </g>
    
    {/* Lightning warning symbol */}
    <path d="M16 16 L14.5 19 L16 19 L15 22 L17.5 18 L16 18 L16 16" fill="#fbbf24"/>
  </svg>
);

/**
 * Get the appropriate icon component for an asset type
 */
export function getAssetIcon(assetType: string): React.FC<IconProps> {
  const type = assetType.toLowerCase();
  switch (type) {
    case 'solar':
    case 'solar_array':
      return SolarArrayIcon;
    case 'battery':
      return BatteryIcon;
    case 'generator':
    case 'gas_turbine':
      return GeneratorIcon;
    case 'substation':
    case 'transformer':
    case 'control_center':
      return SubstationIcon;
    case 'wind_turbine':
    case 'cooling_system':
      return BatteryIcon; // Reuse battery icon for now
    default:
      return SolarArrayIcon; // Default to solar
  }
}

/**
 * Asset icon as data URL for Leaflet markers
 */
export function getAssetIconDataUrl(
  assetType: string, 
  size: number = 32,
  fillColor: string = '#ffffff'
): string {
  const colors: Record<string, string> = {
    solar: '#f59e0b',
    solar_array: '#f59e0b',
    battery: '#3b82f6',
    generator: '#ef4444',
    substation: '#8b5cf6',
    gas_turbine: '#dc2626',
    wind_turbine: '#10b981',
    control_center: '#22c55e',
    cooling_system: '#0ea5e9',
  };
  
  const color = colors[assetType.toLowerCase()] || '#6b7280';
  
  // Simplified SVG icons for markers
  const icons: Record<string, string> = {
    solar: `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 32 32"><rect x="2" y="6" width="28" height="20" rx="2" fill="${fillColor}" stroke="${color}" stroke-width="2"/><line x1="12" y1="6" x2="12" y2="26" stroke="${color}" stroke-width="1"/><line x1="20" y1="6" x2="20" y2="26" stroke="${color}" stroke-width="1"/><line x1="2" y1="16" x2="30" y2="16" stroke="${color}" stroke-width="1"/></svg>`,
    solar_array: `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 32 32"><rect x="2" y="6" width="28" height="20" rx="2" fill="${fillColor}" stroke="${color}" stroke-width="2"/><line x1="12" y1="6" x2="12" y2="26" stroke="${color}" stroke-width="1"/><line x1="20" y1="6" x2="20" y2="26" stroke="${color}" stroke-width="1"/><line x1="2" y1="16" x2="30" y2="16" stroke="${color}" stroke-width="1"/></svg>`,
    battery: `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 32 32"><rect x="2" y="8" width="28" height="18" rx="2" fill="${fillColor}" stroke="${color}" stroke-width="2"/><rect x="5" y="4" width="4" height="4" rx="1" fill="${color}"/><rect x="23" y="4" width="4" height="4" rx="1" fill="${color}"/><rect x="6" y="12" width="5" height="10" rx="1" fill="${color}" opacity="0.6"/><rect x="13" y="12" width="6" height="10" rx="1" fill="${color}" opacity="0.6"/><rect x="21" y="12" width="5" height="10" rx="1" fill="${color}" opacity="0.6"/></svg>`,
    generator: `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 32 32"><rect x="4" y="10" width="24" height="16" rx="2" fill="${fillColor}" stroke="${color}" stroke-width="2"/><rect x="6" y="13" width="12" height="10" rx="1" fill="${color}" opacity="0.4"/><rect x="20" y="13" width="6" height="10" rx="1" fill="${color}" opacity="0.3"/><circle cx="23" cy="15.5" r="1.5" fill="#22c55e"/><rect x="2" y="26" width="28" height="3" rx="1" fill="${color}" opacity="0.6"/></svg>`,
    substation: `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 32 32"><rect x="8" y="12" width="16" height="14" rx="2" fill="${fillColor}" stroke="${color}" stroke-width="2"/><rect x="10" y="6" width="3" height="6" rx="1" fill="${color}"/><rect x="19" y="6" width="3" height="6" rx="1" fill="${color}"/><line x1="11.5" y1="2" x2="11.5" y2="6" stroke="${color}" stroke-width="1.5"/><line x1="20.5" y1="2" x2="20.5" y2="6" stroke="${color}" stroke-width="1.5"/><circle cx="11.5" cy="2" r="1.5" fill="${color}"/><circle cx="20.5" cy="2" r="1.5" fill="${color}"/><rect x="2" y="26" width="28" height="4" rx="1" fill="${color}" opacity="0.4"/></svg>`,
    // Gas turbine - similar to generator but with flame symbol
    gas_turbine: `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 32 32"><rect x="4" y="10" width="24" height="16" rx="2" fill="${fillColor}" stroke="${color}" stroke-width="2"/><rect x="6" y="13" width="12" height="10" rx="1" fill="${color}" opacity="0.4"/><rect x="20" y="13" width="6" height="10" rx="1" fill="${color}" opacity="0.3"/><path d="M16 4 Q14 8 16 10 Q18 8 16 4" fill="#f97316"/><rect x="2" y="26" width="28" height="3" rx="1" fill="${color}" opacity="0.6"/></svg>`,
    // Wind turbine - three blades
    wind_turbine: `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 32 32"><rect x="14" y="16" width="4" height="14" fill="${color}" opacity="0.6"/><circle cx="16" cy="12" r="3" fill="${fillColor}" stroke="${color}" stroke-width="2"/><path d="M16 12 L16 2" stroke="${color}" stroke-width="2"/><path d="M16 12 L24 18" stroke="${color}" stroke-width="2"/><path d="M16 12 L8 18" stroke="${color}" stroke-width="2"/></svg>`,
    // Control center - building with antenna
    control_center: `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 32 32"><rect x="6" y="14" width="20" height="14" rx="2" fill="${fillColor}" stroke="${color}" stroke-width="2"/><rect x="14" y="4" width="4" height="10" fill="${color}"/><circle cx="16" cy="4" r="2" fill="${color}"/><rect x="9" y="18" width="4" height="6" fill="${color}" opacity="0.4"/><rect x="19" y="18" width="4" height="6" fill="${color}" opacity="0.4"/></svg>`,
    // Cooling system - tower with water drops
    cooling_system: `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 32 32"><path d="M8 28 L8 12 Q8 8 16 8 Q24 8 24 12 L24 28 Z" fill="${fillColor}" stroke="${color}" stroke-width="2"/><ellipse cx="16" cy="6" rx="4" ry="2" fill="${color}" opacity="0.3"/><circle cx="12" cy="18" r="1.5" fill="${color}" opacity="0.5"/><circle cx="16" cy="20" r="1.5" fill="${color}" opacity="0.5"/><circle cx="20" cy="18" r="1.5" fill="${color}" opacity="0.5"/></svg>`,
  };
  
  const icon = icons[assetType.toLowerCase()] || icons.solar;
  return `data:image/svg+xml;base64,${btoa(icon)}`;
}





