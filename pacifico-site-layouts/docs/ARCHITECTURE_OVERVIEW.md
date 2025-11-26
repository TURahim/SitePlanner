# Pacifico Site Layouts – Architecture Overview

> November 2025

## System Architecture

### High-Level Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                 FRONTEND                                     │
│                            (React + Vite + Leaflet)                         │
│  ┌──────────┐ ┌──────────┐ ┌─────────────┐ ┌─────────────────────────────┐  │
│  │ Landing  │ │ Projects │ │ SiteDetail  │ │ Components:                  │  │
│  │ Page     │ │ Page     │ │ Page        │ │ - Layout, LayoutVariants    │  │
│  │          │ │          │ │ + Map View  │ │ - ExclusionZonePanel        │  │
│  │          │ │          │ │ + Sidebar   │ │ - AssetIcons                │  │
│  └──────────┘ └──────────┘ └─────────────┘ └─────────────────────────────┘  │
│                              │                                               │
│                              ▼                                               │
│                     API Calls (lib/api.ts)                                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                                 BACKEND                                      │
│                          (FastAPI + SQLAlchemy + PostGIS)                   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                           API LAYER                                  │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │    │
│  │  │ auth.py  │ │ sites.py │ │layouts.py│ │exports.py│ │terrain.py│  │    │
│  │  │          │ │          │ │          │ │          │ │          │  │    │
│  │  │ Cognito  │ │ CRUD     │ │ Generate │ │ GeoJSON  │ │ Contours │  │    │
│  │  │ JWT      │ │ Sites    │ │ Variants │ │ KMZ/PDF  │ │ Heatmaps │  │    │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘  │    │
│  │               ┌────────────────────┐                               │    │
│  │               │ exclusion_zones.py │                               │    │
│  │               │ CRUD zones         │                               │    │
│  │               └────────────────────┘                               │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                              │                                               │
│                              ▼                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                        SERVICE LAYER                                 │    │
│  │  ┌───────────────────┐  ┌───────────────────┐  ┌─────────────────┐  │    │
│  │  │ dem_service.py    │  │terrain_layout_    │  │ export_service  │  │    │
│  │  │ - USGS 3DEP fetch │  │generator.py       │  │ .py             │  │    │
│  │  │ - S3 caching      │  │ - Asset placement │  │ - GeoJSON       │  │    │
│  │  └───────────────────┘  │ - Road generation │  │ - KMZ           │  │    │
│  │  ┌───────────────────┐  │ - Cut/fill calc   │  │ - PDF report    │  │    │
│  │  │ slope_service.py  │  └───────────────────┘  │ - CSV           │  │    │
│  │  │ - Slope rasters   │  ┌───────────────────┐  └─────────────────┘  │    │
│  │  │ - Cache management│  │terrain_analysis_  │  ┌─────────────────┐  │    │
│  │  └───────────────────┘  │service.py         │  │ kml_parser.py   │  │    │
│  │  ┌───────────────────┐  │ - Curvature       │  │ - KML/KMZ parse │  │    │
│  │  │terrain_viz_svc.py │  │ - Aspect          │  │ - Boundary      │  │    │
│  │  │ - Contours        │  │ - Suitability     │  │   extraction    │  │    │
│  │  │ - Buildable area  │  └───────────────────┘  └─────────────────┘  │    │
│  │  └───────────────────┘                                              │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                              │                                               │
│                              ▼                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         MODEL LAYER                                  │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐ │    │
│  │  │ user.py  │ │ site.py  │ │layout.py │ │ asset.py │ │ road.py   │ │    │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └───────────┘ │    │
│  │  ┌────────────────────┐  ┌─────────────────┐                       │    │
│  │  │ exclusion_zone.py  │  │terrain_cache.py │                       │    │
│  │  └────────────────────┘  └─────────────────┘                       │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              INFRASTRUCTURE                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │  PostgreSQL  │  │     S3       │  │     SQS      │  │   Cognito    │    │
│  │  + PostGIS   │  │  DEM Cache   │  │  Job Queue   │  │    Auth      │    │
│  │              │  │  Exports     │  │  (async)     │  │              │    │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
pacifico-site-layouts/
├── backend/
│   ├── app/
│   │   ├── api/               # FastAPI routers
│   │   │   ├── auth.py        # JWT authentication via Cognito
│   │   │   ├── sites.py       # Site CRUD + boundary upload
│   │   │   ├── layouts.py     # Layout generation + variants
│   │   │   ├── exports.py     # Export endpoints (GeoJSON/KMZ/PDF/CSV)
│   │   │   ├── terrain.py     # Terrain visualization endpoints
│   │   │   └── exclusion_zones.py  # Exclusion zone CRUD
│   │   ├── models/            # SQLAlchemy models (PostGIS)
│   │   │   ├── user.py        # User model (Cognito sub)
│   │   │   ├── site.py        # Site with boundary geometry
│   │   │   ├── layout.py      # Layout with status, earthwork
│   │   │   ├── asset.py       # Placed assets with terrain info
│   │   │   ├── road.py        # Road segments with grade
│   │   │   ├── exclusion_zone.py   # Constraint zones
│   │   │   └── terrain_cache.py    # DEM/slope cache metadata
│   │   ├── schemas/           # Pydantic request/response schemas
│   │   ├── services/          # Business logic
│   │   │   ├── dem_service.py           # DEM acquisition (py3dep)
│   │   │   ├── slope_service.py         # Slope computation
│   │   │   ├── terrain_analysis_service.py  # Curvature, suitability
│   │   │   ├── terrain_visualization_service.py  # Contours, heatmaps
│   │   │   ├── terrain_layout_generator.py  # Core placement algorithm
│   │   │   ├── layout_generator.py      # Dummy placement (fallback)
│   │   │   ├── export_service.py        # Export generation
│   │   │   ├── kml_parser.py            # KML/KMZ parsing
│   │   │   ├── s3.py                    # S3 operations
│   │   │   └── sqs_service.py           # SQS job queuing
│   │   ├── config.py          # Environment configuration
│   │   ├── database.py        # Async SQLAlchemy setup
│   │   ├── main.py            # FastAPI app entry point
│   │   └── worker.py          # SQS worker for async jobs
│   ├── alembic/               # Database migrations
│   ├── tests/                 # Unit and integration tests
│   └── requirements.txt       # Python dependencies
│
├── frontend/
│   ├── src/
│   │   ├── components/        # React components
│   │   │   ├── Layout.tsx     # Layout wrapper
│   │   │   ├── LayoutVariants.tsx  # Variant comparison UI
│   │   │   ├── ExclusionZonePanel.tsx  # Zone drawing/editing
│   │   │   ├── AssetIcons.tsx # SVG asset icons
│   │   │   └── ProtectedRoute.tsx  # Auth guard
│   │   ├── pages/             # Page components
│   │   │   ├── LandingPage.tsx
│   │   │   ├── ProjectsPage.tsx
│   │   │   ├── SiteDetailPage.tsx  # Main map view
│   │   │   ├── LoginPage.tsx
│   │   │   └── SignupPage.tsx
│   │   ├── hooks/             # Custom React hooks
│   │   │   └── useLayoutPolling.ts  # Async status polling
│   │   ├── contexts/          # React contexts
│   │   │   └── AuthContext.tsx     # Auth state
│   │   ├── lib/               # Utilities
│   │   │   ├── api.ts         # API client functions
│   │   │   ├── amplify.ts     # AWS Amplify config
│   │   │   ├── config.ts      # Frontend config
│   │   │   └── mapUtils.ts    # Leaflet utilities
│   │   └── types/             # TypeScript types
│   │       └── index.ts
│   └── package.json
│
├── infra/
│   └── terraform/             # AWS infrastructure as code
│
└── docs/
    ├── ARCHITECTURE_OVERVIEW.md      # This file
    ├── LAYOUT_GENERATION_EXPLAINED.md  # Algorithm details
    └── ...
