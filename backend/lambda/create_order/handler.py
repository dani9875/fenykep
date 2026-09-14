"""
POST /orders — rendelés létrehozása és a fizetés elindítása.

A böngészőtől érkező árakat soha nem hisszük el: minden tétel ára a
products.py katalógusból jön újraszámolva. A rendelés a DynamoDB-be
kerül, mielőtt a vásárlót bárhová elküldenénk, hogy egy félbeszakadt
fizetés is nyomot hagyjon.
"""

import json
import os
import re
import uuid

from products import (
    MAX_ITEMS_PER_ORDER,
    MAX_QTY_PER_ITEM,
    SHIPPING_METHODS,
    get_cod_fee,
    get_item_price,
    get_shipping_fee,
    is_payment_allowed,
)
from dynamo import put_order, update_order_status
import barion
from ses_mail import (
    send_admin_notification,
    send_cod_confirmation,
    send_transfer_instructions,
)

HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
}

SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "").rstrip("/")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]{2,}$")
ZIP_RE = re.compile(r"^\d{4}$")
PHONE_RE = re.compile(r"^[+0-9 ()/.-]{7,20}$")

FIELD_LABELS = {
    "name": "teljes név",
    "email": "e-mail cím",
    "phone": "telefonszám",
    "address": "utca, házszám",
    "city": "város",
    "zip": "irányítószám",
}

MAX_FIELD_LENGTH = 200
MAX_NOTES_LENGTH = 1000


def _error(msg: str, code: int = 400):
    return {"statusCode": code, "headers": HEADERS, "body": json.dumps({"error": msg})}


def _ok(payload: dict):
    return {"statusCode": 200, "headers": HEADERS, "body": json.dumps(payload)}


def _clean(value, limit: int = MAX_FIELD_LENGTH) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _validate_address_block(block: dict, prefix: str) -> str | None:
    """None, ha rendben van, különben a magyar hibaüzenet."""
    for field in ("name", "address", "city", "zip"):
        if not block.get(field):
            return f"Hiányzó {prefix}adat: {FIELD_LABELS.get(field, field)}."
    if not ZIP_RE.match(block["zip"]):
        return f"A(z) {prefix}irányítószám négy számjegyű legyen."
    return None


