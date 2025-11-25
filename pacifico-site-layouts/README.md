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
| Frontend Deployment (A-15) | ⏳ Next | S3 + CloudFront deployment |

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

1. **Phase A** — Thin vertical slice: Upload → dummy asset placement → map display
   - Infrastructure: ✅ Complete (A-01, A-02, A-03)
   - Backend foundation: ✅ Complete (A-04, A-08)
   - Backend API: ✅ Complete (A-05, A-06, A-07)
   - Frontend foundation: ✅ Complete (A-09, A-10, A-11, A-12, A-13, A-14)
   - Frontend deployment: ⏳ Next (A-15)

2. **Phase B** — Real layout engine: Terrain-aware placement, routing, cut/fill
   - DEM fetching & caching, slope computation, asset placement algorithm, road routing, cut/fill

3. **Phase C** — Async processing + production hardening
   - SQS worker for async layout generation, monitoring, documentation

See `MVP_Task_List.md` in the project root for detailed task breakdown and progress tracking.

## Current Progress

**Completed (Phase A: 14/15 tasks, 93%):**

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

**Frontend Integration (5 tasks):**
- ✅ A-10: Cognito authentication (login/signup/logout with email verification)
- ✅ A-11: Sites dashboard with file upload modal and site deletion
- ✅ A-12: KML/KMZ drag-and-drop upload component with progress feedback
- ✅ A-13: Leaflet map with site boundary display and auto-zoom
- ✅ A-14: Layout generation button with asset markers and road display on map

**Backend API Summary:**
- **Sites API**: POST/GET /api/sites, GET /api/sites/{id}, DELETE /api/sites/{id}, POST /api/sites/upload
- **Layouts API**: POST/GET /api/layouts, GET /api/layouts/{id}, DELETE /api/layouts/{id}
- **Auth API**: GET /api/me (get current user)
- **Health**: GET /health, GET /health/ready (with DB connectivity check)

**Frontend Features:**
- Complete authentication flow with Cognito and email verification
- Sites dashboard with upload, delete, and navigation
- Interactive map display of site boundaries and generated layouts
- Asset placement visualization with type-based color coding
- Road network display

**Next Steps (Final Phase A Task):**
1. **A-15** - Deploy frontend to S3 + CloudFront for production access

## License

Proprietary — Pacifico Energy Group

