variable "aws_profile" {
  description = "AWS CLI profil neve (~/.aws/config)."
  type        = string
  default     = "wordpress-deploy"
}

variable "region" {
  description = "AWS régió. A Lambda, DynamoDB, S3 és az SES is ide kerül."
  type        = string
  default     = "eu-central-1"
}

variable "environment" {
  description = "Környezet neve. Több környezetet külön name_prefix-szel futtass."
  type        = string
  default     = "dev"
}

variable "name_prefix" {
  description = "Minden erőforrás neve ezzel kezdődik."
  type        = string
  default     = "litho-dev"
}

# ── Frontend ────────────────────────────────────────────────────────────

variable "site_url" {
  description = <<-EOT
    A Cloudflare Pages oldal URL-je, záró / nélkül.
    Például: https://fenykep.pages.dev
    Ebből lesz a Barion visszairányítás és az e-mailekben lévő link.
    Ezt a Pages projekt létrehozása UTÁN tudod (lásd infra/DEPLOY.md 3. lépés).
  EOT
  type        = string

  validation {
    condition     = can(regex("^https://", var.site_url)) && !can(regex("/$", var.site_url))
    error_message = "A site_url https://-sel kezdődjön, és ne legyen a végén perjel."
  }
}

variable "extra_allowed_origins" {
  description = <<-EOT
    További origin-ek, amiket a CORS és az S3 feltöltés elfogad a site_url mellett.
    Dev-hez hasznos: a Pages preview URL-ek (https://<hash>.fenykep.pages.dev) és
    a helyi szerver. Ha egy preview deployról is tesztelnél, vedd fel ide.
  EOT
  type        = list(string)
  default     = ["http://localhost:8787"]
}

variable "enforce_origin" {
  description = <<-EOT
    Megköveteljük-e, hogy a rendelés/feltöltés/kapcsolat hívások a saját
    oldalunkról (Origin fejléc) érkezzenek. Kiszűri a naiv szkripteket és a
    más oldalba ágyazott hívásokat — de a fejléc hamisítható, ezért ez réteg,
    nem biztonsági határ. Hibakereséshez (pl. curl-teszt) kapcsold false-ra.
  EOT
  type        = bool
  default     = true
}

# ── Barion ──────────────────────────────────────────────────────────────

variable "barion_api_base" {
  description = "https://api.test.barion.com (sandbox) vagy https://api.barion.com (éles)."
  type        = string
  default     = "https://api.test.barion.com"
}

variable "barion_poskey" {
  description = "Barion POSKey a kereskedői admin felületről. Titok — dev.auto.tfvars-ba tedd, ne ide."
  type        = string
  sensitive   = true
}

variable "barion_funding_sources" {
  description = <<-EOT
    Mit kínáljon fel a Barion fizetőoldala.
    "BankCard" — csak bankkártya, a vásárló rögtön a kártyaűrlapot kapja.
    "All"      — kártya és Barion egyenleg is; ilyenkor egy létező Barion
                 fiókkal rendelkező vásárló a tárca-belépéssel találkozik.
  EOT
  type        = string
  default     = "BankCard"
}

variable "barion_payee" {
  description = "A Barion fiókhoz tartozó e-mail cím, ami a pénzt kapja."
  type        = string
}

# ── SES ─────────────────────────────────────────────────────────────────

variable "ses_from_address" {
  description = "Feladó cím. Az SES e-mailben küld egy megerősítő linket erre a címre."
  type        = string
}

variable "admin_email" {
  description = "Ide mennek az 'új rendelés' értesítők."
  type        = string
}

variable "ses_verified_recipients" {
  description = <<-EOT
    További címek, amiket hitelesíteni kell.
    SES sandboxban CSAK hitelesített címre lehet levelet küldeni, tehát ide vedd
    fel azokat a teszt-e-mail címeket, amikkel rendelést adsz le. Éles forgalomhoz
    production access kell (lásd infra/DEPLOY.md 8. lépés).
  EOT
  type        = list(string)
  default     = []
}

# ── Utalásos fizetés ────────────────────────────────────────────────────

variable "bank_account_name" {
  description = "Kedvezményezett neve az utalásos e-mailben."
  type        = string
  default     = "Fény·kép Stúdió"
}

variable "bank_account_number" {
  description = "Számlaszám/IBAN az utalásos e-mailben."
  type        = string
  default     = "IBAN NINCS BEÁLLÍTVA"
}

# ── Lambda finomhangolás ────────────────────────────────────────────────

variable "log_retention_days" {
  description = "CloudWatch log megőrzés. Dev-ben ne legyen 'soha' — fizetni kell érte."
  type        = number
  default     = 14
}
