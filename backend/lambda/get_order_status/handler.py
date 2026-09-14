"""
GET /orders/{orderId} — a köszönőoldal ezt kérdezi le.

Ha a rendelés még nyitott bankkártyás fizetés, magunk is rákérdezünk a
Barionnál. Így akkor is helyes állapotot mutatunk, ha az IPN késik vagy
elmarad (rosszul beállított CallbackUrl, sandbox, hálózati hiba).

A PaymentState végpont 5 másodpercen belüli ismételt kérdésre 429-et ad,
ezért csak akkor egyeztetünk, ha az utolsó frissítés óta eltelt ennyi idő.
"""

import json
import time

from dynamo import get_order
import payments

HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Cache-Control": "no-store",
}

RECONCILE_MIN_AGE_SECONDS = 6

# Ezekben az állapotokban érdemes újrakérdezni a Barionnál.
OPEN_FOR_RECONCILE = {"payment_init", "pending_payment"}

STATUS_MESSAGES = {
    "pending_payment": "A fizetés feldolgozás alatt.",
    "payment_init": "A fizetés feldolgozás alatt.",
    "paid": "A fizetés sikeres volt.",
    "pending_transfer": "A rendelést rögzítettük, várjuk az átutalást.",
    "pending_cod": "A rendelést rögzítettük, utánvéttel fizetsz átvételkor.",
    "payment_failed": "A fizetés nem sikerült.",
    "payment_canceled": "A fizetést megszakítottad.",
    "payment_expired": "A fizetési idő lejárt.",
    "payment_start_failed": "A fizetést nem sikerült elindítani.",
    "payment_mismatch": "A fizetett összeg nem egyezik a rendelés végösszegével — kollégánk ellenőrzi.",
    "payment_review": "A fizetés ellenőrzés alatt.",
}


def handler(event, context):
    order_id = (event.get("pathParameters") or {}).get("orderId")
    if not order_id:
        return {"statusCode": 400, "headers": HEADERS, "body": json.dumps({"error": "Missing orderId"})}

    order = get_order(order_id)
    if not order:
        return {"statusCode": 404, "headers": HEADERS, "body": json.dumps({"error": "Not found"})}

    status = order.get("orderStatus", "")
    age = time.time() - float(order.get("updatedAt", 0))
    if status in OPEN_FOR_RECONCILE and order.get("paymentId") and age >= RECONCILE_MIN_AGE_SECONDS:
        try:
            result = payments.reconcile(order, source="status-poll")
            status = result["orderStatus"]
        except Exception as exc:  # noqa: BLE001
            print(f"[status] reconcile failed for {order_id}: {exc}")

    return {
        "statusCode": 200,
        "headers": HEADERS,
        "body": json.dumps(
            {
                "orderId": order["orderId"],
                "status": status,
                "message": STATUS_MESSAGES.get(status, ""),
                "totalHuf": int(order.get("totalHuf", 0)),
                "paymentMethod": order.get("paymentMethod", "barion"),
                "shippingMethod": (order.get("shipping") or {}).get("method", ""),
            }
        ),
    }
