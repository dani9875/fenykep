terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.40"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Dev: a state helyben marad (infra/terraform/terraform.tfstate).
  # FIGYELEM: a state tartalmazza a Barion POSKey-t és a többi titkot is,
  # ezért .gitignore-olt. Ha több gépről vagy csapatban dolgoznál, tedd át
  # egy titkosított S3 backendbe:
  #
  # backend "s3" {
  #   bucket  = "litho-tfstate-<accountid>"
  #   key     = "dev/terraform.tfstate"
  #   region  = "eu-central-1"
  #   profile = "wordpress-deploy"
  #   encrypt = true
  # }
}

provider "aws" {
  region  = var.region
  profile = var.aws_profile

  default_tags {
    tags = {
      Project     = "fenykep"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
