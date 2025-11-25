# =============================================================================
# main.tf - A-01: Infrastructure Foundation
# =============================================================================
# This file defines:
# - VPC, subnets, NAT gateway, security groups
# - RDS PostgreSQL 15 + PostGIS
# - S3 buckets (frontend-assets, site-uploads, site-outputs)
# - Cognito User Pool
# =============================================================================

locals {
  common_tags = {
    Project     = "Pacifico Site Layouts"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# =============================================================================
# VPC & Networking
# =============================================================================

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-vpc"
  })
}

# Internet Gateway
resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-igw"
  })
}

# Public Subnets
resource "aws_subnet" "public" {
  count                   = length(var.public_subnet_cidrs)
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.public_subnet_cidrs[count.index]
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = true

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-public-subnet-${count.index + 1}"
    Type = "Public"
  })
}

# Private Subnets
resource "aws_subnet" "private" {
  count             = length(var.private_subnet_cidrs)
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.private_subnet_cidrs[count.index]
  availability_zone = var.availability_zones[count.index]

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-private-subnet-${count.index + 1}"
    Type = "Private"
  })
}

# Elastic IP for NAT Gateway
resource "aws_eip" "nat" {
  domain = "vpc"

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-nat-eip"
  })

  depends_on = [aws_internet_gateway.main]
}

# NAT Gateway (single NAT for cost savings in MVP)
resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-nat-gw"
  })

  depends_on = [aws_internet_gateway.main]
}

# Public Route Table
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-public-rt"
  })
}

# Private Route Table
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main.id
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-private-rt"
  })
}

# Route Table Associations - Public
resource "aws_route_table_association" "public" {
  count          = length(aws_subnet.public)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# Route Table Associations - Private
resource "aws_route_table_association" "private" {
  count          = length(aws_subnet.private)
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# =============================================================================
# Security Groups
# =============================================================================

# Security Group for ALB (public facing)
resource "aws_security_group" "alb" {
  name        = "${var.project_prefix}-alb-sg"
  description = "Security group for Application Load Balancer"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTPS from anywhere"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTP from anywhere (redirect to HTTPS)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "All outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-alb-sg"
  })
}

# Security Group for ECS Tasks
resource "aws_security_group" "ecs" {
  name        = "${var.project_prefix}-ecs-sg"
  description = "Security group for ECS Fargate tasks"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "HTTP from ALB"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    description = "All outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-ecs-sg"
  })
}

# Security Group for RDS
resource "aws_security_group" "rds" {
  name        = "${var.project_prefix}-rds-sg"
  description = "Security group for RDS PostgreSQL"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "PostgreSQL from ECS"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }

  egress {
    description = "All outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-rds-sg"
  })
}

# =============================================================================
# S3 Buckets
# =============================================================================

# Frontend Assets Bucket (public read for static website hosting)
resource "aws_s3_bucket" "frontend_assets" {
  bucket = "${var.project_prefix}-frontend-assets"

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-frontend-assets"
  })
}

resource "aws_s3_bucket_public_access_block" "frontend_assets" {
  bucket = aws_s3_bucket.frontend_assets.id

  # Block public access - CloudFront OAC provides secure access (A-15)
  block_public_acls       = true
  block_public_policy     = false # Allow CloudFront policy to be applied
  ignore_public_acls      = true
  restrict_public_buckets = false # Allow CloudFront policy to be applied
}

# NOTE: S3 bucket policy moved to cloudfront.tf (A-15)
# CloudFront OAC replaces public bucket access for better security
# The policy in cloudfront.tf allows CloudFront to access the bucket
# while blocking direct public access.

resource "aws_s3_bucket_website_configuration" "frontend_assets" {
  bucket = aws_s3_bucket.frontend_assets.id

  index_document {
    suffix = "index.html"
  }

  error_document {
    key = "index.html"
  }
}

