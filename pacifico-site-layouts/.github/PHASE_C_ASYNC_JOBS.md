# Phase C: Async Layout Generation & Minimal Hardening

## Overview

Phase C implements asynchronous layout generation jobs and production hardening for the Pacifico Site Layouts platform.

**Key Changes:**
- Layout generation runs asynchronously via SQS queue (C-01 to C-05)
- Frontend polls status endpoint for progress updates
- Worker processes jobs reliably with idempotency checks
- Infrastructure monitoring and alarms (C-08)
- Security hardening and graceful shutdown (C-07, C-09)

**Deployment Checklist:**
1. Create SQS infrastructure (C-01)
2. Build and deploy worker container (C-02)
3. Enable async mode in API (C-03)
4. Update frontend for polling (C-05)
5. Configure lifecycle policies (C-06)
6. Harden security groups (C-07)
7. Set up CloudWatch alarms (C-08)

---

## C-01: SQS Queue Infrastructure

### Created Resources

**File:** `infra/terraform/sqs.tf`

- **Main Queue**: `pacifico-layouts-dev-layout-jobs`
  - Visibility timeout: 5 minutes (300 seconds)
  - Message retention: 4 days
  - Auto-redrive to DLQ after 3 failed receives

- **Dead-Letter Queue (DLQ)**: `pacifico-layouts-dev-layout-jobs-dlq`
  - Message retention: 14 days
  - Stores messages that fail 3 times

- **IAM Roles**:
  - `ecs_worker_task`: Task permissions for SQS, S3
  - `ecs_worker_execution`: Execution permissions for ECR, logs, secrets
  - `ecs_task_sqs`: Updated API task role to send messages

- **CloudWatch Alarms**:
  - Queue depth > 10 messages (possible processing backlog)
  - DLQ depth > 5 messages (indicates failures)
  - Optional SNS topic for email notifications

### Deployment

```bash
# 1. Update terraform.tfvars if needed
cd pacifico-site-layouts/infra/terraform
cat terraform.tfvars

# 2. Plan and apply
terraform plan
terraform apply

# 3. Capture outputs
terraform output sqs_layout_jobs_queue_url
terraform output sqs_layout_jobs_queue_arn
terraform output ecs_worker_task_role_arn

# 4. Test queue access (optional)
aws sqs get-queue-attributes \
  --queue-url $(terraform output -raw sqs_layout_jobs_queue_url) \
  --attribute-names All
```

### Monitoring

```bash
# Check queue depth
aws sqs get-queue-attributes \
  --queue-url $(terraform output -raw sqs_layout_jobs_queue_url) \
  --attribute-names ApproximateNumberOfMessages

# List DLQ messages (failed jobs)
aws sqs receive-message \
  --queue-url $(terraform output -raw sqs_layout_jobs_dlq_url) \
  --max-number-of-messages 10
```

---

## C-02: SQS Worker Container

### Architecture

The worker is a standalone Python service that:
1. Polls SQS queue for layout generation jobs
2. Implements idempotency: checks if layout already processed
3. Updates layout status to 'processing'
4. Generates layout (terrain-aware or dummy)
5. Acknowledges message on success
6. Sends failed messages to DLQ

### Implementation

**File:** `backend/app/worker.py`

**Key Features:**
- Long polling (20-second timeout) for efficiency
- Graceful shutdown on SIGTERM/SIGINT
- Comprehensive error handling and logging
- Idempotency checks prevent duplicate work
- Separate database session per job

**Idempotency (C-02 requirement):**
```python
# Before processing, check layout status
if layout.status in ['completed', 'failed']:
    # Already done - skip (duplicate message)
    acknowledge_and_return()
    
if layout.status == 'processing':
    # May have restarted after failure - try again
    set_status_to_processing()
```

### Deployment

**Step 1: Build Docker image with worker**

Worker runs in same Docker image as API. Ensure `Dockerfile` includes app.worker module:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app/ /app/app/
```

**Step 2: Deploy to AWS**

Worker runs as separate ECS service with different command:

```hcl
# Terraform creates:
# - aws_ecs_task_definition.worker (command: python -m app.worker)
# - aws_ecs_service.worker (desired_count: 1)
# - CloudWatch logs group: /ecs/pacifico-layouts-dev-worker
```

```bash
# Push updated backend image to ECR
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
docker build --platform linux/amd64 -t pacifico-layouts-dev-backend .
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com
docker tag pacifico-layouts-dev-backend:latest $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/pacifico-layouts-dev-backend:latest
docker push $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/pacifico-layouts-dev-backend:latest

