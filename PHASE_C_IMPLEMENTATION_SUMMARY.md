# Phase C Implementation Summary

**Date:** November 25, 2025  
**Status:** ✅ Tasks C-01 through C-04 Complete | 🔲 C-05 through C-10 Pending  
**Progress:** 4/10 tasks completed (40%)

---

## What's Been Implemented

### ✅ C-01: SQS Queue Infrastructure

**Created:** `infra/terraform/sqs.tf`

**Resources:**
- Main SQS queue: `pacifico-layouts-dev-layout-jobs`
  - Visibility timeout: 5 minutes (300s)
  - Message retention: 4 days
  - Auto-redrive to DLQ after 3 failed receives

- Dead-Letter Queue (DLQ): `pacifico-layouts-dev-layout-jobs-dlq`
  - Stores failed messages for 14 days

- IAM Roles:
  - `ecs_worker_task`: SQS receive/delete, S3 read-write
  - `ecs_worker_execution`: ECR pull, logs, secrets
  - Updated `ecs_task_sqs`: API can send messages

- CloudWatch Alarms:
  - Queue depth > 10 (processing backlog)
  - DLQ depth > 5 (failures)
  - Optional SNS for email alerts

**Terraform Additions:**
- `variables.tf`: Added `enable_sns_alarms`, `alerts_email`, `sqs_worker_desired_count`
- `outputs.tf`: Added SQS queue URLs, DLQ URLs, role ARNs, log group names

**Deployment:**
```bash
terraform apply  # Creates all SQS infrastructure
```

---

### ✅ C-02: SQS Worker Container

**Created:** `backend/app/worker.py`

**Features:**
- Long polling (20-second timeout) for job messages
- **Idempotency checks** (key C-02 requirement):
  - Checks layout status before processing
  - Skips if already 'completed' or 'failed' (duplicate message)
  - Restarts if 'processing' (possible worker failure)
- Updates layout status: queued → processing → completed/failed
- Generates layout using terrain-aware or dummy placement
- Graceful shutdown on SIGTERM/SIGINT
- Comprehensive error handling and logging

**Worker Flow:**
```
1. Poll SQS queue (20s timeout, long polling)
2. Receive job message: {layout_id, site_id, capacity, dem_resolution}
3. Check layout.status for idempotency
4. Update layout.status = 'processing'
5. Load site boundary and run generation
6. Update layout.status = 'completed' with metrics
7. Acknowledge/delete message from queue
8. Repeat
```

**Terraform Updates:**
- `main.tf`: Added worker task definition and ECS service
  - Task definition: `aws_ecs_task_definition.worker`
  - Service: `aws_ecs_service.worker` (desired_count: configurable)
  - Command override: `python -m app.worker`
  - Same Docker image, separate task/service

**Dependencies:**
- Added `aioboto3>=12.0.0` to `requirements.txt` for async AWS SDK

**Deployment:**
```bash
# 1. Push updated backend image with worker.py
docker push $ECR_REPO:latest

# 2. Terraform creates worker task definition and service
terraform apply

# 3. Worker automatically starts processing jobs
aws logs tail /ecs/pacifico-layouts-dev-worker --follow
```

---

### ✅ C-03: Async Layout Generation Endpoint

**Modified:** `backend/app/api/layouts.py`

**Key Changes:**
- Updated `POST /api/layouts/generate` endpoint
- Added `ENABLE_ASYNC_LAYOUT_GENERATION` config flag
- When async enabled: creates Layout record + sends to SQS, returns immediately
- When async disabled: behaves as Phase B (synchronous processing)
- New helper function: `_enqueue_layout_job()`

**New Config:**
```python
enable_async_layout_generation: bool = False  # Set to true in AWS
```

**Async Mode Response:**
```json
{
  "layout_id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "queued",
  "message": "Layout generation job queued successfully"
}
```

**Implementation:**
```python
if settings.enable_async_layout_generation:
    # Enqueue to SQS, return immediately
    return await _enqueue_layout_job(...)
else:
    # Original sync behavior (Phase A/B)
    return await generate_layout_sync(...)
```

