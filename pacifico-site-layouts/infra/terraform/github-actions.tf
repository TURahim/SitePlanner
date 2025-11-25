# =============================================================================
# A-03: GitHub Actions CI/CD - IAM OIDC Provider and Role
# =============================================================================
# This file configures OIDC-based authentication for GitHub Actions
# to deploy to AWS without using long-lived access keys.
# =============================================================================

variable "github_org" {
  description = "GitHub organization or username"
  type        = string
  default     = "" # Set in terraform.tfvars
}

variable "github_repo" {
  description = "GitHub repository name"
  type        = string
  default     = "" # Set in terraform.tfvars
}

# =============================================================================
# GitHub OIDC Provider
# =============================================================================

# Only create if github_org and github_repo are set
locals {
  enable_github_actions    = var.github_org != "" && var.github_repo != ""
  github_oidc_provider_url = "https://token.actions.githubusercontent.com"
}

# Try to find existing GitHub OIDC provider (may already exist from other projects)
data "aws_iam_openid_connect_provider" "github_existing" {
  count = local.enable_github_actions ? 1 : 0
  url   = local.github_oidc_provider_url
}

# Use the existing provider's ARN
locals {
  github_oidc_provider_arn = local.enable_github_actions ? data.aws_iam_openid_connect_provider.github_existing[0].arn : null
}

# =============================================================================
# IAM Role for GitHub Actions
# =============================================================================

resource "aws_iam_role" "github_actions" {
  count = local.enable_github_actions ? 1 : 0

  name = "${var.project_prefix}-github-actions"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = local.github_oidc_provider_arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          }
          StringLike = {
            # Allow from specific repo and branch
            "token.actions.githubusercontent.com:sub" = "repo:${var.github_org}/${var.github_repo}:*"
          }
        }
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-github-actions"
  })
}

# =============================================================================
# IAM Policies for GitHub Actions
# =============================================================================

# ECR Policy - Push/pull Docker images
resource "aws_iam_role_policy" "github_actions_ecr" {
  count = local.enable_github_actions ? 1 : 0

  name = "${var.project_prefix}-github-actions-ecr"
  role = aws_iam_role.github_actions[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:PutImage"
        ]
        Resource = aws_ecr_repository.backend.arn
      }
    ]
  })
}

# ECS Policy - Deploy services
resource "aws_iam_role_policy" "github_actions_ecs" {
  count = local.enable_github_actions ? 1 : 0

  name = "${var.project_prefix}-github-actions-ecs"
  role = aws_iam_role.github_actions[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecs:DescribeServices",
          "ecs:DescribeTaskDefinition",
          "ecs:DescribeTasks",
          "ecs:ListTasks",
          "ecs:RegisterTaskDefinition",
          "ecs:UpdateService"
        ]
        Resource = "*"
        Condition = {
          ArnLike = {
            "ecs:cluster" = aws_ecs_cluster.main.arn
          }
        }
      },
      {
        # RegisterTaskDefinition doesn't support resource-level permissions
        Effect = "Allow"
        Action = [
          "ecs:RegisterTaskDefinition",
          "ecs:DescribeTaskDefinition"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "iam:PassRole"
        ]
        Resource = [
          aws_iam_role.ecs_task_execution.arn,
          aws_iam_role.ecs_task.arn
        ]
      }
    ]
  })
}

# S3 Policy - Deploy frontend
resource "aws_iam_role_policy" "github_actions_s3" {
  count = local.enable_github_actions ? 1 : 0

  name = "${var.project_prefix}-github-actions-s3"
  role = aws_iam_role.github_actions[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = aws_s3_bucket.frontend_assets.arn
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject"
        ]
        Resource = "${aws_s3_bucket.frontend_assets.arn}/*"
      }
    ]
  })
}

# ELB Policy - Get ALB info for verification
resource "aws_iam_role_policy" "github_actions_elb" {
  count = local.enable_github_actions ? 1 : 0

  name = "${var.project_prefix}-github-actions-elb"
  role = aws_iam_role.github_actions[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "elasticloadbalancing:DescribeLoadBalancers",
          "elasticloadbalancing:DescribeTargetGroups",
          "elasticloadbalancing:DescribeTargetHealth"
        ]
        Resource = "*"
      }
    ]
  })
}

# CloudFront Policy - Invalidate cache (A-15)
resource "aws_iam_role_policy" "github_actions_cloudfront" {
  count = local.enable_github_actions ? 1 : 0

  name = "${var.project_prefix}-github-actions-cloudfront"
  role = aws_iam_role.github_actions[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "cloudfront:CreateInvalidation",
          "cloudfront:GetInvalidation",
          "cloudfront:ListInvalidations"
        ]
        Resource = aws_cloudfront_distribution.frontend.arn
      }
    ]
  })
}

# =============================================================================
# Outputs
# =============================================================================

output "github_actions_role_arn" {
  description = "ARN of the IAM role for GitHub Actions (set as AWS_ROLE_ARN secret)"
  value       = local.enable_github_actions ? aws_iam_role.github_actions[0].arn : null
}

output "github_oidc_provider_arn" {
  description = "ARN of the GitHub OIDC provider"
  value       = local.github_oidc_provider_arn
}

