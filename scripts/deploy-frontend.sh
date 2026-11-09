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
#   ./scripts/deploy-frontend.sh --offline          # kikapcsolja az oldalt (csak egy
#                                                   # "nem elérhető" lap marad fent)
#   ./scripts/deploy-frontend.sh --no-orders        # az oldal fent marad, de rendelni
#                                                   # nem lehet (kapacitáshiány sáv); a
#                                                   # backend is elutasítja az új rendelést
#   Visszakapcsolás: sima ./scripts/deploy-frontend.sh
#   API_URL=https://... ./scripts/deploy-frontend.sh   # Terraform nélkül
#
# Környezeti változók:
#   API_URL            felülírja a Terraform outputot
#   CF_PAGES_PROJECT   a Cloudflare Pages projekt neve (alap: fenykep)
#   ORDERS_PAUSED_PARAM, AWS_REGION, AWS_PROFILE
#                      a backend kapcsolóhoz; alapból a Terraform outputból

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF_DIR="$ROOT/infra/terraform"
PROJECT="${CF_PAGES_PROJECT:-fenykep}"
BRANCH="main"
DRY_RUN=0
OFFLINE=0
NO_ORDERS=0

for arg in "$@"; do
  case "$arg" in
    # A main-től eltérő branch-név preview deployt csinál, saját URL-lel.
    --preview) BRANCH="preview" ;;
    --dry-run) DRY_RUN=1 ;;
    --offline) OFFLINE=1 ;;
    --no-orders) NO_ORDERS=1 ;;
    *) echo "Ismeretlen kapcsoló: $arg" >&2; exit 1 ;;
  esac
done

# ── Kikapcsolt oldal ────────────────────────────────────────────────────
# Minden címen ugyanaz a lap jelenik meg (a 404.html miatt a régi
# címeken is), a keresők pedig noindexet kapnak.
if [[ "$OFFLINE" == "1" ]]; then
  DIST="$(mktemp -d)"
  trap 'rm -rf "$DIST"' EXIT
  cat > "$DIST/index.html" <<'HTML'
<!DOCTYPE html>
<html lang="hu">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Fény·kép</title>
<style>
  html, body { height: 100%; margin: 0; }
  body { display: flex; align-items: center; justify-content: center; text-align: center;
         background: #F3EDE3; color: #1E1B18; padding: 0 16px;
         font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
  h1 { font-weight: 500; letter-spacing: -0.02em; font-size: 3.2rem; margin: 0 0 1rem; }
  h1 span { color: #E39A2D; }
  p { margin: 0.4rem 0; color: #5a534b; font-size: 1.3rem; }
  a { color: inherit; }
</style>
</head>
<body>
  <main>
    <h1>Fény<span>·</span>kép</h1>
    <p>A webshop jelenleg nem elérhető. Hamarosan visszatérünk.</p>
    <p><a href="mailto:info@feny-kep.hu">info@feny-kep.hu</a></p>
  </main>
</body>
</html>
HTML
  cp "$DIST/index.html" "$DIST/404.html"
  printf 'User-agent: *\nDisallow: /\n' > "$DIST/robots.txt"
  printf '/*\n  X-Robots-Tag: noindex, nofollow\n  Cache-Control: no-store\n' > "$DIST/_headers"

  echo "Pages projekt: $PROJECT (branch: $BRANCH) · KIKAPCSOLT oldal"
  if [[ "$DRY_RUN" == "1" ]]; then
    KEEP="$(mktemp -d)"; cp -R "$DIST/." "$KEEP/"
    echo "DRY RUN, nem történt feltöltés. Az oldal itt van: $KEEP"
    exit 0
  fi
  npx --yes wrangler@3 pages deploy "$DIST" \
    --project-name "$PROJECT" --branch "$BRANCH" --commit-dirty=true
  echo
  echo "Az oldal ki van kapcsolva. Visszakapcsolás: ./scripts/deploy-frontend.sh"
  exit 0
fi

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

# ── Rendelésfelvétel szüneteltetése ─────────────────────────────────────
if [[ "$NO_ORDERS" == "1" ]]; then
  sed -i.bak "s|^const ORDERS_PAUSED = .*|const ORDERS_PAUSED = true;|" "$DIST/js/cart.js"
  rm -f "$DIST/js/cart.js.bak"
  if ! grep -q "^const ORDERS_PAUSED = true;" "$DIST/js/cart.js"; then
    echo "HIBA: a rendelésfelvétel kikapcsolása nem sikerült." >&2
    exit 1
  fi
  echo "Rendelésfelvétel: SZÜNETEL (visszakapcsolás: sima ./scripts/deploy-frontend.sh)"
fi

# ── Backend kapcsoló ────────────────────────────────────────────────────
# A create_order Lambda egy SSM paraméterből olvassa, fogad-e rendelést
# (infra/terraform/orders_switch.tf). Ugyanaz a deploy állítja, mint a
# weboldalt, így a kettő nem csúszhat szét.
set_backend_orders_switch() {
  local value="$1" param region profile
  param="${ORDERS_PAUSED_PARAM:-$(terraform -chdir="$TF_DIR" output -raw orders_paused_param 2>/dev/null || true)}"
  region="${AWS_REGION:-$(terraform -chdir="$TF_DIR" output -raw aws_region 2>/dev/null || true)}"
  profile="${AWS_PROFILE:-$(terraform -chdir="$TF_DIR" output -raw aws_profile 2>/dev/null || true)}"
  if [[ -z "$param" || "$param" == *"No outputs"* || "$param" == *"Warning"* ]]; then
    echo "FIGYELEM: nincs backend kapcsoló (futtasd: cd infra/terraform && terraform apply)." >&2
    return 1
  fi
  aws ssm put-parameter --name "$param" --value "$value" --type String --overwrite \
    ${region:+--region "$region"} ${profile:+--profile "$profile"} >/dev/null || return 1
  echo "Backend rendelésfelvétel: $([[ "$value" == "true" ]] && echo SZÜNETEL || echo NYITVA) ($param)"
}

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

# Előbb a backend: szüneteltetésnél így a weboldal frissülése előtt sem
# csúszhat be rendelés. Preview deploy a backendhez nem nyúl.
if [[ "$BRANCH" == "main" ]]; then
  if [[ "$NO_ORDERS" == "1" ]]; then
    if ! set_backend_orders_switch true; then
      echo "HIBA: a backend rendelésfelvételt nem sikerült leállítani, nem deployolok." >&2
      exit 1
    fi
  else
    set_backend_orders_switch false \
      || echo "FIGYELEM: a backend kapcsolót nem sikerült visszaállítani; ellenőrizd kézzel." >&2
  fi
fi

npx --yes wrangler@3 pages deploy "$DIST" \
  --project-name "$PROJECT" \
  --branch "$BRANCH" \
  --commit-dirty=true

echo
echo "Kész. Ha ez az első deploy, ellenőrizd, hogy a Terraform site_url"
echo "változója a fenti URL-re mutat-e — abból lesz a Barion visszairányítás."
