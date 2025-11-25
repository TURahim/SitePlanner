# GitHub Actions CI/CD Setup

This document explains how to configure GitHub Actions for automated deployments of the Pacifico Site Layouts application.

## Overview

Two workflows are configured:
- **Backend Deploy** (`backend-deploy.yml`): Builds Docker image → Pushes to ECR → Updates ECS service
- **Frontend Deploy** (`frontend-deploy.yml`): Builds React app → Syncs to S3 → Invalidates CloudFront (when configured)

Both workflows:
- Trigger on push to `main` branch (when relevant files change)
- Can be manually triggered via `workflow_dispatch`
- Use OIDC for secure AWS authentication (no long-lived credentials)

## Prerequisites

1. AWS infrastructure deployed via Terraform (tasks A-01 and A-02 complete)
2. GitHub repository configured with required secrets

## Setup Instructions

### Step 1: Configure Terraform Variables

Add the GitHub configuration to your `terraform.tfvars`:

```hcl
# GitHub Actions CI/CD
github_org  = "your-github-username-or-org"
github_repo = "your-repo-name"
```

### Step 2: Apply Terraform to Create IAM Role

```bash
cd pacifico-site-layouts/infra/terraform
terraform plan
terraform apply
```

This creates:
- GitHub OIDC provider in AWS
- IAM role with permissions for ECR, ECS, S3, and CloudFront

### Step 3: Get the IAM Role ARN

After `terraform apply`, get the role ARN:

```bash
terraform output github_actions_role_arn
```

### Step 4: Configure GitHub Secrets

Go to your GitHub repository → Settings → Secrets and variables → Actions → New repository secret

Add the following secrets:

| Secret Name | Description | How to Get |
|-------------|-------------|------------|
| `AWS_ROLE_ARN` | IAM role ARN for OIDC auth | `terraform output github_actions_role_arn` |
| `VITE_API_URL` | Backend API URL | `terraform output backend_api_url` |
| `VITE_COGNITO_USER_POOL_ID` | Cognito User Pool ID | `terraform output cognito_user_pool_id` |
| `VITE_COGNITO_CLIENT_ID` | Cognito Client ID | `terraform output cognito_client_id` |

#### Optional Secrets (for future CloudFront setup in A-15):
| Secret Name | Description | How to Get |
|-------------|-------------|------------|
| `CLOUDFRONT_DISTRIBUTION_ID` | CloudFront distribution ID | After A-15 is complete |

### Step 5: Test the Workflows

#### Manual Trigger
Go to Actions tab → Select workflow → Run workflow

#### Automatic Trigger
Push a change to the `main` branch in the relevant directory:

```bash
# Test backend workflow
touch pacifico-site-layouts/backend/test-deploy
git add -A && git commit -m "Test backend deploy" && git push

# Test frontend workflow
touch pacifico-site-layouts/frontend/test-deploy
git add -A && git commit -m "Test frontend deploy" && git push

# Clean up test files
git rm pacifico-site-layouts/backend/test-deploy pacifico-site-layouts/frontend/test-deploy
git commit -m "Clean up test files" && git push
```

## Workflow Details

### Backend Deploy (`backend-deploy.yml`)

**Triggers:** Push to `main` when files in `pacifico-site-layouts/backend/**` change

**Steps:**
1. Checkout code
2. Configure AWS credentials via OIDC
3. Login to ECR
4. Build Docker image (`linux/amd64` platform)
5. Push to ECR with commit SHA tag + `latest`
6. Download current ECS task definition
7. Update task definition with new image
8. Deploy to ECS (waits for stability)
9. Verify health endpoint

**Expected Duration:** ~5 minutes

### Frontend Deploy (`frontend-deploy.yml`)

**Triggers:** Push to `main` when files in `pacifico-site-layouts/frontend/**` change

**Steps:**
1. Checkout code
2. Setup Node.js 18
3. Configure AWS credentials via OIDC
4. Install dependencies (`npm ci`)
5. Run linter
6. Build production bundle
7. Sync to S3 with appropriate cache headers
8. Invalidate CloudFront (when configured)
9. Verify deployment

**Expected Duration:** ~2 minutes

## Troubleshooting

### OIDC Authentication Fails

**Error:** `Error: Could not assume role with OIDC`

**Solutions:**
1. Verify `github_org` and `github_repo` match your repository exactly
2. Check that Terraform was applied after adding the GitHub variables
3. Ensure the role ARN is correctly set in `AWS_ROLE_ARN` secret

### ECS Deployment Hangs

**Error:** Workflow times out waiting for service stability

**Solutions:**
1. Check ECS service events in AWS Console
2. View CloudWatch logs: `/ecs/pacifico-layouts-dev`
3. Verify the new container health checks pass

### Frontend Build Fails

**Error:** TypeScript or lint errors

**Solutions:**
1. Run locally: `cd frontend && npm run lint && npm run build`
2. Fix any errors before pushing

### S3 Sync Permission Denied

**Error:** `AccessDenied` when syncing to S3

**Solutions:**
1. Verify the IAM role has S3 permissions (check `github-actions.tf`)
2. Re-apply Terraform if policies were updated

## Security Notes

1. **OIDC Authentication:** Uses short-lived credentials, no long-lived AWS keys stored in GitHub
2. **Branch Protection:** The IAM role is restricted to the configured repository
3. **Least Privilege:** Each policy grants minimum required permissions
4. **Secrets Management:** Sensitive values are stored in GitHub Secrets, not in code

## Cost Considerations

- GitHub Actions is free for public repos, has free tier for private repos
- AWS costs are minimal for the CI/CD operations themselves
- Main costs are from the deployed resources (ECS, RDS, S3), not the deployments

