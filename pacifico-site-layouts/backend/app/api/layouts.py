"""
Layout management API endpoints.

Handles layout generation, retrieval, and listing.
Supports both dummy placement (Phase A) and terrain-aware placement (Phase B).
Supports async job queuing for layout generation (Phase C).
"""
import json
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from geoalchemy2.functions import ST_AsGeoJSON, ST_GeomFromText, ST_Length, ST_SetSRID
from shapely import wkt
from shapely.geometry import mapping, shape
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models.asset import Asset
from app.models.exclusion_zone import ExclusionZone
from app.models.layout import Layout, LayoutStatus
from app.models.road import Road
from app.models.site import Site
from app.models.user import User
from app.schemas.layout import (
    AssetResponse,
    GenerateLayoutRequest,
    LayoutDetailResponse,
    LayoutEnqueueResponse,
    LayoutGenerateResponse,
    LayoutListResponse,
    LayoutResponse,
    LayoutStatusResponse,
    LayoutStrategy,
    LayoutStrategiesResponse,
    LayoutVariantMetrics,
    LayoutVariantResponse,
    LayoutVariantsResponse,
    RoadResponse,
    STRATEGY_INFO_LIST,
    VariantComparison,
)
# Phase A: Dummy layout generator
from app.services.layout_generator import DummyLayoutGenerator
# Phase B: Terrain-aware services
from app.services.dem_service import get_dem_service
from app.services.slope_service import get_slope_service
# D-05: Import LayoutStrategy enum from generator for strategy mapping
from app.services.terrain_layout_generator import (
    TerrainAwareLayoutGenerator,
    LayoutStrategy as GeneratorStrategy,
)
# Phase E: Enhanced terrain analysis
from app.services.terrain_analysis_service import (
    get_terrain_analysis_service,
    TerrainAnalysisService,
)
# Phase C: Async job queuing
from app.services.sqs_service import get_sqs_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/layouts", tags=["Layouts"])


# =============================================================================
# D-05: Layout Strategies Endpoint
# =============================================================================


@router.get(
    "/strategies",
    response_model=LayoutStrategiesResponse,
    summary="Get available layout strategies",
    description="D-05: Returns all available layout optimization strategies with descriptions.",
)
async def get_layout_strategies() -> LayoutStrategiesResponse:
    """Get available layout strategies for variant generation."""
    return LayoutStrategiesResponse(strategies=STRATEGY_INFO_LIST)


@router.post(
    "/generate",
    response_model=LayoutGenerateResponse | LayoutEnqueueResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate layout",
    description="Generate a layout for a site. Uses terrain-aware placement by default (Phase B). Returns async job ID if enabled (Phase C).",
)
async def generate_layout(
    request: GenerateLayoutRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LayoutGenerateResponse | LayoutEnqueueResponse:
    """
    Generate a new layout for a site.
    
    **Response type depends on configuration:**
    
    **Sync mode (default, Phase A/B):**
    Returns full layout with assets and roads as GeoJSON immediately.
    
    **Async mode (Phase C - enable with ENABLE_ASYNC_LAYOUT_GENERATION=true):**
    Returns layout_id immediately, processing happens in worker. Poll with
    GET /api/layouts/{layout_id}/status to check progress.
    
    **Layout Generation Methods:**
    - Terrain-aware (default): Fetches DEM, computes slope, places assets respecting constraints
    - Dummy (Phase A fallback): Use use_terrain=False for grid-based placement
    
    Parameters:
    - **site_id**: UUID of the site to generate layout for
    - **target_capacity_kw**: Target total capacity in kW (default: 1000)
    - **use_terrain**: Use terrain-aware placement (default: config-dependent)
    - **dem_resolution_m**: DEM resolution in meters (10 or 30)
    """
    # Load site with ownership check
    site_result = await db.execute(
        select(Site).where(
            Site.id == request.site_id,
            Site.owner_id == current_user.id,
        )
    )
    site = site_result.scalar_one_or_none()
    
    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site not found",
        )
    
    # Phase C (C-03): If async mode enabled, enqueue job instead of processing
    settings = get_settings()
    if settings.enable_async_layout_generation:
        return await _enqueue_layout_job(
            request=request,
            site=site,
            db=db,
        )
    
    # Get site boundary as WKT for Shapely
    boundary_wkt_result = await db.execute(
        select(Site.boundary.ST_AsText()).where(Site.id == site.id)
    )
    boundary_wkt = boundary_wkt_result.scalar()
    
    if not boundary_wkt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Site has no boundary geometry",
        )
    
    # Parse boundary with Shapely
    try:
        boundary = wkt.loads(boundary_wkt)
    except Exception as e:
        logger.error(f"Failed to parse site boundary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to parse site boundary",
        )
    
    # Create Layout record
    layout = Layout(
        site_id=site.id,
        status=LayoutStatus.PROCESSING.value,
    )
    db.add(layout)
    await db.flush()  # Get the ID
    
    num_assets = random_asset_count(request.target_capacity_kw)
    
    # Choose generation method based on use_terrain flag
    if request.use_terrain:
        result = await _generate_terrain_aware_layout(
            layout=layout,
            site=site,
            boundary=boundary,
            target_capacity_kw=request.target_capacity_kw,
            dem_resolution_m=request.dem_resolution_m,
            num_assets=num_assets,
            db=db,
        )
    else:
        result = await _generate_dummy_layout(
            layout=layout,
            boundary=boundary,
            target_capacity_kw=request.target_capacity_kw,
            num_assets=num_assets,
            db=db,
        )
    
    return result