# Terraform will auto-deploy worker with new image
```

**Step 3: Verify worker is running**

```bash
# Check worker service status
aws ecs describe-services \
  --cluster pacifico-layouts-dev-cluster \
  --services pacifico-layouts-dev-worker \
  --region us-east-1

# View worker logs
aws logs tail /ecs/pacifico-layouts-dev-worker --follow
```

### Scaling

```bash
# Scale to 2 worker tasks for higher throughput
aws ecs update-service \
  --cluster pacifico-layouts-dev-cluster \
  --service pacifico-layouts-dev-worker \
  --desired-count 2
```

---

## C-03: Async Layout Generation Endpoint

### Configuration

Enable async mode in ECS task environment:

```bash
# In AWS Console or via Terraform variable:
ENABLE_ASYNC_LAYOUT_GENERATION=true
```

### API Changes

**POST /api/layouts/generate** now supports two response types:

**Sync Mode (ENABLE_ASYNC_LAYOUT_GENERATION=false):**
```json
{
  "layout": { ... },
  "assets": [ ... ],
  "roads": [ ... ],
  "geojson": { ... }
}
```
Returns immediately with full layout data (Phase A/B behavior).

**Async Mode (ENABLE_ASYNC_LAYOUT_GENERATION=true):**
```json
{
  "layout_id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "queued",
  "message": "Layout generation job queued successfully"
}
```
Returns immediately with layout_id. Frontend must poll `/api/layouts/{id}/status`.

### Request

```bash
curl -X POST http://localhost:8000/api/layouts/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "site_id": "...",
    "target_capacity_kw": 1000,
    "use_terrain": true,
    "dem_resolution_m": 30
  }'
```

### Implementation Flow

```
1. POST /api/layouts/generate
   ├─ Create Layout record (status='queued')
   ├─ Send message to SQS queue
   └─ Return layout_id immediately

2. Worker polls SQS
   ├─ Check layout status (idempotency)
   ├─ Update to 'processing'
   ├─ Generate layout (terrain or dummy)
   ├─ Update to 'completed' with metrics
   └─ Acknowledge message

3. Frontend polls /api/layouts/{id}/status
   ├─ Returns status: queued/processing/completed/failed
   ├─ When completed: includes metrics (capacity, assets, roads, volumes)
   └─ Updates UI when status changes
```

---

## C-04: Layout Status Polling Endpoint

### API Endpoint

**GET /api/layouts/{layout_id}/status**

Returns current layout generation job status.

### Response Schema

**While Processing:**
```json
{
  "layout_id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "queued" | "processing",
  "error_message": null
}
```

**When Completed:**
```json
{
  "layout_id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "completed",
  "error_message": null,
  "total_capacity_kw": 1000.5,
  "asset_count": 12,
  "road_length_m": 2500.3,
  "cut_volume_m3": 15000.0,
  "fill_volume_m3": 8500.0
}
```

**On Failure:**
```json
{
  "layout_id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "failed",
  "error_message": "Failed to fetch DEM data"
}
```

### Usage Example

```bash
# Poll until completion
LAYOUT_ID="123e4567-e89b-12d3-a456-426614174000"

while true; do
  STATUS=$(curl -s "http://localhost:8000/api/layouts/$LAYOUT_ID/status" \
    -H "Authorization: Bearer $TOKEN" | jq -r '.status')
  
  case $STATUS in
    "completed")
      echo "Layout generation complete!"
      break
      ;;
    "failed")
      echo "Layout generation failed!"
      break
      ;;
    *)
      echo "Status: $STATUS, retrying in 2 seconds..."
      sleep 2
      ;;
  esac
done
```

---

## C-05: Frontend Polling Implementation

### Hook: useLayoutPolling

**File:** `frontend/src/hooks/useLayoutPolling.ts`

```typescript
interface LayoutStatus {
  layout_id: string;
  status: 'queued' | 'processing' | 'completed' | 'failed';
  error_message?: string;
  total_capacity_kw?: number;
  asset_count?: number;
  road_length_m?: number;
  cut_volume_m3?: number;
  fill_volume_m3?: number;
}

