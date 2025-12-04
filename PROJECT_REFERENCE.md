# PROJECT_REFERENCE.md — Pacifico Site Layouts

> **Quick-reference technical summary for onboarding engineers and AI agents.**  
> Last updated: December 3, 2025

---

## 1. Executive Summary

**Pacifico Site Layouts** is an AI-powered geospatial layout tool for DG/microgrid/data center site planning. It automates early-stage real estate due diligence by:

- **Importing** KML/KMZ site boundaries from Google Earth or GIS tools
- **Fetching** elevation data (DEM) from USGS 3DEP
- **Computing** slope, aspect, curvature, and suitability metrics
- **Auto-placing** infrastructure assets via generation profiles (solar arrays, gas turbines, batteries, generators, substations, wind turbines, cooling systems, control centers)
- **Generating** road networks with A* pathfinding on slope-weighted cost surfaces
- **Calculating** cut/fill volumes for earthwork estimation
- **Exporting** layouts as GeoJSON, KMZ, PDF reports, and CSV

**PRD Alignment:** P0 (must-have), P1 (should-have), and P2 (nice-to-have) features are **fully implemented**.

---

## 2. Tech Stack

| Layer | Technology |
|-------|------------|
| **Frontend** | React 19, TypeScript, Vite 7, Leaflet, react-leaflet, leaflet-draw |
| **Backend** | FastAPI, SQLAlchemy 2.0 (async), Python 3.11 |
| **Database** | PostgreSQL 15 + PostGIS 3.4 |
| **Auth** | AWS Cognito + Amplify SDK |
| **Infrastructure** | AWS (ECS Fargate, RDS, S3, CloudFront, SQS, ALB) |
| **IaC** | Terraform |
| **CI/CD** | GitHub Actions (OIDC auth to AWS) |
| **Terrain Data** | USGS 3DEP via py3dep library |
| **Geospatial** | Shapely, rasterio, numpy, scipy, scikit-image, pyproj |

---

## 3. Directory Structure

```
pacifico-site-layouts/
├── backend/
│   ├── app/
│   │   ├── api/                    # FastAPI route handlers
│   │   │   ├── auth.py             # Cognito JWT validation
│   │   │   ├── sites.py            # Site CRUD + KML upload
│   │   │   ├── layouts.py          # Layout generation + variants
│   │   │   ├── exports.py          # GeoJSON/KMZ/PDF/CSV exports
│   │   │   ├── terrain.py          # Terrain visualization endpoints
│   │   │   ├── exclusion_zones.py  # Exclusion zone CRUD
│   │   │   └── compliance.py       # Compliance rules + GIS integration
│   │   ├── models/                 # SQLAlchemy models (PostGIS)
│   │   │   ├── user.py, site.py, layout.py, asset.py, road.py
│   │   │   ├── exclusion_zone.py, terrain_cache.py
│   │   ├── schemas/                # Pydantic request/response schemas
│   │   ├── services/               # Business logic services
│   │   │   ├── dem_service.py      # DEM fetching (py3dep) + S3 caching
│   │   │   ├── slope_service.py    # Slope raster computation
│   │   │   ├── terrain_analysis_service.py    # Suitability scoring
│   │   │   ├── terrain_layout_generator.py    # Core placement algorithm
│   │   │   ├── generation_profiles.py         # Profile configs (solar, gas, wind, hybrid)
│   │   │   ├── terrain_visualization_service.py # Contours, heatmaps
│   │   │   ├── export_service.py   # Export file generation
│   │   │   ├── kml_parser.py       # KML/KMZ parsing (fastkml)
│   │   │   ├── regulatory_service.py          # Regulatory data providers
│   │   │   ├── compliance_rules_engine.py     # Jurisdiction-based rules
│   │   │   ├── gis_integration_service.py     # GIS provider abstraction
│   │   │   ├── s3.py, sqs_service.py          # AWS integrations
│   │   ├── config.py               # Environment configuration
│   │   ├── database.py             # Async SQLAlchemy setup
│   │   ├── main.py                 # FastAPI app entry point
│   │   └── worker.py               # SQS worker for async jobs
│   ├── alembic/                    # Database migrations
│   │   └── versions/               # 7 migration files (001–007)
│   ├── tests/                      # 22 unit tests
│   ├── requirements.txt            # Python dependencies
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.tsx                 # Main router
│   │   ├── components/             # Layout, LayoutVariants, ExclusionZonePanel, etc.
│   │   ├── pages/                  # LandingPage, LoginPage, SignupPage, ProjectsPage, SiteDetailPage
│   │   ├── hooks/useLayoutPolling.ts
│   │   ├── contexts/AuthContext.tsx
│   │   ├── lib/                    # api.ts, amplify.ts, config.ts, mapUtils.ts
│   │   └── types/index.ts          # TypeScript interfaces (50+ types)
│   ├── package.json
│   └── vite.config.ts
├── infra/terraform/                # AWS infrastructure as code
│   ├── main.tf, providers.tf, variables.tf, outputs.tf
│   ├── cloudfront.tf, sqs.tf, monitoring.tf, github-actions.tf
│   └── terraform.tfvars(.example)
├── docs/
│   ├── ARCHITECTURE_OVERVIEW.md    # System architecture diagrams
│   ├── LAYOUT_GENERATION_EXPLAINED.md  # Algorithm deep-dive
│   ├── PHASE_5_IMPLEMENTATION.md   # Compliance & GIS docs
│   └── MAP_VISUALIZATION_UPGRADE_OPTIONS.md
├── test-files/                     # Sample KML/KMZ files for testing
├── memory/                         # AI context files
└── *.md                            # Various docs (PRD, MVP_Task_List, gapimplement, etc.)
```