# =============================================================================
# D-05: Layout Variants Generation Endpoint
# =============================================================================


@router.post(
    "/generate-variants",
    response_model=LayoutVariantsResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate layout variants",
    description="D-05: Generate multiple layout variants with different optimization strategies for comparison.",
)
async def generate_layout_variants(
    request: GenerateLayoutRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LayoutVariantsResponse:
    """
    Generate multiple layout variants for comparison (D-05).
    
    Creates layouts using different optimization strategies:
    - **Balanced**: Balance capacity, earthwork, and access roads
    - **Density**: Maximize capacity per hectare
    - **Low Earthwork**: Minimize grading and cut/fill volumes
    - **Clustered**: Group assets tightly to minimize infrastructure
    
    Returns all variants with a comparison table showing which is best for each metric.
    """
    # Load site with ownership check
    site_result = await db.execute(
        select(Site).where(
            Site.id == request.site_id,
            Site.owner_id == current_user.id,
        )
    )
    site = site_result.scalar_one_or_none()
    
    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site not found",
        )
    
    # Get site boundary as WKT for Shapely
    boundary_wkt_result = await db.execute(
        select(Site.boundary.ST_AsText()).where(Site.id == site.id)
    )
    boundary_wkt = boundary_wkt_result.scalar()
    
    if not boundary_wkt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Site has no boundary geometry",
        )
    
    # Parse boundary with Shapely
    try:
        boundary = wkt.loads(boundary_wkt)
    except Exception as e:
        logger.error(f"Failed to parse site boundary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to parse site boundary",
        )
    
    # Determine which strategies to use
    strategies = request.variant_strategies or [
        LayoutStrategy.BALANCED,
        LayoutStrategy.DENSITY,
        LayoutStrategy.LOW_EARTHWORK,
        LayoutStrategy.CLUSTERED,
    ]
    
    num_assets = random_asset_count(request.target_capacity_kw)
    
    # Generate variants
    variants: list[LayoutVariantResponse] = []
    metrics: list[LayoutVariantMetrics] = []
    
    for strategy in strategies:
        try:
            variant_result = await _generate_variant(
                site=site,
                boundary=boundary,
                target_capacity_kw=request.target_capacity_kw,
                dem_resolution_m=request.dem_resolution_m,
                num_assets=num_assets,
                strategy=strategy,
                db=db,
            )
            variants.append(variant_result["variant"])
            metrics.append(variant_result["metrics"])
        except Exception as e:
            logger.error(f"Failed to generate {strategy} variant: {e}")
            # Continue with other variants
    
    if not variants:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate any layout variants",
        )
    
    # Build comparison
    comparison = _build_variant_comparison(metrics)
    
    logger.info(f"Generated {len(variants)} layout variants for site {site.id}")
    
    return LayoutVariantsResponse(
        site_id=site.id,
        variants=variants,
        comparison=comparison,
    )