export function useLayoutPolling(layoutId: string | null) {
  const [status, setStatus] = useState<LayoutStatus | null>(null);
  const [isPolling, setIsPolling] = useState(false);

  useEffect(() => {
    if (!layoutId || !isPolling) return;

    const interval = setInterval(async () => {
      try {
        const response = await api.layouts.getStatus(layoutId);
        setStatus(response.data);

        if (response.data.status === 'completed' || response.data.status === 'failed') {
          setIsPolling(false); // Stop polling
        }
      } catch (error) {
        console.error('Failed to fetch layout status:', error);
      }
    }, 2000); // Poll every 2 seconds

    return () => clearInterval(interval);
  }, [layoutId, isPolling]);

  return { status, isPolling, setIsPolling };
}
```

### Usage in Component

**File:** `frontend/src/pages/SiteDetailPage.tsx`

```typescript
const { status, isPolling, setIsPolling } = useLayoutPolling(generatingLayoutId);

// When generate button clicked:
const onGenerateLayout = async () => {
  const response = await api.layouts.generate({
    site_id: site.id,
    target_capacity_kw: capacity,
    use_terrain: true,
  });

  // In async mode, get layout_id and start polling
  setGeneratingLayoutId(response.data.layout_id);
  setIsPolling(true);
};

// Show loading state while polling
if (isPolling && status?.status !== 'completed') {
  return (
    <div className="loading-container">
      <Spinner />
      <p>Generating layout... {status?.status}</p>
      <p>Assets: {status?.asset_count || '...'}</p>
    </div>
  );
}

// Show results when complete
if (status?.status === 'completed') {
  return <LayoutResults status={status} />;
}

