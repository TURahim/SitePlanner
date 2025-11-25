# =============================================================================
# Phase C - C-08: CloudWatch Logging and Alarms
# =============================================================================

# =============================================================================
# CloudWatch Log Groups
# =============================================================================

# Dedicated log group for API backend (already exists in main.tf as aws_cloudwatch_log_group.ecs)
# This creates a separate log group for the worker

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ecs/${var.project_prefix}-worker"
  retention_in_days = 7

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-worker-logs"
  })
}

# =============================================================================
# SNS Topic for Alarms (Optional - controlled by enable_sns_alarms variable)
# =============================================================================

resource "aws_sns_topic" "alarms" {
  count = var.enable_sns_alarms ? 1 : 0

  name = "${var.project_prefix}-alarms"

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-alarms"
  })
}

resource "aws_sns_topic_subscription" "alarms_email" {
  count = var.enable_sns_alarms && var.alerts_email != "" ? 1 : 0

  topic_arn = aws_sns_topic.alarms[0].arn
  protocol  = "email"
  endpoint  = var.alerts_email
}

# =============================================================================
# ECS Task Failure Alarms
# =============================================================================

# API Backend Task Failure Alarm
resource "aws_cloudwatch_metric_alarm" "ecs_api_task_failure" {
  alarm_name          = "${var.project_prefix}-api-task-failure"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ECS"
  period              = 300  # 5 minutes
  statistic           = "SampleCount"
  threshold           = 0
  alarm_description   = "API backend ECS task has stopped or restarted"
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName = aws_ecs_cluster.main.name
    ServiceName = aws_ecs_service.backend.name
  }

  # Only set alarm actions if SNS is enabled
  alarm_actions = var.enable_sns_alarms ? [aws_sns_topic.alarms[0].arn] : []
  ok_actions    = var.enable_sns_alarms ? [aws_sns_topic.alarms[0].arn] : []

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-api-task-failure"
  })
}

# Worker Task Failure Alarm (running task count drops to 0)
resource "aws_cloudwatch_metric_alarm" "ecs_worker_running_count" {
  alarm_name          = "${var.project_prefix}-worker-not-running"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 2
  metric_name         = "RunningTaskCount"
  namespace           = "ECS/ContainerInsights"
  period              = 60
  statistic           = "Average"
  threshold           = 1
  alarm_description   = "Worker ECS task is not running"
  treat_missing_data  = "breaching"

  dimensions = {
    ClusterName = aws_ecs_cluster.main.name
    ServiceName = aws_ecs_service.worker.name
  }

  alarm_actions = var.enable_sns_alarms ? [aws_sns_topic.alarms[0].arn] : []
  ok_actions    = var.enable_sns_alarms ? [aws_sns_topic.alarms[0].arn] : []

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-worker-not-running"
  })
}

# =============================================================================
# RDS Alarms
# =============================================================================

# RDS CPU Utilization Alarm (>80% for 10 minutes)
resource "aws_cloudwatch_metric_alarm" "rds_cpu_high" {
  alarm_name          = "${var.project_prefix}-rds-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = 300  # 5 minutes
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "RDS CPU utilization is above 80% for 10 minutes"
  treat_missing_data  = "notBreaching"

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.identifier
  }

  alarm_actions = var.enable_sns_alarms ? [aws_sns_topic.alarms[0].arn] : []
  ok_actions    = var.enable_sns_alarms ? [aws_sns_topic.alarms[0].arn] : []

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-rds-cpu-high"
  })
}

# RDS Free Storage Space Alarm (<10% free)
resource "aws_cloudwatch_metric_alarm" "rds_storage_low" {
  alarm_name          = "${var.project_prefix}-rds-storage-low"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  metric_name         = "FreeStorageSpace"
  namespace           = "AWS/RDS"
  period              = 300  # 5 minutes
  statistic           = "Average"
  # 10% of allocated storage in bytes (default 20GB = 2GB threshold)
  threshold           = var.db_allocated_storage * 1024 * 1024 * 1024 * 0.1
  alarm_description   = "RDS storage space is below 10%"
  treat_missing_data  = "notBreaching"

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.identifier
  }

  alarm_actions = var.enable_sns_alarms ? [aws_sns_topic.alarms[0].arn] : []
  ok_actions    = var.enable_sns_alarms ? [aws_sns_topic.alarms[0].arn] : []

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-rds-storage-low"
  })
}

