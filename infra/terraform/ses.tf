# ── SES (sandbox, e-mail cím hitelesítéssel) ────────────────────────────
#
# Az identity létrehozásakor az AWS küld egy megerősítő linket az adott
# címre. Amíg rá nem kattintasz, arról a címről nem megy ki levél.
#
# SES sandboxban a CÍMZETT-nek is hitelesítettnek kell lennie. Ezért a
# teszteléshez használt vásárlói e-mail címeket is vedd fel a
# ses_verified_recipients listába — különben a rendelés létrejön, de a
# visszaigazoló levél "Email address is not verified" hibára fut.
#
# Éles forgalomhoz production access kell (infra/DEPLOY.md 8. lépés),
# onnantól bármilyen címre mehet levél.

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
