#!/usr/bin/env bash
#
# A frontend kideployolása Cloudflare Pages-re.
#
# Mit csinál:
#   1. Kiolvassa az API Gateway URL-jét a Terraform outputból (vagy az
#      API_URL környezeti változóból, ha megadtad).
#   2. A frontend/ egy ideiglenes másolatában kicseréli a __API_URL__
#      helyőrzőt — a repóban lévő fájlok nem változnak, a helyi tesztelés
#      továbbra is a localhost:8787-et hívja.
#   3. Feltölti a másolatot wrangleren keresztül.
#
# Használat:
#   ./scripts/deploy-frontend.sh                    # production deploy
#   ./scripts/deploy-frontend.sh --preview          # preview (külön URL)
#   ./scripts/deploy-frontend.sh --dry-run          # összeállítja, de nem tölt fel
#   API_URL=https://... ./scripts/deploy-frontend.sh   # Terraform nélkül
#
# Környezeti változók:
#   API_URL            felülírja a Terraform outputot
#   CF_PAGES_PROJECT   a Cloudflare Pages projekt neve (alap: fenykep)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF_DIR="$ROOT/infra/terraform"
PROJECT="${CF_PAGES_PROJECT:-fenykep}"
BRANCH="main"
DRY_RUN=0

for arg in "$@"; do
  case "$arg" in
    # A main-től eltérő branch-név preview deployt csinál, saját URL-lel.
    --preview) BRANCH="preview" ;;
    --dry-run) DRY_RUN=1 ;;
    *) echo "Ismeretlen kapcsoló: $arg" >&2; exit 1 ;;
  esac
done

# ── 1. API URL ──────────────────────────────────────────────────────────
if [[ -z "${API_URL:-}" ]]; then
  if [[ ! -d "$TF_DIR/.terraform" ]]; then
    echo "HIBA: a Terraform még nincs inicializálva ($TF_DIR)." >&2
    echo "Futtasd előbb: cd infra/terraform && terraform init && terraform apply" >&2
    echo "Vagy add meg kézzel: API_URL=https://... $0" >&2
    exit 1
  fi
  API_URL="$(terraform -chdir="$TF_DIR" output -raw api_base_url)"
fi

if [[ -z "$API_URL" || "$API_URL" != https://* ]]; then
  echo "HIBA: érvénytelen API URL: '$API_URL'" >&2
  exit 1
fi

echo "API URL:      $API_URL"
echo "Pages projekt: $PROJECT (branch: $BRANCH)"

# ── 2. Ideiglenes másolat, behelyettesített URL-lel ─────────────────────
DIST="$(mktemp -d)"
trap 'rm -rf "$DIST"' EXIT

cp -R "$ROOT/frontend/." "$DIST/"

# Csak azt az EGY sort írjuk át, ami az URL-t tartalmazza. A korábbi
# globális csere a kódban lévő helyőrző-hivatkozásokat (és a kommenteket)
# is átírta, amitől a "nincs beállítva az API URL" figyelmeztetés minden
# deployolt oldalon hamisan elsült.
# A -i.bak forma GNU és BSD (macOS) seddel is működik.
sed -i.bak "s|^const DEPLOYED_API_URL = .*|const DEPLOYED_API_URL = \"$API_URL\";|" "$DIST/js/config.js"
rm -f "$DIST/js/config.js.bak"

if ! grep -q "^const DEPLOYED_API_URL = \"https://" "$DIST/js/config.js"; then
  echo "HIBA: az API URL behelyettesítése nem sikerült." >&2
  exit 1
fi

# A VERZIO.txt csak a helyi fejlesztést segíti, nincs rá szükség élesben.
rm -f "$DIST/VERZIO.txt"

# ── 3. Feltöltés ────────────────────────────────────────────────────────
if [[ "$DRY_RUN" == "1" ]]; then
  KEEP="$(mktemp -d)"
  cp -R "$DIST/." "$KEEP/"
  echo
  echo "DRY RUN — nem történt feltöltés."
  echo "Az összeállított oldal itt van: $KEEP"
  grep -n "DEPLOYED_API_URL" "$KEEP/js/config.js"
  exit 0
fi

npx --yes wrangler@3 pages deploy "$DIST" \
  --project-name "$PROJECT" \
  --branch "$BRANCH" \
  --commit-dirty=true

echo
echo "Kész. Ha ez az első deploy, ellenőrizd, hogy a Terraform site_url"
echo "változója a fenti URL-re mutat-e — abból lesz a Barion visszairányítás."