---

## 4. Key APIs (Backend)

### 4.1 Sites API (`/api/sites`)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/sites/upload` | Upload KML/KMZ, create site |
| GET | `/api/sites` | List all sites for user |
| GET | `/api/sites/{id}` | Get site with GeoJSON boundary |
| DELETE | `/api/sites/{id}` | Delete site and S3 files |
| GET | `/api/sites/regulatory-layers` | List available regulatory layers |
| POST | `/api/sites/{site_id}/regulatory-sync` | Auto-populate exclusion zones |

### 4.2 Layouts API (`/api/layouts`)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/layouts/profiles` | List available generation profiles |
| POST | `/api/layouts/generate` | Generate single layout (sync or async) |
| POST | `/api/layouts/generate-variants` | Generate 4 strategy variants |
| GET | `/api/layouts` | List layouts (optional site_id filter) |
| GET | `/api/layouts/{id}` | Get layout with assets and roads |
| GET | `/api/layouts/{id}/status` | Poll async job status |
| DELETE | `/api/layouts/{id}` | Delete layout |
| PATCH | `/api/layouts/{id}/assets/{asset_id}` | Move asset (validation + recompute) |
| POST | `/api/layouts/{id}/roads/recompute` | Regenerate road network |
| POST | `/api/layouts/{id}/earthwork/recompute` | Recalculate cut/fill |

**Generate Layout Request:**
```json
{
  "site_id": "uuid",
  "target_capacity_kw": 100000,
  "generation_profile": "gas_bess"  // solar_farm, gas_bess, wind_hybrid, hybrid
}
```

### 4.3 Exports API (`/api/layouts/{id}/export`)

| Format | Endpoint | Description |
|--------|----------|-------------|
| GeoJSON | `/export/geojson` | Full FeatureCollection with properties |
| KMZ | `/export/kmz` | Google Earth compatible |
| PDF | `/export/pdf` | Summary report with tables |
| CSV | `/export/csv` | Tabular asset/road data |

### 4.4 Terrain API (`/api/sites/{id}/terrain`)

| Endpoint | Returns |
|----------|---------|
| `/terrain/summary` | Elevation stats, slope distribution, buildable area % |
| `/terrain/contours?interval_m=10` | GeoJSON contour lines |
| `/terrain/buildable-area?asset_type=solar_array` | GeoJSON buildable polygons |
| `/terrain/slope-heatmap` | GeoJSON slope polygons with legend |