async def _generate_variant(
    site: Site,
    boundary,
    target_capacity_kw: float,
    dem_resolution_m: int,
    num_assets: int,
    strategy: LayoutStrategy,
    db: AsyncSession,
) -> dict:
    """
    Generate a single variant with a specific strategy (D-05).
    
    Phase E: Enhanced with terrain analysis for suitability scoring.
    
    Returns both the variant response and metrics for comparison.
    """
    # Map schema strategy to generator strategy
    strategy_mapping = {
        LayoutStrategy.BALANCED: GeneratorStrategy.BALANCED,
        LayoutStrategy.DENSITY: GeneratorStrategy.DENSITY,
        LayoutStrategy.LOW_EARTHWORK: GeneratorStrategy.LOW_EARTHWORK,
        LayoutStrategy.CLUSTERED: GeneratorStrategy.CLUSTERED,
    }
    generator_strategy = strategy_mapping.get(strategy, GeneratorStrategy.BALANCED)
    
    strategy_names = {
        LayoutStrategy.BALANCED: "Balanced",
        LayoutStrategy.DENSITY: "High Density",
        LayoutStrategy.LOW_EARTHWORK: "Low Earthwork",
        LayoutStrategy.CLUSTERED: "Clustered",
    }
    
    dem_service = get_dem_service()
    slope_service = get_slope_service()
    terrain_analysis = get_terrain_analysis_service()
    
    # Fetch DEM
    dem_s3_key = await dem_service.get_dem_for_site(
        site_id=site.id,
        boundary=boundary,
        db=db,
        resolution_m=dem_resolution_m,
    )
    
    if not dem_s3_key:
        raise Exception("DEM unavailable for site")
    
    # Compute slope
    slope_s3_key = await slope_service.get_slope_for_site(
        site_id=site.id,
        dem_s3_key=dem_s3_key,
        db=db,
    )
    
    if not slope_s3_key:
        raise Exception("Slope computation failed")
    
    # Load raster data
    dem_array, dem_profile = await dem_service.get_dem_array(dem_s3_key)
    slope_array, slope_profile = await slope_service.get_slope_array(slope_s3_key)
    
    # Phase E: Compute enhanced terrain metrics
    transform = dem_profile["transform"]
    crs = dem_profile.get("crs", "EPSG:4326")
    
    terrain_metrics = terrain_analysis.analyze_terrain(
        dem_array=dem_array,
        transform=transform,
        crs=str(crs),
        apply_smoothing=True,
    )
    
    # Create boundary mask for suitability scoring
    from rasterio.features import rasterize
    boundary_mask = rasterize(
        [(boundary, 1)],
        out_shape=dem_array.shape,
        transform=transform,
        fill=0,
        dtype='uint8',
    ).astype(bool)
    
    # Compute suitability scores for each asset type
    suitability_scores = {}
    for asset_type in ["solar_array", "battery", "generator", "substation"]:
        suitability_scores[asset_type] = terrain_analysis.compute_suitability_score(
            metrics=terrain_metrics,
            boundary_mask=boundary_mask,
            asset_type=asset_type,
        )
    
    # Fetch exclusion zones
    exclusion_zones = await _fetch_exclusion_zones(site.id, db)
    
    # Generate layout with strategy and enhanced terrain data
    generator = TerrainAwareLayoutGenerator(
        target_capacity_kw=target_capacity_kw,
        strategy=generator_strategy,
    )
    
    placed_assets, placed_roads, cut_fill = generator.generate(
        boundary=boundary,
        dem_array=dem_array,
        slope_array=slope_array,
        transform=transform,
        num_assets=num_assets,
        exclusion_zones=exclusion_zones,
        aspect_array=terrain_metrics.aspect_deg,
        suitability_scores=suitability_scores,
    )
    
    # Create Layout record
    layout = Layout(
        site_id=site.id,
        status=LayoutStatus.COMPLETED.value,
        terrain_processed=True,
        cut_volume_m3=cut_fill.cut_volume_m3,
        fill_volume_m3=cut_fill.fill_volume_m3,
    )
    db.add(layout)
    await db.flush()
    
    # Build per-asset cut/fill lookup
    per_asset_cutfill: dict[str, dict[str, float]] = {}
    for item in cut_fill.per_asset:
        per_asset_cutfill[item["asset_name"]] = {
            "cut_m3": item.get("cut_m3", 0),
            "fill_m3": item.get("fill_m3", 0),
        }
    
    # Create Asset records
    total_capacity = 0.0
    asset_responses = []
    
    for placed in placed_assets:
        asset = Asset(
            layout_id=layout.id,
            asset_type=placed.asset_type,
            name=placed.name,
            position=ST_SetSRID(
                ST_GeomFromText(placed.position.wkt),
                4326
            ),
            capacity_kw=placed.capacity_kw,
            elevation_m=placed.elevation_m,
            slope_deg=placed.slope_deg,
            footprint_length_m=placed.footprint_length_m,
            footprint_width_m=placed.footprint_width_m,
        )
        db.add(asset)
        await db.flush()
        
        total_capacity += placed.capacity_kw or 0
        asset_cutfill = per_asset_cutfill.get(placed.name, {})
        
        asset_responses.append(AssetResponse(
            id=asset.id,
            asset_type=asset.asset_type,
            name=asset.name,
            capacity_kw=asset.capacity_kw,
            elevation_m=asset.elevation_m,
            slope_deg=asset.slope_deg,
            position=mapping(placed.position),
            footprint_length_m=placed.footprint_length_m,
            footprint_width_m=placed.footprint_width_m,
            cut_m3=asset_cutfill.get("cut_m3"),
            fill_m3=asset_cutfill.get("fill_m3"),
            # Phase E: Enhanced terrain metrics
            aspect_deg=placed.aspect_deg if placed.aspect_deg >= 0 else None,
            suitability_score=placed.suitability_score,
            rotation_deg=placed.rotation_deg,
        ))
    
    # Create Road records
    road_responses = []
    total_road_length = 0.0
    
    for placed in placed_roads:
        road = Road(
            layout_id=layout.id,
            name=placed.name,
            geometry=ST_SetSRID(
                ST_GeomFromText(placed.geometry.wkt),
                4326
            ),
            length_m=placed.length_m,
            width_m=placed.width_m,
            max_grade_pct=placed.max_grade_pct,
        )
        db.add(road)
        await db.flush()
        
        total_road_length += placed.length_m or 0
        
        road_responses.append(RoadResponse(
            id=road.id,
            name=road.name,
            length_m=road.length_m,
            max_grade_pct=road.max_grade_pct,
            geometry=mapping(placed.geometry),
        ))
    
    # Update layout with totals
    layout.total_capacity_kw = round(total_capacity, 1)
    await db.commit()
    await db.refresh(layout)
    
    # Generate GeoJSON
    geojson = TerrainAwareLayoutGenerator.to_geojson_feature_collection(
        placed_assets,
        placed_roads,
        cut_fill,
    )
    
    # Calculate capacity per hectare
    site_area_ha = (site.area_m2 or 0) / 10000
    capacity_per_ha = total_capacity / site_area_ha if site_area_ha > 0 else None
    
    # Build variant response
    variant = LayoutVariantResponse(
        strategy=strategy,
        strategy_name=strategy_names.get(strategy, strategy.value),
        layout=LayoutResponse(
            id=layout.id,
            site_id=layout.site_id,
            status=layout.status,
            total_capacity_kw=layout.total_capacity_kw,
            cut_volume_m3=layout.cut_volume_m3,
            fill_volume_m3=layout.fill_volume_m3,
            error_message=layout.error_message,
            created_at=layout.created_at,
            updated_at=layout.updated_at,
        ),
        assets=asset_responses,
        roads=road_responses,
        geojson=geojson,
    )
    
    # Build metrics
    metrics = LayoutVariantMetrics(
        layout_id=layout.id,
        strategy=strategy,
        strategy_name=strategy_names.get(strategy, strategy.value),
        total_capacity_kw=total_capacity,
        asset_count=len(asset_responses),
        road_length_m=total_road_length,
        cut_volume_m3=cut_fill.cut_volume_m3,
        fill_volume_m3=cut_fill.fill_volume_m3,
        net_earthwork_m3=cut_fill.cut_volume_m3 - cut_fill.fill_volume_m3,
        capacity_per_hectare=capacity_per_ha,
    )
    
    return {"variant": variant, "metrics": metrics}


