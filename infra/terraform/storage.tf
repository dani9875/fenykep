# ── DynamoDB: rendelések ────────────────────────────────────────────────
#
# A paymentId-index a Barion callbackhez kell: a Barion csak a paymentId-t
# küldi vissza, abból kell megtalálni a rendelést.

resource "aws_dynamodb_table" "orders" {
  name         = "${var.name_prefix}-orders"
  billing_mode = "PAY_PER_REQUEST" # dev-ben nincs értelme kapacitást foglalni
  hash_key     = "orderId"

  attribute {
    name = "orderId"
    type = "S"
  }

  attribute {
    name = "paymentId"
    type = "S"
  }

  global_secondary_index {
    name            = "paymentId-index"
    hash_key        = "paymentId"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = false # dev; élesben kapcsold be
  }
}

# ── DynamoDB: kérésszámlálók (rate limit) ───────────────────────────────
#
# IP-nként és időablakonként egy sor, TTL-lel. Magától eltakarít, nincs
# karbantartása. Ez az egyetlen védelem, ami a böngészőn kívülről érkező
# hívásokra is hat — a CORS és az Origin-fejléc nem.

resource "aws_dynamodb_table" "rate_limit" {
  name         = "${var.name_prefix}-ratelimit"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "rateKey"

  attribute {
    name = "rateKey"
    type = "S"
  }

  ttl {
    attribute_name = "expiresAt"
    enabled        = true
  }
}

# ── S3: fotófeltöltés + Foxpost cache ───────────────────────────────────
#
# Egy bucket, két prefix:
#   uploads/  — a vásárlók fotói (presigned PUT-tal kerülnek ide)
#   cache/    — a Foxpost automata-lista napi cache-e

resource "random_id" "bucket_suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "uploads" {
  bucket = "${var.name_prefix}-uploads-${random_id.bucket_suffix.hex}"
}

resource "aws_s3_bucket_public_access_block" "uploads" {
  bucket                  = aws_s3_bucket.uploads.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# A böngésző közvetlenül a presigned URL-re PUT-ol, ezért a bucketnek
# engedélyeznie kell a CORS-t a frontend origin-jéről.
resource "aws_s3_bucket_cors_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id

  cors_rule {
    allowed_origins = local.allowed_origins
    allowed_methods = ["PUT"]
    allowed_headers = ["*"]
    max_age_seconds = 3000
  }
}

# Dev-ben a feltöltött tesztfotók ne gyűljenek örökre.
resource "aws_s3_bucket_lifecycle_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id

  rule {
    id     = "expire-dev-uploads"
    status = var.environment == "dev" ? "Enabled" : "Disabled"

    filter {
      prefix = "uploads/"
    }

    expiration {
      days = 90
    }
  }
}
