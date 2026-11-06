# ── Rendelések szinkronja a Google Sheetbe (Raspberry Pi) ───────────────
#
# A Pi-n futó tools/order-sync/sync_orders.py ezzel a felhasználóval olvassa
# a rendeléstáblát. Csak olvasni tud, és csak ezt az egy táblát.
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
}

resource "aws_iam_user_policy" "order_sync" {
  name   = "orders-read-only"
  user   = aws_iam_user.order_sync.name
  policy = data.aws_iam_policy_document.order_sync.json
}

output "order_sync_user" {
  description = "Ehhez a felhasználóhoz kell kézzel kulcsot kérni a Pi szinkronhoz."
  value       = aws_iam_user.order_sync.name
}