def _build_variant_comparison(metrics: list[LayoutVariantMetrics]) -> VariantComparison:
    """
    Build comparison analysis across variants (D-05).
    
    Identifies best variant for each metric category.
    """
    if not metrics:
        raise ValueError("No metrics to compare")
    
    # Find best for each category
    best_capacity = max(metrics, key=lambda m: m.total_capacity_kw)
    best_earthwork = min(metrics, key=lambda m: abs(m.net_earthwork_m3))
    best_roads = min(metrics, key=lambda m: m.road_length_m)
    
    return VariantComparison(
        best_capacity_id=best_capacity.layout_id,
        best_earthwork_id=best_earthwork.layout_id,
        best_road_network_id=best_roads.layout_id,
        metrics_table=metrics,
    )


# =============================================================================
# Phase C (C-03): Async Job Enqueueing
# =============================================================================


async def _fetch_exclusion_zones(site_id: UUID, db: AsyncSession) -> list:
    """
    Fetch exclusion zones for a site as Shapely polygons.
    
    D-03: Retrieves all exclusion zones and converts them to polygons
    with their buffers applied.
    
    Args:
        site_id: UUID of the site
        db: Database session
        
    Returns:
        List of Shapely Polygon objects with buffers applied
    """
    from shapely.ops import unary_union
    
    result = await db.execute(
        select(ExclusionZone).where(ExclusionZone.site_id == site_id)
    )
    zones = result.scalars().all()
    
    if not zones:
        return []
    
    exclusion_polygons = []
    
    for zone in zones:
        # Get geometry as GeoJSON
        geom_result = await db.execute(
            select(ST_AsGeoJSON(ExclusionZone.geometry))
            .where(ExclusionZone.id == zone.id)
        )
        geom_json = geom_result.scalar()
        
        if geom_json:
            try:
                geom_dict = json.loads(geom_json)
                polygon = shape(geom_dict)
                
                # Apply buffer if specified
                if zone.buffer_m and zone.buffer_m > 0:
                    # Buffer in degrees (approximate: 1 degree ≈ 111km at equator)
                    buffer_deg = zone.buffer_m / 111000
                    polygon = polygon.buffer(buffer_deg)
                
                if polygon.is_valid and not polygon.is_empty:
                    exclusion_polygons.append(polygon)
            except Exception as e:
                logger.warning(f"Could not parse exclusion zone {zone.id}: {e}")
    
    return exclusion_polygons


