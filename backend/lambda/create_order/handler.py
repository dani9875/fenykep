import json
import os
import uuid

from products import get_item_price, get_shipping_fee
from dynamo import put_order
import barion
from ses_mail import send_transfer_instructions, send_admin_notification

HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
}

REQUIRED_CUSTOMER_FIELDS = ["name", "email", "phone", "address", "city", "zip"]
SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "")


def _error(msg: str, code: int = 400):
    return {"statusCode": code, "headers": HEADERS, "body": json.dumps({"error": msg})}


def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _error("Bad JSON")

    customer = body.get("customer", {})
    for field in REQUIRED_CUSTOMER_FIELDS:
        if not customer.get(field):
            return _error(f"Missing customer field: {field}")

    consents = body.get("consents", {})
    if not consents.get("aszf") or not consents.get("privacy"):
        return _error("ÁSZF and privacy consent are both required.")

    shipping = body.get("shipping", {})
    if shipping.get("method") != "foxpost" or not shipping.get("lockerId"):
        return _error("A Foxpost locker must be selected.")

    payment_method = body.get("paymentMethod", "barion")
    if payment_method not in ("barion", "transfer", "cod"):
        return _error("Ismeretlen fizetési mód.")
    if payment_method == "cod" and shipping.get("method") == "foxpost":
        return _error(
            "Utánvét (készpénz) nem választható Foxpost csomagautomatás átvételnél — "
            "az automaták nem fogadnak készpénzt. Válassz bankkártyás fizetést vagy "
            "előre utalást."
        )

    raw_items = body.get("items", [])
    if not raw_items:
        return _error("Cart is empty.")

    # Recompute every price from the server-side catalog.
    # Never trust a price the browser sends.
    priced_items = []
    subtotal = 0
    for raw in raw_items:
        try:
            unit_price = get_item_price(raw["productId"], raw["size"])
        except (KeyError, ValueError) as exc:
            return _error(str(exc))
        if not raw.get("photoKey"):
            return _error(f"Missing uploaded photo for item: {raw.get('productId')}")
        qty = int(raw.get("qty", 1))
        subtotal += unit_price * qty
        priced_items.append(
            {
                "productId": raw["productId"],
                "productName": raw.get("productName", raw["productId"]),
                "size": raw["size"],
                "qty": qty,
                "unitPrice": unit_price,
                "photoKey": raw["photoKey"],
            }
        )

    shipping_fee = get_shipping_fee(subtotal)
    total = subtotal + shipping_fee

    order_id = str(uuid.uuid4())
    order = {
        "orderId": order_id,
        "orderStatus": "pending_payment",
        "paymentMethod": payment_method,
        "customer": customer,
        "shipping": {**shipping, "feeHuf": shipping_fee},
        "items": priced_items,
        "subtotalHuf": subtotal,
        "totalHuf": total,
    }

    if payment_method == "transfer":
        order["orderStatus"] = "pending_transfer"
        put_order(order)
        try:
            send_transfer_instructions(order)
            send_admin_notification(order)
        except Exception as exc:  # noqa: BLE001
            return _error(f"Email küldési hiba: {exc}", code=502)
        return {
            "statusCode": 200,
            "headers": HEADERS,
            "body": json.dumps({
                "orderId": order_id,
                "gatewayUrl": f"{SITE_BASE_URL}/koszonjuk.html?orderId={order_id}&method=transfer",
            }),
        }

    # payment_method == "barion"
    barion_items = [
        {
            "name": f"{i['productName']} ({i['size']})",
            "qty": i["qty"],
            "unit_price": i["unitPrice"],
        }
        for i in priced_items
    ]
    if shipping_fee:
        barion_items.append({"name": "Foxpost szállítás", "qty": 1, "unit_price": shipping_fee})

    try:
        barion_resp = barion.start_payment(order_id, barion_items, total)
    except Exception as exc:  # noqa: BLE001 - surface a clean 502 instead of a stack trace
        return _error(f"Barion error: {exc}", code=502)

    if barion_resp.get("Errors"):
        return _error(f"Barion rejected the payment: {barion_resp['Errors']}", code=502)

    order["paymentId"] = barion_resp["PaymentId"]
    put_order(order)

    return {
        "statusCode": 200,
        "headers": HEADERS,
        "body": json.dumps({"orderId": order_id, "gatewayUrl": barion_resp["GatewayUrl"]}),
    }
