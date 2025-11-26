# Pacifico Site Layouts

**AI-powered geospatial layout tool for DG/microgrid/data center site planning**

Pacifico Site Layouts streamlines early-stage real estate due diligence by automatically generating optimized site layouts from geospatial inputs. Upload a KML/KMZ boundary file, and the tool will auto-position infrastructure assets while respecting terrain constraints, exclusion zones, and spacing requirements.

## Features

- **KML/KMZ Import** — Upload site boundaries from Google Earth or GIS tools
- **Terrain Analysis** — Fetch DEMs and compute slope/aspect from USGS 3DEP or SRTM
- **Smart Asset Placement** — Heuristic placement of solar arrays, batteries, generators, and substations based on terrain suitability
- **Road Network Generation** — Auto-route access roads connecting all assets
- **Cut/Fill Estimation** — Calculate earthwork volumes for pads and roads
- **Multi-format Export** — Download layouts as GeoJSON, KMZ, or PDF reports

## Tech Stack

| Layer          | Technology                              |
|----------------|----------------------------------------|
| Frontend       | React, TypeScript, Vite, Leaflet       |
| Backend        | FastAPI, SQLAlchemy, PostGIS           |
| Database       | PostgreSQL 15 + PostGIS                |
| Auth           | AWS Cognito                            |
| Infrastructure | AWS (ECS Fargate, S3, RDS, CloudFront) |
| IaC            | Terraform                              |

## Directory Structure

```
pacifico-site-layouts/
├── backend/           # FastAPI application
│   ├── app/           # Application code
│   ├── alembic/       # Database migrations
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/          # React + Vite application
│   ├── src/           # Source code
│   ├── public/        # Static assets
│   └── package.json
├── infra/
│   └── terraform/     # AWS infrastructure as code
└── docs/              # Additional documentation
```

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker (for building backend images)
- AWS CLI configured with credentials
- AWS account (for deployment)

### Backend Development

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run database migrations
alembic upgrade head

# Start development server (connects to AWS RDS)
uvicorn app.main:app --reload
```

### Frontend Development

```bash
cd frontend

# Install dependencies
npm install

# Configure environment variables
cp .env.example .env
# Edit .env and add your Cognito credentials from terraform outputs

# Start development server
npm run dev
# Open http://localhost:5173
```

**Frontend Environment Variables** (from Terraform outputs):

```bash
VITE_API_URL=http://localhost:8000  # or ALB DNS name for cloud testing
VITE_COGNITO_USER_POOL_ID=<from terraform output cognito_user_pool_id>
VITE_COGNITO_CLIENT_ID=<from terraform output cognito_client_id>
VITE_AWS_REGION=us-east-1
```

Get these values:
```bash
cd pacifico-site-layouts/infra/terraform
terraform output cognito_user_pool_id
terraform output cognito_client_id
terraform output frontend_url  # CloudFront URL for production frontend
```

### Deploy to AWS

#### Option 1: Automated (via GitHub Actions CI/CD)

After initial setup, deployments are automatic:
- Push to `main` branch triggers deployment
- Backend changes → Docker build → ECR → ECS
- Frontend changes → Build → S3

See `.github/README.md` for setup instructions.

#### Option 2: Manual Deployment

**Step 1: Create infrastructure (first time only)**
```bash
cd infra/terraform
terraform init
terraform plan
terraform apply
```

**Step 2: Build and push backend Docker image**
```bash
# Get AWS account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Build for ECS (linux/amd64, not ARM)
cd pacifico-site-layouts/backend
docker build --platform linux/amd64 -t pacifico-layouts-dev-backend .

# Authenticate to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com

# Tag and push
docker tag pacifico-layouts-dev-backend:latest $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/pacifico-layouts-dev-backend:latest
docker push $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/pacifico-layouts-dev-backend:latest
```

**Step 3: Deploy to ECS**
```bash
aws ecs update-service \
  --cluster pacifico-layouts-dev-cluster \
  --service pacifico-layouts-dev-backend \
  --force-new-deployment \
  --region us-east-1
```

**Step 4: Verify deployment**
```bash
# Get ALB DNS name
cd pacifico-site-layouts/infra/terraform
ALB_DNS=$(terraform output -raw alb_dns_name)