async def _enqueue_layout_job(
    request: GenerateLayoutRequest,
    site: Site,
    db: AsyncSession,
) -> LayoutEnqueueResponse:
    """
    Create layout record and enqueue job to SQS (C-03).
    
    Returns immediately with layout_id. Processing happens in worker.
    """
    # Create Layout record with status='queued'
    layout = Layout(
        site_id=site.id,
        status=LayoutStatus.QUEUED.value,
    )
    db.add(layout)
    await db.flush()  # Get the ID
    await db.commit()
    
    # Enqueue job to SQS
    sqs_service = get_sqs_service()
    success = await sqs_service.send_layout_job(
        layout_id=layout.id,
        site_id=site.id,
        target_capacity_kw=request.target_capacity_kw,
        dem_resolution_m=request.dem_resolution_m,
    )
    
    if not success:
        # If SQS fails, mark layout as failed
        layout.status = LayoutStatus.FAILED.value
        layout.error_message = "Failed to enqueue layout generation job"
        await db.commit()
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue layout generation job",
        )
    
    logger.info(f"Enqueued layout job: layout_id={layout.id}")
    
    return LayoutEnqueueResponse(
        layout_id=layout.id,
        status=LayoutStatus.QUEUED.value,
    )


async def _generate_terrain_aware_layout(
    layout: Layout,
    site: Site,
    boundary,
    target_capacity_kw: float,
    dem_resolution_m: int,
    num_assets: int,
    db: AsyncSession,
) -> LayoutGenerateResponse:
    """Generate layout using terrain-aware placement (Phase B, enhanced Phase E)."""
    
    dem_service = get_dem_service()
    slope_service = get_slope_service()
    terrain_analysis = get_terrain_analysis_service()
    
    try:
        # Step 1: Fetch DEM
        logger.info(f"Fetching DEM for site {site.id} at {dem_resolution_m}m resolution")
        dem_s3_key = await dem_service.get_dem_for_site(
            site_id=site.id,
            boundary=boundary,
            db=db,
            resolution_m=dem_resolution_m,
        )
        
        if not dem_s3_key:
            # Fall back to dummy placement if DEM unavailable
            logger.warning(f"DEM unavailable for site {site.id}, falling back to dummy placement")
            return await _generate_dummy_layout(
                layout=layout,
                boundary=boundary,
                target_capacity_kw=target_capacity_kw,
                num_assets=num_assets,
                db=db,
            )
        
        # Step 2: Compute slope
        logger.info(f"Computing slope for site {site.id}")
        slope_s3_key = await slope_service.get_slope_for_site(
            site_id=site.id,
            dem_s3_key=dem_s3_key,
            db=db,
        )
        
        if not slope_s3_key:
            logger.warning(f"Slope computation failed for site {site.id}, falling back to dummy")
            return await _generate_dummy_layout(
                layout=layout,
                boundary=boundary,
                target_capacity_kw=target_capacity_kw,
                num_assets=num_assets,
                db=db,
            )
        
        # Step 3: Load raster data
        dem_array, dem_profile = await dem_service.get_dem_array(dem_s3_key)
        slope_array, slope_profile = await slope_service.get_slope_array(slope_s3_key)
        
        # Phase E: Compute enhanced terrain metrics
        transform = dem_profile["transform"]
        crs = dem_profile.get("crs", "EPSG:4326")
        
        logger.info(f"Computing enhanced terrain analysis for site {site.id}")
        terrain_metrics = terrain_analysis.analyze_terrain(
            dem_array=dem_array,
            transform=transform,
            crs=str(crs),
            apply_smoothing=True,
        )
        
        # Create boundary mask for suitability scoring
        from rasterio.features import rasterize
        boundary_mask = rasterize(
            [(boundary, 1)],
            out_shape=dem_array.shape,
            transform=transform,
            fill=0,
            dtype='uint8',
        ).astype(bool)
        
        # Compute suitability scores for each asset type
        suitability_scores = {}
        for asset_type in ["solar_array", "battery", "generator", "substation"]:
            suitability_scores[asset_type] = terrain_analysis.compute_suitability_score(
                metrics=terrain_metrics,
                boundary_mask=boundary_mask,
                asset_type=asset_type,
            )
        
        # D-03: Fetch exclusion zones for this site
        exclusion_zones = await _fetch_exclusion_zones(site.id, db)
        if exclusion_zones:
            logger.info(f"Found {len(exclusion_zones)} exclusion zones for site {site.id}")
        
        # Step 4: Generate terrain-aware layout with enhanced metrics
        logger.info(f"Generating terrain-aware layout for site {site.id}")
        generator = TerrainAwareLayoutGenerator(target_capacity_kw=target_capacity_kw)
        
        placed_assets, placed_roads, cut_fill = generator.generate(
            boundary=boundary,
            dem_array=dem_array,
            slope_array=slope_array,
            transform=transform,
            num_assets=num_assets,
            exclusion_zones=exclusion_zones,
            aspect_array=terrain_metrics.aspect_deg,
            suitability_scores=suitability_scores,
        )
        
        # Update layout with terrain flag and cut/fill
        layout.terrain_processed = True
        layout.cut_volume_m3 = cut_fill.cut_volume_m3
        layout.fill_volume_m3 = cut_fill.fill_volume_m3
        layout.status = LayoutStatus.COMPLETED.value
        
        # D-02: Build per-asset cut/fill lookup from CutFillResult
        per_asset_cutfill: dict[str, dict[str, float]] = {}
        for item in cut_fill.per_asset:
            per_asset_cutfill[item["asset_name"]] = {
                "cut_m3": item.get("cut_m3", 0),
                "fill_m3": item.get("fill_m3", 0),
            }
        
        # Create Asset records with terrain data
        total_capacity = 0.0
        asset_responses = []
        
        for placed in placed_assets:
            asset = Asset(
                layout_id=layout.id,
                asset_type=placed.asset_type,
                name=placed.name,
                position=ST_SetSRID(
                    ST_GeomFromText(placed.position.wkt),
                    4326
                ),
                capacity_kw=placed.capacity_kw,
                elevation_m=placed.elevation_m,
                slope_deg=placed.slope_deg,
                footprint_length_m=placed.footprint_length_m,
                footprint_width_m=placed.footprint_width_m,
            )
            db.add(asset)
            await db.flush()
            
            total_capacity += placed.capacity_kw or 0
            
            # D-02: Get per-asset cut/fill from lookup
            asset_cutfill = per_asset_cutfill.get(placed.name, {})
            
            asset_responses.append(AssetResponse(
                id=asset.id,
                asset_type=asset.asset_type,
                name=asset.name,
                capacity_kw=asset.capacity_kw,
                elevation_m=asset.elevation_m,
                slope_deg=asset.slope_deg,
                position=mapping(placed.position),
                footprint_length_m=placed.footprint_length_m,
                footprint_width_m=placed.footprint_width_m,
                cut_m3=asset_cutfill.get("cut_m3"),
                fill_m3=asset_cutfill.get("fill_m3"),
                # Phase E: Enhanced terrain metrics
                aspect_deg=placed.aspect_deg if placed.aspect_deg >= 0 else None,
                suitability_score=placed.suitability_score,
                rotation_deg=placed.rotation_deg,
            ))
        
        # Create Road records with grade data
        road_responses = []
        total_road_length = 0.0
        
        for placed in placed_roads:
            road = Road(
                layout_id=layout.id,
                name=placed.name,
                geometry=ST_SetSRID(
                    ST_GeomFromText(placed.geometry.wkt),
                    4326
                ),
                length_m=placed.length_m,
                width_m=placed.width_m,
                max_grade_pct=placed.max_grade_pct,
            )
            db.add(road)
            await db.flush()
            
            total_road_length += placed.length_m or 0
            
            road_responses.append(RoadResponse(
                id=road.id,
                name=road.name,
                length_m=road.length_m,
                max_grade_pct=road.max_grade_pct,
                geometry=mapping(placed.geometry),
            ))
        
        # Update layout with totals
        layout.total_capacity_kw = round(total_capacity, 1)
        
        await db.commit()
        
        # Refresh layout to get server-generated timestamps (created_at, updated_at)
        await db.refresh(layout)
        
        # Generate GeoJSON
        geojson = TerrainAwareLayoutGenerator.to_geojson_feature_collection(
            placed_assets,
            placed_roads,
            cut_fill,
        )
        
        logger.info(
            f"Generated terrain-aware layout {layout.id} for site {site.id}: "
            f"{len(asset_responses)} assets, {len(road_responses)} roads, "
            f"{total_capacity:.1f} kW, cut={cut_fill.cut_volume_m3:.0f}m³, "
            f"fill={cut_fill.fill_volume_m3:.0f}m³"
        )
        
        return LayoutGenerateResponse(
            layout=LayoutResponse(
                id=layout.id,
                site_id=layout.site_id,
                status=layout.status,
                total_capacity_kw=layout.total_capacity_kw,
                cut_volume_m3=layout.cut_volume_m3,
                fill_volume_m3=layout.fill_volume_m3,
                error_message=layout.error_message,
                created_at=layout.created_at,
                updated_at=layout.updated_at,
            ),
            assets=asset_responses,
            roads=road_responses,
            geojson=geojson,
        )
        
    except Exception as e:
        logger.exception(f"Terrain-aware layout generation failed: {e}")
        layout.status = LayoutStatus.FAILED.value
        layout.error_message = str(e)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Layout generation failed: {e}",
        )


