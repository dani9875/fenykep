"""
POST /barion-callback — a Barion IPN végpontja.

A Barion minden állapotváltozásnál meghívja ezt az URL-t, és csak a
paymentId-t küldi. A hívás maga NEM bizonyítja, hogy a fizetés sikeres
volt — az állapotot a PaymentState végpontról kérdezzük le (payments.py).

Mindig 200-at adunk vissza, üzleti elutasításnál is. A Barion 15
másodpercen belül vár választ, és 200 hiányában ötször újrahív
(2, 6, 18, 54, 102 másodperc múlva).
"""

import json

from dynamo import get_order_by_payment_id
import payments

HEADERS = {"Content-Type": "application/json"}


def _ok(message: str, extra: dict | None = None):
    body = {"message": message}
    body.update(extra or {})
    return {"statusCode": 200, "headers": HEADERS, "body": json.dumps(body)}


def _payment_id_from(event) -> str | None:
    """
    A paymentId query paraméterben jön. Néhány Barion-integrációnál a
    törzsben is megérkezik (form-encoded vagy JSON), ezért mindkettőt nézzük.
    """
    params = event.get("queryStringParameters") or {}
    for key in ("paymentId", "PaymentId", "paymentid"):
        if params.get(key):
            return params[key]

    raw_body = event.get("body")
    if not raw_body:
        return None
    try:
        parsed = json.loads(raw_body)
        if isinstance(parsed, dict):
            for key in ("paymentId", "PaymentId"):
                if parsed.get(key):
                    return parsed[key]
    except (json.JSONDecodeError, TypeError):
        import urllib.parse

        form = urllib.parse.parse_qs(raw_body)
        for key in ("paymentId", "PaymentId"):
            if form.get(key):
                return form[key][0]
    return None


def handler(event, context):
    payment_id = _payment_id_from(event)
    if not payment_id:
        # 400 itt rendben van: nincs mit újrapróbálni, ez nem a Barion hívása.
        return {"statusCode": 400, "headers": HEADERS, "body": json.dumps({"error": "Missing paymentId"})}

    try:
        order = get_order_by_payment_id(payment_id)
    except Exception as exc:  # noqa: BLE001
        # Adatbázis hiba: 500-at adunk, hogy a Barion újrapróbálja.
        print(f"[callback] lookup failed for {payment_id}: {exc}")
        return {"statusCode": 500, "headers": HEADERS, "body": json.dumps({"error": "lookup failed"})}

    if not order:
        # Nem a mi fizetésünk (vagy törölt rendelés). Nincs értelme újrahívni.
        print(f"[callback] unknown paymentId {payment_id}")
        return _ok("Unknown payment, ignored")

    try:
        result = payments.reconcile(order, source="callback")
    except Exception as exc:  # noqa: BLE001
        print(f"[callback] reconcile crashed for {payment_id}: {exc}")
        return _ok("Error logged")

    return _ok("OK", {"orderStatus": result["orderStatus"], "paymentStatus": result["paymentStatus"]})
