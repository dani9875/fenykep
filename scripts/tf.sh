#!/usr/bin/env bash
#
# Terraform a megfelelő környezetre.
#
#   ./scripts/tf.sh dev plan
#   ./scripts/tf.sh dev apply
#   ./scripts/tf.sh prod plan
#   ./scripts/tf.sh prod apply
#   ./scripts/tf.sh prod output
#
# A környezet választja ki a Terraform workspace-t (külön state) és a hozzá
# tartozó tfvars fájlt, így a dev beállításai nem kerülhetnek a prodra.
#   dev  -> "default" workspace (a meglévő state), dev.tfvars
#   prod -> "prod" workspace, prod.tfvars

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF_DIR="$ROOT/infra/terraform"

ENV="${1:-}"
shift || true
case "$ENV" in
  dev)  WORKSPACE="default" ;;
  prod) WORKSPACE="prod" ;;
  *) echo "Használat: $0 dev|prod <terraform parancs> [kapcsolók]" >&2; exit 1 ;;
esac

CMD="${1:-plan}"
shift || true

VARS="$TF_DIR/$ENV.tfvars"

# A prod workspace az első futáskor jön létre.
if [[ "$WORKSPACE" != "default" ]] && ! terraform -chdir="$TF_DIR" workspace list | grep -qw "$WORKSPACE"; then
  terraform -chdir="$TF_DIR" workspace new "$WORKSPACE" >/dev/null
fi
export TF_WORKSPACE="$WORKSPACE"

case "$CMD" in
  plan|apply|destroy|import|refresh|console)
    if [[ ! -f "$VARS" ]]; then
      echo "HIBA: hiányzik a $VARS (másold le a $ENV.tfvars.example-ből)." >&2
      exit 1
    fi
    if [[ "$ENV" == "prod" && "$CMD" =~ ^(apply|destroy)$ ]]; then
      read -r -p "ÉLES környezet: terraform $CMD. Írd be, hogy prod: " answer
      [[ "$answer" == "prod" ]] || { echo "Megszakítva."; exit 1; }
    fi
    echo "Környezet: $ENV (workspace: $WORKSPACE, $ENV.tfvars)"
    exec terraform -chdir="$TF_DIR" "$CMD" -var-file="$VARS" "$@"
    ;;
  *)
    exec terraform -chdir="$TF_DIR" "$CMD" "$@"
    ;;
esac