```

---

## Data Flow

### Layout Generation (Sync)

```
1. User clicks "Generate Layout" in SiteDetailPage
                │
                ▼
2. POST /api/layouts/generate { site_id, target_capacity_kw }
                │
                ▼
3. Backend validates ownership, fetches boundary
                │
                ▼
4. DEMService.get_dem_for_site()
   └─→ Check TerrainCache → S3 → py3dep → USGS 3DEP
                │
                ▼
5. SlopeService.get_slope_for_site()
   └─→ Compute from DEM, cache result
                │
                ▼
6. TerrainAnalysisService.analyze_terrain()
   └─→ Aspect, curvature, suitability scores
                │
                ▼
7. _fetch_exclusion_zones()
   └─→ Get constraints from DB
                │
                ▼
8. TerrainAwareLayoutGenerator.generate()
   ├─→ _place_assets_terrain_aware()
   ├─→ _generate_roads_terrain_aware()
   └─→ _compute_cut_fill()
                │
                ▼
9. Persist Layout, Asset, Road records
                │
                ▼
10. Return LayoutGenerateResponse with GeoJSON
                │
                ▼
11. Frontend renders on Leaflet map
```

### Layout Generation (Async)

```
1. POST /api/layouts/generate (ENABLE_ASYNC_LAYOUT_GENERATION=true)
                │
                ▼
2. Create Layout record with status='queued'
                │
                ▼
