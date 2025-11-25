# =============================================================================
# Core Configuration
# =============================================================================

variable "aws_region" {
  description = "AWS region to deploy to"
  type        = string
  default     = "us-east-1"
}

variable "project_prefix" {
  description = "Prefix for resource names"
  type        = string
  default     = "pacifico-layouts-dev"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

# =============================================================================
# VPC Configuration
# =============================================================================

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Availability zones for subnets"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets"
  type        = list(string)
  default     = ["10.0.10.0/24", "10.0.11.0/24"]
}

# =============================================================================
# RDS Configuration
# =============================================================================

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}

variable "db_name" {
  description = "Name of the database"
  type        = string
  default     = "pacifico_layouts"
}

variable "db_username" {
  description = "Master username for the database"
  type        = string
  default     = "pacifico_admin"
  sensitive   = true
}

variable "db_password" {
  description = "Master password for the database"
  type        = string
  sensitive   = true
}

variable "db_allocated_storage" {
  description = "Allocated storage for RDS in GB"
  type        = number
  default     = 20
}

variable "db_max_allocated_storage" {
  description = "Maximum allocated storage for RDS autoscaling in GB"
  type        = number
  default     = 100
}

# =============================================================================
# Cognito Configuration
# =============================================================================

variable "cognito_password_min_length" {
  description = "Minimum password length for Cognito users"
  type        = number
  default     = 8
}

variable "cognito_email_verification_subject" {
  description = "Subject for verification emails"
  type        = string
  default     = "Pacifico Site Layouts - Verify your email"
}

variable "cognito_email_verification_message" {
  description = "Body for verification emails"
  type        = string
  default     = "Your verification code is {####}"
}

# =============================================================================
# ECS Configuration
# =============================================================================

variable "ecs_task_cpu" {
  description = "CPU units for ECS task (256, 512, 1024, 2048, 4096)"
  type        = number
  default     = 256
}

variable "ecs_task_memory" {
  description = "Memory for ECS task in MB (512, 1024, 2048, etc.)"
  type        = number
  default     = 512
}

variable "ecs_desired_count" {
  description = "Desired number of ECS tasks"
  type        = number
  default     = 1
}

# =============================================================================
# SQS Configuration (Phase C)
# =============================================================================

variable "enable_sns_alarms" {
  description = "Enable SNS topic for CloudWatch alarms"
  type        = bool
  default     = false
}

variable "alerts_email" {
  description = "Email address for alarm notifications (leave empty to disable)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "sqs_worker_desired_count" {
  description = "Desired number of SQS worker tasks"
  type        = number
  default     = 1
}

# =============================================================================
# Security Configuration (Phase C - C-07)
# =============================================================================

variable "enable_bastion_access" {
  description = "Enable bastion host for RDS access (set to false in production)"
  type        = bool
  default     = true
}

variable "enable_deletion_protection" {
  description = "Enable deletion protection for critical resources (RDS, ALB)"
  type        = bool
  default     = false  # Set to true in production
}