resource "aws_s3_bucket_cors_configuration" "frontend_assets" {
  bucket = aws_s3_bucket.frontend_assets.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "HEAD"]
    allowed_origins = ["*"]
    max_age_seconds = 3000
  }
}

# Site Uploads Bucket (private - stores uploaded KML/KMZ files)
resource "aws_s3_bucket" "site_uploads" {
  bucket = "${var.project_prefix}-site-uploads"

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-site-uploads"
  })
}

resource "aws_s3_bucket_public_access_block" "site_uploads" {
  bucket = aws_s3_bucket.site_uploads.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "site_uploads" {
  bucket = aws_s3_bucket.site_uploads.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "site_uploads" {
  bucket = aws_s3_bucket.site_uploads.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_cors_configuration" "site_uploads" {
  bucket = aws_s3_bucket.site_uploads.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "PUT", "POST"]
    allowed_origins = ["*"] # Restrict in production
    max_age_seconds = 3000
  }
}

# =============================================================================
# S3 Lifecycle Policies (Phase C - C-06)
# =============================================================================

# Lifecycle policy for site uploads - delete files >90 days old
resource "aws_s3_bucket_lifecycle_configuration" "site_uploads" {
  bucket = aws_s3_bucket.site_uploads.id

  rule {
    id     = "delete-old-uploads"
    status = "Enabled"

    filter {
      prefix = "" # Apply to all objects
    }

    # Delete current versions after 90 days
    expiration {
      days = 90
    }

    # Delete non-current versions after 30 days (versioned bucket)
    noncurrent_version_expiration {
      noncurrent_days = 30
    }

    # Transition to cheaper storage before deletion (optional cost optimization)
    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }
  }

  rule {
    id     = "delete-terrain-cache"
    status = "Enabled"

    filter {
      prefix = "terrain/" # Cached DEM files
    }

    # Delete terrain cache after 30 days
    expiration {
      days = 30
    }
  }

  # Abort incomplete multipart uploads after 7 days
  rule {
    id     = "abort-incomplete-multipart"
    status = "Enabled"

    filter {
      prefix = ""
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# Site Outputs Bucket (private - stores generated layouts, exports)
resource "aws_s3_bucket" "site_outputs" {
  bucket = "${var.project_prefix}-site-outputs"

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-site-outputs"
  })
}