### 4.5 Exclusion Zones API (`/api/sites/{id}/exclusion-zones`)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/exclusion-zones` | List zones for site |
| POST | `/exclusion-zones` | Create zone (GeoJSON polygon) |
| PUT | `/exclusion-zones/{zone_id}` | Update zone |
| DELETE | `/exclusion-zones/{zone_id}` | Delete zone |
| GET | `/api/sites/exclusion-zone-types` | Get available zone types |

### 4.6 Compliance & GIS API

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/layouts/{id}/compliance/check` | Validate against jurisdiction rules |
| GET | `/api/compliance/rules` | List rules for jurisdiction |
| GET | `/api/compliance/jurisdictions` | Available jurisdictions |
| POST | `/api/layouts/{id}/compliance/override-rule` | Add project-specific rule |
| POST | `/api/layouts/{id}/gis/publish` | Publish to GIS system |
| GET | `/api/gis/providers` | List available GIS providers |

### 4.7 Health Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Liveness probe (always 200) |
| `GET /health/ready` | Readiness probe (checks DB) |
| `GET /health/live` | Detailed status (DB, SQS, resources) |

---

## 5. Database Schema (Core Tables)

```sql
-- Users (Cognito integration)
users (id UUID, cognito_sub TEXT UNIQUE, email TEXT, name TEXT)

-- Sites with PostGIS geometry
sites (id UUID, owner_id FK, name TEXT, boundary GEOMETRY(POLYGON, 4326),
       entry_point GEOMETRY(POINT, 4326), area_m2 FLOAT, preferred_layout_id FK)

-- Layouts with status tracking
layouts (id UUID, site_id FK, status TEXT, strategy TEXT,
         total_capacity_kw FLOAT, cut_volume_m3 FLOAT, fill_volume_m3 FLOAT,
         road_cut_m3 FLOAT, road_fill_m3 FLOAT,
         stage TEXT, progress_pct INT, stage_message TEXT,
         error_message TEXT, terrain_processed BOOL)

-- Placed assets with terrain info
assets (id UUID, layout_id FK, asset_type TEXT, name TEXT,
        position GEOMETRY(POINT, 4326), capacity_kw FLOAT,
        elevation_m FLOAT, slope_deg FLOAT, aspect_deg FLOAT,
        suitability_score FLOAT, rotation_deg FLOAT,
        footprint_length_m FLOAT, footprint_width_m FLOAT,
        cut_m3 FLOAT, fill_m3 FLOAT)

-- Road segments with stationing
roads (id UUID, layout_id FK, name TEXT, geometry GEOMETRY(LINESTRING, 4326),
       length_m FLOAT, width_m FLOAT, max_grade_pct FLOAT, road_class TEXT,
       stationing_json JSONB, cut_m3 FLOAT, fill_m3 FLOAT)

-- Exclusion zones (constraints)
exclusion_zones (id UUID, site_id FK, name TEXT, zone_type TEXT,
                 geometry GEOMETRY(POLYGON, 4326), buffer_m FLOAT,
                 cost_multiplier FLOAT, description TEXT)

-- Terrain cache for DEM/slope reuse
terrain_cache (id UUID, site_id FK, data_type TEXT, s3_key TEXT,
               resolution_m INT, variant_key TEXT, terrain_type TEXT,
               expires_at TIMESTAMP)
