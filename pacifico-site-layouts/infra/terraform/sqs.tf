# =============================================================================
# sqs.tf - C-01: SQS Queue Infrastructure for Async Layout Generation
# =============================================================================
# This file defines:
# - Main SQS queue for layout generation jobs
# - Dead-letter queue (DLQ) for failed jobs
# - Queue visibility timeout and message retention
# - IAM permissions for ECS tasks to send/receive messages
# - CloudWatch alarms for queue monitoring
# =============================================================================

# =============================================================================
# SQS Queues
# =============================================================================

# Dead-Letter Queue (DLQ) - receives messages after max retries
resource "aws_sqs_queue" "layout_jobs_dlq" {
  name                      = "${var.project_prefix}-layout-jobs-dlq"
  message_retention_seconds = 1209600  # 14 days
  
  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-layout-jobs-dlq"
  })
}

# Main Queue - receives layout generation job messages
resource "aws_sqs_queue" "layout_jobs" {
  name                       = "${var.project_prefix}-layout-jobs"
  visibility_timeout_seconds = 300  # 5 minutes for processing
  message_retention_seconds  = 345600  # 4 days
  
  # Redrive policy - send to DLQ after 3 failed attempts
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.layout_jobs_dlq.arn
    maxReceiveCount     = 3
  })
  
  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-layout-jobs"
  })
}

# =============================================================================
# IAM Role for Worker Tasks (separate from API tasks)
# =============================================================================

resource "aws_iam_role" "ecs_worker_task" {
  name = "${var.project_prefix}-ecs-worker-task"

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
    Name = "${var.project_prefix}-ecs-worker-task"
  })
}

# Policy for worker to access SQS
resource "aws_iam_role_policy" "ecs_worker_sqs" {
  name = "${var.project_prefix}-ecs-worker-sqs-policy"
  role = aws_iam_role.ecs_worker_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
          "sqs:ChangeMessageVisibility"
        ]
        Resource = [
          aws_sqs_queue.layout_jobs.arn,
          aws_sqs_queue.layout_jobs_dlq.arn
        ]
      }
    ]
  })
}

# Policy for worker to access S3 (terrain data, outputs)
resource "aws_iam_role_policy" "ecs_worker_s3" {
  name = "${var.project_prefix}-ecs-worker-s3-policy"
  role = aws_iam_role.ecs_worker_task.id

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

# Worker Execution Role (for pulling images, sending logs)
resource "aws_iam_role" "ecs_worker_execution" {
  name = "${var.project_prefix}-ecs-worker-execution"

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
    Name = "${var.project_prefix}-ecs-worker-execution"
  })
}

resource "aws_iam_role_policy_attachment" "ecs_worker_execution" {
  role       = aws_iam_role.ecs_worker_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Policy to read secrets from Secrets Manager (for worker)
resource "aws_iam_role_policy" "ecs_worker_execution_secrets" {
  name = "${var.project_prefix}-ecs-worker-secrets-policy"
  role = aws_iam_role.ecs_worker_execution.id

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

# Update existing API task role to allow sending messages to SQS
resource "aws_iam_role_policy" "ecs_task_sqs" {
  name = "${var.project_prefix}-ecs-task-sqs-policy"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sqs:SendMessage",
          "sqs:GetQueueUrl",
          "sqs:GetQueueAttributes"
        ]
        Resource = [
          aws_sqs_queue.layout_jobs.arn
        ]
      }
    ]
  })
}

# =============================================================================
# CloudWatch Log Group for Worker Tasks
# =============================================================================

resource "aws_cloudwatch_log_group" "ecs_worker" {
  name              = "/ecs/${var.project_prefix}-worker"
  retention_in_days = 7

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-worker-logs"
  })
}

# =============================================================================
# CloudWatch Alarms for Queue Monitoring
# =============================================================================

# Alarm: SQS queue depth exceeds 10 messages
resource "aws_cloudwatch_metric_alarm" "queue_depth_high" {
  alarm_name          = "${var.project_prefix}-queue-depth-high"
  alarm_description   = "Alert when layout jobs queue has >10 messages (possible backup)"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = "300"  # 5 minutes
  statistic           = "Average"
  threshold           = 10
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.layout_jobs.name
  }

  alarm_actions = var.enable_sns_alarms ? [aws_sns_topic.alerts[0].arn] : []
}

# Alarm: DLQ depth exceeds 5 messages
resource "aws_cloudwatch_metric_alarm" "dlq_depth_high" {
  alarm_name          = "${var.project_prefix}-dlq-depth-high"
  alarm_description   = "Alert when layout jobs DLQ has >5 messages (indicates failures)"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = "300"
  statistic           = "Maximum"
  threshold           = 5
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.layout_jobs_dlq.name
  }

  alarm_actions = var.enable_sns_alarms ? [aws_sns_topic.alerts[0].arn] : []
}

# =============================================================================
# SNS Topic for Alarms (Optional - requires enable_sns_alarms = true)
# =============================================================================

resource "aws_sns_topic" "alerts" {
  count = var.enable_sns_alarms ? 1 : 0
  name  = "${var.project_prefix}-alerts"

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-alerts"
  })
}

resource "aws_sns_topic_subscription" "alerts_email" {
  count     = var.enable_sns_alarms && var.alerts_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.alerts[0].arn
  protocol  = "email"
  endpoint  = var.alerts_email
}