3. Enqueue to SQS via sqs_service.send_layout_job()
                │
                ▼
4. Return LayoutEnqueueResponse { layout_id, status: 'queued' }
                │
                ▼
5. Frontend starts polling GET /api/layouts/{id}/status
                │
   ┌────────────┴────────────┐
   │      SQS Worker         │
   │   (worker.py)           │
   │                         │
   │ 6. Receive message      │
   │ 7. Run generation       │
   │ 8. Update Layout status │
   │    to 'completed'       │
   └─────────────────────────┘
                │
                ▼
9. Poll returns status='completed', frontend fetches full layout
```

---

## Key Technologies

| Component | Technology | Purpose |
|-----------|------------|---------|
| Backend Framework | FastAPI | Async API with OpenAPI docs |
| Database | PostgreSQL + PostGIS | Spatial queries, geometry storage |
| ORM | SQLAlchemy 2.0 | Async database access |
| DEM Data | py3dep / USGS 3DEP | Open elevation data |
| Spatial Processing | Shapely, rasterio, numpy | Geometry ops, raster analysis |
| Pathfinding | Custom A* | Slope-weighted road routing |
| Frontend Framework | React 18 + TypeScript | UI components |
| Build Tool | Vite | Fast development server |
| Maps | Leaflet + react-leaflet | Interactive map rendering |
| Drawing | leaflet-draw | Polygon drawing for zones |
| Auth | AWS Cognito + Amplify | User authentication |
| Object Storage | AWS S3 | DEM cache, exports |
| Job Queue | AWS SQS | Async layout generation |
| CDN | AWS CloudFront | Frontend hosting |
| IaC | Terraform | Infrastructure provisioning |

---

## Authentication Flow

```
1. User signs up/in via Cognito Hosted UI
                │
                ▼
2. Cognito returns JWT tokens (id, access, refresh)
                │
                ▼
3. Frontend stores tokens in localStorage (Amplify)
                │
                ▼
4. API calls include Authorization: Bearer <access_token>
                │
                ▼
5. Backend auth.py validates JWT, extracts Cognito sub
                │
                ▼
6. get_current_user() returns/creates User record
```

---

## Database Schema (Core Tables)

```sql
-- Users (Cognito integration)
users (id UUID, cognito_sub TEXT UNIQUE, email TEXT, ...)

-- Sites with PostGIS geometry
sites (id UUID, owner_id FK, name TEXT, boundary GEOMETRY(POLYGON), 
       entry_point GEOMETRY(POINT), area_m2 FLOAT, ...)

-- Layouts with status tracking
layouts (id UUID, site_id FK, status TEXT, total_capacity_kw FLOAT,
         cut_volume_m3 FLOAT, fill_volume_m3 FLOAT, ...)

-- Placed assets with terrain info
assets (id UUID, layout_id FK, asset_type TEXT, name TEXT,
        position GEOMETRY(POINT), capacity_kw FLOAT, elevation_m FLOAT,
        slope_deg FLOAT, footprint_length_m FLOAT, footprint_width_m FLOAT, ...)

-- Road segments with stationing
roads (id UUID, layout_id FK, name TEXT, geometry GEOMETRY(LINESTRING),
       length_m FLOAT, width_m FLOAT, max_grade_pct FLOAT, road_class TEXT, ...)

-- Exclusion zones (constraints)
exclusion_zones (id UUID, site_id FK, name TEXT, zone_type TEXT,
                 geometry GEOMETRY(POLYGON), buffer_m FLOAT, 
                 cost_multiplier FLOAT, ...)

-- Terrain cache for DEM/slope reuse
terrain_cache (id UUID, site_id FK, data_type TEXT, s3_key TEXT,
               resolution_m INT, expires_at TIMESTAMP, ...)
```

---

## Configuration Reference

### Backend Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `AWS_REGION` | Yes | AWS region for services |
| `AWS_S3_BUCKET_NAME` | Yes | S3 bucket for cache/exports |
| `COGNITO_USER_POOL_ID` | Yes | Cognito user pool ID |
| `COGNITO_CLIENT_ID` | Yes | Cognito app client ID |
| `USE_TERRAIN` | No | Enable terrain-aware (default: true) |
| `ENABLE_ASYNC_LAYOUT_GENERATION` | No | Use SQS worker (default: false) |
| `SQS_QUEUE_URL` | If async | SQS queue URL |

### Frontend Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `VITE_API_URL` | Yes | Backend API base URL |
| `VITE_COGNITO_USER_POOL_ID` | Yes | Cognito user pool ID |
| `VITE_COGNITO_CLIENT_ID` | Yes | Cognito app client ID |
| `VITE_COGNITO_DOMAIN` | Yes | Cognito hosted UI domain |

