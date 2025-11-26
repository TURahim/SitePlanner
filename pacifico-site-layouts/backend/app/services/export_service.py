"""
Export generation services for layouts.

Supports:
- GeoJSON export (B-08)
- KMZ export for Google Earth (B-09)
- PDF report generation (B-10)
- CSV tabular export (D-04-05)

Phase D-04 enhancements:
- PDF includes terrain summary, slope stats, buildable %
- KMZ includes slope/buildability styling
- CSV export for tabular data
"""
import csv
import io
import json
import logging
import zipfile
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from app.config import get_settings
from app.services.s3 import get_s3_service

logger = logging.getLogger(__name__)
settings = get_settings()


# D-04: Slope limits by asset type (degrees)
SLOPE_LIMITS = {
    "solar_array": 15.0,
    "battery": 5.0,
    "generator": 5.0,
    "substation": 5.0,
}


def _safe_number(value: Optional[float], default: float = 0.0) -> float:
    """Return a numeric value that is safe to format (treat None as default)."""
    return value if value is not None else default


class ExportService:
    """
    Service for generating layout exports in various formats.
    """
    
    OUTPUTS_S3_PREFIX = "outputs"
    
    def __init__(self):
        """Initialize the export service."""
        self._s3_service = get_s3_service()
    
    async def export_geojson(
        self,
        layout_id: UUID,
        geojson: dict[str, Any],
        site_name: str,
    ) -> str:
        """
        Export layout as GeoJSON and return presigned download URL.
        
        Args:
            layout_id: UUID of the layout
            geojson: GeoJSON FeatureCollection dict
            site_name: Name of the site for metadata
            
        Returns:
            Presigned S3 download URL
        """
        s3_key = f"{self.OUTPUTS_S3_PREFIX}/{layout_id}/layout.geojson"
        
        # Add metadata to GeoJSON
        geojson["name"] = f"{site_name} Layout"
        geojson["generated_at"] = datetime.utcnow().isoformat()
        
        await self._s3_service.upload_json(s3_key, geojson)
        
        url = await self._s3_service.get_output_presigned_url(s3_key)
        logger.info(f"Generated GeoJSON export for layout {layout_id}")
        
        return url
    
    async def export_kmz(
        self,
        layout_id: UUID,
        site_name: str,
        site_boundary: dict,
        assets: list[dict],
        roads: list[dict],
        layout_data: Optional[dict] = None,
        terrain_summary: Optional[dict] = None,
    ) -> str:
        """
        Export layout as KMZ for Google Earth.
        
        D-04-04: Includes slope/buildability styling with color-coded assets.
        
        Args:
            layout_id: UUID of the layout
            site_name: Name of the site
            site_boundary: Site boundary as GeoJSON
            assets: List of asset dicts with position, type, etc.
            roads: List of road dicts with geometry, etc.
            layout_data: Layout metadata (capacity, cut/fill, etc.)
            terrain_summary: Terrain analysis data (D-04)
            
        Returns:
            Presigned S3 download URL
        """
        try:
            import simplekml
        except ImportError:
            logger.error("simplekml not installed. Run: pip install simplekml")
            raise
        
        kml = simplekml.Kml(name=f"{site_name} Layout")
        layout_data = layout_data or {}
        
        # Asset type colors (AABBGGRR format for KML)
        ASSET_COLORS = {
            "solar_array": "ff00ffff",    # Yellow
            "battery": "ffff00ff",         # Magenta/Purple
            "generator": "ff0000ff",       # Red
            "substation": "ffff0000",      # Blue
        }
        
        # D-04-04: Road grade colors
        ROAD_GRADE_COLORS = {
            "easy": "ff00ff00",      # Green (< 5%)
            "moderate": "ff00a5ff",  # Orange (5-10%)
            "steep": "ff0000ff",     # Red (> 10%)
        }
        
        # Add site boundary
        if site_boundary and site_boundary.get("coordinates"):
            coords = site_boundary["coordinates"][0]  # Outer ring
            boundary = kml.newfolder(name="Site Boundary")
            pol = boundary.newpolygon(name=site_name)
            pol.outerboundaryis = [(c[0], c[1]) for c in coords]
            pol.style.linestyle.color = "ff0000ff"  # Red
            pol.style.linestyle.width = 3
            pol.style.polystyle.fill = 0
            
            # Add site info to description
            desc_parts = [f"Site: {site_name}"]
            if layout_data:
                total_capacity = _safe_number(layout_data.get("total_capacity_kw"))
                desc_parts.append(f"Total Capacity: {total_capacity:,.0f} kW")
                cut_volume = layout_data.get("cut_volume_m3")
                if cut_volume:
                    desc_parts.append(f"Cut Volume: {_safe_number(cut_volume):,.0f} m³")
                fill_volume = layout_data.get("fill_volume_m3")
                if fill_volume:
                    desc_parts.append(f"Fill Volume: {_safe_number(fill_volume):,.0f} m³")
            pol.description = "\n".join(desc_parts)
        
        # Add assets with D-04-04 slope/buildability styling
        assets_folder = kml.newfolder(name="Assets")
        for asset in assets:
            if not asset.get("position"):
                continue
            
            coords = asset["position"].get("coordinates", [])
            if len(coords) < 2:
                continue
            
            pnt = assets_folder.newpoint(
                name=asset.get("name", "Asset"),
                coords=[(coords[0], coords[1])],
            )
            
            # D-04-04: Enhanced description with slope suitability
            asset_type = asset.get("asset_type", "unknown")
            slope_limit = SLOPE_LIMITS.get(asset_type, 15.0)
            actual_slope = asset.get("slope_deg")
            
            capacity_kw = _safe_number(asset.get("capacity_kw"))
            desc_parts = [
                f"Type: {asset_type.replace('_', ' ').title()}",
                f"Capacity: {capacity_kw:,.0f} kW",
            ]
            if asset.get("elevation_m"):
                desc_parts.append(f"Elevation: {asset['elevation_m']:.1f} m")
            if actual_slope is not None:
                slope_status = "✓ Within limit" if actual_slope <= slope_limit else "⚠ Exceeds limit"
                desc_parts.append(f"Slope: {actual_slope:.1f}° ({slope_status})")
                desc_parts.append(f"Max allowed: {slope_limit}°")
            if asset.get("footprint_length_m") and asset.get("footprint_width_m"):
                desc_parts.append(f"Footprint: {asset['footprint_length_m']:.0f}×{asset['footprint_width_m']:.0f} m")
            pnt.description = "\n".join(desc_parts)
            
            # D-04-04: Color based on slope suitability
            base_color = ASSET_COLORS.get(asset_type, "ffffffff")
            if actual_slope is not None and actual_slope > slope_limit:
                # Asset exceeds slope limit - use red tint
                pnt.style.iconstyle.color = "ff5555ff"  # Reddish
                pnt.style.iconstyle.scale = 1.0
            else:
                pnt.style.iconstyle.color = base_color
                pnt.style.iconstyle.scale = 1.2
        
        # Add roads with D-04-04 grade-based coloring
        roads_folder = kml.newfolder(name="Roads")
        for i, road in enumerate(roads):
            if not road.get("geometry"):
                continue
            
            coords = road["geometry"].get("coordinates", [])
            if len(coords) < 2:
                continue
            
            line = roads_folder.newlinestring(
                name=road.get("name", f"Road {i+1}"),
                coords=[(c[0], c[1]) for c in coords],
            )
            
            # D-04-04: Color based on grade
            grade = road.get("max_grade_pct", 0) or 0
            if grade < 5:
                grade_class = "easy"
            elif grade <= 10:
                grade_class = "moderate"
            else:
                grade_class = "steep"
            
            line.style.linestyle.color = ROAD_GRADE_COLORS[grade_class]
            line.style.linestyle.width = 4
            
            length_m = _safe_number(road.get("length_m"))
            desc_parts = [f"Length: {length_m:.0f} m"]
            if road.get("max_grade_pct") is not None:
                desc_parts.append(
                    f"Max Grade: {road['max_grade_pct']:.1f}% ({grade_class.title()})"
                )
            line.description = "\n".join(desc_parts)
        
        # D-04-04: Add terrain summary as a document description
        if terrain_summary:
            elev = terrain_summary.get("elevation", {})
            slope = terrain_summary.get("slope", {})
            elev_min = _safe_number(elev.get("min_m"))
            elev_max = _safe_number(elev.get("max_m"))
            elev_range = _safe_number(elev.get("range_m"))
            slope_min = _safe_number(slope.get("min_deg"))
            slope_max = _safe_number(slope.get("max_deg"))
            slope_mean = _safe_number(slope.get("mean_deg"))
            kml.document.description = (
                f"Terrain Summary for {site_name}\n\n"
                f"DEM Source: {terrain_summary.get('dem_source', 'Unknown')}\n"
                f"Resolution: {terrain_summary.get('dem_resolution_m', 'N/A')} m\n\n"
                f"Elevation: {elev_min:.0f} - {elev_max:.0f} m "
                f"(range: {elev_range:.0f} m)\n"
                f"Slope: {slope_min:.1f}° - {slope_max:.1f}° "
                f"(mean: {slope_mean:.1f}°)\n"
            )
        
        # Save as KMZ (zipped KML)
        kml_content = kml.kml()
        
        # Create KMZ (ZIP with .kml file inside)
        kmz_buffer = io.BytesIO()
        with zipfile.ZipFile(kmz_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("doc.kml", kml_content)
        kmz_bytes = kmz_buffer.getvalue()
        
        # Upload to S3
        s3_key = f"{self.OUTPUTS_S3_PREFIX}/{layout_id}/layout.kmz"
        await self._s3_service.upload_output_file(
            s3_key=s3_key,
            content=kmz_bytes,
            content_type="application/vnd.google-earth.kmz",
        )
        
        url = await self._s3_service.get_output_presigned_url(s3_key)
        logger.info(f"Generated KMZ export for layout {layout_id}")
        
        return url
    
    async def export_pdf(
        self,
        layout_id: UUID,
        site_name: str,
        site_area_m2: float,
        layout_data: dict,
        assets: list[dict],
        roads: list[dict],
        terrain_summary: Optional[dict] = None,
    ) -> str:
        """
        Export layout as PDF report.
        
        D-04-01: Includes terrain summary (slope stats, buildable %).
        
        Args:
            layout_id: UUID of the layout
            site_name: Name of the site
            site_area_m2: Site area in square meters
            layout_data: Layout metadata (capacity, cut/fill, etc.)
            assets: List of asset dicts
            roads: List of road dicts
            terrain_summary: Terrain analysis data (D-04)
            
        Returns:
            Presigned S3 download URL
        """
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.platypus import (
                SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                PageBreak
            )
        except ImportError:
            logger.error("reportlab not installed. Run: pip install reportlab")
            raise
        
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72,
        )
        
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            textColor=colors.HexColor('#1a365d'),
        )
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            spaceBefore=20,
            spaceAfter=10,
            textColor=colors.HexColor('#2c5282'),
        )
        subheading_style = ParagraphStyle(
            'CustomSubheading',
            parent=styles['Heading3'],
            fontSize=11,
            spaceBefore=12,
            spaceAfter=6,
            textColor=colors.HexColor('#4a5568'),
        )
        
        story = []
        
        # Title
        story.append(Paragraph(f"Site Layout Report", title_style))
        story.append(Paragraph(f"<b>{site_name}</b>", styles['Heading2']))
        story.append(Spacer(1, 12))
        
        # Generation info
        story.append(Paragraph(
            f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
            styles['Normal']
        ))
        story.append(Spacer(1, 24))
        
        # Site Summary
        story.append(Paragraph("Site Summary", heading_style))
        
        site_area_ha = site_area_m2 / 10000
        total_capacity_kw = _safe_number(layout_data.get("total_capacity_kw"))
        site_data = [
            ["Property", "Value"],
            ["Site Area", f"{site_area_ha:.2f} hectares ({site_area_m2:,.0f} m²)"],
            ["Total Capacity", f"{total_capacity_kw:,.1f} kW"],
            ["Asset Count", str(len(assets))],
            ["Road Network", f"{sum(r.get('length_m', 0) or 0 for r in roads):,.0f} m"],
        ]
        
        # D-04: Enhanced cut/fill display with net earthwork
        cut_vol = layout_data.get("cut_volume_m3") or 0
        fill_vol = layout_data.get("fill_volume_m3") or 0
        if cut_vol > 0 or fill_vol > 0:
            site_data.append(["Cut Volume", f"{cut_vol:,.0f} m³"])
            site_data.append(["Fill Volume", f"{fill_vol:,.0f} m³"])
            net = cut_vol - fill_vol
            net_label = "Net Export" if net > 0 else "Net Import" if net < 0 else "Balanced"
            site_data.append(["Net Earthwork", f"{abs(net):,.0f} m³ ({net_label})"])
        
        # Add terrain mode
        if layout_data.get("terrain_processed"):
            site_data.append(["Terrain Mode", "Terrain-aware placement"])
        
        site_table = Table(site_data, colWidths=[2*inch, 3*inch])
        site_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5282')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f7fafc')),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0')),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('TOPPADDING', (0, 1), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
        ]))
        story.append(site_table)
        story.append(Spacer(1, 24))
        
        # D-04-01: Terrain Analysis Summary (if available)
        if terrain_summary:
            story.append(Paragraph("Terrain Analysis", heading_style))
            
            elev = terrain_summary.get("elevation", {})
            slope = terrain_summary.get("slope", {})
            elev_min = _safe_number(elev.get("min_m"))
            elev_max = _safe_number(elev.get("max_m"))
            elev_mean = _safe_number(elev.get("mean_m"))
            slope_min = _safe_number(slope.get("min_deg"))
            slope_max = _safe_number(slope.get("max_deg"))
            slope_mean = _safe_number(slope.get("mean_deg"))
            
            terrain_data = [
                ["Property", "Value"],
                ["DEM Source", terrain_summary.get("dem_source", "N/A")],
                ["DEM Resolution", f"{terrain_summary.get('dem_resolution_m', 'N/A')} m"],
                ["Elevation Range", f"{elev_min:.0f} - {elev_max:.0f} m"],
                ["Elevation Mean", f"{elev_mean:.1f} m"],
                ["Slope Range", f"{slope_min:.1f}° - {slope_max:.1f}°"],
                ["Slope Mean", f"{slope_mean:.1f}°"],
            ]
            
            terrain_table = Table(terrain_data, colWidths=[2*inch, 3*inch])
            terrain_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5282')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f7fafc')),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0')),
                ('FONTSIZE', (0, 1), (-1, -1), 10),
                ('TOPPADDING', (0, 1), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
            ]))
            story.append(terrain_table)
            story.append(Spacer(1, 16))
            
            # D-04-01: Slope Distribution
            distribution = slope.get("distribution", [])
            if distribution:
                story.append(Paragraph("Slope Distribution", subheading_style))
                
                slope_dist_data = [["Slope Range", "Percentage", "Area (m²)"]]
                for bucket in distribution:
                    pct = _safe_number(bucket.get("percentage"))
                    area = _safe_number(bucket.get("area_m2"))
                    slope_dist_data.append([
                        bucket.get("range", ""),
                        f"{pct:.1f}%",
                        f"{area:,.0f}",
                    ])
                
                slope_dist_table = Table(slope_dist_data, colWidths=[2*inch, 1.5*inch, 1.5*inch])
                slope_dist_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4a5568')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f7fafc')),
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0')),
                    ('FONTSIZE', (0, 1), (-1, -1), 9),
                    ('TOPPADDING', (0, 1), (-1, -1), 6),
                    ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
                ]))
                story.append(slope_dist_table)
                story.append(Spacer(1, 16))
            
            # D-04-01: Buildable Area by Asset Type
            buildable_areas = terrain_summary.get("buildable_area", [])
            if buildable_areas:
                story.append(Paragraph("Buildable Area by Asset Type", subheading_style))
                
                buildable_data = [["Asset Type", "Max Slope", "Buildable Area", "% of Site"]]
                for ba in buildable_areas:
                    area_ha = _safe_number(ba.get("area_ha"))
                    pct = _safe_number(ba.get("percentage"))
                    buildable_data.append([
                        ba.get("asset_type", "").replace("_", " ").title(),
                        f"{ba.get('max_slope_deg', 0)}°",
                        f"{area_ha:.2f} ha",
                        f"{pct:.1f}%",
                    ])
                
                buildable_table = Table(buildable_data, colWidths=[1.8*inch, 1.2*inch, 1.5*inch, 1*inch])
                buildable_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4a5568')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f7fafc')),
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0')),
                    ('FONTSIZE', (0, 1), (-1, -1), 9),
                    ('TOPPADDING', (0, 1), (-1, -1), 6),
                    ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
                ]))
                story.append(buildable_table)
            
            story.append(Spacer(1, 24))
        
        # Asset Inventory
        story.append(Paragraph("Asset Inventory", heading_style))
        
        # Group assets by type with D-04 cut/fill breakdown
        asset_summary = {}
        for asset in assets:
            atype = asset.get("asset_type", "unknown")
            if atype not in asset_summary:
                asset_summary[atype] = {"count": 0, "capacity": 0}
            asset_summary[atype]["count"] += 1
            asset_summary[atype]["capacity"] += asset.get("capacity_kw", 0) or 0
        
        asset_data = [["Asset Type", "Count", "Total Capacity (kW)"]]
        for atype, data in sorted(asset_summary.items()):
            asset_data.append([
                atype.replace("_", " ").title(),
                str(data["count"]),
                f"{data['capacity']:,.1f}",
            ])
        
        asset_table = Table(asset_data, colWidths=[2.5*inch, 1.5*inch, 2*inch])
        asset_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5282')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 0), (2, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f7fafc')),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0')),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('TOPPADDING', (0, 1), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
        ]))
        story.append(asset_table)
        story.append(Spacer(1, 24))
        
        # Asset Details (if not too many)
        if len(assets) <= 20:
            story.append(Paragraph("Asset Details", heading_style))
            
            detail_data = [["Name", "Type", "Capacity", "Elevation", "Slope"]]
            for asset in assets:
                asset_capacity = _safe_number(asset.get("capacity_kw"))
                detail_data.append([
                    asset.get("name", "-"),
                    asset.get("asset_type", "-").replace("_", " ").title(),
                    f"{asset_capacity:.0f} kW",
                    f"{asset.get('elevation_m', 0):.1f} m" if asset.get('elevation_m') else "-",
                    f"{asset.get('slope_deg', 0):.1f}°" if asset.get('slope_deg') else "-",
                ])
            
            detail_table = Table(detail_data, colWidths=[1.5*inch, 1.3*inch, 1*inch, 1*inch, 0.8*inch])
            detail_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4a5568')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (2, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f7fafc')),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0')),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('TOPPADDING', (0, 1), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
            ]))
            story.append(detail_table)
            story.append(Spacer(1, 24))
        
        # Road Network Details
        if roads:
            story.append(Paragraph("Road Network", heading_style))
            
            road_data = [["Road", "Length (m)", "Max Grade (%)"]]
            for road in roads:
                grade = road.get("max_grade_pct")
                length_m = _safe_number(road.get("length_m"))
                grade_str = f"{grade:.1f}%" if grade is not None else "-"
                road_data.append([
                    road.get("name", "-"),
                    f"{length_m:.0f}",
                    grade_str,
                ])
            
            road_table = Table(road_data, colWidths=[2.5*inch, 1.5*inch, 1.5*inch])
            road_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4a5568')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f7fafc')),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0')),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('TOPPADDING', (0, 1), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
            ]))
            story.append(road_table)
        
        # Build PDF
        doc.build(story)
        pdf_bytes = buffer.getvalue()
        
        # Upload to S3
        s3_key = f"{self.OUTPUTS_S3_PREFIX}/{layout_id}/report.pdf"
        await self._s3_service.upload_output_file(
            s3_key=s3_key,
            content=pdf_bytes,
            content_type="application/pdf",
        )
        
        url = await self._s3_service.get_output_presigned_url(s3_key)
        logger.info(f"Generated PDF export for layout {layout_id}")
        
        return url
    
    async def export_csv(
        self,
        layout_id: UUID,
        site_name: str,
        site_area_m2: float,
        layout_data: dict,
        assets: list[dict],
        roads: list[dict],
    ) -> str:
        """
        Export layout as CSV for spreadsheet analysis.
        
        D-04-05: New export format with tabular asset/road data.
        
        Args:
            layout_id: UUID of the layout
            site_name: Name of the site
            site_area_m2: Site area in square meters
            layout_data: Layout metadata
            assets: List of asset dicts
            roads: List of road dicts
            
        Returns:
            Presigned S3 download URL
        """
        # Create multi-sheet CSV as a ZIP file with separate CSVs
        csv_buffer = io.BytesIO()
        
        with zipfile.ZipFile(csv_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Summary sheet
            summary_csv = io.StringIO()
            summary_writer = csv.writer(summary_csv)
            summary_writer.writerow(["Property", "Value"])
            summary_writer.writerow(["Site Name", site_name])
            summary_writer.writerow(["Site Area (m²)", f"{site_area_m2:.0f}"])
            summary_writer.writerow(["Site Area (ha)", f"{site_area_m2 / 10000:.2f}"])
            total_capacity = _safe_number(layout_data.get("total_capacity_kw"))
            summary_writer.writerow(["Total Capacity (kW)", f"{total_capacity:.1f}"])
            summary_writer.writerow(["Asset Count", len(assets)])
            summary_writer.writerow(["Road Count", len(roads)])
            summary_writer.writerow(["Total Road Length (m)", f"{sum(r.get('length_m', 0) or 0 for r in roads):.0f}"])
            cut_volume = _safe_number(layout_data.get("cut_volume_m3"))
            fill_volume = _safe_number(layout_data.get("fill_volume_m3"))
            summary_writer.writerow(["Cut Volume (m³)", f"{cut_volume:.0f}"])
            summary_writer.writerow(["Fill Volume (m³)", f"{fill_volume:.0f}"])
            summary_writer.writerow(["Generated At", datetime.utcnow().isoformat()])
            zf.writestr("summary.csv", summary_csv.getvalue())
            
            # Assets sheet
            assets_csv = io.StringIO()
            assets_writer = csv.writer(assets_csv)
            assets_writer.writerow([
                "ID", "Name", "Asset Type", "Capacity (kW)",
                "Longitude", "Latitude", "Elevation (m)", "Slope (deg)",
                "Footprint Length (m)", "Footprint Width (m)"
            ])
            for asset in assets:
                coords = asset.get("position", {}).get("coordinates", [None, None])
                assets_writer.writerow([
                    asset.get("id", ""),
                    asset.get("name", ""),
                    asset.get("asset_type", ""),
                    asset.get("capacity_kw", ""),
                    coords[0] if len(coords) > 0 else "",
                    coords[1] if len(coords) > 1 else "",
                    asset.get("elevation_m", ""),
                    asset.get("slope_deg", ""),
                    asset.get("footprint_length_m", ""),
                    asset.get("footprint_width_m", ""),
                ])
            zf.writestr("assets.csv", assets_csv.getvalue())
            
            # Roads sheet
            roads_csv = io.StringIO()
            roads_writer = csv.writer(roads_csv)
            roads_writer.writerow([
                "ID", "Name", "Length (m)", "Max Grade (%)", "Coordinate Count"
            ])
            for road in roads:
                coords = road.get("geometry", {}).get("coordinates", [])
                length_val = road.get("length_m")
                grade_val = road.get("max_grade_pct")
                roads_writer.writerow([
                    road.get("id", ""),
                    road.get("name", ""),
                    f"{_safe_number(length_val):.0f}" if length_val is not None else "",
                    f"{grade_val:.1f}" if grade_val is not None else "",
                    len(coords),
                ])
            zf.writestr("roads.csv", roads_csv.getvalue())
        
        csv_bytes = csv_buffer.getvalue()
        
        # Upload to S3
        s3_key = f"{self.OUTPUTS_S3_PREFIX}/{layout_id}/layout_data.zip"
        await self._s3_service.upload_output_file(
            s3_key=s3_key,
            content=csv_bytes,
            content_type="application/zip",
        )
        
        url = await self._s3_service.get_output_presigned_url(s3_key)
        logger.info(f"Generated CSV export for layout {layout_id}")
        
        return url


# Global service instance
_export_service: Optional[ExportService] = None


def get_export_service() -> ExportService:
    """Get the export service singleton."""
    global _export_service
    if _export_service is None:
        _export_service = ExportService()
    return _export_service