```

---

## 6. Layout Generation Algorithm

### 6.1 Generation Profiles

**Available Profiles:**
| Profile | Description | Primary Assets |
|---------|-------------|----------------|
| `solar_farm` | Traditional utility-scale solar | Solar arrays, batteries, generators, substations |
| `gas_bess` | Off-grid data center microgrids | Gas turbines (35-50 MW), batteries, cooling, control center |
| `wind_hybrid` | Sites with good wind resources | Wind turbines, solar arrays, batteries |
| `hybrid` | Maximum flexibility | Mix of all asset types |

**Gas Turbine Specifications (SGT-800 Class):**
| Parameter | Value |
|-----------|-------|
| Capacity Range | 35-50 MW per turbine |
| Footprint | 80m × 60m |
| Slope Limit | 3° max, 1° optimal |

### 6.2 Asset Placement

**Slope Limits by Asset Type:**
| Asset Type | Max Slope | Optimal Slope |
|------------|-----------|---------------|
| Solar Array | 10° | 5° |
| Battery | 4° | 2° |
| Generator | 5° | 3° |
| Substation | 3° | 1° |
| Wind Turbine | 20° | 8° |
| Gas Turbine | 3° | 1° |
| Cooling System | 4° | 2° |
| Control Center | 3° | 1° |

**4 Optimization Strategies:**
| Strategy | Spacing | Description |
|----------|---------|-------------|
| `balanced` | 15m | Default: balance capacity, earthwork, access |
| `density` | 10m | Maximize kW/ha, may increase earthwork |
| `low_earthwork` | 20m | Minimize cut/fill, may reduce capacity |
| `clustered` | 12m | Group assets tightly, minimize roads |

**Standard Placement Process (Solar/Wind):**
1. Substation placed at flattest region centroid
2. Poisson-disk sampling generates candidate positions
3. Multi-factor scoring: slope + proximity + suitability + aspect + curvature
4. Assets placed iteratively until target capacity reached

### 6.3 Block Layout System (Gas Turbine Campuses)

**For gas_bess profile, uses structured block-based placement:**

1. **Calculate Grid Size:**
   - Blocks needed = Target capacity ÷ ~42.5 MW per block
   - Grid dimensions = √(blocks) × √(blocks), roughly square
   - Maximum: 20×20 = 400 blocks (~17 GW)

2. **Find Optimal Anchor:**
   - Scans buildable area for regions that can fit entire grid footprint
   - Scores by: suitability (×100) - slope (×3) + buildable_ratio (×30) + centrality (×20)
   - Prefers central locations in large flat areas

3. **Place Block Assets:**
   - Each block contains: gas turbine, battery, cooling system
   - Spacing: 260m row, 220m column
   - Global assets: control center, substation (placed once)

4. **Capacity Attribution:**
   - Only generators (gas_turbine, solar_array, wind_turbine) count toward capacity
   - Batteries are storage (0 kW generation capacity)
   - Infrastructure (cooling, control center, substation) = 0 kW

### 6.4 Road Network

**Standard Multi-Tier Hierarchy (Solar/Wind):**
- `spine`: Entry point → Substation (A* pathfinding)
- `secondary`: MST connections biased toward spine
- `tertiary`: Local connections for remote assets

**Block-Aware Corridor Roads (Gas Turbine):**
- `spine`: Entry point → Center of block grid
- `row_corridor`: Horizontal roads connecting blocks in each row
- `col_corridor`: Vertical roads connecting rows
- `spur`: Short connections from corridors to individual assets

**A* Cost Surface:**
```python
cost = 1 + (slope / max_grade)³ + curvature_penalty + zone_multiplier
```

**Fallback:** Direct line if pathfinding fails after 3 retries.

### 6.5 Cut/Fill Calculation

- **Asset pads:** Level pad at asset elevation, compute volume difference
- **Road corridors:** Buffer geometry by width, sample centerline elevations

---

## 7. Environment Configuration

### 7.1 Backend Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL async connection string |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USERNAME`, `DB_PASSWORD` | Yes | Individual DB params |
| `AWS_REGION` | Yes | AWS region (default: `us-east-1`) |
| `S3_UPLOADS_BUCKET` | Yes | S3 bucket for KML uploads |
| `S3_OUTPUTS_BUCKET` | Yes | S3 bucket for exports |
| `COGNITO_USER_POOL_ID` | Yes | Cognito user pool ID |
| `COGNITO_CLIENT_ID` | Yes | Cognito app client ID |
| `USE_TERRAIN` | No | Enable terrain-aware generation (default: `false`) |
| `ENABLE_ASYNC_LAYOUT_GENERATION` | No | Use SQS worker (default: `false`) |
| `SQS_QUEUE_URL` | If async | SQS queue URL |
| `CORS_ORIGINS` | No | Comma-separated allowed origins |