async def _generate_dummy_layout(
    layout: Layout,
    boundary,
    target_capacity_kw: float,
    num_assets: int,
    db: AsyncSession,
) -> LayoutGenerateResponse:
    """Generate layout using dummy placement (Phase A fallback)."""
    
    generator = DummyLayoutGenerator(target_capacity_kw=target_capacity_kw)
    
    try:
        placed_assets, placed_roads = generator.generate(
            boundary=boundary,
            num_assets=num_assets,
        )
    except Exception as e:
        logger.exception(f"Dummy layout generation failed: {e}")
        layout.status = LayoutStatus.FAILED.value
        layout.error_message = str(e)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Layout generation failed: {e}",
        )
    
    layout.status = LayoutStatus.COMPLETED.value
    layout.terrain_processed = False
    
    # Create Asset records
    total_capacity = 0.0
    asset_responses = []
    
    for placed in placed_assets:
        asset = Asset(
            layout_id=layout.id,
            asset_type=placed.asset_type,
            name=placed.name,
            position=ST_SetSRID(
                ST_GeomFromText(placed.position.wkt),
                4326
            ),
            capacity_kw=placed.capacity_kw,
            footprint_length_m=placed.footprint_length_m,
            footprint_width_m=placed.footprint_width_m,
        )
        db.add(asset)
        await db.flush()
        
        total_capacity += placed.capacity_kw or 0
        
        asset_responses.append(AssetResponse(
            id=asset.id,
            asset_type=asset.asset_type,
            name=asset.name,
            capacity_kw=asset.capacity_kw,
            position=mapping(placed.position),
        ))
    
    # Create Road records
    road_responses = []
    total_road_length = 0.0
    
    for placed in placed_roads:
        road = Road(
            layout_id=layout.id,
            name=placed.name,
            geometry=ST_SetSRID(
                ST_GeomFromText(placed.geometry.wkt),
                4326
            ),
            length_m=placed.length_m,
            width_m=placed.width_m,
        )
        db.add(road)
        await db.flush()
        
        total_road_length += placed.length_m or 0
        
        road_responses.append(RoadResponse(
            id=road.id,
            name=road.name,
            length_m=road.length_m,
            geometry=mapping(placed.geometry),
        ))
    
    # Update layout with totals
    layout.total_capacity_kw = round(total_capacity, 1)
    
    await db.commit()
    
    # Refresh layout to get server-generated timestamps (created_at, updated_at)
    await db.refresh(layout)
    
    # Generate GeoJSON
    geojson = DummyLayoutGenerator.to_geojson_feature_collection(
        placed_assets,
        placed_roads,
    )
    
    logger.info(
        f"Generated dummy layout {layout.id}: "
        f"{len(asset_responses)} assets, {len(road_responses)} roads, "
        f"{total_capacity:.1f} kW total capacity"
    )
    
    return LayoutGenerateResponse(
        layout=LayoutResponse(
            id=layout.id,
            site_id=layout.site_id,
            status=layout.status,
            total_capacity_kw=layout.total_capacity_kw,
            cut_volume_m3=layout.cut_volume_m3,
            fill_volume_m3=layout.fill_volume_m3,
            error_message=layout.error_message,
            created_at=layout.created_at,
            updated_at=layout.updated_at,
        ),
        assets=asset_responses,
        roads=road_responses,
        geojson=geojson,
    )