resource "aws_s3_bucket_public_access_block" "site_outputs" {
  bucket = aws_s3_bucket.site_outputs.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "site_outputs" {
  bucket = aws_s3_bucket.site_outputs.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "site_outputs" {
  bucket = aws_s3_bucket.site_outputs.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_cors_configuration" "site_outputs" {
  bucket = aws_s3_bucket.site_outputs.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET"]
    allowed_origins = ["*"] # Restrict in production
    max_age_seconds = 3000
  }
}

# Lifecycle policy for site outputs - delete files >30 days old
resource "aws_s3_bucket_lifecycle_configuration" "site_outputs" {
  bucket = aws_s3_bucket.site_outputs.id

  rule {
    id     = "delete-old-outputs"
    status = "Enabled"

    filter {
      prefix = "" # Apply to all objects
    }

    # Delete current versions after 30 days
    expiration {
      days = 30
    }

    # Delete non-current versions after 7 days (versioned bucket)
    noncurrent_version_expiration {
      noncurrent_days = 7
    }
  }

  rule {
    id     = "delete-temp-exports"
    status = "Enabled"

    filter {
      prefix = "exports/" # Temporary export files
    }

    # Delete export files after 7 days (they're downloaded immediately)
    expiration {
      days = 7
    }
  }

  # Abort incomplete multipart uploads after 1 day
  rule {
    id     = "abort-incomplete-multipart"
    status = "Enabled"

    filter {
      prefix = ""
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

# =============================================================================
# RDS PostgreSQL with PostGIS
# =============================================================================

# DB Subnet Group
resource "aws_db_subnet_group" "main" {
  name        = "${var.project_prefix}-db-subnet-group"
  description = "Database subnet group for RDS"
  subnet_ids  = aws_subnet.private[*].id

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-db-subnet-group"
  })
}

# RDS Parameter Group for PostGIS
resource "aws_db_parameter_group" "postgis" {
  family      = "postgres15"
  name        = "${var.project_prefix}-postgis-params"
  description = "PostgreSQL 15 parameters for PostGIS"

  # PostGIS requires shared_preload_libraries - handled automatically by RDS
  parameter {
    name  = "shared_preload_libraries"
    value = "pg_stat_statements"
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-postgis-params"
  })
}

# RDS Instance
resource "aws_db_instance" "main" {
  identifier = "${var.project_prefix}-postgres"

  # Engine configuration
  engine               = "postgres"
  engine_version       = "15"
  instance_class       = var.db_instance_class
  parameter_group_name = aws_db_parameter_group.postgis.name

  # Storage
  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_max_allocated_storage
  storage_type          = "gp3"
  storage_encrypted     = true

  # Database
  db_name  = var.db_name
  username = var.db_username
  password = var.db_password

  # Network
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false
  port                   = 5432

  # Availability (single-AZ for MVP)
  multi_az = false

  # Backup
  backup_retention_period = 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "Mon:04:00-Mon:05:00"

  # Performance Insights (free tier)
  performance_insights_enabled          = true
  performance_insights_retention_period = 7

  # Skip final snapshot for dev (change for prod)
  skip_final_snapshot       = true
  final_snapshot_identifier = "${var.project_prefix}-final-snapshot"
  deletion_protection       = false # Set to true for production

  # Enable IAM authentication
  iam_database_authentication_enabled = true

  # Auto minor version upgrade
  auto_minor_version_upgrade = true

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-postgres"
  })
}

# =============================================================================
# Cognito User Pool
# =============================================================================

resource "aws_cognito_user_pool" "main" {
  name = "${var.project_prefix}-user-pool"

  # Username configuration
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  # Password policy
  password_policy {
    minimum_length                   = var.cognito_password_min_length
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = true
    require_uppercase                = true
    temporary_password_validity_days = 7
  }

  # User verification
  verification_message_template {
    default_email_option = "CONFIRM_WITH_CODE"
    email_subject        = var.cognito_email_verification_subject
    email_message        = var.cognito_email_verification_message
  }

  # Account recovery
  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  # Email configuration (using Cognito default for MVP)
  email_configuration {
    email_sending_account = "COGNITO_DEFAULT"
  }

  # User attribute schema
  schema {
    name                     = "email"
    attribute_data_type      = "String"
    mutable                  = true
    required                 = true
    developer_only_attribute = false

    string_attribute_constraints {
      min_length = 1
      max_length = 256
    }
  }

  schema {
    name                     = "name"
    attribute_data_type      = "String"
    mutable                  = true
    required                 = false
    developer_only_attribute = false

    string_attribute_constraints {
      min_length = 1
      max_length = 256
    }
  }

  # MFA configuration (optional for MVP)
  mfa_configuration = "OFF"

  # Admin create user config
  admin_create_user_config {
    allow_admin_create_user_only = false
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-user-pool"
  })
}

# Cognito User Pool Client
resource "aws_cognito_user_pool_client" "web" {
  name         = "${var.project_prefix}-web-client"
  user_pool_id = aws_cognito_user_pool.main.id

  # No client secret for public web client (SPA)
  generate_secret = false

  # Token validity
  access_token_validity  = 1  # hours
  id_token_validity      = 1  # hours
  refresh_token_validity = 30 # days

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }

  # OAuth flows
  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH"
  ]

  # Prevent user existence errors (security best practice)
  prevent_user_existence_errors = "ENABLED"

  # Read/write attributes
  read_attributes  = ["email", "name", "email_verified"]
  write_attributes = ["email", "name"]
}