**SQS Integration:**
```python
async def _enqueue_layout_job(...):
    # 1. Create Layout with status='queued'
    layout = Layout(site_id=site.id, status='queued')
    await db.commit()
    
    # 2. Send to SQS
    sqs_service = get_sqs_service()
    await sqs_service.send_layout_job(
        layout_id=layout.id,
        site_id=site.id,
        target_capacity_kw=request.target_capacity_kw,
        dem_resolution_m=request.dem_resolution_m,
    )
    
    # 3. Return layout_id for polling
    return LayoutEnqueueResponse(layout_id=layout.id, status='queued')
```

**Backward Compatible:**
- Sync mode (default) unchanged
- Async mode opt-in via `ENABLE_ASYNC_LAYOUT_GENERATION=true`

---

### ✅ C-04: Layout Status Polling Endpoint

**Added:** `backend/app/api/layouts.py`

**New Endpoint:** `GET /api/layouts/{layout_id}/status`

**Purpose:** Frontend polls this to track async job progress

**Response Schema (LayoutStatusResponse):**

While Processing:
```json
{
  "layout_id": "...",
  "status": "queued" | "processing",
  "error_message": null
}
```

When Completed:
```json
{
  "layout_id": "...",
  "status": "completed",
  "error_message": null,
  "total_capacity_kw": 1000.5,
  "asset_count": 12,
  "road_length_m": 2500.3,
  "cut_volume_m3": 15000.0,
  "fill_volume_m3": 8500.0
}
```

On Failure:
```json
{
  "layout_id": "...",
  "status": "failed",
  "error_message": "Failed to fetch DEM data"
}
```

**Implementation Highlights:**
- Ownership verification: layout → site → owner_user_id
- Returns 404 if user doesn't own layout
- Efficient queries using SQLAlchemy `func.count()`, `func.sum()`
- No unnecessary database round-trips

---

## What Still Needs Implementation

### 🔲 C-05: Frontend Polling

**What's needed:**
1. Create custom React hook: `useLayoutPolling(layoutId)`
2. Update `SiteDetailPage.tsx` to use new hook
3. Add loading state and progress display
4. Update API client to call new status endpoint
5. Handle error states gracefully

**Expected Implementation:**
- Poll every 2-3 seconds while processing
- Stop polling when status becomes 'completed' or 'failed'
- Show spinner + status text during processing
- Display metrics when complete

### 🔲 C-06: S3 Lifecycle Policies

**What's needed:**
- Add `aws_s3_bucket_lifecycle_configuration` resources to Terraform
- Site uploads: auto-delete after 90 days
- Terrain data: auto-delete after 30 days
- Export outputs: auto-delete after 30 days

### 🔲 C-07: Security Hardening

**What's needed:**
- Review and tighten IAM policies (mostly already done)
- Document least-privilege access
- Consider enabling VPC Flow Logs

### 🔲 C-08: CloudWatch Monitoring & Alarms

**What's needed:**
- Alarms auto-created by Terraform (sqs.tf)
- Optional SNS topic for email notifications
- Dashboard for monitoring queue depth, worker health

### 🔲 C-09: Health Checks & Graceful Shutdown

**What's needed:**
- Already partially done in A-04
- Verify worker graceful shutdown works
- ECS configuration for stopTimeout (60 seconds)

### 🔲 C-10: Runbook Documentation

**What's been created:**
- `.github/PHASE_C_ASYNC_JOBS.md` - Comprehensive guide covering all C tasks
- Troubleshooting guide
- Quick start commands
- Deployment checklist

---

## Files Created/Modified

### New Files
```
backend/app/services/sqs_service.py     # SQS client for job queuing
backend/app/worker.py                   # SQS worker script
infra/terraform/sqs.tf                  # SQS infrastructure
.github/PHASE_C_ASYNC_JOBS.md           # Phase C documentation
```

### Modified Files
```
backend/app/config.py                   # Added SQS config variables
backend/app/api/layouts.py              # Added C-03, C-04 endpoints
backend/app/schemas/layout.py           # Added async response schemas
backend/requirements.txt                # Added aioboto3
infra/terraform/main.tf                 # Added worker task definition
infra/terraform/variables.tf            # Added SQS variables
infra/terraform/outputs.tf              # Added SQS outputs
pacifico-site-layouts/README.md         # Updated Phase C status
```