### 7.2 Frontend Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `VITE_API_URL` | Yes | Backend API base URL |
| `VITE_COGNITO_USER_POOL_ID` | Yes | Cognito user pool ID |
| `VITE_COGNITO_CLIENT_ID` | Yes | Cognito app client ID |
| `VITE_AWS_REGION` | Yes | AWS region |

---

## 8. AWS Infrastructure (Terraform)

### 8.1 Deployed Resources

| Resource | Name/ID |
|----------|---------|
| VPC | `pacifico-layouts-dev-vpc` |
| RDS PostgreSQL | `pacifico-layouts-dev-postgres` |
| ECS Cluster | `pacifico-layouts-dev-cluster` |
| ECS Service | `pacifico-layouts-dev-backend` |
| ALB | `pacifico-layouts-dev-alb` |
| S3 (Frontend) | `pacifico-layouts-dev-frontend-assets` |
| S3 (Uploads) | `pacifico-layouts-dev-site-uploads` |
| S3 (Outputs) | `pacifico-layouts-dev-site-outputs` |
| CloudFront | Frontend CDN distribution |
| Cognito | User pool + app client |
| SQS | Layout jobs queue + DLQ |
| ECR | Backend container registry |

### 8.2 Terraform Commands

```bash
cd infra/terraform
terraform init
terraform plan
terraform apply

# Get outputs
terraform output cognito_user_pool_id
terraform output cognito_client_id
terraform output alb_dns_name
terraform output frontend_url
```

---

## 9. Development Setup

### 9.1 Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Start dev server
uvicorn app.main:app --reload
# → http://localhost:8000
# → http://localhost:8000/docs (Swagger UI)
```

### 9.2 Frontend

```bash
cd frontend
npm install
cp .env.example .env
# Edit .env with Cognito credentials
npm run dev
# → http://localhost:5173
```

### 9.3 SSM Tunnel for RDS (if needed)

```bash
aws ssm start-session \
  --target i-02353dfd1437523f5 \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters '{"host":["<RDS_ENDPOINT>"],"portNumber":["5432"],"localPortNumber":["5432"]}' \
  --region us-east-1
```

---

## 10. Testing

```bash
cd backend
pytest tests/ -v

# Expected: 22 tests passing in <1 second
```

**Test Coverage:**
- Flat/steep terrain placement
- Boundary enforcement
- Spacing constraints
- Capacity targeting
- Road generation
- Cut/fill calculation
- GeoJSON output
- Export service

---

## 11. Deployment

### 11.1 Manual Backend Deployment

```bash
# Build for ECS (linux/amd64)
cd backend
docker build --platform linux/amd64 -t pacifico-layouts-dev-backend .

# Push to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com
docker tag pacifico-layouts-dev-backend:latest $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/pacifico-layouts-dev-backend:latest
docker push $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/pacifico-layouts-dev-backend:latest