# Cognito User Pool Domain (for hosted UI, optional)
resource "aws_cognito_user_pool_domain" "main" {
  domain       = var.project_prefix
  user_pool_id = aws_cognito_user_pool.main.id
}

# =============================================================================
# SSM Bastion Host for Database Admin Access
# =============================================================================

# Data source for Amazon Linux 2023 AMI
data "aws_ami" "amazon_linux_2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  filter {
    name   = "root-device-type"
    values = ["ebs"]
  }
}

# =============================================================================
# Bastion Host (Phase C - C-07: Conditional based on environment)
# Set enable_bastion_access = false in production for better security
# =============================================================================

# IAM Role for SSM
resource "aws_iam_role" "bastion_ssm" {
  count = var.enable_bastion_access ? 1 : 0

  name = "${var.project_prefix}-bastion-ssm-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-bastion-ssm-role"
  })
}

# Attach SSM Managed Instance Core policy
resource "aws_iam_role_policy_attachment" "bastion_ssm" {
  count = var.enable_bastion_access ? 1 : 0

  role       = aws_iam_role.bastion_ssm[0].name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# Instance Profile for Bastion
resource "aws_iam_instance_profile" "bastion" {
  count = var.enable_bastion_access ? 1 : 0

  name = "${var.project_prefix}-bastion-profile"
  role = aws_iam_role.bastion_ssm[0].name

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-bastion-profile"
  })
}

# Security Group for Bastion (SSM - no inbound needed)
resource "aws_security_group" "bastion" {
  count = var.enable_bastion_access ? 1 : 0

  name        = "${var.project_prefix}-bastion-sg"
  description = "Security group for SSM bastion host"
  vpc_id      = aws_vpc.main.id

  # No inbound rules - SSM connects outbound via VPC endpoints or NAT

  egress {
    description = "All outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-bastion-sg"
  })
}

# Add rule to RDS security group to allow bastion access
resource "aws_security_group_rule" "rds_from_bastion" {
  count = var.enable_bastion_access ? 1 : 0

  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.bastion[0].id
  security_group_id        = aws_security_group.rds.id
  description              = "PostgreSQL from Bastion"
}

# Bastion EC2 Instance
resource "aws_instance" "bastion" {
  count = var.enable_bastion_access ? 1 : 0

  ami                    = data.aws_ami.amazon_linux_2023.id
  instance_type          = "t3.micro"
  subnet_id              = aws_subnet.private[0].id
  vpc_security_group_ids = [aws_security_group.bastion[0].id]
  iam_instance_profile   = aws_iam_instance_profile.bastion[0].name

  # No key pair needed - using SSM Session Manager
  associate_public_ip_address = false

  # User data to install PostgreSQL client
  user_data = <<-EOF
              #!/bin/bash
              dnf update -y
              dnf install -y postgresql15
              EOF

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 30
    encrypted             = true
    delete_on_termination = true
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required" # IMDSv2 required
    http_put_response_hop_limit = 1
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-bastion"
  })
}

# =============================================================================
# A-02: ECS Fargate Service for FastAPI Backend
# =============================================================================

# =============================================================================
# ECR Repository
# =============================================================================

resource "aws_ecr_repository" "backend" {
  name                 = "${var.project_prefix}-backend"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-backend"
  })
}

resource "aws_ecr_lifecycle_policy" "backend" {
  repository = aws_ecr_repository.backend.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 10 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

# =============================================================================
# Secrets Manager for DB Credentials
# =============================================================================

resource "aws_secretsmanager_secret" "db_credentials" {
  name = "${var.project_prefix}-db-credentials"

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-db-credentials"
  })
}

resource "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id = aws_secretsmanager_secret.db_credentials.id
  secret_string = jsonencode({
    username = var.db_username
    password = var.db_password
    host     = aws_db_instance.main.address
    port     = aws_db_instance.main.port
    dbname   = var.db_name
  })
}

# =============================================================================
# CloudWatch Log Group for ECS
# =============================================================================

