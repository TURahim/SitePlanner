"""
Export generation services for layouts.

Supports:
- GeoJSON export (B-08)
- KMZ export for Google Earth (B-09)
- PDF report generation (B-10)
"""
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
    ) -> str:
        """
        Export layout as KMZ for Google Earth.
        
        Args:
            layout_id: UUID of the layout
            site_name: Name of the site
            site_boundary: Site boundary as GeoJSON
            assets: List of asset dicts with position, type, etc.
            roads: List of road dicts with geometry, etc.
            
        Returns:
            Presigned S3 download URL
        """
        try:
            import simplekml
        except ImportError:
            logger.error("simplekml not installed. Run: pip install simplekml")
            raise
        
        kml = simplekml.Kml(name=f"{site_name} Layout")
        
        # Asset type colors (AABBGGRR format for KML)
        ASSET_COLORS = {
            "solar_array": "ff00ffff",    # Yellow
            "battery": "ffff00ff",         # Magenta/Purple
            "generator": "ff0000ff",       # Red
            "substation": "ffff0000",      # Blue
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
        
        # Add assets
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
            
            # Set description
            desc_parts = [
                f"Type: {asset.get('asset_type', 'Unknown')}",
                f"Capacity: {asset.get('capacity_kw', 0)} kW",
            ]
            if asset.get("elevation_m"):
                desc_parts.append(f"Elevation: {asset['elevation_m']} m")
            if asset.get("slope_deg"):
                desc_parts.append(f"Slope: {asset['slope_deg']}°")
            pnt.description = "\n".join(desc_parts)
            
            # Set color based on asset type
            color = ASSET_COLORS.get(asset.get("asset_type"), "ffffffff")
            pnt.style.iconstyle.color = color
            pnt.style.iconstyle.scale = 1.2
        
        # Add roads
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
            line.style.linestyle.color = "ff00ffff"  # Yellow
            line.style.linestyle.width = 3
            
            desc_parts = [f"Length: {road.get('length_m', 0):.0f} m"]
            if road.get("max_grade_pct"):
                desc_parts.append(f"Max Grade: {road['max_grade_pct']:.1f}%")
            line.description = "\n".join(desc_parts)
        
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
    ) -> str:
        """
        Export layout as PDF report.
        
        Args:
            layout_id: UUID of the layout
            site_name: Name of the site
            site_area_m2: Site area in square meters
            layout_data: Layout metadata (capacity, cut/fill, etc.)
            assets: List of asset dicts
            roads: List of road dicts
            
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
        site_data = [
            ["Property", "Value"],
            ["Site Area", f"{site_area_ha:.2f} hectares ({site_area_m2:,.0f} m²)"],
            ["Total Capacity", f"{layout_data.get('total_capacity_kw', 0):,.1f} kW"],
            ["Asset Count", str(len(assets))],
            ["Road Network", f"{sum(r.get('length_m', 0) for r in roads):,.0f} m"],
        ]
        
        if layout_data.get("cut_volume_m3"):
            site_data.append(["Cut Volume", f"{layout_data['cut_volume_m3']:,.0f} m³"])
        if layout_data.get("fill_volume_m3"):
            site_data.append(["Fill Volume", f"{layout_data['fill_volume_m3']:,.0f} m³"])
        
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
        
        # Asset Inventory
        story.append(Paragraph("Asset Inventory", heading_style))
        
        # Group assets by type
        asset_summary = {}
        for asset in assets:
            atype = asset.get("asset_type", "unknown")
            if atype not in asset_summary:
                asset_summary[atype] = {"count": 0, "capacity": 0}
            asset_summary[atype]["count"] += 1
            asset_summary[atype]["capacity"] += asset.get("capacity_kw", 0)
        
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
                detail_data.append([
                    asset.get("name", "-"),
                    asset.get("asset_type", "-").replace("_", " ").title(),
                    f"{asset.get('capacity_kw', 0):.0f} kW",
                    f"{asset.get('elevation_m', '-')} m" if asset.get('elevation_m') else "-",
                    f"{asset.get('slope_deg', '-')}°" if asset.get('slope_deg') else "-",
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


# Global service instance
_export_service: Optional[ExportService] = None


def get_export_service() -> ExportService:
    """Get the export service singleton."""
    global _export_service
    if _export_service is None:
        _export_service = ExportService()
    return _export_service