# RDS Database Connections Alarm (>80% of max connections)
resource "aws_cloudwatch_metric_alarm" "rds_connections_high" {
  alarm_name          = "${var.project_prefix}-rds-connections-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "DatabaseConnections"
  namespace           = "AWS/RDS"
  period              = 300  # 5 minutes
  statistic           = "Average"
  # db.t3.micro has ~85 max connections, alert at 70
  threshold           = 70
  alarm_description   = "RDS database connections are high"
  treat_missing_data  = "notBreaching"

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.identifier
  }

  alarm_actions = var.enable_sns_alarms ? [aws_sns_topic.alarms[0].arn] : []
  ok_actions    = var.enable_sns_alarms ? [aws_sns_topic.alarms[0].arn] : []

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-rds-connections-high"
  })
}

# =============================================================================
# ALB Alarms
# =============================================================================

# ALB 5xx Error Rate Alarm
resource "aws_cloudwatch_metric_alarm" "alb_5xx_errors" {
  alarm_name          = "${var.project_prefix}-alb-5xx-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "HTTPCode_ELB_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  period              = 300  # 5 minutes
  statistic           = "Sum"
  threshold           = 10
  alarm_description   = "ALB is returning 5xx errors"
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = aws_lb.main.arn_suffix
  }

  alarm_actions = var.enable_sns_alarms ? [aws_sns_topic.alarms[0].arn] : []
  ok_actions    = var.enable_sns_alarms ? [aws_sns_topic.alarms[0].arn] : []

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-alb-5xx-errors"
  })
}

# ALB Target Response Time Alarm (>2 seconds average)
resource "aws_cloudwatch_metric_alarm" "alb_latency_high" {
  alarm_name          = "${var.project_prefix}-alb-latency-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "TargetResponseTime"
  namespace           = "AWS/ApplicationELB"
  period              = 300  # 5 minutes
  statistic           = "Average"
  threshold           = 2  # 2 seconds
  alarm_description   = "ALB target response time is above 2 seconds"
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = aws_lb.main.arn_suffix
  }

  alarm_actions = var.enable_sns_alarms ? [aws_sns_topic.alarms[0].arn] : []
  ok_actions    = var.enable_sns_alarms ? [aws_sns_topic.alarms[0].arn] : []

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-alb-latency-high"
  })
}

# ALB Healthy Host Count Alarm
resource "aws_cloudwatch_metric_alarm" "alb_unhealthy_hosts" {
  alarm_name          = "${var.project_prefix}-alb-unhealthy-hosts"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 2
  metric_name         = "HealthyHostCount"
  namespace           = "AWS/ApplicationELB"
  period              = 60
  statistic           = "Average"
  threshold           = 1
  alarm_description   = "No healthy hosts behind ALB"
  treat_missing_data  = "breaching"

  dimensions = {
    LoadBalancer = aws_lb.main.arn_suffix
    TargetGroup  = aws_lb_target_group.backend.arn_suffix
  }

  alarm_actions = var.enable_sns_alarms ? [aws_sns_topic.alarms[0].arn] : []
  ok_actions    = var.enable_sns_alarms ? [aws_sns_topic.alarms[0].arn] : []

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-alb-unhealthy-hosts"
  })
}

