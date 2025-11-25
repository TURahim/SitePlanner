# =============================================================================
# Outputs - A-01 Infrastructure
# =============================================================================

# =============================================================================
# VPC Outputs
# =============================================================================

output "vpc_id" {
  description = "ID of the VPC"
  value       = aws_vpc.main.id
}

output "vpc_cidr" {
  description = "CIDR block of the VPC"
  value       = aws_vpc.main.cidr_block
}

output "public_subnet_ids" {
  description = "IDs of the public subnets"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "IDs of the private subnets"
  value       = aws_subnet.private[*].id
}

output "nat_gateway_ip" {
  description = "Elastic IP of the NAT Gateway"
  value       = aws_eip.nat.public_ip
}

# =============================================================================
# Security Group Outputs
# =============================================================================

output "alb_security_group_id" {
  description = "Security group ID for ALB"
  value       = aws_security_group.alb.id
}

output "ecs_security_group_id" {
  description = "Security group ID for ECS tasks"
  value       = aws_security_group.ecs.id
}

output "rds_security_group_id" {
  description = "Security group ID for RDS"
  value       = aws_security_group.rds.id
}

# =============================================================================
# S3 Bucket Outputs
# =============================================================================

output "frontend_assets_bucket_name" {
  description = "Name of the frontend assets S3 bucket"
  value       = aws_s3_bucket.frontend_assets.id
}

output "frontend_assets_bucket_arn" {
  description = "ARN of the frontend assets S3 bucket"
  value       = aws_s3_bucket.frontend_assets.arn
}

output "frontend_assets_website_endpoint" {
  description = "Website endpoint for frontend assets bucket"
  value       = aws_s3_bucket_website_configuration.frontend_assets.website_endpoint
}

output "site_uploads_bucket_name" {
  description = "Name of the site uploads S3 bucket"
  value       = aws_s3_bucket.site_uploads.id
}

output "site_uploads_bucket_arn" {
  description = "ARN of the site uploads S3 bucket"
  value       = aws_s3_bucket.site_uploads.arn
}

output "site_outputs_bucket_name" {
  description = "Name of the site outputs S3 bucket"
  value       = aws_s3_bucket.site_outputs.id
}

output "site_outputs_bucket_arn" {
  description = "ARN of the site outputs S3 bucket"
  value       = aws_s3_bucket.site_outputs.arn
}

# =============================================================================
# RDS Outputs
# =============================================================================

output "rds_endpoint" {
  description = "Endpoint of the RDS instance"
  value       = aws_db_instance.main.endpoint
}

output "rds_address" {
  description = "Hostname of the RDS instance"
  value       = aws_db_instance.main.address
}

output "rds_port" {
  description = "Port of the RDS instance"
  value       = aws_db_instance.main.port
}

output "rds_database_name" {
  description = "Name of the database"
  value       = aws_db_instance.main.db_name
}

output "rds_instance_id" {
  description = "ID of the RDS instance"
  value       = aws_db_instance.main.id
}

# =============================================================================
# Cognito Outputs
# =============================================================================

output "cognito_user_pool_id" {
  description = "ID of the Cognito User Pool"
  value       = aws_cognito_user_pool.main.id
}

output "cognito_user_pool_arn" {
  description = "ARN of the Cognito User Pool"
  value       = aws_cognito_user_pool.main.arn
}

output "cognito_user_pool_endpoint" {
  description = "Endpoint of the Cognito User Pool"
  value       = aws_cognito_user_pool.main.endpoint
}

output "cognito_client_id" {
  description = "ID of the Cognito User Pool Client"
  value       = aws_cognito_user_pool_client.web.id
}

output "cognito_domain" {
  description = "Domain of the Cognito User Pool"
  value       = aws_cognito_user_pool_domain.main.domain
}

output "cognito_hosted_ui_url" {
  description = "URL for Cognito Hosted UI"
  value       = "https://${aws_cognito_user_pool_domain.main.domain}.auth.${var.aws_region}.amazoncognito.com"
}

# =============================================================================
# Bastion Outputs
# =============================================================================

output "bastion_instance_id" {
  description = "Instance ID of the SSM bastion host (use with 'aws ssm start-session')"
  value       = aws_instance.bastion.id
}

output "bastion_security_group_id" {
  description = "Security group ID for bastion host"
  value       = aws_security_group.bastion.id
}

# =============================================================================
# A-02: ECS Outputs
# =============================================================================

output "ecr_repository_url" {
  description = "URL of the ECR repository for backend images"
  value       = aws_ecr_repository.backend.repository_url
}

output "ecr_repository_arn" {
  description = "ARN of the ECR repository"
  value       = aws_ecr_repository.backend.arn
}

output "ecs_cluster_id" {
  description = "ID of the ECS cluster"
  value       = aws_ecs_cluster.main.id
}

output "ecs_cluster_arn" {
  description = "ARN of the ECS cluster"
  value       = aws_ecs_cluster.main.arn
}

output "ecs_cluster_name" {
  description = "Name of the ECS cluster"
  value       = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  description = "Name of the ECS service"
  value       = aws_ecs_service.backend.name
}

output "ecs_task_definition_arn" {
  description = "ARN of the ECS task definition"
  value       = aws_ecs_task_definition.backend.arn
}

output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer"
  value       = aws_lb.main.dns_name
}

output "alb_zone_id" {
  description = "Zone ID of the Application Load Balancer"
  value       = aws_lb.main.zone_id
}

output "alb_arn" {
  description = "ARN of the Application Load Balancer"
  value       = aws_lb.main.arn
}

output "backend_target_group_arn" {
  description = "ARN of the backend target group"
  value       = aws_lb_target_group.backend.arn
}

output "backend_api_url" {
  description = "URL to access the backend API (HTTP)"
  value       = "http://${aws_lb.main.dns_name}"
}

output "cloudwatch_log_group_name" {
  description = "Name of the CloudWatch log group for ECS"
  value       = aws_cloudwatch_log_group.ecs.name
}

output "secrets_manager_secret_arn" {
  description = "ARN of the Secrets Manager secret for DB credentials"
  value       = aws_secretsmanager_secret.db_credentials.arn
}

output "ecs_task_execution_role_arn" {
  description = "ARN of the ECS task execution role"
  value       = aws_iam_role.ecs_task_execution.arn
}

output "ecs_task_role_arn" {
  description = "ARN of the ECS task role"
  value       = aws_iam_role.ecs_task.arn
}

