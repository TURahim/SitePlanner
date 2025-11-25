# Phase C Implementation - What's Next

## Status Overview

**✅ Completed (Nov 25, 2025):**
- C-01: SQS Queue Infrastructure 
- C-02: Worker Container
- C-03: Async Layout Generation Endpoint
- C-04: Status Polling Endpoint
- C-10: Comprehensive Documentation

**Progress: 50% (5/10 tasks) 🎉**

**📋 Remaining:**
- C-05: Frontend Polling
- C-06: S3 Lifecycle Policies
- C-07: Security Hardening
- C-08: CloudWatch Alarms
- C-09: Health Checks & Graceful Shutdown

---

## Immediate Next Steps (Today/This Week)

### 1. Review Infrastructure Code

```bash
# Review what was created
cat infra/terraform/sqs.tf                    # 200 lines
cat PHASE_C_IMPLEMENTATION_SUMMARY.md         # Full implementation details
cat .github/PHASE_C_ASYNC_JOBS.md            # Deployment guide
```

**Key Points:**
- SQS queue with DLQ auto-configured
- Worker task definition ready
- IAM roles with least-privilege access
- CloudWatch alarms for monitoring

### 2. Deploy Infrastructure (5 minutes)

```bash
cd pacifico-site-layouts/infra/terraform

# Review changes
terraform plan

# Apply (creates SQS, logs, alarms, roles)
terraform apply

# Verify
terraform output sqs_layout_jobs_queue_url
terraform output ecs_worker_log_group_name
```

**What gets created:**
- SQS main queue + DLQ
- 2 new IAM roles (worker task + execution)
- CloudWatch log group for worker
- CloudWatch alarms (queue depth, DLQ depth)

### 3. Build & Push Worker Image (10 minutes)

```bash
cd pacifico-site-layouts/backend

# Build for ECS
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
docker build --platform linux/amd64 -t pacifico-layouts-dev-backend .

# Push to ECR
aws ecr get-login-password --region us-east-1 | docker login \
  --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com

docker tag pacifico-layouts-dev-backend \
  $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/pacifico-layouts-dev-backend:latest

docker push $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/pacifico-layouts-dev-backend:latest
```

**What happens:**
- ECS auto-deploys new API and worker tasks
- Worker starts polling SQS (check logs in 1-2 minutes)

### 4. Verify Worker is Running (2 minutes)

```bash
# Check worker service
aws ecs describe-services \
  --cluster pacifico-layouts-dev-cluster \
  --services pacifico-layouts-dev-worker

# Should show: desiredCount=1, runningCount=1

# Check worker logs
aws logs tail /ecs/pacifico-layouts-dev-worker --follow

# Should show: "Layout generation worker started"
```

### 5. Test Sync Mode (Local, 5 minutes)

```bash
# Terminal 1
cd backend
uvicorn app.main:app --reload

# Terminal 2 - Test that old sync mode still works
curl -X POST http://localhost:8000/api/layouts/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "site_id": "YOUR_SITE_ID",
    "target_capacity_kw": 1000,
    "use_terrain": false
  }'

# Should return: Full layout immediately (sync)
```

---

## Next Phase: Frontend Polling (C-05)

### Overview

The frontend needs to:
1. Call `/api/layouts/generate` → get `layout_id`
2. Poll `/api/layouts/{id}/status` every 2-3 seconds
3. Show loading state with spinner
4. Display results when status='completed'

### Implementation Checklist

```bash
cd pacifico-site-layouts/frontend

# 1. Create polling hook
touch src/hooks/useLayoutPolling.ts

# 2. Add hook to SiteDetailPage
# - Import useLayoutPolling
# - Call when generate button clicked
# - Render loading state during polling

# 3. Update API client
# - Add getLayoutStatus() method to api.ts

# 4. Update types
# - Add LayoutStatusResponse interface

# 5. Test locally
npm run dev
# Navigate to site, click Generate, watch polling work
```

### Code Template (useLayoutPolling)

