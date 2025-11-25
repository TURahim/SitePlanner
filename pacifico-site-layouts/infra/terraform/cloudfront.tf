# =============================================================================
# A-15: CloudFront Distribution for Frontend
# =============================================================================
# This file configures CloudFront CDN for the React frontend:
# - Origin Access Control (OAC) for secure S3 access
# - SPA routing with custom error responses
# - Cache optimization for static assets
# - Optional custom domain support with ACM certificate
# =============================================================================

# =============================================================================
# Variables for Custom Domain (Optional)
# =============================================================================

variable "custom_domain" {
  description = "Custom domain for the frontend (e.g., app.pacifico.com). Leave empty to use CloudFront default domain."
  type        = string
  default     = ""
}

variable "custom_domain_certificate_arn" {
  description = "ARN of ACM certificate for custom domain (must be in us-east-1 for CloudFront)"
  type        = string
  default     = ""
}

# =============================================================================
# Origin Access Control (OAC)
# =============================================================================
# OAC is the recommended way to give CloudFront access to S3 (replaces OAI)

resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${var.project_prefix}-frontend-oac"
  description                       = "OAC for ${var.project_prefix} frontend S3 bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# =============================================================================
# CloudFront Distribution
# =============================================================================

resource "aws_cloudfront_distribution" "frontend" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "Pacifico Site Layouts Frontend (${var.environment})"
  default_root_object = "index.html"
  price_class         = "PriceClass_100" # US, Canada, Europe - cheapest for MVP

  # Aliases (custom domain) - only if provided
  aliases = var.custom_domain != "" ? [var.custom_domain] : []

  # ==========================================================================
  # S3 Origin Configuration
  # ==========================================================================
  origin {
    domain_name              = aws_s3_bucket.frontend_assets.bucket_regional_domain_name
    origin_id                = "S3-${aws_s3_bucket.frontend_assets.id}"
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }

  # ==========================================================================
  # Default Cache Behavior (for all requests)
  # ==========================================================================
  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-${aws_s3_bucket.frontend_assets.id}"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 86400    # 1 day
    max_ttl                = 31536000 # 1 year
    compress               = true
  }

  # ==========================================================================
  # Cache Behavior for index.html (no caching - always fresh)
  # ==========================================================================
  ordered_cache_behavior {
    path_pattern     = "/index.html"
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-${aws_s3_bucket.frontend_assets.id}"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 0 # No caching for index.html
    max_ttl                = 0
    compress               = true
  }

  # ==========================================================================
  # Cache Behavior for hashed assets (long-term caching)
  # ==========================================================================
  ordered_cache_behavior {
    path_pattern     = "/assets/*"
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-${aws_s3_bucket.frontend_assets.id}"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 31536000 # 1 year
    default_ttl            = 31536000
    max_ttl                = 31536000
    compress               = true
  }

  # ==========================================================================
  # Custom Error Responses (for SPA routing)
  # ==========================================================================
  # Return index.html for 403/404 errors to enable client-side routing

  custom_error_response {
    error_code            = 403
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 0
  }

  custom_error_response {
    error_code            = 404
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 0
  }

  # ==========================================================================
  # SSL/TLS Configuration
  # ==========================================================================
  viewer_certificate {
    # Use custom certificate if domain is provided, otherwise CloudFront default
    acm_certificate_arn            = var.custom_domain_certificate_arn != "" ? var.custom_domain_certificate_arn : null
    cloudfront_default_certificate = var.custom_domain_certificate_arn == ""
    minimum_protocol_version       = var.custom_domain_certificate_arn != "" ? "TLSv1.2_2021" : "TLSv1"
    ssl_support_method             = var.custom_domain_certificate_arn != "" ? "sni-only" : null
  }

  # ==========================================================================
  # Geographic Restrictions (none for MVP)
  # ==========================================================================
  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  # ==========================================================================
  # Logging (disabled for MVP - enable for production)
  # ==========================================================================
  # logging_config {
  #   bucket          = aws_s3_bucket.logs.bucket_domain_name
  #   prefix          = "cloudfront/"
  #   include_cookies = false
  # }

  tags = merge(local.common_tags, {
    Name = "${var.project_prefix}-frontend-cdn"
  })
}

# =============================================================================
# S3 Bucket Policy for CloudFront OAC
# =============================================================================
# Replace the existing public bucket policy with CloudFront-only access

resource "aws_s3_bucket_policy" "frontend_assets_cloudfront" {
  bucket = aws_s3_bucket.frontend_assets.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudFrontServicePrincipal"
        Effect = "Allow"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.frontend_assets.arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.frontend.arn
          }
        }
      }
    ]
  })

  # This replaces the original public policy
  depends_on = [aws_s3_bucket_public_access_block.frontend_assets]
}

# =============================================================================
# CloudFront Outputs
# =============================================================================

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID (for cache invalidation)"
  value       = aws_cloudfront_distribution.frontend.id
}

output "cloudfront_distribution_arn" {
  description = "ARN of the CloudFront distribution"
  value       = aws_cloudfront_distribution.frontend.arn
}

output "cloudfront_domain_name" {
  description = "CloudFront distribution domain name"
  value       = aws_cloudfront_distribution.frontend.domain_name
}

output "frontend_url" {
  description = "URL to access the frontend"
  value       = var.custom_domain != "" ? "https://${var.custom_domain}" : "https://${aws_cloudfront_distribution.frontend.domain_name}"
}

