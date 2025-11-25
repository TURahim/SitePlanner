# MVP Task List - Pacifico Energy Site Layouts Tool

**Project:** Geospatial layout tool for DG/microgrid/data center sites  
**Scope:** Three-phase MVP delivering cloud-deployed, multi-user, terrain-aware layout generation  
**Last Updated:** November 25, 2025 (A-01–A-15 Complete ✅ | B-01–B-04, B-06–B-10 Complete ✅ | **Phase B Backend 80% Complete** 🚀)

---

## Progress Summary

| Task | Status | Completed |
|------|--------|-----------|
| A-01 | ✅ Complete | Nov 24, 2025 |
| A-02 | ✅ Complete | Nov 24, 2025 |
| A-03 | ✅ Complete | Nov 25, 2025 |
| A-04 | ✅ Complete | Nov 25, 2025 |
| A-05 | ✅ Complete | Nov 25, 2025 |
| A-06 | ✅ Complete | Nov 25, 2025 |
| A-07 | ✅ Complete | Nov 25, 2025 |
| A-08 | ✅ Complete | Nov 25, 2025 |
| A-09 | ✅ Complete | Nov 25, 2025 |
| A-10 | ✅ Complete | Nov 25, 2025 |
| A-11 | ✅ Complete | Nov 25, 2025 |
| A-12 | ✅ Complete | Nov 25, 2025 |
| A-13 | ✅ Complete | Nov 25, 2025 |
| A-14 | ✅ Complete | Nov 25, 2025 |
| A-15 | ✅ Complete | Nov 25, 2025 |
| B-01 | ✅ Complete | Nov 25, 2025 |
| B-02 | ✅ Complete | Nov 25, 2025 |
| B-03 | ✅ Complete | Nov 25, 2025 |
| B-04 | ✅ Complete | Nov 25, 2025 |
| B-05 | ⏳ Pending | — |
| B-06 | ✅ Complete | Nov 25, 2025 |
| B-07 | ✅ Complete | Nov 25, 2025 |
| B-08 | ✅ Complete | Nov 25, 2025 |
| B-09 | ✅ Complete | Nov 25, 2025 |
| B-10 | ✅ Complete | Nov 25, 2025 |
| B-11 | ⏳ Pending | — |

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

### A-08: Implement Cognito JWT authentication middleware ✅ COMPLETE
**Owner:** BE  
**Story Points:** 3  
**Dependencies:** A-04  
**Completed:** November 25, 2025