```typescript
// src/hooks/useLayoutPolling.ts
import { useState, useEffect } from 'react';
import { api } from '../lib/api';

export interface LayoutStatus {
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

        if (['completed', 'failed'].includes(response.data.status)) {
          setIsPolling(false);
        }
      } catch (error) {
        console.error('Error polling status:', error);
      }
    }, 2000); // Poll every 2 seconds

    return () => clearInterval(interval);
  }, [layoutId, isPolling]);

  return { status, isPolling, setIsPolling };
}
```

---

## Step-by-Step Deployment Guide

### For Backend Team

**Total Time: 20 minutes**

```bash
# 1. Review Phase C implementation
cat PHASE_C_IMPLEMENTATION_SUMMARY.md

# 2. Check infrastructure plan
cd infra/terraform && terraform plan

# 3. Deploy infrastructure
terraform apply

# 4. Build and push image
cd ../backend
docker build --platform linux/amd64 -t pacifico-layouts-dev-backend .
aws ecr get-login-password --region us-east-1 | docker login \
  --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com
docker tag pacifico-layouts-dev-backend \
  $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/pacifico-layouts-dev-backend:latest
docker push $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/pacifico-layouts-dev-backend:latest

# 5. Verify worker
aws logs tail /ecs/pacifico-layouts-dev-worker --follow
# Wait for: "Layout generation worker started"

# Done! Worker is running and ready for jobs
```

### For Frontend Team

**Total Time: 1-2 hours (depending on testing)**

1. Implement `useLayoutPolling` hook
2. Update `SiteDetailPage.tsx` to use hook
3. Update API client with `getStatus()` method
4. Add loading UI component
5. Test end-to-end locally
6. Deploy to frontend (CI/CD or manual)

### For DevOps

**Total Time: 30 minutes**

1. Review infrastructure additions (sqs.tf)
2. Configure SNS for alarms (optional)
3. Test SQS queue access
4. Monitor CloudWatch logs during first test
5. Document monitoring procedures

---

## Testing Workflow

### Local Testing (Sync Mode)

```bash
# Terminal 1: Backend
cd backend && uvicorn app.main:app --reload

# Terminal 2: Test generate endpoint
SITE_ID="..." # Get from database or upload a test site
curl -X POST http://localhost:8000/api/layouts/generate \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"site_id": "'$SITE_ID'", "target_capacity_kw": 1000}'

# Response: Full layout (sync - Phase B behavior, takes 1 second)
```

### AWS Testing (Async Mode)

```bash
# 1. Enable async in ECS (via AWS Console)
# Set: ENABLE_ASYNC_LAYOUT_GENERATION=true

# 2. Deploy updated API
aws ecs update-service --cluster pacifico-layouts-dev-cluster \
  --service pacifico-layouts-dev-backend --force-new-deployment

# 3. Call generate endpoint
curl -X POST https://api.pacifico.example.com/api/layouts/generate \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"site_id": "'$SITE_ID'", "target_capacity_kw": 1000}'

# Response: {"layout_id": "...", "status": "queued"}

# 4. Poll status
curl https://api.pacifico.example.com/api/layouts/$LAYOUT_ID/status \
  -H "Authorization: Bearer $TOKEN"

# Returns status changing: queued → processing → completed

# 5. Verify worker processed
aws logs tail /ecs/pacifico-layouts-dev-worker --follow
```

---

## Risk Mitigation

### What Could Go Wrong?

1. **Worker doesn't start**
   - ✅ Solution: Check `/ecs/pacifico-layouts-dev-worker` logs
   - ✅ Solution: Verify IAM role permissions
   - ✅ Solution: Restart service: `aws ecs update-service --force-new-deployment`

2. **SQS messages accumulate**
   - ✅ Solution: Check worker logs for errors
   - ✅ Solution: Scale workers: `--desired-count 2+`
   - ✅ Solution: CloudWatch alarm will notify

3. **Frontend polling breaks**
   - ✅ Solution: Check browser console for errors
   - ✅ Solution: Verify API responds with correct schema
   - ✅ Solution: Use `/api/docs` (Swagger) to test endpoint

4. **Terraform apply fails**
   - ✅ Solution: Check credentials: `aws sts get-caller-identity`
   - ✅ Solution: Review terraform.tfstate for conflicts
   - ✅ Solution: Try: `terraform refresh` then `terraform apply`