# =============================================================================
# CloudWatch Dashboard
# =============================================================================

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${var.project_prefix}-dashboard"

  dashboard_body = jsonencode({
    widgets = [
      # Row 1: ECS Metrics
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 8
        height = 6
        properties = {
          title   = "ECS API - CPU & Memory"
          region  = var.aws_region
          metrics = [
            ["AWS/ECS", "CPUUtilization", "ClusterName", aws_ecs_cluster.main.name, "ServiceName", aws_ecs_service.backend.name],
            [".", "MemoryUtilization", ".", ".", ".", "."]
          ]
          period = 300
          stat   = "Average"
        }
      },
      {
        type   = "metric"
        x      = 8
        y      = 0
        width  = 8
        height = 6
        properties = {
          title   = "ECS Worker - CPU & Memory"
          region  = var.aws_region
          metrics = [
            ["AWS/ECS", "CPUUtilization", "ClusterName", aws_ecs_cluster.main.name, "ServiceName", aws_ecs_service.worker.name],
            [".", "MemoryUtilization", ".", ".", ".", "."]
          ]
          period = 300
          stat   = "Average"
        }
      },
      {
        type   = "metric"
        x      = 16
        y      = 0
        width  = 8
        height = 6
        properties = {
          title   = "ECS Running Tasks"
          region  = var.aws_region
          metrics = [
            ["ECS/ContainerInsights", "RunningTaskCount", "ClusterName", aws_ecs_cluster.main.name, "ServiceName", aws_ecs_service.backend.name, { label = "API" }],
            [".", ".", ".", ".", ".", aws_ecs_service.worker.name, { label = "Worker" }]
          ]
          period = 60
          stat   = "Average"
        }
      },
      # Row 2: RDS Metrics
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 8
        height = 6
        properties = {
          title   = "RDS CPU Utilization"
          region  = var.aws_region
          metrics = [
            ["AWS/RDS", "CPUUtilization", "DBInstanceIdentifier", aws_db_instance.main.identifier]
          ]
          period = 300
          stat   = "Average"
          annotations = {
            horizontal = [{ value = 80, label = "Alert Threshold" }]
          }
        }
      },
      {
        type   = "metric"
        x      = 8
        y      = 6
        width  = 8
        height = 6
        properties = {
          title   = "RDS Connections"
          region  = var.aws_region
          metrics = [
            ["AWS/RDS", "DatabaseConnections", "DBInstanceIdentifier", aws_db_instance.main.identifier]
          ]
          period = 300
          stat   = "Average"
          annotations = {
            horizontal = [{ value = 70, label = "Alert Threshold" }]
          }
        }
      },
      {
        type   = "metric"
        x      = 16
        y      = 6
        width  = 8
        height = 6
        properties = {
          title   = "RDS Free Storage (GB)"
          region  = var.aws_region
          metrics = [
            ["AWS/RDS", "FreeStorageSpace", "DBInstanceIdentifier", aws_db_instance.main.identifier, { id = "m1" }]
          ]
          period = 300
          stat   = "Average"
          yAxis = {
            left = { min = 0 }
          }
        }
      },
      # Row 3: SQS Metrics
      {
        type   = "metric"
        x      = 0
        y      = 12
        width  = 8
        height = 6
        properties = {
          title   = "SQS Queue Depth"
          region  = var.aws_region
          metrics = [
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", aws_sqs_queue.layout_jobs.name, { label = "Main Queue" }],
            [".", ".", ".", aws_sqs_queue.layout_jobs_dlq.name, { label = "DLQ" }]
          ]
          period = 60
          stat   = "Average"
        }
      },
      {
        type   = "metric"
        x      = 8
        y      = 12
        width  = 8
        height = 6
        properties = {
          title   = "SQS Messages Processed"
          region  = var.aws_region
          metrics = [
            ["AWS/SQS", "NumberOfMessagesReceived", "QueueName", aws_sqs_queue.layout_jobs.name, { label = "Received" }],
            [".", "NumberOfMessagesDeleted", ".", ".", { label = "Deleted" }]
          ]
          period = 300
          stat   = "Sum"
        }
      },
      {
        type   = "metric"
        x      = 16
        y      = 12
        width  = 8
        height = 6
        properties = {
          title   = "SQS Age of Oldest Message"
          region  = var.aws_region
          metrics = [
            ["AWS/SQS", "ApproximateAgeOfOldestMessage", "QueueName", aws_sqs_queue.layout_jobs.name]
          ]
          period = 60
          stat   = "Maximum"
        }
      },
      # Row 4: ALB Metrics
      {
        type   = "metric"
        x      = 0
        y      = 18
        width  = 8
        height = 6
        properties = {
          title   = "ALB Request Count"
          region  = var.aws_region
          metrics = [
            ["AWS/ApplicationELB", "RequestCount", "LoadBalancer", aws_lb.main.arn_suffix]
          ]
          period = 300
          stat   = "Sum"
        }
      },
      {
        type   = "metric"
        x      = 8
        y      = 18
        width  = 8
        height = 6
        properties = {
          title   = "ALB Response Time"
          region  = var.aws_region
          metrics = [
            ["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", aws_lb.main.arn_suffix]
          ]
          period = 300
          stat   = "Average"
          annotations = {
            horizontal = [{ value = 2, label = "Alert Threshold" }]
          }
        }
      },
      {
        type   = "metric"
        x      = 16
        y      = 18
        width  = 8
        height = 6
        properties = {
          title   = "ALB HTTP Errors"
          region  = var.aws_region
          metrics = [
            ["AWS/ApplicationELB", "HTTPCode_ELB_4XX_Count", "LoadBalancer", aws_lb.main.arn_suffix, { label = "4xx" }],
            [".", "HTTPCode_ELB_5XX_Count", ".", ".", { label = "5xx" }],
            [".", "HTTPCode_Target_5XX_Count", ".", ".", { label = "Target 5xx" }]
          ]
          period = 300
          stat   = "Sum"
        }
      }
    ]
  })
}

# =============================================================================
# Outputs
# =============================================================================

output "cloudwatch_dashboard_url" {
  description = "URL for the CloudWatch dashboard"
  value       = "https://${var.aws_region}.console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}#dashboards:name=${aws_cloudwatch_dashboard.main.dashboard_name}"
}

output "sns_alarms_topic_arn" {
  description = "ARN of the SNS topic for alarms (if enabled)"
  value       = var.enable_sns_alarms ? aws_sns_topic.alarms[0].arn : null
}