resource "aws_cloudwatch_log_group" "ecs" {
  name              = "/ecs/${var.project_prefix}"
  retention_in_days = 7

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-ecs-logs"
  })
}

# =============================================================================
# IAM Roles for ECS
# =============================================================================

# ECS Task Execution Role (for pulling images, sending logs)
resource "aws_iam_role" "ecs_task_execution" {
  name = "${var.project_prefix}-ecs-task-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-ecs-task-execution"
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Policy to read secrets from Secrets Manager
resource "aws_iam_role_policy" "ecs_task_execution_secrets" {
  name = "${var.project_prefix}-ecs-secrets-policy"
  role = aws_iam_role.ecs_task_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          aws_secretsmanager_secret.db_credentials.arn
        ]
      }
    ]
  })
}

# ECS Task Role (for application runtime permissions)
resource "aws_iam_role" "ecs_task" {
  name = "${var.project_prefix}-ecs-task"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-ecs-task"
  })
}

# S3 access policy for ECS tasks
resource "aws_iam_role_policy" "ecs_task_s3" {
  name = "${var.project_prefix}-ecs-s3-policy"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.site_uploads.arn,
          "${aws_s3_bucket.site_uploads.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.site_outputs.arn,
          "${aws_s3_bucket.site_outputs.arn}/*"
        ]
      }
    ]
  })
}

# =============================================================================
# ECS Cluster
# =============================================================================

resource "aws_ecs_cluster" "main" {
  name = "${var.project_prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  configuration {
    execute_command_configuration {
      logging = "OVERRIDE"
      log_configuration {
        cloud_watch_log_group_name = aws_cloudwatch_log_group.ecs.name
      }
    }
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-cluster"
  })
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name = aws_ecs_cluster.main.name

  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
    base              = 1
  }
}

# =============================================================================
# Application Load Balancer
# =============================================================================

resource "aws_lb" "main" {
  name               = "${var.project_prefix}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id

  enable_deletion_protection = false # Set to true for production

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-alb"
  })
}

resource "aws_lb_target_group" "backend" {
  name        = "${var.project_prefix}-backend-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    enabled             = true
    healthy_threshold   = 2
    interval            = 30
    matcher             = "200"
    path                = "/health"
    port                = "traffic-port"
    protocol            = "HTTP"
    timeout             = 5
    unhealthy_threshold = 3
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-backend-tg"
  })
}

# HTTP Listener (redirects to HTTPS when certificate is available)
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-http-listener"
  })
}

# =============================================================================
# ECS Task Definition
# =============================================================================

resource "aws_ecs_task_definition" "backend" {
  family                   = "${var.project_prefix}-backend"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.ecs_task_cpu
  memory                   = var.ecs_task_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "backend"
      image     = "${aws_ecr_repository.backend.repository_url}:latest"
      essential = true

      portMappings = [
        {
          containerPort = 8000
          protocol      = "tcp"
        }
      ]

      environment = [
        {
          name  = "AWS_REGION"
          value = var.aws_region
        },
        {
          name  = "COGNITO_USER_POOL_ID"
          value = aws_cognito_user_pool.main.id
        },
        {
          name  = "COGNITO_CLIENT_ID"
          value = aws_cognito_user_pool_client.web.id
        },
        {
          name  = "S3_UPLOADS_BUCKET"
          value = aws_s3_bucket.site_uploads.id
        },
        {
          name  = "S3_OUTPUTS_BUCKET"
          value = aws_s3_bucket.site_outputs.id
        }
      ]

      secrets = [
        {
          name      = "DB_HOST"
          valueFrom = "${aws_secretsmanager_secret.db_credentials.arn}:host::"
        },
        {
          name      = "DB_PORT"
          valueFrom = "${aws_secretsmanager_secret.db_credentials.arn}:port::"
        },
        {
          name      = "DB_NAME"
          valueFrom = "${aws_secretsmanager_secret.db_credentials.arn}:dbname::"
        },
        {
          name      = "DB_USERNAME"
          valueFrom = "${aws_secretsmanager_secret.db_credentials.arn}:username::"
        },
        {
          name      = "DB_PASSWORD"
          valueFrom = "${aws_secretsmanager_secret.db_credentials.arn}:password::"
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "backend"
        }
      }

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:8000/health/ready || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
      
      # Phase C - C-09: Graceful shutdown timeout (60 seconds)
      stopTimeout = 60
    }
  ])

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-backend-task"
  })
}

