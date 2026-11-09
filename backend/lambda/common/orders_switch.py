"""
Rendelésfelvétel kapcsoló (SSM paraméter, lásd infra/terraform/orders_switch.tf).

A scripts/deploy-frontend.sh --no-orders állítja "true"-ra. Ilyenkor a
create_order új rendelést nem fogad; a már leadott rendelések (Barion
callback, állapotlekérdezés) ettől függetlenül rendben lefutnak.

Az értéket egy percig gyorsítótárazzuk a meleg Lambdában, így nem megy
SSM hívás minden rendelésnél. Ha az SSM nem elérhető, a rendelést
engedjük: egy AWS-hiba miatt ne álljon le az értékesítés.
"""

import os
import time

import boto3

PARAM_NAME = os.environ.get("ORDERS_PAUSED_PARAM", "")
CACHE_SECONDS = 60

PAUSED_MESSAGE = (
    "A rendelések nagy száma miatt átmenetileg nem tudunk új rendelést fogadni. "
    "Hamarosan újra rendelhetsz."
)

_ssm = None
_cached: tuple[float, bool] | None = None


def orders_paused() -> bool:
    global _ssm, _cached
    if not PARAM_NAME:
        return False
    now = time.time()
    if _cached and now - _cached[0] < CACHE_SECONDS:
        return _cached[1]
    try:
        if _ssm is None:
            _ssm = boto3.client("ssm")
        value = _ssm.get_parameter(Name=PARAM_NAME)["Parameter"]["Value"]
        paused = value.strip().lower() == "true"
    except Exception as exc:  # noqa: BLE001
        print(f"[orders_switch] nem olvasható a kapcsoló ({PARAM_NAME}): {exc}")
        paused = False
    _cached = (now, paused)
    return paused