def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _error("Hibás kérés formátum.")

    # ---- vásárlói adatok ----
    raw_customer = body.get("customer") or {}
    customer = {
        "name": _clean(raw_customer.get("name")),
        "email": _clean(raw_customer.get("email")),
        "phone": _clean(raw_customer.get("phone"), 40),
        "address": _clean(raw_customer.get("address")),
        "city": _clean(raw_customer.get("city")),
        "zip": _clean(raw_customer.get("zip"), 10),
        "notes": _clean(raw_customer.get("notes"), MAX_NOTES_LENGTH),
    }
    for field in ("name", "email", "phone", "address", "city", "zip"):
        if not customer[field]:
            return _error(f"Hiányzó adat: {FIELD_LABELS[field]}.")
    if not EMAIL_RE.match(customer["email"]):
        return _error("Az e-mail cím formátuma nem megfelelő.")
    if not PHONE_RE.match(customer["phone"]):
        return _error("A telefonszám formátuma nem megfelelő.")
    if not ZIP_RE.match(customer["zip"]):
        return _error("Az irányítószám négy számjegyű legyen.")

    consents = body.get("consents") or {}
    if not consents.get("aszf") or not consents.get("privacy"):
        return _error("Az ÁSZF és az adatvédelmi tájékoztató elfogadása kötelező.")

    # ---- szállítás ----
    raw_shipping = body.get("shipping") or {}
    shipping_method = raw_shipping.get("method")
    if shipping_method not in SHIPPING_METHODS:
        return _error("Ismeretlen szállítási mód.")

    shipping: dict = {"method": shipping_method, "label": SHIPPING_METHODS[shipping_method]["label"]}

    if shipping_method == "foxpost":
        locker_id = _clean(raw_shipping.get("lockerId"), 64)
        if not locker_id:
            return _error("Válassz egy Foxpost csomagautomatát.")
        shipping["lockerId"] = locker_id
        shipping["lockerName"] = _clean(raw_shipping.get("lockerName"), 250)
    else:  # házhozszállítás
        same_as_billing = bool(raw_shipping.get("sameAsBilling"))
        if same_as_billing:
            address = {
                "name": customer["name"],
                "address": customer["address"],
                "city": customer["city"],
                "zip": customer["zip"],
            }
        else:
            raw_address = raw_shipping.get("address") or {}
            address = {
                "name": _clean(raw_address.get("name")),
                "address": _clean(raw_address.get("address")),
                "city": _clean(raw_address.get("city")),
                "zip": _clean(raw_address.get("zip"), 10),
            }
            problem = _validate_address_block(address, "szállítási ")
            if problem:
                return _error(problem)
        shipping["sameAsBilling"] = same_as_billing
        shipping["address"] = address

    # ---- fizetési mód ----
    payment_method = body.get("paymentMethod", "barion")
    if not is_payment_allowed(payment_method, shipping_method):
        if payment_method == "cod":
            return _error(
                "Utánvét csak házhozszállításnál választható — a Foxpost "
                "csomagautomaták nem fogadnak készpénzt."
            )
        return _error("A választott fizetési mód nem használható ezzel a szállítási móddal.")

    # ---- tételek, árak ----
    raw_items = body.get("items") or []
    if not raw_items:
        return _error("A kosár üres.")
    if len(raw_items) > MAX_ITEMS_PER_ORDER:
        return _error("Túl sok tétel a kosárban. Kérjük, oszd több rendelésre.")

    priced_items = []
    subtotal = 0
    for raw in raw_items:
        if not isinstance(raw, dict):
            return _error("Hibás tétel a kosárban.")
        try:
            unit_price = get_item_price(raw.get("productId"), raw.get("size"))
        except (KeyError, ValueError):
            return _error("A kosárban ismeretlen termék vagy méret szerepel. Frissítsd az oldalt.")
        if not raw.get("photoKey"):
            return _error("Minden tételhez fel kell tölteni egy fotót.")
        try:
            qty = int(raw.get("qty", 1))
        except (TypeError, ValueError):
            return _error("Hibás darabszám.")
        if qty < 1 or qty > MAX_QTY_PER_ITEM:
            return _error(f"A darabszám 1 és {MAX_QTY_PER_ITEM} között lehet.")
        subtotal += unit_price * qty
        priced_items.append(
            {
                "productId": raw["productId"],
                "productName": _clean(raw.get("productName")) or raw["productId"],
                "size": raw["size"],
                "qty": qty,
                "unitPrice": unit_price,
                "photoKey": _clean(raw["photoKey"], 300),
            }
        )

    shipping_fee = get_shipping_fee(subtotal, shipping_method)
    cod_fee = get_cod_fee(payment_method)
    total = subtotal + shipping_fee + cod_fee
    if total <= 0:
        return _error("Érvénytelen végösszeg.")

    shipping["feeHuf"] = shipping_fee

    order_id = str(uuid.uuid4())
    order = {
        "orderId": order_id,
        "orderStatus": "pending_payment",
        "paymentMethod": payment_method,
        "customer": customer,
        "shipping": shipping,
        "items": priced_items,
        "subtotalHuf": subtotal,
        "shippingFeeHuf": shipping_fee,
        "codFeeHuf": cod_fee,
        "totalHuf": total,
        "currency": "HUF",
    }

    # ---- előre utalás ----
    if payment_method == "transfer":
        order["orderStatus"] = "pending_transfer"
        put_order(order)
        try:
            send_transfer_instructions(order)
            send_admin_notification(order)
        except Exception as exc:  # noqa: BLE001
            # A rendelés már létezik, csak az email nem ment ki. Ezt jelezzük
            # a vásárlónak is, de a rendelést nem dobjuk el.
            print(f"[ses] transfer email failed for {order_id}: {exc}")
            update_order_status(order_id, "pending_transfer", {"emailError": str(exc)[:300]})
            return _error(
                "A rendelést rögzítettük, de a fizetési adatokat tartalmazó e-mailt "
                f"nem sikerült elküldeni. Rendelési szám: {order_id}. "
                "Kérjük, vedd fel velünk a kapcsolatot.",
                code=502,
            )
        return _ok({
            "orderId": order_id,
            "paymentMethod": payment_method,
            "redirectUrl": f"{SITE_BASE_URL}/koszonjuk.html?orderId={order_id}",
        })

    # ---- utánvét ----
    if payment_method == "cod":
        order["orderStatus"] = "pending_cod"
        put_order(order)
        try:
            send_cod_confirmation(order)
            send_admin_notification(order)
        except Exception as exc:  # noqa: BLE001
            print(f"[ses] cod email failed for {order_id}: {exc}")
            update_order_status(order_id, "pending_cod", {"emailError": str(exc)[:300]})
        return _ok({
            "orderId": order_id,
            "paymentMethod": payment_method,
            "redirectUrl": f"{SITE_BASE_URL}/koszonjuk.html?orderId={order_id}",
        })

    # ---- bankkártya (Barion) ----
    barion_items = [
        {
            "name": f"{i['productName']} ({i['size']})",
            "description": f"Egyedi litofán, {i['size']}",
            "qty": i["qty"],
            "unit_price": i["unitPrice"],
            "sku": f"{i['productId']}-{i['size']}",
        }
        for i in priced_items
    ]
    if shipping_fee:
        barion_items.append(
            {
                "name": shipping["label"],
                "description": "Szállítási díj",
                "qty": 1,
                "unit_price": shipping_fee,
                "sku": f"shipping-{shipping_method}",
            }
        )

    # A rendelést a Barion hívás ELŐTT elmentjük. Ha a Barion hibázik vagy
    # időtúllépésre fut, a kísérlet így sem tűnik el nyomtalanul.
    order["orderStatus"] = "payment_init"
    put_order(order)

    try:
        barion_resp = barion.start_payment(
            order_id,
            barion_items,
            total,
            customer=customer,
            shipping_address=shipping.get("address"),
            order_number=order_id,
        )
    except barion.BarionError as exc:
        print(f"[barion] start failed for {order_id}: {exc} codes={exc.error_codes}")
        update_order_status(order_id, "payment_start_failed", {"paymentError": str(exc)[:500]})
        return _error(
            "A bankkártyás fizetést nem sikerült elindítani. Próbáld újra, "
            "vagy válaszd az előre utalást.",
            code=502,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[barion] unexpected error for {order_id}: {exc}")
        update_order_status(order_id, "payment_start_failed", {"paymentError": str(exc)[:500]})
        return _error("A fizetés indítása közben váratlan hiba történt. Próbáld újra.", code=502)

    update_order_status(
        order_id,
        "pending_payment",
        {"paymentId": barion_resp["PaymentId"], "paymentRequestId": order_id},
    )

    return _ok({
        "orderId": order_id,
        "paymentMethod": payment_method,
        "gatewayUrl": barion_resp["GatewayUrl"],
    })
