# ── Rendelésfelvétel kapcsoló ───────────────────────────────────────────
#
# "true" értéknél a create_order nem fogad új rendelést (kapacitáshiány).
# A scripts/deploy-frontend.sh --no-orders állítja true-ra, a sima deploy
# vissza false-ra, így a weboldal és a backend mindig együtt vált.
#
# A Terraform csak létrehozza; az értékét utána a deploy szkript kezeli,
# ezért egy későbbi terraform apply nem írja vissza.

resource "aws_ssm_parameter" "orders_paused" {
  name        = "/${var.name_prefix}/orders_paused"
  description = "true: a webshop nem fogad új rendelést (deploy-frontend.sh --no-orders)"
  type        = "String"
  value       = "false"

  lifecycle {
    ignore_changes = [value]
  }
}

data "aws_iam_policy_document" "orders_switch" {
  statement {
    actions   = ["ssm:GetParameter"]
    resources = [aws_ssm_parameter.orders_paused.arn]
  }
}

output "orders_paused_param" {
  description = "A rendelésfelvétel kapcsoló SSM paraméter neve (a deploy szkript használja)."
  value       = aws_ssm_parameter.orders_paused.name
}

output "aws_region" {
  value = var.region
}

output "aws_profile" {
  value = var.aws_profile
}
