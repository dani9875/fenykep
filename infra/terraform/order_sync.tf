# ── Rendelések szinkronja a Google Sheetbe és a fotóké a Drive-ba (Pi) ──
#
# A Pi-n futó tools/order-sync/sync_orders.py ezzel a felhasználóval olvassa
# a rendeléstáblát, az rclone pedig a rendelések fotóit (orders/ mappa).
# Csak olvasni tud: ezt az egy táblát és a bucket orders/ mappáját.
#
# A hozzáférési kulcsot NEM itt hozzuk létre (akkor a titok a
# terraform.tfstate-be kerülne), hanem egyszer kézzel:
#   aws iam create-access-key --user-name <name_prefix>-order-sync --profile ...

resource "aws_iam_user" "order_sync" {
  name = "${var.name_prefix}-order-sync"
}

data "aws_iam_policy_document" "order_sync" {
  statement {
    actions   = ["dynamodb:Scan", "dynamodb:GetItem"]
    resources = [aws_dynamodb_table.orders.arn]
  }

  # A rendelések beszédes nevű fotói (lásd backend/lambda/common/photo_files.py).
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.uploads.arn}/orders/*"]
  }

  statement {
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.uploads.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["orders/", "orders/*"]
    }
  }
}

resource "aws_iam_user_policy" "order_sync" {
  name   = "orders-read-only"
  user   = aws_iam_user.order_sync.name
  policy = data.aws_iam_policy_document.order_sync.json
}

output "order_photos_bucket" {
  description = "Ebből a bucketből (orders/ mappa) másolja az rclone a fotókat a Drive-ba."
  value       = aws_s3_bucket.uploads.bucket
}

output "order_sync_user" {
  description = "Ehhez a felhasználóhoz kell kézzel kulcsot kérni a Pi szinkronhoz."
  value       = aws_iam_user.order_sync.name
}