// Show error if failed
if (status?.status === 'failed') {
  return <ErrorAlert message={status.error_message} />;
}
```

### UI Components

- **Loading spinner** during 'queued' and 'processing' states
- **Progress indicator** showing asset count, road length
- **Elapsed time** display
- **Cancel button** to stop polling (doesn't stop actual processing)
- **Error message** if status becomes 'failed'

---

## C-06: S3 Lifecycle Policies

### Purpose

Automatically delete old files to reduce storage costs and clean up temporary data.

### Configuration

**File:** To be added to `infra/terraform/main.tf`

```hcl
# Site uploads: delete after 90 days
resource "aws_s3_bucket_lifecycle_configuration" "site_uploads" {
  bucket = aws_s3_bucket.site_uploads.id

  rule {
    id     = "delete-old-uploads"
    status = "Enabled"

    expiration {
      days = 90
    }

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}

# Terrain data: delete after 30 days (cached DEMs, slopes)
resource "aws_s3_bucket_lifecycle_configuration" "site_outputs" {
  bucket = aws_s3_bucket.site_outputs.id

  rule {
    id     = "delete-old-terrain"
    status = "Enabled"

    expiration {
      prefix = "terrain/"
      days   = 30
    }
  }

  rule {
    id     = "delete-old-exports"
    status = "Enabled"

    expiration {
      prefix = "outputs/"
      days   = 30
    }
  }
}
```

### Deployment

```bash
terraform apply
```

### Monitoring

```bash
# Check lifecycle policies
aws s3api get-bucket-lifecycle-configuration \
  --bucket pacifico-layouts-dev-site-uploads
```

---

## C-07: Security Hardening

### Security Group Updates

**RDS**: Remove direct access, limit to ECS security group only

```bash
# No changes needed - already configured in A-01
# RDS only accepts connections from ECS security group on port 5432
```

**ECS**: Restrict to necessary ports

```bash
# Already in A-01 - ECS accepts 8000 from ALB only
# Worker uses same security group - no additional inbound needed
```

**API Task Role**: Least privilege S3 access

```hcl
# Already configured in A-01
# Statement 1: Read from site-uploads (for source KML)
# Statement 2: Read/Write to site-outputs (for terrain, exports)
```

**Worker Task Role**: SQS + S3 access

```hcl
# Configured in C-01 (sqs.tf)
# Statement 1: SQS receive/delete/change-visibility
# Statement 2: S3 read uploads, read/write outputs
```

### IAM Policy Review

```bash
# Verify no overly permissive policies
aws iam get-role-policy \
  --role-name pacifico-layouts-dev-ecs-task \
  --policy-name pacifico-layouts-dev-ecs-s3-policy

# Should NOT have:
# - "s3:*" actions (too broad)
# - Effect: "Allow" with Resource: "*"
# - EC2 or RDS permissions
```

### TODO: Production Hardening

- [ ] Enable VPC Flow Logs for network monitoring
- [ ] Enable RDS encryption at rest (in variables)
- [ ] Add WAF rules to ALB (rate limiting, SQL injection protection)
- [ ] Restrict CORS origins to production domains
- [ ] Enable MFA for AWS IAM users
- [ ] Set up CloudTrail for API auditing

---

## C-08: CloudWatch Monitoring & Alarms

### Logs

**API Container:**
- Log group: `/ecs/pacifico-layouts-dev`
- Prefix: `backend`

**Worker Container:**
- Log group: `/ecs/pacifico-layouts-dev-worker`
- Prefix: `worker`

### Alarms (C-01: SQS + C-08: Monitoring)

**Queue Depth High (> 10 messages)**
- Indicates possible processing backlog
- Check worker logs for errors
- May need to scale worker tasks

**DLQ Depth High (> 5 messages)**
- Indicates repeated job failures
- Check DLQ messages for error patterns
- May need code fixes or DEM API issues

**ECS Task Failures (> 2 in 5 min)**
- Worker or API container crashed
- Check CloudWatch logs for error details
- Auto-restart via ECS service discovery

**RDS CPU High (> 80% for 10 min)**
- Database under heavy load
- May need query optimization or instance upgrade
- Check slow query log

**RDS Storage Low (< 10% free)**
- Approaching storage limit
- Enable auto-scaling (already configured in A-01)
- Check for log bloat

### CloudWatch Dashboard

**File:** To be created as `infra/terraform/cloudwatch-dashboard.tf`

```json
{
  "widgets": [
    {
      "type": "metric",
      "properties": {
        "metrics": [
          ["AWS/SQS", "ApproximateNumberOfMessages", {"QueueName": "..."}],
          ["AWS/ECS", "CPUUtilization", {"ServiceName": "...", "ClusterName": "..."}],
          ["AWS/RDS", "CPUUtilization", {"DBInstanceIdentifier": "..."}]
        ],
        "period": 300,
        "stat": "Average"
      }
    }
  ]
}
```

### Querying Logs

```bash
# Recent worker errors
aws logs tail /ecs/pacifico-layouts-dev-worker --follow \
  --filter-pattern "ERROR" --max-items 50

# Layout processing times
aws logs filter-log-events \
  --log-group-name /ecs/pacifico-layouts-dev-worker \
  --filter-pattern "Processing layout" \
  --query 'events[*].message'
```

---

## C-09: Health Checks & Graceful Shutdown

### Enhanced Health Checks

**GET /health/ready** (already configured in A-04)

```python
@app.get("/health/ready")
async def health_ready():
    db_healthy = await check_db_connection()
    if not db_healthy:
        raise HTTPException(status_code=503, detail="DB unavailable")
    return {"status": "ready"}
```

### Graceful Shutdown

**API Service:**
- ECS sends SIGTERM before terminating container
- ALB drains connections (waits for in-flight requests)
- Deployment circuit breaker prevents cascading failures

**Worker Service:**
- ECS sends SIGTERM on deployment
- Worker sets `should_shutdown = True`
- Finishes current job before exiting
- No jobs lost due to message visibility timeout

**Configuration:**
```hcl
# In ECS task definition:
stopTimeout = 60  # Give 60 seconds to graceful shutdown

# In ECS service:
deployment_circuit_breaker {
  enable   = true
  rollback = true
}
```

---

## C-10: Runbook & Operations

### Quick Start

```bash
# 1. Check service health
curl http://localhost:8000/health
curl http://localhost:8000/health/ready

# 2. Monitor queue depth
aws sqs get-queue-attributes \
  --queue-url $(terraform output -raw sqs_layout_jobs_queue_url) \
  --attribute-names ApproximateNumberOfMessages

# 3. Check worker logs
aws logs tail /ecs/pacifico-layouts-dev-worker --follow

# 4. Scale workers if needed
aws ecs update-service --cluster ... --service ... --desired-count 2
```

### Troubleshooting

**Layout stuck in 'processing'**
1. Check worker logs for errors
2. Verify worker ECS task is running
3. Kill stuck task: `aws ecs stop-task --cluster ... --task ...`
4. Worker will receive message again

**SQS queue growing (backup)**
1. Scale up workers: `--desired-count 2`
2. Check for errors in `/ecs/pacifico-layouts-dev-worker` logs
3. Monitor RDS - may need optimization

**DLQ messages (repeated failures)**
1. Check DLQ messages: `aws sqs receive-message --queue-url ...`
2. Common causes:
   - Site not found (frontend issue)
   - DEM API unavailable (network/quota)
   - RDS connection issues
3. Fix root cause, then manually retry or delete messages

**Worker not starting**
1. Check task logs: `aws logs tail /ecs/pacifico-layouts-dev-worker`
2. Verify task definition has correct image tag
3. Check IAM role permissions for SQS/S3
4. Force new deployment: `aws ecs update-service --force-new-deployment ...`

### Common Commands

```bash
# View all task logs (API + worker)
aws logs tail /ecs/pacifico-layouts-dev --follow

# Test layout generation (sync mode)
curl -X POST http://localhost:8000/api/layouts/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"site_id": "...", "target_capacity_kw": 1000}'

# Poll layout status (async mode)
curl http://localhost:8000/api/layouts/$LAYOUT_ID/status \
  -H "Authorization: Bearer $TOKEN"

# View layout jobs queue (first 10 messages)
aws sqs receive-message \
  --queue-url $(terraform output -raw sqs_layout_jobs_queue_url) \
  --max-number-of-messages 10

# Purge queue (caution!)
aws sqs purge-queue \
  --queue-url $(terraform output -raw sqs_layout_jobs_queue_url)

# Scale worker tasks
aws ecs update-service \
  --cluster pacifico-layouts-dev-cluster \
  --service pacifico-layouts-dev-worker \
  --desired-count 3
```

---

## Deployment Summary

### Prerequisites

- [ ] AWS credentials configured
- [ ] Terraform state backend initialized
- [ ] Backend container image pushed to ECR

### Deployment Order

1. **C-01: SQS Infrastructure**
   ```bash
   terraform apply
   terraform output sqs_layout_jobs_queue_url
   ```

2. **C-02: Worker Container**
   ```bash
   # Push new image (includes worker.py)
   docker push $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/pacifico-layouts-dev-backend:latest
   aws ecs update-service --cluster ... --service ... --force-new-deployment
   ```

3. **C-03: Enable Async Mode**
   ```bash
   # Update ECS task definition:
   # ENABLE_ASYNC_LAYOUT_GENERATION=true
   # (Do via AWS Console or terraform variable)
   ```

4. **C-04**: Auto-included in API (C-03)

5. **C-05: Frontend Polling**
   - Implement useLayoutPolling hook
   - Update SiteDetailPage component
   - Deploy frontend via CI/CD

6. **C-06: S3 Lifecycle Policies**
   ```bash
   terraform apply
   ```

7. **C-07: Security Hardening**
   - Review IAM policies (already strict)
   - Enable VPC Flow Logs (optional)

8. **C-08: CloudWatch Setup**
   ```bash
   # Alarms auto-created by terraform
   # Set SNS email if desired:
   # ALERTS_EMAIL=ops@pacifico.com
   ```

9. **C-09**: Auto-configured in ECS

10. **C-10**: Runbook documentation (this file)

---

## Production Checklist

- [ ] SQS queues created with DLQ
- [ ] Worker service running (desired_count > 0)
- [ ] Async mode enabled in API
- [ ] Frontend polling implemented and tested
- [ ] S3 lifecycle policies active
- [ ] CloudWatch alarms configured
- [ ] SNS email subscribed (ops@pacifico.com)
- [ ] Tested graceful shutdown (kill container, verify message requeued)
- [ ] Tested DLQ recovery (manual message processing)
- [ ] Load tested with 5+ concurrent layout generations
- [ ] All CloudWatch logs searchable and retained

---

## Next Steps

- Implement C-10 runbook automation (scripts)
- Add Fargate Spot instances for worker cost savings
- Implement job timeout and max retries (currently 3 retries)
- Add metrics dashboard to frontend (queue depth, processing time)
- Consider step functions for complex multi-stage jobs (future)


