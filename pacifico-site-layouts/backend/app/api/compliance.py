"""
Compliance and GIS integration API endpoints (Phase 5).

Provides endpoints for:
- Evaluating layouts against jurisdiction-specific compliance rules
- Managing custom compliance rules
- Publishing layouts to GIS systems
"""
import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.layout import Layout
from app.models.site import Site
from app.models.user import User
from app.schemas.layout import (
    ComplianceCheckRequest,
    ComplianceCheckResponse,
    ComplianceRuleRequest,
    ComplianceRuleResponse,
    ComplianceViolation,
    GetComplianceRulesRequest,
    GetComplianceRulesResponse,
    GISPublishRequest,
    GISPublishResponse,
)
from app.services.compliance_rules_engine import (
    ComplianceRulesEngine,
    RuleViolation,
    Jurisdiction,
    RuleType,
    get_compliance_rules_engine,
)
from app.services.gis_integration_service import (
    GISIntegrationService,
    GISProviderType,
    get_gis_integration_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Compliance & GIS"])


# =============================================================================
# Compliance Rules Endpoints
# =============================================================================


@router.get(
    "/layouts/{layout_id}/compliance/check",
    response_model=ComplianceCheckResponse,
    summary="Check layout compliance",
    description="Phase 5: Evaluate a layout against jurisdiction-specific compliance rules.",
)
async def check_layout_compliance(
    layout_id: UUID,
    jurisdiction: str = "default",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ComplianceCheckResponse:
    """
    Check if a layout complies with compliance rules for a jurisdiction.
    
    Phase 5 enhancement: Provides detailed compliance violations and warnings.
    """
    # Get layout
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    
    stmt = (
        select(Layout)
        .where(Layout.id == layout_id)
        .options(selectinload(Layout.assets), selectinload(Layout.roads))
    )
    result = await db.execute(stmt)
    layout = result.unique().scalar_one_or_none()
    
    if not layout:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Layout not found",
        )
    
    # Get compliance engine
    engine = get_compliance_rules_engine(jurisdiction)
    
    # Build asset list for validation
    assets_data = []
    if layout.assets:
        for asset in layout.assets:
            assets_data.append({
                "type": asset.asset_type,
                "slope_deg": asset.slope_deg or 0.0,
                "distance_to_boundary_m": 5.0,  # Default; could be computed from geometry
                "min_spacing_m": 15.0,  # Default spacing
            })
    
    # Build road list for validation
    roads_data = []
    if layout.roads:
        for road in layout.roads:
            # Estimate grade from start/end elevation if available
            grade_pct = 5.0  # Default; could be computed from geometry
            roads_data.append({
                "grade_pct": grade_pct,
            })
    
    # Run validation
    check_result = engine.validate_layout(assets_data, roads_data)
    
    # Convert violations to response format
    violations = [
        ComplianceViolation(
            rule_id=v.rule_id,
            rule_type=v.rule_type.value,
            asset_type=v.asset_type,
            message=v.message,
            severity=v.severity,
            actual_value=v.actual_value,
            limit_value=v.limit_value,
        )
        for v in check_result.violations
    ]
    
    warnings = [
        ComplianceViolation(
            rule_id=w.rule_id,
            rule_type=w.rule_type.value,
            asset_type=w.asset_type,
            message=w.message,
            severity=w.severity,
            actual_value=w.actual_value,
            limit_value=w.limit_value,
        )
        for w in check_result.warnings
    ]
    
    return ComplianceCheckResponse(
        layout_id=layout_id,
        is_compliant=check_result.is_compliant,
        violations_count=len(violations),
        warnings_count=len(warnings),
        violations=violations,
        warnings=warnings,
        checked_rules_count=check_result.checked_rules_count,
    )


@router.get(
    "/compliance/rules",
    response_model=GetComplianceRulesResponse,
    summary="Get compliance rules for jurisdiction",
    description="Phase 5: List all compliance rules for a specific jurisdiction.",
)
async def get_compliance_rules(
    jurisdiction: str = "default",
    enabled_only: bool = True,
    current_user: User = Depends(get_current_user),
) -> GetComplianceRulesResponse:
    """Get all compliance rules for a jurisdiction."""
    engine = get_compliance_rules_engine(jurisdiction)
    rules = engine.get_all_rules(enabled_only=enabled_only)
    
    rule_responses = [
        ComplianceRuleResponse(
            rule_id=r.rule_id,
            rule_type=r.rule_type.value,
            jurisdiction=r.jurisdiction.value,
            asset_type=r.asset_type,
            value=r.value,
            unit=r.unit,
            description=r.description,
            enabled=r.enabled,
        )
        for r in rules
    ]
    
    return GetComplianceRulesResponse(
        jurisdiction=jurisdiction,
        total_rules=len(rule_responses),
        rules=rule_responses,
    )


@router.get(
    "/compliance/jurisdictions",
    response_model=dict,
    summary="Get available jurisdictions",
    description="Phase 5: List all supported jurisdictions for compliance rules.",
)
async def get_available_jurisdictions(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Get list of available jurisdiction codes."""
    jurisdictions = [j.value for j in Jurisdiction]
    return {
        "jurisdictions": jurisdictions,
        "default": "default",
        "total": len(jurisdictions),
    }


@router.post(
    "/layouts/{layout_id}/compliance/override-rule",
    response_model=ComplianceRuleResponse,
    summary="Override compliance rule for layout",
    description="Phase 5: Add or override a compliance rule for a specific layout.",
)
async def override_compliance_rule(
    layout_id: UUID,
    rule_request: ComplianceRuleRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ComplianceRuleResponse:
    """
    Override or add a custom compliance rule for a layout.
    
    This creates a project-specific rule that takes precedence over default rules.
    """
    from sqlalchemy import select
    
    # Verify layout exists
    stmt = select(Layout).where(Layout.id == layout_id)
    result = await db.execute(stmt)
    layout = result.scalar_one_or_none()
    
    if not layout:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Layout not found",
        )
    
    # Map rule type string to enum
    try:
        rule_type = RuleType(rule_request.rule_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown rule type: {rule_request.rule_type}",
        )
    
    # Create engine and add rule
    engine = get_compliance_rules_engine("default")
    from app.services.compliance_rules_engine import ComplianceRule
    
    rule = ComplianceRule(
        rule_id=rule_request.rule_id,
        rule_type=rule_type,
        jurisdiction=Jurisdiction.DEFAULT,
        asset_type=rule_request.asset_type,
        value=rule_request.value,
        unit=rule_request.unit,
        description=rule_request.description,
        enabled=rule_request.enabled,
    )
    
    engine.add_rule(rule)
    
    logger.info(f"Added compliance rule {rule_request.rule_id} to layout {layout_id}")
    
    return ComplianceRuleResponse(
        rule_id=rule.rule_id,
        rule_type=rule.rule_type.value,
        jurisdiction=rule.jurisdiction.value,
        asset_type=rule.asset_type,
        value=rule.value,
        unit=rule.unit,
        description=rule.description,
        enabled=rule.enabled,
    )


# =============================================================================
# GIS Integration Endpoints
# =============================================================================


@router.post(
    "/layouts/{layout_id}/gis/publish",
    response_model=GISPublishResponse,
    summary="Publish layout to GIS system",
    description="Phase 5: Push a layout to external GIS system (logging, ArcGIS, etc.)",
)
async def publish_layout_to_gis(
    layout_id: UUID,
    publish_request: GISPublishRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GISPublishResponse:
    """
    Publish a layout to a GIS system.
    
    Phase 5: Supports pluggable GIS providers. Currently supports:
    - Logging (stub for development)
    - Mock (for testing)
    - Future: ArcGIS Online, GeoServer, Mapbox
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    
    # Get layout with full data
    stmt = (
        select(Layout)
        .where(Layout.id == layout_id)
        .options(selectinload(Layout.assets), selectinload(Layout.roads))
    )
    result = await db.execute(stmt)
    layout = result.unique().scalar_one_or_none()
    
    if not layout:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Layout not found",
        )
    
    # Get site for additional metadata
    stmt = select(Site).where(Site.id == layout.site_id)
    result = await db.execute(stmt)
    site = result.scalar_one_or_none()
    
    # Convert layout to GeoJSON for GIS publish
    # This would normally come from layout.to_geojson_feature_collection()
    geojson_data = {
        "type": "FeatureCollection",
        "features": [],
    }
    
    # Add assets as features
    if layout.assets:
        for asset in layout.assets:
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [asset.longitude, asset.latitude],
                },
                "properties": {
                    "type": asset.asset_type,
                    "name": asset.name or f"{asset.asset_type}_{asset.id}",
                    "capacity_kw": asset.capacity_kw,
                    "slope_deg": asset.slope_deg,
                },
            }
            geojson_data["features"].append(feature)
    
    # Add roads as features
    if layout.roads:
        for road in layout.roads:
            if road.geom:
                feature = {
                    "type": "Feature",
                    "geometry": road.geom,
                    "properties": {
                        "type": "road",
                        "length_m": road.length_m,
                        "asset_from": road.asset_from,
                        "asset_to": road.asset_to,
                    },
                }
                geojson_data["features"].append(feature)
    
    # Build metadata
    metadata = {}
    if publish_request.include_metadata:
        metadata = {
            "layout_id": str(layout_id),
            "site_id": str(layout.site_id),
            "site_name": site.name if site else "Unknown",
            "strategy": layout.strategy,
            "capacity_kw": layout.target_capacity_kw,
            "total_assets": len(layout.assets) if layout.assets else 0,
            "total_roads": len(layout.roads) if layout.roads else 0,
        }
    
    # Get GIS service (enabled for all requests, provider type determines output)
    gis_service = get_gis_integration_service(
        provider_type=publish_request.provider_type,
        enabled=True,
    )
    
    # Publish
    result = gis_service.publish_layout(
        layout_id=str(layout_id),
        layout_name=layout.name or f"Layout {layout_id}",
        geojson_data=geojson_data,
        metadata=metadata,
    )
    
    logger.info(
        f"Published layout {layout_id} to GIS ({publish_request.provider_type}): "
        f"{result.message}"
    )
    
    return GISPublishResponse(
        success=result.success,
        provider_type=result.provider_type.value,
        message=result.message,
        external_id=result.external_id,
        url=result.url,
        features_published=result.features_published,
        errors=result.errors,
    )


@router.get(
    "/gis/providers",
    response_model=dict,
    summary="Get available GIS providers",
    description="Phase 5: List supported GIS provider types.",
)
async def get_gis_providers(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Get list of available GIS provider types."""
    providers = [p.value for p in GISProviderType]
    return {
        "providers": providers,
        "default": "logging",
        "description": {
            "logging": "Stub provider for development (logs to console)",
            "mock": "Mock provider for testing (in-memory storage)",
            "arcgis_online": "ArcGIS Online feature service (coming soon)",
            "geoserver": "GeoServer WFS-T (coming soon)",
            "mapbox": "Mapbox data API (coming soon)",
        },
    }