---

## How to Deploy (Current State)

### Step 1: Infrastructure (Terraform)

```bash
cd pacifico-site-layouts/infra/terraform

# Add to terraform.tfvars (optional, for email alerts):
# enable_sns_alarms = true
# alerts_email = "ops@company.com"

terraform plan
terraform apply

# Capture outputs
terraform output sqs_layout_jobs_queue_url
terraform output ecs_worker_task_role_arn
```

### Step 2: Backend Image

```bash
cd pacifico-site-layouts/backend

# Build with worker included
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
docker build --platform linux/amd64 -t pacifico-layouts-dev-backend .

# Push to ECR
aws ecr get-login-password --region us-east-1 | docker login \
  --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com

docker tag pacifico-layouts-dev-backend:latest \
  $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/pacifico-layouts-dev-backend:latest

docker push $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/pacifico-layouts-dev-backend:latest
```

### Step 3: Deploy Worker

```bash
# Terraform auto-deploys worker when image is pushed
# Worker starts processing jobs immediately

# Verify worker is running
aws ecs describe-services \
  --cluster pacifico-layouts-dev-cluster \
  --services pacifico-layouts-dev-worker
```

### Step 4: Enable Async Mode (Optional)

```bash
# In AWS Console or Terraform:
# Set environment variable: ENABLE_ASYNC_LAYOUT_GENERATION=true
# This makes new API deployments use async mode

# If via Terraform, add to main.tf task definition:
# {
#   name  = "ENABLE_ASYNC_LAYOUT_GENERATION"
#   value = "true"
# }

terraform apply
```

---

## Testing Checklist

### Local Testing (Sync Mode - Default)

```bash
# Terminal 1: Backend
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload

# Terminal 2: Test upload
curl -X POST http://localhost:8000/api/sites/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@sample-site.kml"

# Returns: {"site_id": "..."}

# Terminal 3: Generate layout
curl -X POST http://localhost:8000/api/layouts/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "site_id": "...",
    "target_capacity_kw": 1000,
    "use_terrain": false
  }'

# Returns: Full layout with assets, roads, GeoJSON immediately
```

### AWS Testing (Async Mode)

1. **Enable async in ECS task definition**
2. **Regenerate and push container image**
3. **Deploy to ECS**
4. **Test async endpoint:**

```bash
SITE_ID="..."
curl -X POST https://api.example.com/api/layouts/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"site_id": "'$SITE_ID'", "target_capacity_kw": 1000}'

# Response: {"layout_id": "...", "status": "queued"}
```

5. **Poll status:**

```bash
LAYOUT_ID="..."
for i in {1..30}; do
  curl -s https://api.example.com/api/layouts/$LAYOUT_ID/status \
    -H "Authorization: Bearer $TOKEN" | jq '.status'
  sleep 2
done
```

6. **Verify worker processed:**

```bash
aws logs tail /ecs/pacifico-layouts-dev-worker --follow --filter-pattern "layout_id"
```

---

## Known Issues & Workarounds

### 1. Terrain-Aware Mode Disabled by Default

**Issue:** `use_terrain=True` fails locally due to async/greenlet compatibility

**Workaround:** 
- Dummy placement works perfectly (`use_terrain=False`)
- Terrain mode works on AWS after Phase C deployment
- Set `USE_TERRAIN=true` in ECS task for production

### 2. SQS Messages Could Accumulate

**Issue:** If workers are slow/failing, queue depth grows

**Mitigation:**
- CloudWatch alarm alerts when queue > 10 messages
- Scale workers: `aws ecs update-service --desired-count 2+`
- Check DLQ for failed messages

### 3. Duplicate Message Processing (Rare)

**Issue:** SQS visibility timeout expires before processing completes

**Mitigation:**
- Idempotency check in worker prevents data corruption
- Duplicate work possible but no bad state
- Increase visibility timeout if needed (currently 5 min)