@router.get(
    "/{layout_id}",
    response_model=LayoutDetailResponse,
    summary="Get layout details",
    description="Retrieve layout details including assets and roads.",
)
async def get_layout(
    layout_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LayoutDetailResponse:
    """
    Get layout details by ID.
    
    Returns 404 if the layout doesn't exist or belongs to another user.
    """
    # Query layout with ownership check through site
    result = await db.execute(
        select(Layout)
        .options(selectinload(Layout.assets), selectinload(Layout.roads))
        .join(Site, Layout.site_id == Site.id)
        .where(
            Layout.id == layout_id,
            Site.owner_id == current_user.id,
        )
    )
    layout = result.scalar_one_or_none()
    
    if not layout:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Layout not found",
        )
    
    # Build asset responses with GeoJSON positions
    asset_responses = []
    for asset in layout.assets:
        # Get position as GeoJSON
        pos_result = await db.execute(
            select(ST_AsGeoJSON(Asset.position)).where(Asset.id == asset.id)
        )
        position_geojson = json.loads(pos_result.scalar() or "{}")
        
        asset_responses.append(AssetResponse(
            id=asset.id,
            asset_type=asset.asset_type,
            name=asset.name,
            capacity_kw=asset.capacity_kw,
            position=position_geojson,
        ))
    
    # Build road responses with GeoJSON geometries
    road_responses = []
    for road in layout.roads:
        # Get geometry as GeoJSON
        geom_result = await db.execute(
            select(ST_AsGeoJSON(Road.geometry)).where(Road.id == road.id)
        )
        geometry_geojson = json.loads(geom_result.scalar() or "{}")
        
        road_responses.append(RoadResponse(
            id=road.id,
            name=road.name,
            length_m=road.length_m,
            geometry=geometry_geojson,
        ))
    
    return LayoutDetailResponse(
        id=layout.id,
        site_id=layout.site_id,
        status=layout.status,
        total_capacity_kw=layout.total_capacity_kw,
        cut_volume_m3=layout.cut_volume_m3,
        fill_volume_m3=layout.fill_volume_m3,
        error_message=layout.error_message,
        created_at=layout.created_at,
        updated_at=layout.updated_at,
        assets=asset_responses,
        roads=road_responses,
    )