---

## Deployment Checklist

### Pre-Deployment

- [ ] Read Phase C implementation summary
- [ ] Review all changed files
- [ ] Run `terraform plan` and review changes
- [ ] Verify all team members understand async flow

### Deployment

- [ ] Apply Terraform (creates SQS, logs, roles)
- [ ] Build Docker image with worker.py
- [ ] Push image to ECR
- [ ] Wait for ECS to auto-deploy (2-3 minutes)
- [ ] Verify worker is running: `aws logs tail ... --follow`

### Post-Deployment

- [ ] Test sync mode locally
- [ ] Enable async mode in ECS
- [ ] Test async endpoint manually
- [ ] Verify polling works
- [ ] Check CloudWatch alarms configured
- [ ] Monitor worker logs for 30 minutes
- [ ] Document any issues encountered

### Production Readiness

- [ ] Load test with 5+ concurrent layouts
- [ ] Test worker failure recovery
- [ ] Test DLQ message handling
- [ ] Test CloudWatch alarms trigger
- [ ] Verify graceful shutdown works
- [ ] Update runbooks with real URLs/IDs

---

## Quick Reference

### Files Created

```
✅ backend/app/worker.py                 # Worker script
✅ backend/app/services/sqs_service.py   # SQS client
✅ infra/terraform/sqs.tf                # SQS infrastructure
✅ .github/PHASE_C_ASYNC_JOBS.md        # Full guide
✅ PHASE_C_IMPLEMENTATION_SUMMARY.md     # What's done
✅ PHASE_C_NEXT_STEPS.md                 # This file
```

### Files Modified

```
✅ backend/app/config.py                 # SQS config
✅ backend/app/api/layouts.py            # Async endpoints
✅ backend/app/schemas/layout.py         # Async schemas
✅ backend/requirements.txt              # aioboto3
✅ infra/terraform/main.tf               # Worker task
✅ infra/terraform/variables.tf          # SQS vars
✅ infra/terraform/outputs.tf            # SQS outputs
✅ README.md                              # Updated status
```

### Key Endpoints

```
POST /api/layouts/generate               # Returns layout_id (async) or full layout (sync)
GET  /api/layouts/{id}/status            # Poll for progress
GET  /health                             # Health check
GET  /health/ready                       # Readiness check (DB connectivity)
```

### Monitoring Commands

```bash
# Watch worker
aws logs tail /ecs/pacifico-layouts-dev-worker --follow

# Check queue depth
aws sqs get-queue-attributes \
  --queue-url $(terraform output -raw sqs_layout_jobs_queue_url) \
  --attribute-names ApproximateNumberOfMessages

# View failed messages
aws sqs receive-message \
  --queue-url $(terraform output -raw sqs_layout_jobs_dlq_url)

# Scale workers
aws ecs update-service \
  --cluster pacifico-layouts-dev-cluster \
  --service pacifico-layouts-dev-worker \
  --desired-count 2

# Restart service
aws ecs update-service \
  --cluster pacifico-layouts-dev-cluster \
  --service pacifico-layouts-dev-worker \
  --force-new-deployment
```

---

## Success Criteria

Phase C is "complete and working" when:

✅ Infrastructure deployed (SQS, worker roles, alarms)
✅ Worker container running in ECS
✅ Sync mode works (old Phase B behavior)
✅ Async mode works (layout_id → polling → results)
✅ Frontend polling implemented and tested
✅ CloudWatch shows queue depth, no errors
✅ Load tested with 5+ concurrent jobs
✅ Worker graceful shutdown verified

**Expected Timeline:**
- Infrastructure: 1 day
- Backend testing: 1-2 days
- Frontend polling: 2-3 days
- Full integration testing: 2-3 days
- **Total: 1-2 weeks**

---

## Questions?

Refer to:
1. **Full Guide**: `.github/PHASE_C_ASYNC_JOBS.md`
2. **Implementation Details**: `PHASE_C_IMPLEMENTATION_SUMMARY.md`
3. **MVP Task List**: `MVP_Task_List.md` (Phase C section)

Good luck! 🚀