# Deploy to ECS
aws ecs update-service --cluster pacifico-layouts-dev-cluster --service pacifico-layouts-dev-backend --force-new-deployment
```

### 11.2 CI/CD (GitHub Actions)

Workflows in `.github/workflows/`:
- `backend-deploy.yml`: Docker → ECR → ECS on push to `main`
- `frontend-deploy.yml`: Build → S3 → CloudFront invalidation

**GitHub Secrets Required:**
- `AWS_ROLE_ARN`
- `VITE_API_URL`
- `VITE_COGNITO_USER_POOL_ID`
- `VITE_COGNITO_CLIENT_ID`
- `CLOUDFRONT_DISTRIBUTION_ID`

---

## 12. Key Files for Common Tasks

| Task | File(s) |
|------|---------|
| Add new API endpoint | `backend/app/api/*.py` |
| Add new model | `backend/app/models/*.py` + migration |
| Modify layout algorithm | `backend/app/services/terrain_layout_generator.py` |
| Add/modify generation profile | `backend/app/services/generation_profiles.py` |
| Change terrain analysis | `backend/app/services/terrain_analysis_service.py` |
| Add frontend page | `frontend/src/pages/*.tsx` + `App.tsx` |
| Modify map rendering | `frontend/src/lib/mapUtils.ts`, `SiteDetailPage.tsx` |
| Add asset icons | `frontend/src/components/AssetIcons.tsx` |
| Add TypeScript types | `frontend/src/types/index.ts` |
| Update infrastructure | `infra/terraform/*.tf` |
| Add compliance rule | `backend/app/services/compliance_rules_engine.py` |

---

## 13. Known Issues & Technical Debt

### 13.1 Terrain Services Async Issue

**Problem:** Terrain-aware generation fails in some environments due to `greenlet_spawn` error with SQLAlchemy async sessions when `py3dep` (sync) is called in thread pools.

**Workaround:** `USE_TERRAIN=false` by default locally. Enable with `USE_TERRAIN=true` in AWS.

**Potential Fixes:**
1. Replace `boto3` with `aioboto3`
2. Replace `py3dep` with custom async HTTP calls
3. Create new DB sessions after threaded operations

### 13.2 Production Readiness

- ✅ All 22 backend tests passing
- ✅ ESLint validation passing
- ✅ TypeScript compilation successful
- ⚠️ Enable HTTPS for ALB (requires ACM certificate)
- ⚠️ Set `enable_deletion_protection=true` in production

---

## 14. Project Status

### 14.1 Phase Completion

| Phase | Description | Status |
|-------|-------------|--------|
| **A** | Thin Vertical Slice (infrastructure, auth, upload, dummy layouts) | ✅ 100% |
| **B** | Real Layout Engine (DEM, slope, terrain-aware placement, exports) | ✅ 100% |
| **C** | Async Jobs + Hardening (SQS, worker, monitoring, security) | ✅ 100% |
| **D** | Terrain Visualization + Exclusion Zones + Variants | ✅ 100% |
| **E** | Gap Implementation (PRD alignment) | ✅ 100% |
| **5** | Compliance Rules + Wind Turbines + GIS Integration | ✅ 100% |
| **F** | Generation Profiles + Block Layouts + GW-Scale Support | ✅ 100% |

### 14.2 PRD Alignment

- **P0 (must-have):** ✅ All implemented
- **P1 (should-have):** ✅ All implemented
- **P2 (nice-to-have):** ✅ All implemented

---

## 15. Quick Reference Commands

```bash
# Backend dev server
cd backend && uvicorn app.main:app --reload

# Frontend dev server
cd frontend && npm run dev

# Run backend tests
cd backend && pytest tests/ -v

# Lint frontend
cd frontend && npm run lint

# Build frontend
cd frontend && npm run build

# Apply DB migrations
cd backend && alembic upgrade head

# Create new migration
cd backend && alembic revision --autogenerate -m "description"

# Terraform plan
cd infra/terraform && terraform plan

# View ECS logs
aws logs tail /ecs/pacifico-layouts-dev --follow
```

---

## 16. Documentation Index

| Document | Location | Content |
|----------|----------|---------|
| PRD | `PRD_Pacifico_Energy_Group_MVP_Site_Layouts_Use_code_and_open_source_data_to_.md` | Product requirements |
| MVP Task List | `MVP_Task_List.md` | Detailed task breakdown |
| Architecture | `docs/ARCHITECTURE_OVERVIEW.md` | System diagrams |
| Layout Generation | `docs/LAYOUT_GENERATION_EXPLAINED.md` | Algorithm deep-dive |
| Phase 5 | `docs/PHASE_5_IMPLEMENTATION.md` | Compliance & GIS |
| Gap Implementation | `gapimplement.md` | PRD gap analysis |
| Map Visualization | `docs/MAP_VISUALIZATION_UPGRADE_OPTIONS.md` | Frontend upgrade options |

---

## 17. Contact & Support

- **Project Owner:** Pacifico Energy Group
- **Repository:** `pacifico-site-layouts/`
- **License:** Proprietary

---

*This document is auto-generated context for AI agents and serves as the primary onboarding reference. Keep it updated when making architectural changes.*