@router.get(
    "",
    response_model=LayoutListResponse,
    summary="List layouts",
    description="List all layouts for the current user.",
)
async def list_layouts(
    site_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LayoutListResponse:
    """
    List layouts for the current user.
    
    Optionally filter by site_id.
    """
    try:
        query = (
            select(Layout)
            .join(Site, Layout.site_id == Site.id)
            .where(Site.owner_id == current_user.id)
            .order_by(Layout.created_at.desc())
        )
        
        if site_id:
            query = query.where(Layout.site_id == site_id)
        
        result = await db.execute(query)
        layouts = result.scalars().all()
        
        return LayoutListResponse(
            layouts=[
                {
                    "id": layout.id,
                    "site_id": layout.site_id,
                    "status": layout.status,
                    "total_capacity_kw": layout.total_capacity_kw,
                    "created_at": layout.created_at,
                }
                for layout in layouts
            ],
            total=len(layouts),
        )
    except Exception as e:
        logger.exception(f"Failed to list layouts for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error listing layouts: {str(e)}. Have migrations been run?",
        )


# =============================================================================
# Phase C: Async Layout Generation Endpoints
# =============================================================================


@router.get(
    "/{layout_id}/status",
    response_model=LayoutStatusResponse,
    summary="Get layout status (polling)",
    description="Poll for layout generation status. Used by frontend to track async jobs (C-04).",
)
async def get_layout_status(
    layout_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LayoutStatusResponse:
    """
    Get the current status of a layout generation job (C-04).
    
    Returns 404 if the layout doesn't exist or belongs to another user.
    
    Polling response includes:
    - status: queued, processing, completed, or failed
    - error_message: Details if status is 'failed'
    - Metrics (when status='completed'): capacity, asset_count, road_length, volumes
    
    Used by frontend for async job tracking - call every 2-3 seconds during processing.
    """
    # Query layout with ownership check through site
    result = await db.execute(
        select(Layout)
        .join(Site, Layout.site_id == Site.id)
        .where(
            Layout.id == layout_id,
            Site.owner_id == current_user.id,
        )
    )
    layout = result.scalar_one_or_none()
    
    if not layout:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Layout not found",
        )
    
    # If not completed, return minimal status
    if layout.status != LayoutStatus.COMPLETED.value:
        return LayoutStatusResponse(
            layout_id=layout.id,
            status=layout.status,
            error_message=layout.error_message if layout.status == LayoutStatus.FAILED.value else None,
        )
    
    # If completed, calculate additional metrics
    # Count assets
    asset_count_result = await db.execute(
        select(func.count(Asset.id)).where(Asset.layout_id == layout.id)
    )
    asset_count = asset_count_result.scalar() or 0
    
    # Sum road lengths
    road_length_result = await db.execute(
        select(func.sum(Road.length_m)).where(Road.layout_id == layout.id)
    )
    total_road_length = road_length_result.scalar() or 0.0
    
    return LayoutStatusResponse(
        layout_id=layout.id,
        status=layout.status,
        error_message=None,
        total_capacity_kw=layout.total_capacity_kw,
        asset_count=asset_count,
        road_length_m=total_road_length,
        cut_volume_m3=layout.cut_volume_m3,
        fill_volume_m3=layout.fill_volume_m3,
    )


@router.delete(
    "/{layout_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete layout",
    description="Delete a layout and all associated assets and roads.",
)
async def delete_layout(
    layout_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """
    Delete a layout by ID.
    """
    # Query layout with ownership check through site
    result = await db.execute(
        select(Layout)
        .join(Site, Layout.site_id == Site.id)
        .where(
            Layout.id == layout_id,
            Site.owner_id == current_user.id,
        )
    )
    layout = result.scalar_one_or_none()
    
    if not layout:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Layout not found",
        )
    
    # Delete layout (cascades to assets and roads)
    await db.delete(layout)
    await db.commit()
    
    logger.info(f"Deleted layout {layout_id}")


def random_asset_count(target_capacity_kw: float) -> int:
    """
    Determine number of assets based on target capacity.
    
    Roughly scales between 5-15 assets based on capacity.
    """
    import random
    
    base = 5
    if target_capacity_kw > 500:
        base += int((target_capacity_kw - 500) / 500)
    
    # Add some randomness
    return min(15, max(5, base + random.randint(-1, 2)))