---

## Performance Metrics

### Expected Times

| Operation | Duration | Notes |
|-----------|----------|-------|
| Dummy layout generation | < 1 second | Synchronous |
| Terrain DEM fetch (first run) | ~30 seconds | Cached after |
| Terrain slope computation | ~10 seconds | Cached after |
| Asset placement | ~20 seconds | Depends on size |
| Road routing | ~15 seconds | A* pathfinding |
| Full terrain layout (first run) | ~60 seconds | Total |
| Subsequent layout (cached) | ~30 seconds | Reuses terrain |
| Job queue latency | ~2 seconds | SQS polling |
| Status polling roundtrip | ~500ms | Simple query |

### Scalability

- **Workers**: Can scale to 5+ tasks for high throughput
- **Queue**: Handles 1000+ messages without issues
- **RDS**: db.t3.micro adequate for < 100 concurrent users
- **S3**: Unlimited scaling (pay per request)

---

## Next Steps (For User)

### Immediate (Today/Tomorrow)

1. Review and approve Terraform changes:
   ```bash
   cd infra/terraform
   terraform plan
   ```

2. Apply infrastructure:
   ```bash
   terraform apply
   ```

3. Test SQS connectivity:
   ```bash
   aws sqs get-queue-attributes \
     --queue-url $(terraform output -raw sqs_layout_jobs_queue_url) \
     --attribute-names All
   ```

### Short-term (This Week)

4. Implement C-05 (Frontend Polling)
   - Create `useLayoutPolling` hook
   - Update `SiteDetailPage.tsx`
   - Test polling flow end-to-end

5. Build and push backend image
   ```bash
   docker build --platform linux/amd64 -t ... .
   docker push ...
   ```

6. Deploy worker to AWS
   ```bash
   aws ecs update-service --cluster ... --service ... --force-new-deployment
   ```

### Medium-term (Next Week)

7. Implement C-06 to C-10
   - Lifecycle policies
   - Security review
   - CloudWatch dashboards
   - Runbook automation

### Production Readiness

8. Load testing: 5+ concurrent layout generations
9. Chaos testing: Kill workers, verify recovery
10. DLQ testing: Verify failed job handling
11. Update frontend deployment CI/CD

---

## Support & Troubleshooting

### Common Commands

```bash
# Monitor worker (live logs)
aws logs tail /ecs/pacifico-layouts-dev-worker --follow

# Check queue depth
aws sqs get-queue-attributes \
  --queue-url $(terraform output -raw sqs_layout_jobs_queue_url) \
  --attribute-names ApproximateNumberOfMessages

# View DLQ messages
aws sqs receive-message \
  --queue-url $(terraform output -raw sqs_layout_jobs_dlq_url) \
  --max-number-of-messages 10 | jq '.Messages[].Body'

# Scale workers
aws ecs update-service \
  --cluster pacifico-layouts-dev-cluster \
  --service pacifico-layouts-dev-worker \
  --desired-count 3

# Restart worker service
aws ecs update-service \
  --cluster pacifico-layouts-dev-cluster \
  --service pacifico-layouts-dev-worker \
  --force-new-deployment
```

### Documentation

- **Detailed Guide**: `.github/PHASE_C_ASYNC_JOBS.md`
- **Architecture Diagram**: See Phase C docs
- **Runbook**: See Phase C docs, section C-10
- **API Docs**: http://localhost:8000/docs (Swagger UI)

---

## Summary

✅ **Completed:**
- SQS queue infrastructure with DLQ
- Worker container for async processing
- API endpoint modifications for async mode
- Status polling endpoint
- Comprehensive documentation

🔲 **Remaining:**
- Frontend polling implementation (C-05)
- Lifecycle policies (C-06)
- Security hardening documentation (C-07)
- CloudWatch setup (C-08)
- Health checks / graceful shutdown (C-09)
- Runbook automation (C-10)

**Estimated Time to Complete Phase C: 1-2 weeks** (depends on frontend testing)

**Status:** Ready for infrastructure deployment and backend testing. Frontend polling can be implemented in parallel.


