# ── SES (e-mail cím hitelesítéssel) ─────────────────────────────────────
#
# Az identity létrehozásakor az AWS küld egy megerősítő linket az adott
# címre. Amíg rá nem kattintasz, arról a címről nem megy ki levél.
#
# A fióknak production accessa van, így bármilyen címzettnek mehet levél.
# Sandboxban (pl. egy új régióban vagy fiókban) a CÍMZETT-nek is
# hitelesítettnek kell lennie: ilyenkor a teszteléshez használt címeket
# vedd fel a ses_verified_recipients listába (infra/DEPLOY.md 8. lépés).

resource "aws_ses_email_identity" "from" {
  email = var.ses_from_address
}

resource "aws_ses_email_identity" "admin" {
  count = var.admin_email == var.ses_from_address ? 0 : 1
  email = var.admin_email
}

resource "aws_ses_email_identity" "recipients" {
  for_each = toset([
    for address in var.ses_verified_recipients :
    address if address != var.ses_from_address && address != var.admin_email
  ])

  email = each.value
}