# Test health endpoint (wait ~2 minutes for deployment)
curl http://$ALB_DNS/health
# Expected response: {"status":"ok"}
```

### Deployment Status

| Component | Status | Notes |
|-----------|--------|-------|
| Infrastructure (A-01) | ✅ Deployed | VPC, RDS, S3, Cognito, Bastion |
| Backend Service (A-02) | ✅ Deployed | ECS Fargate, ALB, ECR |
| CI/CD Pipeline (A-03) | ✅ Ready | GitHub Actions workflows (see `.github/README.md`) |
| Backend API Models (A-04) | ✅ Complete | FastAPI + SQLAlchemy + PostGIS |
| Backend Auth (A-08) | ✅ Complete | Cognito JWT validation, user auto-creation |
| Site Management (A-05, A-06) | ✅ Complete | KML/KMZ upload, site retrieval with GeoJSON |
| Layout Generation (A-07) | ✅ Complete | Dummy asset placement, road generation |
| Frontend Setup (A-09) | ✅ Complete | React + TypeScript + Vite + routing |
| Frontend Auth (A-10) | ✅ Complete | Cognito login/signup/logout with Amplify |
| Frontend Sites & Upload (A-11, A-12) | ✅ Complete | Sites list, drag-drop KML upload |
| Frontend Map (A-13) | ✅ Complete | Leaflet map with site boundary display |
| Frontend Layout Generation (A-14) | ✅ Complete | Generate button, asset & road display |
| Frontend Deployment (A-15) | ✅ Complete | S3 + CloudFront with HTTPS |

## Deployment Troubleshooting

### Docker build fails on Mac

**Issue:** `image Manifest does not contain descriptor matching platform 'linux/amd64'`

**Solution:** Always build with explicit platform flag:
```bash
docker build --platform linux/amd64 -t pacifico-layouts-dev-backend .
```

### ECS tasks not starting

**Check service status:**
```bash
aws ecs describe-services \
  --cluster pacifico-layouts-dev-cluster \
  --services pacifico-layouts-dev-backend \
  --region us-east-1
```

**View recent logs:**
```bash
aws logs tail /ecs/pacifico-layouts-dev --follow --region us-east-1
```

### ALB health checks failing

**Verify FastAPI is running on port 8000 and has `/health` endpoint:**
```python
@app.get("/health")
async def health():
    return {"status": "ok"}
```

**Test manually from ECS task:**
```bash
# Get task ID
TASK_ID=$(aws ecs list-tasks --cluster pacifico-layouts-dev-cluster --service-name pacifico-layouts-dev-backend --query 'taskArns[0]' --output text --region us-east-1 | cut -d'/' -f3)

