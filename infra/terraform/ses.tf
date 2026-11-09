# ── SES (e-mail cím hitelesítéssel) ─────────────────────────────────────
#
# Az identity létrehozásakor az AWS küld egy megerősítő linket az adott
# címre. Amíg rá nem kattintasz, arról a címről nem megy ki levél.
#
# A fióknak production accessa van, így bármilyen címzettnek mehet levél.
# Sandboxban (pl. egy új régióban vagy fiókban) a CÍMZETT-nek is
# hitelesítettnek kell lennie: ilyenkor a teszteléshez használt címeket
# vedd fel a ses_verified_recipients listába (infra/DEPLOY.md 8. lépés).

#
# Az SES cím az AWS fiókhoz tartozik, nem egy környezethez. Ha a dev és a
# prod ugyanazt a feladót használja, csak az egyik (a dev) hozza létre:
# különben a prod lebontása a dev levelezését is elvágná.
# Prodban ezért manage_ses_identities = false.

resource "aws_ses_email_identity" "from" {
  count = var.manage_ses_identities ? 1 : 0
  email = var.ses_from_address
}

resource "aws_ses_email_identity" "admin" {
  count = var.manage_ses_identities && var.admin_email != var.ses_from_address ? 1 : 0
  email = var.admin_email
}

resource "aws_ses_email_identity" "recipients" {
  for_each = var.manage_ses_identities ? toset([
    for address in var.ses_verified_recipients :
    address if address != var.ses_from_address && address != var.admin_email
  ]) : toset([])

  email = each.value
}

data "aws_caller_identity" "current" {}

locals {
  # A feladó identity ARN-je akkor is, ha nem ez a környezet kezeli.
  ses_from_identity_arn = "arn:aws:ses:${var.region}:${data.aws_caller_identity.current.account_id}:identity/${var.ses_from_address}"
}

# A korábbi, count nélküli címet a state-ben átnevezzük, így a dev
# apply nem törli és hozza létre újra (és nem kell újra hitelesíteni).
moved {
  from = aws_ses_email_identity.from
  to   = aws_ses_email_identity.from[0]
}
