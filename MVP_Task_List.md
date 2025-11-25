# MVP Task List - Pacifico Energy Site Layouts Tool

**Project:** Geospatial layout tool for DG/microgrid/data center sites  
**Scope:** Three-phase MVP delivering cloud-deployed, multi-user, terrain-aware layout generation  
**Last Updated:** November 25, 2025 (A-04 Complete ✅)

---

## Progress Summary

| Task | Status | Completed |
|------|--------|-----------|
| A-01 | ✅ Complete | Nov 24, 2025 |
| A-02 | ✅ Complete | Nov 24, 2025 |
| A-03 | ✅ Complete | Nov 25, 2025 |
| A-04 | ✅ Complete | Nov 25, 2025 |
| A-05 | 🔲 Not Started | - |
| A-06 | 🔲 Not Started | - |
| A-07 | 🔲 Not Started | - |
| A-08 | 🔲 Not Started | - |
| A-09 | 🔲 Not Started | - |
| A-10 | 🔲 Not Started | - |
| A-11 | 🔲 Not Started | - |
| A-12 | 🔲 Not Started | - |
| A-13 | 🔲 Not Started | - |
| A-14 | 🔲 Not Started | - |
| A-15 | 🔲 Not Started | - |

---

## Table of Contents

1. [Phase A: Thin Vertical Slice](#phase-a-thin-vertical-slice)
2. [Phase B: Real Layout Engine MVP](#phase-b-real-layout-engine-mvp)
3. [Phase C: Async Jobs + Minimal Hardening](#phase-c-async-jobs--minimal-hardening)
4. [Summary & Risk Assessment](#summary--risk-assessment)

---

# Phase A: Thin Vertical Slice

**Goal:** Cloud-deployed, multi-user application. Upload a site, see auto-placed dummy assets on a map.

**AWS Services:** S3 + CloudFront, ECS Fargate, RDS PostgreSQL + PostGIS, Cognito

---

## Epic A1: Infrastructure Foundation

### A-01: Set up AWS infrastructure with Terraform ✅ COMPLETE
**Owner:** DevOps  
**Story Points:** 5  
**Dependencies:** None  
**Completed:** November 24, 2025

Create Terraform configuration for minimal AWS resources:
- S3 buckets (frontend-assets, site-uploads, site-outputs) with public read for frontend bucket
- RDS PostgreSQL 15 instance with PostGIS extension, db.t3.micro, single-AZ for MVP
- Cognito User Pool with email/password authentication, standard password policy
- VPC with public/private subnets, NAT gateway, security groups for RDS (5432 from ECS only) and ECS (443/80)

**Acceptance Criteria:**
- ✅ `terraform apply` successfully provisions all resources
- ✅ RDS accessible from local machine via bastion/tunnel for initial setup
- ✅ S3 buckets created with appropriate policies
- ✅ Cognito User Pool operational

**Deployed Resources:**
| Resource | ID/Name |
|----------|---------|
| VPC | `vpc-0f2191e1017ae3a43` |
| Public Subnets | `subnet-0d93fb744bdcbf9c8`, `subnet-09ff2f53ac3621847` |
| Private Subnets | `subnet-0628c70bfeeb539d7`, `subnet-0e387d308a9167194` |
| RDS Endpoint | `pacifico-layouts-dev-postgres.crws0amqe1e3.us-east-1.rds.amazonaws.com:5432` |
| RDS Database | `pacifico_layouts` (PostGIS 3.4 enabled) |
| Cognito User Pool | `us-east-1_5TNDHK21Y` |
| Cognito Client ID | `3f9aqjli9r80u90f7ehoq9gf4d` |
| S3 Frontend | `pacifico-layouts-dev-frontend-assets` |
| S3 Uploads | `pacifico-layouts-dev-site-uploads` |
| S3 Outputs | `pacifico-layouts-dev-site-outputs` |
| SSM Bastion | `i-02353dfd1437523f5` (added for DB admin access) |

**Notes:**
- Added SSM bastion host (not in original spec) for secure RDS access without exposing DB publicly
- PostGIS 3.4 extensions installed: `postgis`, `postgis_topology`
- Security groups configured for ALB, ECS, RDS, and Bastion

---

### A-02: Configure ECS Fargate service for FastAPI backend ✅ COMPLETE
**Owner:** DevOps  
**Story Points:** 3  
**Dependencies:** A-01  
**Completed:** November 24, 2025

Set up ECS cluster and Fargate task definition:
- Create ECS cluster
- Task definition with FastAPI container (Python 3.11 slim base image)
- Environment variables from Secrets Manager (DB credentials, Cognito config)
- Service with 1-2 tasks behind Application Load Balancer
- Health check endpoint configuration (GET /health)

**Acceptance Criteria:**
- ✅ ECS service runs successfully
- ✅ ALB health checks pass
- ✅ Can deploy new container images via AWS CLI/Console
- ✅ Backend accessible at http://{alb-dns-name}

**Terraform Resources Configured:**
| Resource | Name |
|----------|------|
| ECR Repository | `pacifico-layouts-dev-backend` |
| ECS Cluster | `pacifico-layouts-dev-cluster` |
| ECS Service | `pacifico-layouts-dev-backend` |
| ECS Task Definition | `pacifico-layouts-dev-backend` |
| ALB | `pacifico-layouts-dev-alb` |
| Target Group | `pacifico-layouts-dev-backend-tg` |
| CloudWatch Logs | `/ecs/pacifico-layouts-dev` |
| Secrets Manager | `pacifico-layouts-dev-db-credentials` |
| IAM Task Execution Role | `pacifico-layouts-dev-ecs-task-execution` |
| IAM Task Role | `pacifico-layouts-dev-ecs-task` |

**Deployment Steps:**

**Step 1: Apply Terraform to create AWS resources**
```bash
cd pacifico-site-layouts/infra/terraform
terraform apply
```

**Step 2: Get your AWS Account ID**
```bash
aws sts get-caller-identity --query Account --output text
# Returns: 123456789012 (your 12-digit account ID)
```

**Step 3: Build the Docker image**
```bash
cd pacifico-site-layouts/backend
docker build -t pacifico-layouts-dev-backend .
```

**Step 4: Authenticate Docker to ECR**
```bash
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com
```

**Step 5: Tag and push image to ECR**
```bash
docker tag pacifico-layouts-dev-backend:latest <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/pacifico-layouts-dev-backend:latest
docker push <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/pacifico-layouts-dev-backend:latest
```

**Step 6: Force ECS to deploy the new image**
```bash
aws ecs update-service --cluster pacifico-layouts-dev-cluster --service pacifico-layouts-dev-backend --force-new-deployment
```

**Step 7: Test the deployment**
```bash
# Get ALB DNS name
cd pacifico-site-layouts/infra/terraform
terraform output alb_dns_name

# Test health endpoint
curl http://<ALB_DNS_NAME>/health
# Expected: {"status": "ok"}
```

**✅ Deployment Verified:**
- Backend URL: `http://pacifico-layouts-dev-alb-980890644.us-east-1.elb.amazonaws.com`
- Health check: `{"status":"ok"}`
- ECS tasks running: 1 active
- ALB health checks: PASSING

**Important Notes:**
- **Platform requirement:** Docker images must be built for `linux/amd64` (use `docker build --platform linux/amd64`), not `linux/arm64` (Mac ARM)
- HTTP listener on port 80 (HTTPS requires ACM certificate - add in production)
- ECS task uses 256 CPU / 512 MB memory (configurable via `ecs_task_cpu` and `ecs_task_memory` variables)
- Container health check configured for `/health` endpoint
- S3 access policies attached to task role for uploads/outputs buckets
- Deployment circuit breaker enabled for automatic rollback on failures
- First deployment takes 2-3 minutes for ECS to provision and health checks to pass

---

### A-03: Set up GitHub Actions CI/CD pipeline ✅ COMPLETE
**Owner:** DevOps  
**Story Points:** 3  
**Dependencies:** A-02  
**Completed:** November 25, 2025

Create basic CI/CD for automated deployments:
- Backend: Build Docker image, push to ECR, update ECS service
- Frontend: Build React app, sync to S3, invalidate CloudFront
- Trigger: On push to `main` branch
- Separate workflows for backend and frontend

**Acceptance Criteria:**
- ✅ Push to main triggers automatic deployment
- ✅ Backend container updates in ECS within 5 minutes
- ✅ Frontend updates visible in S3 within 2 minutes (CloudFront ready for A-15)
- ✅ Failed builds do not deploy

**Files Created:**

| File | Purpose |
|------|---------|
| `.github/workflows/backend-deploy.yml` | Backend CI/CD: Docker → ECR → ECS |
| `.github/workflows/frontend-deploy.yml` | Frontend CI/CD: Build → S3 (CloudFront invalidation ready) |
| `.github/README.md` | Setup instructions and troubleshooting guide |
| `infra/terraform/github-actions.tf` | IAM OIDC provider and role for GitHub Actions |

**GitHub Secrets Required:**

| Secret | Description |
|--------|-------------|
| `AWS_ROLE_ARN` | IAM role ARN from `terraform output github_actions_role_arn` |
| `VITE_API_URL` | Backend API URL from `terraform output backend_api_url` |
| `VITE_COGNITO_USER_POOL_ID` | From `terraform output cognito_user_pool_id` |
| `VITE_COGNITO_CLIENT_ID` | From `terraform output cognito_client_id` |

**Setup Steps:**

1. Add GitHub config to `terraform.tfvars`:
```hcl
github_org  = "your-org-or-username"
github_repo = "your-repo-name"
```

2. Apply Terraform to create IAM role:
```bash
cd pacifico-site-layouts/infra/terraform
terraform apply
```

3. Get role ARN and configure GitHub secrets:
```bash
terraform output github_actions_role_arn
# Copy this value to GitHub → Settings → Secrets → AWS_ROLE_ARN
```

4. Push to `main` branch to trigger workflows

**Implementation Notes:**
- Uses OIDC authentication (no long-lived AWS credentials in GitHub)
- Backend workflow uses `amazon-ecs-deploy-task-definition` for zero-downtime deployments
- Frontend workflow sets proper cache headers (immutable for assets, no-cache for index.html)
- CloudFront invalidation is commented out, ready to enable when A-15 is complete
- Workflows can be manually triggered via `workflow_dispatch`

---

## Epic A2: Backend API MVP

### A-04: Initialize FastAPI project with SQLAlchemy + PostGIS models ✅ COMPLETE
**Owner:** BE  
**Story Points:** 3  
**Dependencies:** A-01  
**Completed:** November 25, 2025

Set up FastAPI application structure and database models:
- FastAPI app with CORS middleware, exception handlers, health endpoint
- SQLAlchemy with async support (asyncpg driver)
- Alembic for migrations
- PostGIS models: 
  - User (cognito_sub, email, name)
  - Project (name, description, owner_id references User)
  - Site (project_id references Project, name, boundary as GEOMETRY(POLYGON), area_m2, **owner_user_id references User** - ensures every site is owned by a specific user)
  - Layout (site_id references Site, status, total_capacity_kw - ownership flows through site)
  - Asset (layout_id, type, position as GEOMETRY(POINT), capacity_kw)
  - Road (layout_id, geometry as GEOMETRY(LINESTRING), length_m)
  - TerrainCache (site_id, type, s3_key, resolution_m, created_at)
- **Multi-tenant isolation:** All queries must filter by owner_user_id or project membership to prevent users from accessing other users' data

**Acceptance Criteria:**
- ✅ FastAPI server runs locally and in Docker
- ✅ GET /health returns 200 OK
- ✅ GET /health/ready checks database connectivity
- ✅ Alembic configured for migrations with PostGIS support
- ✅ All models defined with PostGIS geometry columns

**Files Created/Updated:**

| File | Purpose |
|------|---------|
| `app/config.py` | Pydantic settings from environment variables |
| `app/database.py` | Async database connection and session management |
| `app/main.py` | FastAPI app with CORS, exception handlers, health endpoints |
| `app/models/base.py` | Base model class with UUID and timestamp mixins |
| `app/models/user.py` | User model (linked to Cognito) |
| `app/models/project.py` | Project model (organizes sites) |
| `app/models/site.py` | Site model with PostGIS POLYGON boundary |
| `app/models/layout.py` | Layout model with status tracking |
| `app/models/asset.py` | Asset model with PostGIS POINT position |
| `app/models/road.py` | Road model with PostGIS LINESTRING geometry |
| `app/models/terrain_cache.py` | TerrainCache model for DEM/slope caching |
| `alembic.ini` | Alembic configuration |
| `alembic/env.py` | Alembic environment with PostGIS support |
| `requirements.txt` | Updated with all dependencies |
| `Dockerfile` | Updated to include alembic files |

**Model Relationships:**
```
User ──┬── Project ── Site ── Layout ──┬── Asset
       │                    │          └── Road
       └── Site ────────────┘
                    │
                    └── TerrainCache
```

**Next Steps:**
1. Run `alembic revision --autogenerate -m "Initial models"` to create migration
2. Run `alembic upgrade head` to apply migration to database
3. Test locally with `uvicorn app.main:app --reload`

---

### A-05: Implement POST /api/sites/upload endpoint
**Owner:** BE  
**Story Points:** 5  
**Dependencies:** A-04

Create endpoint to accept and process KML/KMZ files:
- Accept multipart/form-data with file upload (max 10MB)
- Validate file type (.kml, .kmz only)
- Parse KML/KMZ using fastkml or simplekml library, extract first Polygon/MultiPolygon
- Convert to GeoJSON format
- Store original file in S3 (site-uploads bucket)
- Insert Site record with boundary geometry in PostGIS
- Calculate and store area_m2 using ST_Area
- Return site_id and boundary GeoJSON

**Acceptance Criteria:**
- Valid KML uploads successfully, returns site_id
- **Site record associated with current_user via owner_user_id (derived from Cognito JWT, never from client input)**
- Boundary stored correctly in PostGIS (verify with ST_AsGeoJSON)
- Original file in S3 at `uploads/{site_id}/original.{ext}`
- Invalid files return 400 with clear error message
- Files >10MB rejected with 413

---

### A-06: Implement GET /api/sites/{id} endpoint
**Owner:** BE  
**Story Points:** 2  
**Dependencies:** A-04

Create endpoint to retrieve site details:
- Query Site by ID **AND owner_user_id = current_user.id** (or via project_id membership)
- Return site metadata (id, name, area_m2, created_at)
- Return boundary as GeoJSON using ST_AsGeoJSON
- **If no such site exists for this user, return 404 (do not leak existence of other users' site IDs)**

**Acceptance Criteria:**
- Returns site data with valid GeoJSON boundary for sites owned by current user
- 404 for non-existent sites **or sites owned by other users** (indistinguishable responses)
- Response time <500ms for typical site

---

### A-07: Implement POST /api/layouts/generate with dummy placement
**Owner:** BE  
**Story Points:** 3  
**Dependencies:** A-04, A-06

Create endpoint that generates a dummy layout for a site:
- Accept site_id and simple config (e.g., target_capacity_kw)
- **Load Site by site_id scoped to current_user (owner_user_id check)**
- **If site not owned by user or their project, return 404**
- Create Layout record with status='completed'
- Generate 5-10 dummy assets evenly spaced within site bbox using ST_MakeEnvelope and ST_GeneratePoints (or simple grid math)
- Assign types randomly (solar, battery, generator) with placeholder capacities
- Insert Asset records with POINT geometries
- Create simple dummy road as LineString connecting assets
- Return layout_id and asset/road GeoJSON

**Acceptance Criteria:**
- Creates Layout and Asset records in database **only for sites owned by current user**
- Returns GeoJSON with 5-10 point features (assets) and 1-2 line features (roads)
- Assets fall within site boundary (verify with ST_Within)
- **Returns 404 if user attempts to generate layout for another user's site**
- Endpoint completes in <3 seconds

---

### A-08: Implement Cognito JWT authentication middleware
**Owner:** BE  
**Story Points:** 3  
**Dependencies:** A-04

Add authentication to protect API endpoints:
- Middleware to validate JWT tokens from Cognito
- Extract user identity (sub, email) from token claims
- Fetch Cognito public keys and verify signature
- Dependency injection for current_user in route handlers
- Protect all /api/* routes except /health
- Handle expired/invalid tokens with 401 response

**Acceptance Criteria:**
- Requests with valid JWT succeed
- Requests without token return 401
- Expired tokens return 401
- current_user available in protected routes

**Multi-Tenant Access Control Note:** All API endpoints that list or query resources (projects, sites, layouts) must filter by current_user (via owner_user_id or project membership) so users only see their own data. Never trust client-supplied user IDs; always derive from validated JWT token.

---

## Epic A3: Frontend Map MVP

### A-09: Initialize React + TypeScript project with routing
**Owner:** FE  
**Story Points:** 2  
**Dependencies:** None

Set up frontend application structure:
- Create React app with TypeScript and Vite
- Install dependencies: react-router-dom, axios, leaflet, @types/leaflet
- Set up basic routing: / (landing), /login, /projects, /sites/{id}
- Configure environment variables for API_URL and Cognito config
- Basic layout component with header and content area

**Acceptance Criteria:**
- Dev server runs at localhost:5173
- TypeScript compilation succeeds
- Navigation between routes works
- Environment variables load correctly

---

### A-10: Implement Cognito authentication (login/signup/logout)
**Owner:** FE  
**Story Points:** 5  
**Dependencies:** A-09

Build authentication flow using AWS Amplify or Cognito SDK:
- Login page with email/password form
- Signup page with email/password/name
- AuthContext to manage authentication state
- Store JWT tokens in localStorage
- Axios interceptor to add Authorization header
- Redirect to /login if 401 response received
- Logout functionality to clear tokens

**Security Note:** For the MVP, storing Cognito JWTs in localStorage is acceptable for simplicity. For production hardening, migrate to httpOnly secure cookies or another token storage strategy that reduces XSS risk.

**Acceptance Criteria:**
- User can sign up and receive verification email
- User can log in with verified account
- Tokens stored and sent with API requests
- Logout clears tokens and redirects to login
- Protected routes redirect to login if not authenticated

---

### A-11: Create Project list and Site detail pages
**Owner:** FE  
**Story Points:** 3  
**Dependencies:** A-10

Build basic UI for project/site navigation:
- Projects page: list projects (hardcoded or from API if implemented)
- Site detail page: display site name and metadata
- Navigate from projects → site detail
- Simple card-based layout with Tailwind CSS or similar

**Acceptance Criteria:**
- Can navigate to site detail page
- Page displays site metadata
- Clean, professional UI design

---

### A-12: Implement KML/KMZ upload component
**Owner:** FE  
**Story Points:** 3  
**Dependencies:** A-11

Create file upload interface:
- Drag-and-drop zone for KML/KMZ files
- File validation (type, size)
- Upload progress indicator
- Call POST /api/sites/upload with FormData
- Handle success (store site_id, navigate to site detail) and errors (display message)

**Acceptance Criteria:**
- Drag-and-drop works for .kml/.kmz files
- Upload progress shown
- Success navigates to site detail page
- Errors display user-friendly messages
- File size limit enforced (10MB)

---

### A-13: Display site boundary on Leaflet map
**Owner:** FE  
**Story Points:** 3  
**Dependencies:** A-11, A-06

Create interactive map component:
- Initialize Leaflet map with OpenStreetMap tiles
- Fetch site boundary from GET /api/sites/{id}
- Display boundary as polygon overlay (blue stroke, semi-transparent fill)
- Zoom map to fit boundary using L.geoJSON().getBounds()
- Add basic controls (zoom, attribution)

**Map Tile Strategy Note:** Using public OpenStreetMap tiles is acceptable for the MVP. For production usage at scale, plan to switch to a paid tile provider (Mapbox, MapTiler) or self-hosted tile server to respect OSM usage limits and improve reliability.

**Acceptance Criteria:**
- Map displays with OSM tiles
- Site boundary renders correctly
- Map auto-zooms to fit boundary
- Boundary popup shows site name on click

---

### A-14: Add "Generate Layout" button with results display
**Owner:** FE  
**Story Points:** 3  
**Dependencies:** A-13, A-07

Implement layout generation UI:
- "Generate Layout" button on site detail page
- Call POST /api/layouts/generate with site_id
- Display loading spinner during request
- On success, add asset markers (colored circles by type) and road polylines to map
- Simple legend showing asset types
- Display total capacity in summary panel

**Acceptance Criteria:**
- Button triggers layout generation
- Assets appear as markers on map after generation
- Roads appear as lines
- Legend shows asset type colors
- Loading state shown during generation

---

### A-15: Deploy frontend to S3 + CloudFront
**Owner:** DevOps  
**Story Points:** 2  
**Dependencies:** A-09, A-02

Configure static site hosting:
- S3 bucket for frontend with static website hosting
- CloudFront distribution pointing to S3
- Custom domain with SSL certificate (ACM)
- Build React app for production
- Sync build output to S3
- Set cache headers for optimal performance

**Acceptance Criteria:**
- Frontend accessible at https://{domain}
- SSL certificate valid
- CloudFront caching working
- Build time <2 minutes

---

# Phase B: Real Layout Engine MVP

**Goal:** Replace dummy layout with terrain-aware placement, heuristic routing, cut/fill calculation, and exports.

---

## Epic B1: Terrain & DEM Pipeline

### B-01: Implement DEM fetching for site bounding box
**Owner:** Geo/Algo  
**Story Points:** 5  
**Dependencies:** A-04

Create service to fetch elevation data with caching:
- **First, check TerrainCache table for existing DEM entry for this site_id with required resolution**
- **If valid cached DEM exists in S3, reuse it and skip external API call**
- **If not cached, proceed with fetch:**
  - Calculate site bounding box using ST_Envelope and ST_Extent
  - Call OpenTopography API or USGS 3DEP with bbox parameters
  - Request GeoTIFF format at 10-30m resolution
  - Handle API authentication if needed
  - Download DEM to temporary local storage
  - Fallback to SRTM 30m if 3DEP unavailable for location
  - Store DEM in S3 at `terrain/{site_id}/dem.tif`
  - **Create/update TerrainCache record** (site_id, type='elevation', s3_key, resolution_m, created_at)

**Acceptance Criteria:**
- Successfully fetches DEM for test site (US location)
- DEM covers entire site boundary
- GeoTIFF stored in S3 with correct georeference
- Falls back to SRTM for international sites
- **Subsequent requests for same site reuse cached DEM without hitting external APIs**
- **Cache entry created in TerrainCache table with S3 reference**

---

### B-02: Compute slope raster from DEM using GDAL/Rasterio
**Owner:** Geo/Algo  
**Story Points:** 3  
**Dependencies:** B-01

Process DEM to generate slope map with caching:
- **Check TerrainCache for existing slope raster for this site_id**
- **If cached slope exists, load from S3 and skip recomputation**
- **If not cached, compute slope:**
  - Load DEM from S3 using Rasterio
  - Compute slope in degrees using GDAL's gdaldem or NumPy gradient
  - Optionally compute aspect raster
  - Clip to exact site boundary using site polygon mask
  - Save slope GeoTIFF to S3 at `terrain/{site_id}/slope.tif`
  - **Update TerrainCache with slope reference** (type='slope')

**Acceptance Criteria:**
- Slope raster has same extent/resolution as DEM
- Values in degrees (0-90) or percent
- Raster properly clipped to site
- Processing time <30 seconds for typical site on first run
- **Subsequent layout generations reuse cached slope, completing in <5 seconds**
- **Cache entry in TerrainCache allows skipping recomputation**

---

### B-03: Add terrain processing to layout generation workflow
**Owner:** BE  
**Story Points:** 2  
**Dependencies:** B-02, A-07

Integrate terrain processing into POST /api/layouts/generate:
- Before asset placement, check TerrainCache for existing DEM and slope
- **If cached terrain data exists, load from S3 (fast path)**
- **If not cached, trigger DEM fetch and slope calculation (slow path, first run only)**
- Wait for terrain processing to complete (synchronous for Phase B)
- Pass slope raster to asset placement algorithm
- Update Layout record with terrain_processed=true

**Acceptance Criteria:**
- Layout generation includes terrain processing
- Slope data available for subsequent steps
- **First layout generation for a site takes ~60 seconds (includes DEM fetch)**
- **Subsequent layouts for same site take <30 seconds (reuses cached terrain)**
- Endpoint response time reflects caching benefit

---

## Epic B2: Real Asset Placement

### B-04: Implement heuristic asset placement algorithm
**Owner:** Geo/Algo  
**Story Points:** 8  
**Dependencies:** B-02

Replace dummy placement with terrain-aware heuristic:
- Rasterize site boundary to grid matching DEM resolution
- Load slope raster and create buildable mask (slope < 15° for solar, <5° for battery/generator)
- Define asset types with constraints (footprint size, slope tolerance, capacity per unit)
- Place assets using simple greedy algorithm:
  - Substation: find centroid of buildable area
  - Battery/generators: near substation, flat areas
  - Solar arrays: iterate over buildable cells, place arrays at regular spacing until target capacity met
- Enforce minimum spacing (10m between assets) using buffers
- Store Asset records with POINT geometries (array centroids)
- Return list of placed assets with types, positions, capacities

**Acceptance Criteria:**
- Assets only placed in buildable areas (slope check)
- Minimum spacing enforced
- Target capacity roughly achieved (±20%)
- No assets outside site boundary
- Algorithm completes in <30 seconds for 50-asset layout

---

### B-05: Create unit tests for asset placement
**Owner:** Geo/Algo  
**Story Points:** 3  
**Dependencies:** B-04

Write tests to validate placement logic:
- Test with synthetic flat terrain → all assets placed
- Test with steep terrain → only flat areas used
- Test boundary enforcement → no assets outside polygon
- Test spacing constraint → verify min distance between assets
- Test capacity target → verify actual vs target capacity

**Acceptance Criteria:**
- 5+ test cases covering key scenarios
- All tests pass
- Test suite runs in <10 seconds
- Mock terrain data (simple NumPy arrays)

---

## Epic B3: Road Routing

### B-06: Implement simple road routing algorithm
**Owner:** Geo/Algo  
**Story Points:** 5  
**Dependencies:** B-04

Generate road network connecting assets:
- Identify substation as root node
- Connect all assets to substation using simplified heuristic:
  - For each asset, find path to nearest connected node
  - Use straight line biased toward lower slope cells (simple cost surface: slope-weighted Dijkstra on coarse grid, or just prefer <10% grade when deviating from straight line)
- Merge parallel/overlapping segments
- Store Road records as LINESTRING geometries
- Calculate total length using ST_Length

**Acceptance Criteria:**
- All assets connected by road network
- Roads generally avoid steep slopes where possible
- No duplicate road segments
- Total road length reasonable (not excessively convoluted)
- Algorithm completes in <20 seconds

---

## Epic B4: Cut/Fill Calculation

### B-07: Compute cut/fill volumes for pads and roads
**Owner:** Geo/Algo  
**Story Points:** 5  
**Dependencies:** B-04, B-06

Calculate earthwork requirements:
- Create "proposed graded surface" by flattening asset pad areas and road corridors:
  - For each asset, define level pad (e.g., 20m x 20m) at target elevation
  - For roads, define road surface with max 10% grade
- Use NumPy to compute elevation difference per cell:
  - `dz = DEM_before - DEM_proposed` (in meters)
  - Where `DEM_before` is existing terrain and `DEM_proposed` is graded surface
- Calculate per-cell volume:
  - `cell_area = resolution_x * resolution_y` (in m²)
  - `cell_volume_m3 = dz * cell_area` (in m³)
- Accumulate totals:
  - If `dz > 0`: add `cell_volume_m3` to `cut_volume_m3` (excavation)
  - If `dz < 0`: add `|dz| * cell_area` to `fill_volume_m3` (backfill)
- Return total cut volume (m³), total fill volume (m³), and per-asset breakdown
- Store in Layout metadata (cut_volume_m3, fill_volume_m3)

**Acceptance Criteria:**
- Cut/fill volumes reported in cubic meters (m³) with physically correct units
- Volumes non-zero for non-flat terrain
- Volumes physically reasonable (sanity check: not >100,000 m³ for small site)
- Per-asset breakdown sums to total
- Calculation completes in <10 seconds

---

## Epic B5: Export Outputs

### B-08: Generate GeoJSON export for assets and roads
**Owner:** BE  
**Story Points:** 2  
**Dependencies:** B-04, B-06

Create endpoint to export layout data:
- GET /api/layouts/{id}/export/geojson
- **Verify layout ownership through site → owner_user_id chain before allowing export**
- **Return 404 if layout not owned by current user (same as other endpoints)**
- Query all assets and roads for layout
- Convert to GeoJSON FeatureCollection with separate features for each asset and road
- Include properties: type, capacity_kw, elevation, etc.
- Store GeoJSON in S3 at `outputs/{layout_id}/layout.geojson`
- Return presigned URL for download

**Acceptance Criteria:**
- Valid GeoJSON with all features
- Opens correctly in QGIS or other GIS tools
- Properties include all relevant attributes
- Presigned URL expires in 1 hour
- **Only exports layouts owned by current user**

---

### B-09: Generate KMZ export for Google Earth
**Owner:** BE  
**Story Points:** 3  
**Dependencies:** B-04, B-06

Create KMZ export:
- GET /api/layouts/{id}/export/kmz
- Use simplekml library to create KML
- Add Placemarks for each asset (colored icons by type)
- Add LineStrings for roads (yellow lines)
- Add site boundary polygon (red outline)
- Include descriptions with asset metadata
- Package as KMZ (zipped KML)
- Store in S3 and return presigned URL

**Acceptance Criteria:**
- KMZ opens in Google Earth
- Assets display with correct icons and colors
- Roads and boundary visible
- Descriptions show metadata

---

### B-10: Generate PDF report with map and summary
**Owner:** BE  
**Story Points:** 5  
**Dependencies:** B-04, B-06, B-07

Create basic PDF report:
- GET /api/layouts/{id}/export/pdf
- Use ReportLab library
- Include:
  - Cover page: site name, layout date, user
  - Site map: render static map image using Matplotlib or PIL (show boundary, assets, roads)
  - Asset inventory table: type, capacity, count
  - Road network summary: total length (m)
  - Cut/fill summary: total cut (m³), total fill (m³)
- Store PDF in S3 at `outputs/{layout_id}/report.pdf`
- Return presigned URL

**Acceptance Criteria:**
- PDF generates successfully
- Map image shows layout clearly
- Tables formatted properly
- File size <5MB
- Generation time <20 seconds

---

### B-11: Add export buttons to frontend
**Owner:** FE  
**Story Points:** 2  
**Dependencies:** B-08, B-09, B-10

Update UI to allow downloads:
- Add "Export" dropdown on layout detail page
- Options: GeoJSON, KMZ, PDF
- Click triggers API call to respective endpoint
- Download file using presigned URL
- Show loading spinner during generation
- Display success/error messages

**Acceptance Criteria:**
- All three export formats accessible
- Files download successfully
- Loading states shown
- Errors handled gracefully

---

# Phase C: Async Jobs + Minimal Hardening

**Goal:** Make layout generation asynchronous, add basic production readiness.

---

## Epic C1: Async Job Processing

### C-01: Set up SQS queue for layout generation jobs
**Owner:** DevOps  
**Story Points:** 2  
**Dependencies:** A-01

Create SQS infrastructure:
- Standard SQS queue for layout jobs
- Dead-letter queue for failed jobs
- Visibility timeout: 300 seconds (5 min)
- IAM permissions for ECS tasks to send/receive messages
- CloudWatch alarms for queue depth >10 and DLQ >5

**Acceptance Criteria:**
- Queue created and accessible
- ECS tasks can send messages
- DLQ configured with redrive policy (maxReceiveCount=3)
- CloudWatch alarms set up

---

### C-02: Create worker container to process layout jobs
**Owner:** BE  
**Story Points:** 5  
**Dependencies:** C-01, B-04, B-06, B-07

Build async worker service with idempotency:
- Separate Python script that polls SQS queue
- Message format: {layout_id, site_id, config}
- **Worker must be idempotent with respect to layout_id:**
  - **Before starting heavy work, check layout.status in database**
  - **If status is 'completed' or 'failed', acknowledge message and skip (duplicate message)**
  - **If status is 'pending' or 'queued', set status='processing' and proceed**
- On message received:
  - Update Layout status='processing'
  - **Reuse terrain data from TerrainCache when available (check before fetching DEM/slope)**
  - **Only call external DEM APIs or recompute slope when no valid cached data exists**
  - Run full pipeline: terrain fetch (if needed) → slope compute (if needed) → asset placement → road routing → cut/fill
  - **Use deterministic S3 keys for outputs so re-processing overwrites with identical results**
  - Update Layout status='completed' or 'failed'
  - Delete message from queue on success, allow DLQ on failure
- Run as separate ECS task (same cluster, different task definition)
- Include error handling and logging

**Acceptance Criteria:**
- Worker processes messages successfully
- **Duplicate messages do not cause duplicate work or inconsistent state**
- Layout status updates correctly (queued → processing → completed/failed)
- **Cached terrain data reused, no redundant API calls for same site**
- Failures go to DLQ
- Worker logs to CloudWatch
- Can scale to 2+ worker tasks

---

### C-03: Modify POST /api/layouts/generate to enqueue job
**Owner:** BE  
**Story Points:** 3  
**Dependencies:** C-02

Update endpoint to async pattern:
- Create Layout record with status='queued'
- Send message to SQS with layout details
- Return layout_id immediately (don't wait for processing)
- Response time <500ms

**Acceptance Criteria:**
- Endpoint returns quickly with layout_id
- Layout status='queued' initially
- Message in SQS queue
- No processing done in API request

---

### C-04: Add GET /api/layouts/{id}/status endpoint
**Owner:** BE  
**Story Points:** 2  
**Dependencies:** C-03

Create status checking endpoint:
- **Verify layout ownership through site → owner_user_id before returning status**
- **Return 404 if layout not owned by current user**
- Return layout status (queued, processing, completed, failed)
- If completed, include asset_count, road_length, cut_volume, fill_volume
- If failed, include error message
- Fast response (<100ms)

**Acceptance Criteria:**
- Returns current status for layouts owned by current user
- Completed layouts include summary metrics
- Failed layouts include error details
- **Returns 404 for other users' layouts (prevents information leakage)**

---

### C-05: Implement polling on frontend for layout status
**Owner:** FE  
**Story Points:** 3  
**Dependencies:** C-04

Update UI for async workflow:
- After "Generate Layout" clicked, show "Processing..." state
- Poll GET /api/layouts/{id}/status every 3 seconds
- When status='completed', fetch layout data and display on map
- If status='failed', show error message
- Progress indicator showing elapsed time
- Cancel button to stop polling

**Acceptance Criteria:**
- UI updates when layout completes
- Polling stops after completion or failure
- Loading state shows progress
- Error messages displayed clearly
- User can navigate away and come back (resume polling if still processing)

---

## Epic C2: Infrastructure Hardening

### C-06: Configure S3 lifecycle policies for temporary files
**Owner:** DevOps  
**Story Points:** 1  
**Dependencies:** A-01

Set up data retention policies:
- Lifecycle rule for `site-uploads/`: delete files >90 days old
- Lifecycle rule for `terrain/`: delete files >30 days old (cached DEMs)
- Lifecycle rule for `outputs/`: delete files >30 days old
- Tag objects appropriately for lifecycle management

**Acceptance Criteria:**
- Lifecycle policies active
- Old files automatically deleted
- Cost savings measurable after 30 days

---

### C-07: Tighten security groups and IAM policies
**Owner:** DevOps  
**Story Points:** 2  
**Dependencies:** A-01, A-02

Review and harden security:
- RDS security group: only allow 5432 from ECS tasks (remove bastion access if present)
- ECS task role: least privilege for S3 (read uploads, write outputs), SQS (send/receive), Secrets Manager (read)
- Remove any overly permissive policies (no * actions)
- Enable CloudTrail for API auditing (optional but recommended)

**Acceptance Criteria:**
- Security groups follow least privilege
- IAM policies scoped to minimum required permissions
- RDS not publicly accessible
- ECS tasks have separate roles for API vs worker

---

### C-08: Set up CloudWatch logging and basic alarms
**Owner:** DevOps  
**Story Points:** 3  
**Dependencies:** A-02, C-02

Configure monitoring:
- CloudWatch log groups for ECS tasks (API and worker)
- Log all requests (API gateway level or FastAPI middleware)
- Alarms:
  - ECS task failure (>2 failures in 5 min)
  - SQS DLQ depth >5 messages
  - RDS CPU >80% for 10 min
  - RDS storage <10% free space
- SNS topic for alarm notifications (email)

**Acceptance Criteria:**
- Logs visible in CloudWatch
- Alarms trigger correctly (test with simulated failure)
- Email notifications received
- Log retention set to 7 days

---

### C-09: Add health checks and graceful shutdown
**Owner:** BE  
**Story Points:** 2  
**Dependencies:** A-04, C-02

Improve service reliability:
- Enhance GET /health endpoint to check DB connectivity and return 503 if unhealthy
- Implement graceful shutdown in worker: finish current job before exiting
- Set stopTimeout in ECS task definition to 60 seconds
- Add readiness probe for ECS

**Acceptance Criteria:**
- Health check detects DB issues
- Worker completes in-progress job before shutdown
- No jobs lost during deployment
- ECS health checks pass

---

### C-10: Create basic runbook documentation
**Owner:** BE + DevOps  
**Story Points:** 2  
**Dependencies:** C-08

Document operational procedures:
- How to check service health (CloudWatch, ECS task status)
- How to restart services
- How to manually process a stuck job
- How to check SQS queues
- Common error scenarios and solutions
- Deployment checklist

**Acceptance Criteria:**
- Runbook document exists (Markdown in repo)
- Covers 5+ common scenarios
- Contact information for escalations
- Deployment steps documented

---

# Summary & Risk Assessment

## Task Count Summary

| Phase | Epics | Tasks | Total Story Points |
|-------|-------|-------|-------------------|
| **Phase A: Thin Vertical Slice** | 3 | 15 | 43 |
| **Phase B: Real Layout Engine MVP** | 5 | 11 | 43 |
| **Phase C: Async + Hardening** | 2 | 10 | 21 |
| **TOTAL** | 10 | **36 tasks** | **107 points** |

## Estimation

- **Team Size:** 1 FE, 1 BE, 1 Geo/Algo, 0.5 DevOps
- **Velocity:** ~15-20 story points per week (team of 3.5)
- **Duration:** 5-7 weeks total
  - Phase A: 2-3 weeks
  - Phase B: 2-3 weeks
  - Phase C: 1 week

## Biggest Risk Areas

### 1. **External API Dependencies (HIGH RISK)**
- **Tasks:** B-01 (DEM fetching)
- **Risk:** USGS 3DEP or OpenTopography APIs may have rate limits, downtime, or authentication issues
- **Mitigation:**
  - Test API access early in Phase A
  - Implement robust retry logic
  - Cache DEMs aggressively
  - Have fallback to lower-resolution SRTM data
  - Budget for potential API costs

### 2. **Geospatial Algorithm Performance (MEDIUM RISK)**
- **Tasks:** B-04 (asset placement), B-06 (routing), B-07 (cut/fill)
- **Risk:** Processing time may exceed 60-second timeout for large sites, causing poor UX or failures
- **Mitigation:**
  - Start with small test sites (<100 hectares)
  - Optimize raster operations (use NumPy vectorization, avoid loops)
  - Consider downsampling DEM if needed (trade accuracy for speed)
  - Phase C async processing addresses this, but test performance in Phase B
  - Set realistic scope: "It works for 90% of typical sites"

### 3. **PostGIS Spatial Query Performance (MEDIUM RISK)**
- **Tasks:** A-04, B-04 (spatial indexes)
- **Risk:** Slow queries on geometry operations, especially ST_Within, ST_Intersects
- **Mitigation:**
  - Ensure spatial indexes created (GIST indexes on GEOMETRY columns)
  - Test with realistic data volumes early
  - Use EXPLAIN ANALYZE to identify slow queries
  - Consider spatial denormalization if needed (store bboxes separately)

### 4. **File Upload Size & Format Handling (LOW-MEDIUM RISK)**
- **Tasks:** A-05, A-12 (KML/KMZ parsing)
- **Risk:** Users upload malformed KML, huge files, or files with complex geometries
- **Mitigation:**
  - Strict validation on file size (10MB limit) and format
  - Geometry simplification if >1000 vertices (Douglas-Peucker)
  - Clear error messages to users
  - Test with variety of KML files from different sources (Google Earth, QGIS, CAD)

### 5. **Async Worker Reliability (MEDIUM RISK)**
- **Tasks:** C-02, C-03 (SQS worker)
- **Risk:** Worker crashes mid-job, leaving layout stuck in 'processing' state
- **Mitigation:**
  - Use SQS visibility timeout + DLQ for failed jobs
  - Worker health checks and auto-restart
  - Manual admin endpoint to reset stuck layouts (not in task list, but add if needed)
  - Comprehensive error logging to diagnose failures

### 6. **Frontend-Backend Integration (LOW RISK)**
- **Tasks:** A-10, A-14, C-05 (auth, API integration)
- **Risk:** CORS issues, auth token handling bugs, API schema mismatches
- **Mitigation:**
  - Use OpenAPI spec to generate TypeScript client (or manual types)
  - Early integration testing (FE + BE working together in Phase A)
  - Mock API responses during FE development
  - Thorough error handling on both sides

### 7. **AWS Cost Overruns (LOW-MEDIUM RISK)**
- **Tasks:** A-01, B-01 (AWS infrastructure, DEM storage)
- **Risk:** S3 storage costs, RDS costs, or external API costs higher than expected
- **Mitigation:**
  - Monitor costs weekly with AWS Cost Explorer
  - Set up billing alarms ($50, $100, $200 thresholds)
  - Lifecycle policies to delete old files (C-06)
  - Use t3.micro RDS instance (easily upgradable if needed)
  - Consider spot instances for worker tasks in future

## Success Criteria for MVP Launch

- [ ] User can sign up, log in, upload KML, and see site on map (Phase A complete)
- [ ] Generated layouts respect terrain (assets on flat areas) (Phase B complete)
- [ ] Exports work (GeoJSON, KMZ, PDF downloadable) (Phase B complete)
- [ ] Layout generation runs asynchronously without blocking UI (Phase C complete)
- [ ] System handles 5 concurrent users without issues
- [ ] Average layout generation time <60 seconds for typical site (50 hectares, 30 assets)
- [ ] Zero critical bugs in production for 1 week post-launch

---

**Next Steps:**
1. Review and prioritize tasks with team
2. Assign ownership (FE/BE/Geo/DevOps)
3. Set up project board (Jira, Linear, GitHub Projects)
4. Begin Phase A with A-01 (infrastructure)
5. Schedule daily standups and weekly sprint reviews
