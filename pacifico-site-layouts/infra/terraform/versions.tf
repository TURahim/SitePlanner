terraform {
  required_version = ">= 1.6.0"

  backend "s3" {
    bucket = "pacifico-tfstate-dev"
    key    = "site-layouts/terraform.tfstate"
    region = "us-east-1"
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}