Add authentication to protect API endpoints:
- ✅ Middleware to validate JWT tokens from Cognito
- ✅ Extract user identity (sub, email) from token claims
- ✅ Fetch Cognito public keys and verify signature
- ✅ Dependency injection for current_user in route handlers
- ✅ Protect all /api/* routes except /health
- ✅ Handle expired/invalid tokens with 401 response

**Implementation Details:**

| File | Purpose |
|------|---------|
| `app/api/auth.py` | JWT validation, JWKS fetching, user creation |
| `app/api/__init__.py` | Auth module exports |
| `requirements.txt` | Added `python-jose[cryptography]`, `httpx` |

**Features:**
- CognitoJWKS class manages JWKS endpoint caching (with refresh on key rotation)
- `decode_token()` verifies JWT with RS256 algorithm
- `get_current_user()` dependency auto-creates User on first login
- Auto-updates user email/name from Cognito claims
- `/api/me` endpoint for testing auth (returns current user info)

**Acceptance Criteria:**
- ✅ Requests with valid JWT succeed
- ✅ Requests without token return 401
- ✅ Expired tokens return 401
- ✅ current_user available in protected routes
- ✅ User auto-created on first login

---

### A-09: Initialize React + TypeScript project with routing ✅ COMPLETE
**Owner:** FE  
**Story Points:** 2  
**Dependencies:** None  
**Completed:** November 25, 2025

Set up frontend application structure:
- ✅ React + TypeScript with Vite build
- ✅ React Router v6 with protected routes
- ✅ AWS Amplify Cognito auth integration
- ✅ Axios HTTP client with auth interceptor
- ✅ Professional design system with dark theme

**Routes Implemented:**

| Route | Component | Protection | Status |
|-------|-----------|-----------|--------|
| `/` | LandingPage | Public | ✅ Landing with features |
| `/login` | LoginPage | Public | ✅ Email/password login |
| `/signup` | SignupPage | Public | ✅ Email verification flow |
| `/projects` | ProjectsPage | Protected | ✅ Dashboard with placeholders |
| `/sites/:id` | SiteDetailPage | Protected | ✅ Map + layout controls |

**UI Components:**

| Component | Purpose |
|-----------|---------|
| Layout | Header with nav, protected route wrapper |
| ProtectedRoute | Auth guard for protected routes |
| AuthContext | Cognito auth state (login, signup, logout) |
| AuthPages | Login/signup forms with validation |
| LandingPage | Public landing with hero + features |
| ProjectsPage | Sites list with upload modal |
| SiteDetailPage | Site detail with generate layout UI |

**Dependencies Installed:**
- `react-router-dom` - Client-side routing
- `axios` - HTTP client
- `@aws-amplify/auth` - Cognito SDK
- `@aws-amplify/core` - Amplify core
- `leaflet` + `react-leaflet` - Map library (prep for A-13)
- `@types/geojson` - Type definitions

**Design System:**
- Dark professional theme (Pacifico brand)
- Color palette: Teal accents (#10b981), dark surfaces (#0a0f14)
- Typography: IBM Plex Sans/Mono
- Responsive grid layouts
- Smooth animations and transitions

**Configuration:**
- `.env.example` with Cognito variables
- API client configured for backend integration
- CORS ready for cross-origin requests

**Acceptance Criteria:**
- ✅ Dev server runs at localhost:5173
- ✅ TypeScript compilation succeeds
- ✅ Navigation between routes works
- ✅ Environment variables load correctly
- ✅ Production build outputs to dist/

---

### A-05: Implement POST /api/sites/upload endpoint ✅ COMPLETE
**Owner:** BE  
**Story Points:** 5  
**Dependencies:** A-04  
**Completed:** November 25, 2025

Create endpoint to accept and process KML/KMZ files:
- ✅ Accept multipart/form-data with file upload (max 10MB)
- ✅ Validate file type (.kml, .kmz only)
- ✅ Parse KML/KMZ using fastkml library, extract first Polygon/MultiPolygon
- ✅ Convert to GeoJSON format
- ✅ Store original file in S3 (site-uploads bucket)
- ✅ Insert Site record with boundary geometry in PostGIS
- ✅ Calculate and store area_m2 using ST_Area with geography cast
- ✅ Return site_id and boundary GeoJSON

**Implementation Details:**

| File | Purpose |
|------|---------|
| `app/schemas/site.py` | Pydantic schemas for site endpoints |
| `app/services/kml_parser.py` | KML/KMZ parsing with fastkml + Shapely |
| `app/services/s3.py` | S3 upload and presigned URL service |
| `app/api/sites.py` | Sites router with upload, get, list, delete |

**Features:**
- KML/KMZ parser supports both file types with ZIP extraction
- Recursively searches KML structure for first polygon
- Automatic geometry validation with repair for invalid polygons
- S3 upload with metadata and automatic cleanup on delete
- Area calculation in square meters using PostGIS geography cast
- Multi-tenant isolation via owner_id checks
- 404 indistinguishable for missing/unauthorized sites

**Endpoints Implemented:**
- `POST /api/sites/upload` - Upload KML/KMZ file
- `GET /api/sites/{id}` - Get site with GeoJSON boundary
- `GET /api/sites` - List all sites for current user
- `DELETE /api/sites/{id}` - Delete site and S3 files

**Acceptance Criteria:**
- ✅ Valid KML uploads successfully, returns site_id
- ✅ Site record associated with current_user via owner_id
- ✅ Boundary stored correctly in PostGIS (ST_AsGeoJSON)
- ✅ Original file in S3 at `uploads/{site_id}/original.{ext}`
- ✅ Invalid files return 400 with clear error message
- ✅ Files >10MB rejected with 413
- ✅ 404 for non-existent or unauthorized sites

---

### A-06: Implement GET /api/sites/{id} endpoint ✅ COMPLETE
**Owner:** BE  
**Story Points:** 2  
**Dependencies:** A-04  
**Completed:** November 25, 2025 (included in A-05)

Create endpoint to retrieve site details:
- ✅ Query Site by ID AND owner_id = current_user.id
- ✅ Return site metadata (id, name, area_m2, created_at)
- ✅ Return boundary as GeoJSON using ST_AsGeoJSON
- ✅ Return 404 for missing or unauthorized sites (indistinguishable)

**Acceptance Criteria:**
- ✅ Returns site data with valid GeoJSON boundary for sites owned by current user
- ✅ 404 for non-existent sites or sites owned by other users
- ✅ Response time <500ms for typical site

---

### A-07: Implement POST /api/layouts/generate with dummy placement ✅ COMPLETE
**Owner:** BE  
**Story Points:** 3  
**Dependencies:** A-04, A-06  
**Completed:** November 25, 2025

Create endpoint that generates a dummy layout for a site:
- ✅ Accept site_id and target_capacity_kw config
- ✅ Load Site by site_id scoped to current_user (owner_id check)
- ✅ Return 404 if site not owned by user
- ✅ Create Layout record with status='completed'
- ✅ Generate 5-10+ dummy assets using grid-based placement within site boundary
- ✅ Assign types randomly based on weights (solar 60%, battery 20%, generator 15%, substation 5%)
- ✅ Ensure at least one substation for layouts with 3+ assets
- ✅ Insert Asset records with POINT geometries
- ✅ Generate star-topology roads connecting substation to all assets
- ✅ Return layout_id, assets, and roads as GeoJSON FeatureCollection

**Implementation Details:**

| File | Purpose |
|------|---------|
| `app/schemas/layout.py` | Pydantic schemas for layout endpoints |
| `app/services/layout_generator.py` | Dummy layout generation with grid placement |
| `app/api/layouts.py` | Layouts router with all endpoints |

**Features:**
- Grid-based asset placement within site boundary
- Random fallback for points outside grid
- Minimum distance enforcement between assets
- Capacity scaling to target_capacity_kw
- Configurable asset type weights
- Star topology road network (hub-and-spoke from substation)
- Length calculation approximated from coordinates (111km per degree)
- Full GeoJSON FeatureCollection output for frontend display
- Multi-tenant isolation via Site.owner_id chain

**Endpoints Implemented:**
- `POST /api/layouts/generate` - Generate layout for site
- `GET /api/layouts/{id}` - Get layout with assets and roads
- `GET /api/layouts` - List layouts (optional site_id filter)
- `DELETE /api/layouts/{id}` - Delete layout

**Acceptance Criteria:**
- ✅ Creates Layout and Asset records only for sites owned by current user
- ✅ Returns GeoJSON FeatureCollection with asset points and road lines
- ✅ Assets placed within site boundary (grid-based)
- ✅ Returns 404 if user attempts to generate layout for another user's site
- ✅ Endpoint completes in <1 second (synchronous in Phase A)
- ✅ Asset count scales with target_capacity_kw (5-15 assets)

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

### A-10: Implement Cognito authentication (login/signup/logout) ✅ COMPLETE
**Owner:** FE  
**Story Points:** 5  
**Dependencies:** A-09
**Completed:** November 25, 2025

Build authentication flow using AWS Amplify or Cognito SDK:
- ✅ Login page with email/password form
- ✅ Signup page with email/password verification flow
- ✅ AuthContext to manage authentication state
- ✅ Amplify SDK integration (replaces manual JWT handling)
- ✅ Axios interceptor to add Authorization header
- ✅ Redirect to /login if 401 response received
- ✅ Logout functionality to clear tokens and redirect

**Implementation Details:**
- AWS Amplify Auth SDK configured in `src/lib/amplify.ts`
- AuthContext manages user state via `useAuthenticator` hook
- Email verification flow with confirmation PIN (automatic redirection if account unverified)
- Cognito JWT automatically handled and injected by Amplify

**Security Note:** Amplify handles secure token storage internally. For production, consider configuring httpOnly cookies via Amplify settings.

**Acceptance Criteria:**
- ✅ User can sign up and receive verification email
- ✅ User can confirm email with PIN
- ✅ User can log in with verified account
- ✅ Tokens automatically sent with API requests via interceptor
- ✅ Logout clears auth state and redirects to login
- ✅ Protected routes redirect to login if not authenticated
- ✅ Unconfirmed accounts redirected to confirmation flow

---

### A-11: Create Project list and Site detail pages ✅ COMPLETE
**Owner:** FE  
**Story Points:** 3  
**Dependencies:** A-10
**Completed:** November 25, 2025

Build basic UI for project/site navigation:
- ✅ Projects/Sites page: list sites from `GET /api/sites` API
- ✅ Site detail page: display site boundary on Leaflet map
- ✅ Navigate from sites list → site detail
- ✅ Professional UI with light theme matching Pacifico brand
- ✅ Delete site functionality
- ✅ Upload KML/KMZ file modal

**Implementation Details:**
- `ProjectsPage.tsx` fetches and displays sites list with upload interface
- `SiteDetailPage.tsx` shows Leaflet map with site boundary polygon
- Responsive card-based layout with proper error handling
- Light theme with navy, blue, and gray color palette

**Acceptance Criteria:**
- ✅ Can navigate to site detail page
- ✅ Page displays site metadata and boundary on map
- ✅ Can delete sites (with confirmation)
- ✅ Can upload new KML/KMZ files
- ✅ Clean, professional UI matching Pacifico brand
- ✅ Proper error handling and loading states

---

### A-12: Implement KML/KMZ upload component ✅ COMPLETE
**Owner:** FE  
**Story Points:** 3  
**Dependencies:** A-11
**Completed:** November 25, 2025

Create file upload interface:
- ✅ Drag-and-drop zone for KML/KMZ files in modal
- ✅ File validation (type and size checks)
- ✅ Upload progress indicator
- ✅ Calls `POST /api/sites/upload` with FormData
- ✅ Success automatically refreshes sites list
- ✅ Error handling with user-friendly messages

**Implementation Details:**
- Upload modal component in `ProjectsPage.tsx`
- Accepts .kml and .kmz file types
- 10MB file size limit enforced
- Uses `sites.upload()` from API service
- Auto-refreshes sites list on successful upload

**Acceptance Criteria:**
- ✅ Drag-and-drop works for .kml/.kmz files
- ✅ Upload feedback shown with spinner
- ✅ Success automatically refreshes sites list
- ✅ Errors display user-friendly messages
- ✅ File size limit enforced (10MB)
- ✅ File type validation prevents invalid uploads

---

### A-13: Display site boundary on Leaflet map ✅ COMPLETE
**Owner:** FE  
**Story Points:** 3  
**Dependencies:** A-11, A-06
**Completed:** November 25, 2025

Create interactive map component:
- ✅ Initialize Leaflet map with OpenStreetMap tiles
- ✅ Fetch site boundary from `GET /api/sites/{id}`
- ✅ Display boundary as polygon overlay (blue stroke, semi-transparent fill)
- ✅ Auto-zoom map to fit boundary using `geoJSON.getBounds()`
- ✅ Add basic controls (zoom, attribution)
- ✅ Leaflet icons properly configured

**Implementation Details:**
- React-Leaflet integration in `SiteDetailPage.tsx`
- GeoJSON polygon rendered with custom styling
- Map automatically centers and zooms on site boundary
- Fixed Leaflet marker icons for proper rendering

**Map Tile Strategy Note:** Using public OpenStreetMap tiles is acceptable for the MVP. For production usage at scale, plan to switch to a paid tile provider (Mapbox, MapTiler) or self-hosted tile server to respect OSM usage limits and improve reliability.

**Acceptance Criteria:**
- ✅ Map displays with OSM tiles
- ✅ Site boundary renders as polygon
- ✅ Map auto-zooms to fit boundary
- ✅ Boundary properly styled with blue outline
- ✅ No Leaflet icon errors

---

### A-14: Add "Generate Layout" button with results display ✅ COMPLETE
**Owner:** FE  
**Story Points:** 3  
**Dependencies:** A-13, A-07
**Completed:** November 25, 2025

Implement layout generation UI:
- ✅ "Generate Layout" button on site detail page with capacity input
- ✅ Call `POST /api/layouts/generate` with site_id and target capacity
- ✅ Display loading spinner during request
- ✅ On success, add asset markers (colored by type) to map
- ✅ Display roads as polylines on map
- ✅ Legend showing asset type colors and counts
- ✅ Display total capacity in summary panel

**Implementation Details:**
- Layout generation triggered from `SiteDetailPage.tsx`
- Target capacity configurable (default 1000 kW)
- Assets displayed as markers with color-coding:
  - 🟡 Solar (60% of assets)
  - 🟣 Battery (20% of assets)
  - 🔴 Generator (15% of assets)
  - ⭐ Substation (5% of assets)
- Roads displayed as connected polylines
- Summary shows asset count, total capacity, total road length

**Acceptance Criteria:**
- ✅ Button triggers layout generation
- ✅ Assets appear as colored markers on map
- ✅ Roads appear as polylines connecting assets
- ✅ Legend shows asset type colors and counts
- ✅ Loading state shown during generation
- ✅ Summary panel displays layout metrics

---

### A-15: Deploy frontend to S3 + CloudFront ✅ COMPLETE
**Owner:** DevOps  
**Story Points:** 2  
**Dependencies:** A-09, A-02  
**Completed:** November 25, 2025

Configure static site hosting with CloudFront CDN:
- ✅ CloudFront distribution with Origin Access Control (OAC)
- ✅ S3 bucket configured for CloudFront-only access (secure)
- ✅ SPA routing support (custom error responses for 403/404)
- ✅ Cache optimization (1 year for hashed assets, no-cache for index.html)
- ✅ HTTPS with automatic redirect
- ✅ GitHub Actions workflow updated with CloudFront invalidation
- ✅ Optional custom domain support (via variables)

**Implementation Details:**

| File | Purpose |
|------|---------|
| `infra/terraform/cloudfront.tf` | CloudFront distribution, OAC, S3 bucket policy |
| `.github/workflows/frontend-deploy.yml` | Updated with CloudFront invalidation |
| `.github/README.md` | Updated setup instructions |

**Terraform Resources Created:**
- `aws_cloudfront_distribution.frontend` - CDN distribution
- `aws_cloudfront_origin_access_control.frontend` - OAC for secure S3 access
- `aws_s3_bucket_policy.frontend_assets_cloudfront` - Allow CloudFront access

**New Terraform Outputs:**
- `cloudfront_distribution_id` - For cache invalidation
- `cloudfront_domain_name` - CloudFront URL
- `frontend_url` - Full HTTPS URL

**GitHub Secrets Required:**
| Secret | Description |
|--------|-------------|
| `CLOUDFRONT_DISTRIBUTION_ID` | From `terraform output cloudfront_distribution_id` |

**Deployment Steps:**

1. Apply Terraform to create CloudFront:
```bash
cd pacifico-site-layouts/infra/terraform
terraform plan
terraform apply
```

2. Get CloudFront distribution ID and add to GitHub secrets:
```bash
terraform output cloudfront_distribution_id
# Add to GitHub → Settings → Secrets → CLOUDFRONT_DISTRIBUTION_ID
```

3. Get the frontend URL:
```bash
terraform output frontend_url
# Output: https://d1234567890.cloudfront.net
```

4. Push to main branch to trigger deployment

**Acceptance Criteria:**
- ✅ Frontend accessible at https://{cloudfront-domain}
- ✅ HTTPS with valid certificate (CloudFront default)
- ✅ CloudFront caching working (1 year for assets)
- ✅ SPA routing works (client-side navigation)
- ✅ GitHub Actions invalidates cache on deploy
- ✅ Build + deploy time <4 minutes

---

# Phase B: Real Layout Engine MVP

**Goal:** Replace dummy layout with terrain-aware placement, heuristic routing, cut/fill calculation, and exports.

---

## Epic B1: Terrain & DEM Pipeline

### B-01: Implement DEM fetching for site bounding box ✅ COMPLETE
**Owner:** Geo/Algo  
**Story Points:** 5  
**Dependencies:** A-04  
**Completed:** November 25, 2025

Create service to fetch elevation data with caching:
- ✅ Check TerrainCache table for existing DEM entry for this site_id with required resolution
- ✅ If valid cached DEM exists in S3, reuse it and skip external API call
- ✅ Calculate site bounding box from Shapely Polygon
- ✅ Call USGS 3DEP via py3dep library with bbox parameters
- ✅ Request GeoTIFF format at 10-30m resolution (configurable)
- ✅ Download DEM to memory using MemoryFile
- ✅ Store DEM in S3 at `terrain/{site_id}/dem.tif`
- ✅ Create/update TerrainCache record (site_id, type='elevation', s3_key, resolution_m, created_at)
- ✅ Async implementation with httpx client

**Implementation:**
- `app/services/dem_service.py`: `DEMService` class with `get_dem_for_site()` method
- Uses `py3dep>=0.16.0` for USGS 3DEP data access
- Rasterio for GeoTIFF handling
- Comprehensive error handling and logging

**Acceptance Criteria (All Met):**
- ✅ Fetches DEM for test sites (US locations with CONUS coverage)
- ✅ DEM covers entire site boundary with buffer
- ✅ GeoTIFF stored in S3 with correct georeference (EPSG:4326)
- ✅ Subsequent requests for same site reuse cached DEM without hitting external APIs
- ✅ Cache entry created in TerrainCache table with S3 reference

---

### B-02: Compute slope raster from DEM using GDAL/Rasterio ✅ COMPLETE
**Owner:** Geo/Algo  
**Story Points:** 3  
**Dependencies:** B-01  
**Completed:** November 25, 2025

Process DEM to generate slope map with caching:
- ✅ Check TerrainCache for existing slope raster for this site_id
- ✅ If cached slope exists, load from S3 and skip recomputation
- ✅ Load DEM from S3 using Rasterio
- ✅ Compute slope in degrees using NumPy gradient (finite difference method)
- ✅ Handle geographic coordinates with latitude-aware cell size conversion (111km/degree)
- ✅ Save slope GeoTIFF to S3 at `terrain/{site_id}/slope.tif`
- ✅ Update TerrainCache with slope reference (type='slope')

**Implementation:**
- `app/services/slope_service.py`: `SlopeService` class with `get_slope_for_site()` method
- NumPy gradient for efficient computation: `slope = arctan(sqrt(dx² + dy²)) * 180/π`
- Handles nodata values (-9999 convention)
- LZW compression for GeoTIFF storage

**Acceptance Criteria (All Met):**
- ✅ Slope raster has same extent/resolution as DEM
- ✅ Values in degrees (0-90, -9999 for nodata)
- ✅ Processing time <30 seconds for typical site on first run
- ✅ Subsequent layout generations reuse cached slope in <2 seconds
- ✅ Cache entry in TerrainCache allows skipping recomputation
- ✅ Logging shows min/max/mean slope statistics

---

### B-03: Add terrain processing to layout generation workflow ✅ COMPLETE
**Owner:** BE  
**Story Points:** 2  
**Dependencies:** B-02, A-07  
**Completed:** November 25, 2025

Integrate terrain processing into POST /api/layouts/generate:
- ✅ Modified `POST /api/layouts/generate` endpoint to support terrain-aware generation
- ✅ Added request parameters: `use_terrain` (bool, default=True), `dem_resolution_m` (10 or 30)
- ✅ Before asset placement, check TerrainCache for existing DEM and slope
- ✅ If cached terrain data exists, load from S3 (fast path, ~5 sec)
- ✅ If not cached, trigger DEM fetch and slope calculation (slow path, ~60 sec first run)
- ✅ Pass slope raster to asset placement algorithm
- ✅ Update Layout record with `terrain_processed=true` and cut/fill volumes
- ✅ Fallback to dummy placement if terrain unavailable (graceful degradation)

**Implementation:**
- `app/api/layouts.py`: Refactored `generate_layout()` with `_generate_terrain_aware_layout()` and `_generate_dummy_layout()` helpers
- Async chain: DEM fetch → slope compute → asset placement → road routing → cut/fill
- Comprehensive error handling with automatic fallback

**Acceptance Criteria (All Met):**
- ✅ Layout generation includes terrain processing by default
- ✅ Slope data available for subsequent steps
- ✅ First layout generation for a site takes ~60 seconds (includes DEM fetch + slope compute)
- ✅ Subsequent layouts for same site take <30 seconds (reuses cached terrain)
- ✅ Fallback to dummy placement if DEM unavailable
- ✅ Layout status: PROCESSING → COMPLETED or FAILED

---

## Epic B2: Real Asset Placement

### B-04: Implement heuristic asset placement algorithm ✅ COMPLETE
**Owner:** Geo/Algo  
**Story Points:** 8  
**Dependencies:** B-02  
**Completed:** November 25, 2025

Replace dummy placement with terrain-aware heuristic:
- ✅ Rasterize site boundary to grid matching DEM resolution
- ✅ Load slope raster and create buildable masks (slope < 15° for solar, <5° for battery/generator)
- ✅ Define asset types with constraints (footprint size, slope tolerance, capacity per unit)
- ✅ Place assets using intelligent greedy algorithm:
  - Substation: find centroid of flattest buildable region (<3°)
  - Battery/generators: near substation, prioritize flatness + proximity
  - Solar arrays: fill remaining capacity in buildable areas
- ✅ Enforce minimum spacing (15m between assets) using exclusion masks
- ✅ Store Asset records with POINT geometries, elevation, slope
- ✅ Return list of placed assets with types, positions, capacities, terrain data

**Implementation:**
- `app/services/terrain_layout_generator.py`: `TerrainAwareLayoutGenerator` class
- Slope-based buildable masks per asset type
- Centroid + nearest-available position finding for optimal placement
- Configurable: `MIN_SPACING_M=15.0`, slope limits per type
- Full GeoJSON FeatureCollection output

**Acceptance Criteria (All Met):**
- ✅ Assets only placed in buildable areas (slope constraint enforced)
- ✅ Minimum 15m spacing between assets
- ✅ Target capacity achieved (±20%)
- ✅ No assets outside site boundary
- ✅ Algorithm completes in <20 seconds for 50-asset layout
- ✅ Buildable area percentages logged per asset type
- ✅ Elevation and slope captured for each asset

---

### B-05: Create unit tests for asset placement ⏳ PENDING
**Owner:** Geo/Algo  
**Story Points:** 3  
**Dependencies:** B-04

Write tests to validate placement logic:
- Test with synthetic flat terrain → all assets placed
- Test with steep terrain → only flat areas used
- Test boundary enforcement → no assets outside polygon
- Test spacing constraint → verify min distance between assets
- Test capacity target → verify actual vs target capacity

**Status:** Ready for implementation - all core placement logic complete and testable

**Acceptance Criteria:**
- 5+ test cases covering key scenarios
- All tests pass
- Test suite runs in <10 seconds
- Mock terrain data (simple NumPy arrays)

---

## Epic B3: Road Routing

### B-06: Implement slope-weighted road routing algorithm ✅ COMPLETE
**Owner:** Geo/Algo  
**Story Points:** 5  
**Dependencies:** B-04  
**Completed:** November 25, 2025

Generate road network connecting assets:
- ✅ Identify substation as root node (or first asset)
- ✅ Connect all assets to substation using A* pathfinding
- ✅ Slope-weighted cost surface: `cost = 1 + (slope / max_grade)²`
- ✅ Prohibitive cost for slopes >15% to strongly prefer flat paths
- ✅ 8-connected neighborhood search (allows diagonal movement)
- ✅ Store Road records as LINESTRING geometries
- ✅ Calculate max grade along each road segment
- ✅ Return roads with length (meters) and max_grade_pct

**Implementation:**
- `app/services/terrain_layout_generator.py`: `_find_path_astar()` and `_generate_roads_terrain_aware()`
- A* heuristic: Euclidean distance to end point
- Cost function penalizes steep slopes, nearly prohibits >15% grades
- Per-road maximum grade tracking for compliance checking

**Acceptance Criteria (All Met):**
- ✅ All assets connected by road network
- ✅ Roads generally avoid steep slopes (A* optimization)
- ✅ No duplicate road segments (star topology from hub)
- ✅ Road lengths calculated per segment
- ✅ Algorithm completes in <20 seconds for typical layout
- ✅ Max grade percentage reported per road
- ✅ Straight-line fallback if A* fails to converge

---

## Epic B4: Cut/Fill Calculation

### B-07: Compute cut/fill volumes for pads and roads ✅ COMPLETE
**Owner:** Geo/Algo  
**Story Points:** 5  
**Dependencies:** B-04, B-06  
**Completed:** November 25, 2025

Calculate earthwork requirements:
- ✅ Create "proposed graded surface" for asset pads:
  - For each asset, define level pad at asset's target elevation (configurable size per type)
  - Pad sizes: substation 25m, battery 20m, generator 15m, solar 35m
- ✅ Use NumPy to compute elevation difference per cell:
  - `dz = DEM_before - DEM_proposed` (in meters)
- ✅ Calculate per-cell volume:
  - `cell_area = resolution_x * resolution_y` (in m²)
  - `cell_volume_m3 = dz * cell_area` (in m³)
- ✅ Accumulate totals:
  - If `dz > 0`: cut (excavation)
  - If `dz < 0`: fill (backfill)
- ✅ Return total cut volume (m³), total fill volume (m³), per-asset breakdown
- ✅ Store in Layout record (cut_volume_m3, fill_volume_m3)

**Implementation:**
- `app/services/terrain_layout_generator.py`: `_compute_cut_fill()` method
- Returns `CutFillResult` dataclass with totals and per-asset breakdown
- Handles nodata values (-9999 convention)
- Comprehensive logging of volumes

**Acceptance Criteria (All Met):**
- ✅ Cut/fill volumes reported in cubic meters (m³)
- ✅ Volumes non-zero for non-flat terrain
- ✅ Volumes physically reasonable (tested with realistic sites)
- ✅ Per-asset breakdown sums to total
- ✅ Calculation completes in <5 seconds
- ✅ Layout record updated with total volumes

---

## Epic B5: Export Outputs

### B-08: Generate GeoJSON export for assets and roads ✅ COMPLETE
**Owner:** BE  
**Story Points:** 2  
**Dependencies:** B-04, B-06  
**Completed:** November 25, 2025

Create endpoint to export layout data:
- ✅ GET `/api/layouts/{id}/export/geojson` endpoint implemented
- ✅ Verify layout ownership through site → owner_user_id chain before allowing export
- ✅ Return 404 if layout not owned by current user (same as other endpoints)
- ✅ Query all assets and roads for layout with ownership check
- ✅ Convert to GeoJSON FeatureCollection with separate features for each asset and road
- ✅ Include properties: type, capacity_kw, elevation, slope, length, max_grade, etc.
- ✅ Store GeoJSON in S3 at `outputs/{layout_id}/layout.geojson`
- ✅ Return presigned URL for download (1 hour expiration)

**Implementation:**
- `app/api/exports.py`: `export_geojson()` endpoint
- `app/services/export_service.py`: `ExportService.export_geojson()` method
- Uses async S3 upload and presigned URL generation

**Acceptance Criteria (All Met):**
- ✅ Valid GeoJSON FeatureCollection with all features
- ✅ Opens correctly in QGIS and other GIS tools
- ✅ Properties include all relevant attributes (terrain data)
- ✅ Presigned URL expires in 1 hour
- ✅ Only exports layouts owned by current user
- ✅ Includes layout metadata in FeatureCollection properties

---

### B-09: Generate KMZ export for Google Earth ✅ COMPLETE
**Owner:** BE  
**Story Points:** 3  
**Dependencies:** B-04, B-06  
**Completed:** November 25, 2025

Create KMZ export:
- ✅ GET `/api/layouts/{id}/export/kmz` endpoint implemented
- ✅ Use simplekml library to create KML structure
- ✅ Add Placemarks for each asset with colored icons by type:
  - 🟡 Yellow: Solar arrays
  - 🟣 Purple/Magenta: Batteries
  - 🔴 Red: Generators
  - 🔵 Blue: Substations
- ✅ Add LineStrings for roads (yellow lines with width 3)
- ✅ Add site boundary polygon (red outline, unfilled)
- ✅ Include descriptions with asset metadata (type, capacity, elevation, slope)
- ✅ Package as KMZ (zipped KML with doc.kml inside)
- ✅ Store in S3 and return presigned URL

**Implementation:**
- `app/api/exports.py`: `export_kmz()` endpoint
- `app/services/export_service.py`: `ExportService.export_kmz()` method
- Uses `simplekml>=1.3.6` for KML generation
- Proper AABBGGRR color format for KML

**Acceptance Criteria (All Met):**
- ✅ KMZ opens in Google Earth
- ✅ Assets display with correct colored icons
- ✅ Roads and boundary visible with proper styling
- ✅ Descriptions show metadata (type, capacity, elevation, slope, grade)
- ✅ File properly compressed as ZIP

---

### B-10: Generate PDF report with map and summary ✅ COMPLETE
**Owner:** BE  
**Story Points:** 5  
**Dependencies:** B-04, B-06, B-07  
**Completed:** November 25, 2025

Create basic PDF report:
- ✅ GET `/api/layouts/{id}/export/pdf` endpoint implemented
- ✅ Use ReportLab library for PDF generation
- ✅ Include:
  - Site name and generation timestamp
  - Site Summary table: area, total capacity, asset count, road network length, cut/fill volumes
  - Asset Inventory table: asset type, count, total capacity by type
  - Asset Details table (if ≤20 assets): name, type, capacity, elevation, slope
  - Professional styling with color scheme
- ✅ Store PDF in S3 at `outputs/{layout_id}/report.pdf`
- ✅ Return presigned URL

**Implementation:**
- `app/api/exports.py`: `export_pdf()` endpoint
- `app/services/export_service.py`: `ExportService.export_pdf()` method
- Uses `reportlab>=4.2.0` for PDF generation
- Professional table styling with header styling

**Acceptance Criteria (All Met):**
- ✅ PDF generates successfully
- ✅ Tables formatted properly with styling
- ✅ File size <3MB
- ✅ Generation time <20 seconds
- ✅ All metadata correctly included

---

### B-11: Add export buttons to frontend ⏳ PENDING
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

**Status:** Ready for implementation - all backend APIs complete

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

- [x] User can sign up, log in, upload KML, and see site on map (Phase A complete) ✅
- [ ] Generated layouts respect terrain (assets on flat areas) (Phase B complete)
- [ ] Exports work (GeoJSON, KMZ, PDF downloadable) (Phase B complete)
- [ ] Layout generation runs asynchronously without blocking UI (Phase C complete)
- [ ] System handles 5 concurrent users without issues
- [ ] Average layout generation time <60 seconds for typical site (50 hectares, 30 assets)
- [ ] Zero critical bugs in production for 1 week post-launch

---

## Phase A Summary - Complete ✅

**Achievements:**
- ✅ Multi-user cloud infrastructure (VPC, RDS, S3, Cognito, ECS)
- ✅ Automated CI/CD with GitHub Actions (backend & frontend)
- ✅ Full authentication flow with Cognito (signup, email verification, login)
- ✅ KML/KMZ upload with geospatial processing
- ✅ Interactive map with Leaflet and site boundary visualization
- ✅ Dummy layout generation (grid-based asset placement, star-topology roads)
- ✅ Production frontend deployment to CloudFront (HTTPS, SPA routing, global CDN)

**Deployment:**
- Backend: `http://pacifico-layouts-dev-alb-980890644.us-east-1.elb.amazonaws.com`
- Frontend: `https://d178b416db7o5o.cloudfront.net`
- Database: PostgreSQL 15 + PostGIS in RDS (private)

**Next Steps (Phase B - Real Layout Engine):**

Phase B replaces dummy layout generation with terrain-aware placement, real routing, and cut/fill calculation.

| Task | Priority | Dependencies |
|------|----------|--------------|
| B-01: DEM fetching & caching | High | A-04 |
| B-02: Slope computation | High | B-01 |
| B-04: Terrain-aware asset placement | High | B-02 |
| B-06: Road routing algorithm | High | B-04 |
| B-07: Cut/fill calculation | High | B-04, B-06 |
| B-08 to B-11: Exports & UI | Medium | B-04, B-06, B-07 |

**Estimated Duration:** 2-3 weeks (depending on team size and geospatial algorithm complexity)

---

## Phase B Summary - Core Backend Complete ✅ (80% Done)

**Achievements (Backend):**
- ✅ **B-01: DEM fetching** - USGS 3DEP integration with TerrainCache for efficient reuse
- ✅ **B-02: Slope computation** - NumPy-based gradient calculation from DEM rasters
- ✅ **B-03: Terrain integration** - Modified layout generation to use terrain by default with graceful fallback
- ✅ **B-04: Asset placement** - Slope-constrained intelligent placement with A* optimization
- ✅ **B-06: Road routing** - Slope-weighted A* pathfinding for optimal road networks
- ✅ **B-07: Cut/fill volumes** - Earthwork calculations for each asset pad
- ✅ **B-08: GeoJSON export** - Full FeatureCollection with terrain properties
- ✅ **B-09: KMZ export** - Google Earth compatible with colored markers
- ✅ **B-10: PDF reports** - Professional reports with asset inventory & cut/fill summary

**Remaining (Frontend):**
- ⏳ **B-05: Unit tests** - Test suite for asset placement algorithms
- ⏳ **B-11: Export UI** - Frontend dropdown menu for downloads

**New Services Created:**
- `DEMService`: Elevation data fetching & caching via py3dep
- `SlopeService`: Slope raster computation with caching
- `TerrainAwareLayoutGenerator`: Intelligent asset/road placement with terrain constraints
- `ExportService`: GeoJSON, KMZ, PDF export generation

**New API Endpoints:**
- `POST /api/layouts/generate` (enhanced): Now supports terrain-aware placement by default
- `GET /api/layouts/{id}/export/geojson`: Download layout as GeoJSON
- `GET /api/layouts/{id}/export/kmz`: Download layout as KMZ
- `GET /api/layouts/{id}/export/pdf`: Download layout as PDF report

**Database Migrations:**
- `002_phase_b_terrain_columns.py`: Added `slope_deg` to assets, `max_grade_pct` to roads

**Next Steps (Frontend B-05 & B-11):**
1. Create unit test suite for placement algorithms (B-05)
2. Add export dropdown UI to frontend (B-11)
3. Phase C planning: Async job processing & production hardening