# =============================================================================
# ECS Service
# =============================================================================

resource "aws_ecs_service" "backend" {
  name            = "${var.project_prefix}-backend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = var.ecs_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "backend"
    container_port   = 8000
  }

  deployment_maximum_percent         = 200
  deployment_minimum_healthy_percent = 100

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  # Allow service to be deployed even if no container image exists yet
  lifecycle {
    ignore_changes = [task_definition]
  }

  depends_on = [
    aws_lb_listener.http,
    aws_iam_role_policy.ecs_task_execution_secrets
  ]

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-backend-service"
  })
}

# =============================================================================
# C-02: ECS Task Definition for SQS Worker
# =============================================================================

resource "aws_ecs_task_definition" "worker" {
  family                   = "${var.project_prefix}-worker"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.ecs_task_cpu
  memory                   = var.ecs_task_memory
  execution_role_arn       = aws_iam_role.ecs_worker_execution.arn
  task_role_arn            = aws_iam_role.ecs_worker_task.arn

  container_definitions = jsonencode([
    {
      name      = "worker"
      image     = "${aws_ecr_repository.backend.repository_url}:latest"
      essential = true
      
      # Override default command to run worker instead of API
      command = ["python", "-m", "app.worker"]

      environment = [
        {
          name  = "AWS_REGION"
          value = var.aws_region
        },
        {
          name  = "COGNITO_USER_POOL_ID"
          value = aws_cognito_user_pool.main.id
        },
        {
          name  = "COGNITO_CLIENT_ID"
          value = aws_cognito_user_pool_client.web.id
        },
        {
          name  = "S3_UPLOADS_BUCKET"
          value = aws_s3_bucket.site_uploads.id
        },
        {
          name  = "S3_OUTPUTS_BUCKET"
          value = aws_s3_bucket.site_outputs.id
        },
        {
          name  = "SQS_QUEUE_URL"
          value = aws_sqs_queue.layout_jobs.url
        }
      ]

      secrets = [
        {
          name      = "DB_HOST"
          valueFrom = "${aws_secretsmanager_secret.db_credentials.arn}:host::"
        },
        {
          name      = "DB_PORT"
          valueFrom = "${aws_secretsmanager_secret.db_credentials.arn}:port::"
        },
        {
          name      = "DB_NAME"
          valueFrom = "${aws_secretsmanager_secret.db_credentials.arn}:dbname::"
        },
        {
          name      = "DB_USERNAME"
          valueFrom = "${aws_secretsmanager_secret.db_credentials.arn}:username::"
        },
        {
          name      = "DB_PASSWORD"
          valueFrom = "${aws_secretsmanager_secret.db_credentials.arn}:password::"
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs_worker.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "worker"
        }
      }
      
      # Phase C - C-09: Graceful shutdown timeout (60 seconds)
      # Worker handles SIGTERM to finish current job before exiting
      stopTimeout = 60
    }
  ])

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-worker-task"
  })
}

# =============================================================================
# C-02: ECS Service for Worker
# =============================================================================

resource "aws_ecs_service" "worker" {
  name            = "${var.project_prefix}-worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = var.sqs_worker_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  # Allow service to be deployed even if no container image exists yet
  lifecycle {
    ignore_changes = [task_definition]
  }

  depends_on = [
    aws_iam_role_policy.ecs_worker_sqs,
    aws_iam_role_policy.ecs_worker_s3
  ]

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-worker-service"
  })
}