# Describe task to check status
aws ecs describe-tasks --cluster pacifico-layouts-dev-cluster --tasks $TASK_ID --region us-east-1
```

## Architecture Overview

The application follows a three-phase MVP approach:

1. **Phase A** — Thin vertical slice: Upload → dummy asset placement → map display ✅ **COMPLETE**
   - Infrastructure: ✅ Complete (A-01, A-02, A-03)
   - Backend foundation: ✅ Complete (A-04, A-08)
   - Backend API: ✅ Complete (A-05, A-06, A-07)
   - Frontend foundation: ✅ Complete (A-09, A-10, A-11, A-12, A-13, A-14)
   - Frontend deployment: ✅ Complete (A-15 - CloudFront CDN with HTTPS)

2. **Phase B** — Real layout engine: Terrain-aware placement, routing, cut/fill ✅ **COMPLETE**
   - DEM fetching & caching, slope computation, asset placement algorithm, road routing, cut/fill
   - Exports: GeoJSON, KMZ, PDF reports
   - 22 unit tests validating all terrain-aware features

3. **Phase C** — Async processing + production hardening ✅ **COMPLETE**
   - ✅ SQS infrastructure with DLQ (C-01)
   - ✅ Worker container for async processing (C-02)
   - ✅ Async API endpoints with job queuing (C-03, C-04)
   - ✅ Frontend polling for status (C-05)
   - ✅ Lifecycle policies, security hardening, monitoring (C-06 to C-10)

4. **Phase D** — Terrain visualization, exclusion zones, layout variants ✅ **COMPLETE** (100%)
   - ✅ D-01: Terrain visualization (slope heatmap, contours, buildable areas) — COMPLETE
   - ✅ D-02: Cut/fill volume display with net earthwork indicators — COMPLETE
   - ✅ D-03: Exclusion zones & buffers (Leaflet Draw, CRUD API, layout integration) — COMPLETE
   - ✅ D-04: Export functionality completion (terrain in PDF, CSV export, filenames) — COMPLETE
   - ✅ D-05: Layout variants & comparison (4 strategies, comparison table, variant tabs) — COMPLETE

See `MVP_Task_List.md` in the project root for detailed task breakdown and progress tracking.
See `PHASE_D_PROGRESS.md` in the project root for current Phase D implementation details.

## Phase C: Async Jobs + Hardening (10/10 tasks, 100% ✅)

**Status:** Complete — All tasks delivered on schedule

## Phase D: Terrain Visualization & Advanced Features (6/6 tasks, 100% ✅)

**Status:** COMPLETE — All features delivered ahead of schedule

**Infrastructure Enhancements:**
- ✅ **C-01**: SQS queue with DLQ (5-min visibility timeout, 3 max retries)
- ✅ **C-02**: SQS worker service (async layout generation, idempotency, graceful shutdown)
- ✅ **C-03**: Async `/api/layouts/generate` endpoint (enqueues jobs, returns immediately)
- ✅ **C-04**: Status polling endpoint `/api/layouts/{id}/status` (ownership checks)
- ✅ **C-05**: Frontend polling UI (custom hook, progress indicator, elapsed time)
- ✅ **C-06**: S3 lifecycle policies (90-day uploads, 30-day outputs/terrain)
- ✅ **C-07**: Security hardening (conditional bastion, least-privilege IAM)
- ✅ **C-08**: CloudWatch monitoring (alarms, dashboard, SNS notifications)
- ✅ **C-09**: Health checks & graceful shutdown (60-second stopTimeout)
- ✅ **C-10**: Operational runbook documentation

**New Features (Phase C & D):**
- Async layout generation with job queuing (SQS)
- Frontend polling with progress indicators
- S3 lifecycle policies for cost optimization
- Enhanced monitoring with CloudWatch alarms
- Production-ready health checks
- **Persistent terrain overlays** (Nov 26) — slope heatmaps, contours, and buildable areas saved and cached
  - Overlays persist across browser refreshes and client-side navigation
  - Variant-aware caching supports multiple configurations per site
  - Instant toggle after initial generation

**Enable Async Mode:**
```hcl
# In infra/terraform/terraform.tfvars:
# Enable async layout generation in API task definition
backend_env_vars = {
  ENABLE_ASYNC_LAYOUT_GENERATION = "true"
}
```

---

## Current Progress

**Phase A Completed (15/15 tasks, 100% ✅):**

**Infrastructure & Backend (9 tasks):**
- ✅ A-01: Infrastructure foundation (VPC, RDS, S3, Cognito, ECR, ALB, Bastion)
- ✅ A-02: ECS backend deployment with health checks and auto-scaling
- ✅ A-03: GitHub Actions CI/CD pipeline with OIDC authentication
- ✅ A-04: FastAPI app with SQLAlchemy models and PostGIS geometry support
- ✅ A-05: KML/KMZ upload endpoint with S3 storage and GeoJSON conversion
- ✅ A-06: Site retrieval with GeoJSON boundary and area calculation
- ✅ A-07: Dummy layout generation (grid-based asset placement with star-topology roads)
- ✅ A-08: Cognito JWT authentication middleware with auto-user-creation
- ✅ A-09: React frontend with TypeScript, Vite, routing, and brand styling

**Frontend Integration (6 tasks):**
- ✅ A-10: Cognito authentication (login/signup/logout with email verification)
- ✅ A-11: Sites dashboard with file upload modal and site deletion
- ✅ A-12: KML/KMZ drag-and-drop upload component with progress feedback
- ✅ A-13: Leaflet map with site boundary display and auto-zoom
- ✅ A-14: Layout generation button with asset markers and road display on map
- ✅ A-15: CloudFront CDN with S3 OAC, HTTPS, SPA routing support

**Phase B Complete (11/11 tasks, 100% ✅):**

**Terrain Pipeline & Processing:**
- ✅ B-01: DEM fetching from USGS 3DEP with automatic TerrainCache caching
- ✅ B-02: Slope computation from DEM using NumPy gradient method
- ✅ B-03: Integrated terrain processing into layout generation workflow

**Asset & Road Placement:**
- ✅ B-04: Terrain-aware asset placement with slope constraints per type
- ✅ B-05: 22 comprehensive unit tests for placement algorithms (all passing)
- ✅ B-06: Slope-weighted A* pathfinding for optimal road networks
- ✅ B-07: Cut/fill volume calculations for earthwork estimation

**Export Functionality:**
- ✅ B-08: GeoJSON export endpoint with full FeatureCollection
- ✅ B-09: KMZ export for Google Earth with colored markers
- ✅ B-10: PDF report generation with asset inventory and cut/fill summary
- ✅ B-11: Frontend export UI with download buttons and loading states

**Backend API Summary:**

*Phase A (Complete):*
- **Sites API**: POST/GET /api/sites, GET /api/sites/{id}, DELETE /api/sites/{id}, POST /api/sites/upload
- **Layouts API**: POST/GET /api/layouts, GET /api/layouts/{id}, DELETE /api/layouts/{id}
- **Auth API**: GET /api/me (get current user)
- **Health**: GET /health, GET /health/ready (with DB connectivity check)

*Phase B (New):*
- **Layout Generation**: Enhanced POST /api/layouts/generate with terrain-aware placement (default)
- **Exports API**: 
  - GET /api/layouts/{id}/export/geojson (GeoJSON FeatureCollection)
  - GET /api/layouts/{id}/export/kmz (Google Earth KMZ)
  - GET /api/layouts/{id}/export/pdf (Professional PDF report)

**Frontend Features (Phase A):**
- Complete authentication flow with Cognito and email verification
- Sites dashboard with upload, delete, and navigation
- Interactive map display of site boundaries and generated layouts
- Asset placement visualization with type-based color coding
- Road network display

**Backend Services (Phase B):**
- **DEM Service**: Fetches elevation data from USGS 3DEP with automatic caching
- **Slope Service**: Computes slope rasters from DEM using NumPy
- **Terrain-Aware Layout Generator**: Intelligent asset placement respecting slope constraints
- **Export Service**: Generates GeoJSON, KMZ, and PDF exports

**Phase C Implementation (✅ Complete):**
1. ✅ **C-01** - Set up SQS queue for layout generation jobs (completed)
2. ✅ **C-02** - Create worker container to process layout jobs asynchronously (completed)
3. ✅ **C-03** - Modify POST /api/layouts/generate to enqueue job (completed)
4. ✅ **C-04** - Add GET /api/layouts/{id}/status endpoint for polling (completed)
5. ✅ **C-05** - Implement polling on frontend for layout status (completed)
6. ✅ **C-06 to C-10** - Security hardening & monitoring (completed)

**Phase D Implementation (✅ COMPLETE - 100%):**
1. ✅ **D-01** - Terrain visualization layer with slope heatmap, contours, buildable areas (Nov 25)
   - 4 new REST endpoints with terrain data visualization
   - Scikit-image contour extraction + rasterio polygon vectorization
   - Interactive map layers with dynamic legends
   - **Nov 26 Update**: Persistent overlay caching — generated GeoJSON saved to S3 and cached in DB
     - Slope heatmaps, contours, and buildable areas survive page refresh
     - Variant-aware caching: each interval/asset-type combination cached independently
     - New `TerrainCache` fields: `variant_key`, `terrain_type` (contours, heatmap, buildable_area)
     - Toggle overlays instantly after first generation

2. ✅ **D-02** - Cut/fill volume display in sidebar with net earthwork indicators (Nov 25)
   - Earthwork section showing cut/fill totals in thousands-separator format
   - Export/Import/Balanced net earthwork indicators with color coding
   - Per-asset grading display in popups (↑Cut / ↓Fill)
3. ✅ **D-03** - Exclusion zones & buffers with drawing UI (Nov 25)
   - New ExclusionZone model with CRUD API endpoints
   - Leaflet Draw integration for polygon creation on map
   - Zone type modal with Environmental, Regulatory, Infrastructure, Safety, Custom types
   - Layout generator respects exclusion zones (buildable mask integration)
   - Zone list panel with expand/collapse, edit, delete functionality
4. ✅ **D-04** - Export functionality completion (Nov 25)
   - PDF includes terrain analysis summary (slope stats, buildable area %)
   - GeoJSON includes terrain metadata per feature (slope suitability, grade class)
   - KMZ includes slope/buildability styling with color-coded roads
   - NEW: CSV export for tabular asset/road data
   - Filenames now include site name + timestamp
5. ✅ **D-05** - Layout variants & comparison (Nov 25)
   - 4 optimization strategies: Balanced, Density, Low Earthwork, Clustered
   - New `/api/layouts/generate-variants` endpoint generates all variants at once
   - Strategy-specific generator configs (spacing, slope weight, capacity multiplier)
   - Variant tabs UI with best-in-category badges
   - Expandable comparison table showing all metrics across variants

---

## Phase E: Gap Implementation (Phases 1-4, ✅ COMPLETE)

**Status:** Complete — All 4 phases implemented from PRD alignment plan

**Phase 1 - Documentation & Exposure (✅ Complete):**
- ✅ Updated `docs/LAYOUT_GENERATION_EXPLAINED.md` with comprehensive architecture documentation
  - Service responsibilities and interactions
  - Asset placement algorithm with slope limits and strategies (4 strategies: Balanced, Density, Low Earthwork, Clustered)
  - Road network generation (A* pathfinding, MST vs Star topology)
  - Earthwork calculation for pads and corridors
  - Exclusion zone handling
  - Export formats and API reference
- ✅ Created `docs/ARCHITECTURE_OVERVIEW.md` with system-wide architecture
  - High-level component diagram
  - Directory structure mapping
  - Data flow for sync/async generation
  - Technology stack and database schema
  - Configuration reference for environment setup

**Phase 2 - Regulatory & Environmental Constraints (✅ Complete):**
- ✅ Created `RegulatoryService` with provider abstraction layer
  - `RegulatoryDataProvider` - Abstract interface for pluggable data sources
  - `MockRegulatoryProvider` - Generates synthetic regulatory features (wetlands, utilities, setbacks)
  - Supports 9 layer types: wetland, floodplain, water_body, species_habitat, setback, easement, right_of_way, utility_corridor, existing_structure
- ✅ New API endpoints:
  - `GET /api/sites/regulatory-layers` - List available regulatory layers
  - `POST /api/sites/{site_id}/regulatory-sync` - Fetch regulatory data and auto-populate exclusion zones
- ✅ Automatic zone type mapping with defaults (buffers, cost multipliers)

**Phase 3 - User-Defined Asset Adjustments (✅ Complete):**
- ✅ New asset manipulation endpoints:
  - `PATCH /api/layouts/{layout_id}/assets/{asset_id}` - Move asset with validation and local terrain recompute
  - `POST /api/layouts/{layout_id}/roads/recompute` - Regenerate road network based on current asset positions
  - `POST /api/layouts/{layout_id}/earthwork/recompute` - Recalculate cut/fill volumes
- ✅ Validation logic:
  - New position must be within site boundary
  - New position cannot be in hard exclusion zones
  - Warnings for soft exclusion zones
  - Re-evaluation of slope, elevation, suitability at new position
  - Flags warning if slope exceeds asset type limits

**Phase 4 - Real-Time Progress Tracking (✅ Complete):**
- ✅ Enhanced `LayoutStatusResponse` with progress fields:
  - `stage` - Current generation stage (fetching_dem, computing_slope, analyzing_terrain, placing_assets, generating_roads, computing_earthwork, finalizing)
  - `progress_pct` - Progress percentage (0-100)
  - `stage_message` - Human-readable stage description
- ✅ Database migration (006_layout_progress_tracking.py):
  - Added `stage`, `progress_pct`, `stage_message` columns to layouts table
  - Auto-migration for existing records
- ✅ Frontend updates:
  - Enhanced `LayoutStatusResponse` TypeScript interface
  - Progress bar now shows actual `progress_pct` instead of fixed values
  - Stage-specific messages displayed to user
  - Elapsed time display during generation

---

**Testing:**
- ✅ All 22 backend tests passing in <1 second
- ✅ ESLint validation passing
- ✅ TypeScript compilation successful
- ✅ Frontend production build passing

## License

Proprietary — Pacifico Energy Group

