"""
A fizetés állapotának egyeztetése a Barionnal.

Két helyről hívjuk, és mindkettőnek pontosan ugyanúgy kell viselkednie:
  * barion_callback — a Barion szól, hogy változott valami (IPN);
  * get_order_status — a köszönőoldal kérdez rá, mert az IPN késhet vagy
    (sandboxban, rosszul beállított URL-nél) el is maradhat.

Amit ez a modul garantál:
  * A Barion callback tartalma soha nem forrása az igazságnak — mindig
    a PaymentState hívás dönt.
  * Az összeg és a pénznem egyezését ellenőrizzük. Eltérésnél a rendelés
    NEM lesz "fizetve", hanem kézi vizsgálatra kerül.
  * A "fizetve" állapotba lépés (és így a visszaigazoló email) feltételes
    DynamoDB írással történik, tehát a Barion ötszöri újrahívása után is
    pontosan egyszer fut le.
"""

import barion
from dynamo import StatusAlreadySet, get_order, transition_order_status, update_order_status
from ses_mail import send_admin_notification, send_payment_failed_notice, send_customer_confirmation

# Ezekből az állapotokból még van értelme továbblépni egy Barion válasz alapján.
OPEN_STATUSES = ["payment_init", "pending_payment", "payment_failed", "payment_canceled", "payment_expired"]

# Végállapotok, ahol már nincs teendő.
SETTLED_STATUSES = frozenset({"paid", "payment_mismatch", "payment_review", "fulfilled", "canceled"})


def _notify(fn, order: dict, label: str) -> None:
    """Email küldés úgy, hogy egy SES hiba ne bukjon vissza a hívóra.

    A callbacknek 200-at kell adnia 15 másodpercen belül, különben a Barion
    újrahív — egy elakadt email miatt nem érdemes az egész feldolgozást
    megismételtetni.
    """
    try:
        fn(order)
    except Exception as exc:  # noqa: BLE001
        print(f"[ses] {label} failed for {order.get('orderId')}: {exc}")


def reconcile(order: dict, *, source: str = "callback") -> dict:
    """
    Lekérdezi a fizetés állapotát, és ennek megfelelően frissíti a rendelést.

    Visszatérés: {"orderStatus": ..., "paymentStatus": ..., "changed": bool}
    Kivételt nem dob: minden hibát elnyel és naplóz, mert a hívó
    (callback és státuszlekérdezés) egyikének sem szabad elszállnia emiatt.
    """
    order_id = order["orderId"]
    current = order.get("orderStatus", "")
    payment_id = order.get("paymentId")

    result = {"orderStatus": current, "paymentStatus": None, "changed": False}

    if order.get("paymentMethod") != "barion" or not payment_id:
        return result
    if current in SETTLED_STATUSES:
        return result

    try:
        state = barion.get_payment_state(payment_id)
    except barion.BarionThrottledError:
        # 5 mp-en belül másodszor kérdeztünk rá. Nem hiba: a következő
        # lekérdezés/callback úgyis megismétli.
        print(f"[barion] throttled while checking {payment_id} ({source})")
        return result
    except barion.BarionError as exc:
        print(f"[barion] state check failed for {payment_id} ({source}): {exc}")
        return result

    payment_status = state.get("Status")
    result["paymentStatus"] = payment_status
    print(f"[barion] order={order_id} payment={payment_id} status={payment_status} source={source}")

    if payment_status in barion.PENDING_STATUSES:
        return result  # a vásárló még a fizetőoldalon van

    if payment_status == barion.STATUS_SUCCEEDED:
        return _handle_success(order, state, result)

    if payment_status == barion.STATUS_PARTIALLY_SUCCEEDED:
        # Több kedvezményezettes fizetésnél fordulhat elő; nálunk egy
        # kedvezményezett van, tehát ez rendellenes. Nem teljesítünk.
        note = "Részben sikeres fizetés — kézi ellenőrzés szükséges."
        if _settle(order, result, "payment_review", {"paymentStatus": payment_status, "paymentNote": note}):
            _notify(
                send_admin_notification,
                {**order, "orderStatus": "payment_review", "paymentNote": note},
                "admin review notice",
            )
        return result

    mapped = barion.ORDER_STATUS_BY_PAYMENT_STATUS.get(payment_status)
    if mapped:
        changed = _settle(order, result, mapped, {"paymentStatus": payment_status})
        if changed:
            _notify(send_payment_failed_notice, {**order, "orderStatus": mapped}, "payment failure notice")
        return result

    # Ismeretlen / új Barion státusz: nem találgatunk, csak eltároljuk.
    print(f"[barion] unhandled status '{payment_status}' for order {order_id}")
    update_order_status(order_id, current, {"paymentStatus": payment_status or "Unknown"})
    return result


def _handle_success(order: dict, state: dict, result: dict) -> dict:
    """Sikeres Barion fizetés — de csak akkor teljesítünk, ha az összeg is stimmel."""
    order_id = order["orderId"]
    expected_total = int(order.get("totalHuf", 0))
    paid_total = barion.payment_total(state)
    currency = barion.payment_currency(state) or "HUF"

    mismatch = None
    if paid_total is None:
        mismatch = "A Barion válaszából nem olvasható ki a fizetett összeg."
    elif paid_total != expected_total:
        mismatch = f"Fizetett összeg {paid_total} {currency}, várt összeg {expected_total} HUF."
    elif currency != "HUF":
        mismatch = f"Eltérő pénznem: {currency}."

    if mismatch:
        print(f"[barion] AMOUNT MISMATCH order={order_id}: {mismatch}")
        changed = _settle(order, result, "payment_mismatch", {
            "paymentStatus": barion.STATUS_SUCCEEDED,
            "paymentNote": mismatch[:300],
            "paidTotalHuf": paid_total if paid_total is not None else 0,
        })
        if changed:
            _notify(
                send_admin_notification,
                {**order, "orderStatus": "payment_mismatch", "paymentNote": mismatch},
                "admin mismatch notice",
            )
        return result

    extra = {
        "paymentStatus": barion.STATUS_SUCCEEDED,
        "paidTotalHuf": paid_total,
        "paymentCard": barion.card_summary(state)[:100],
    }
    if state.get("CompletedAt"):
        extra["paidAt"] = str(state["CompletedAt"])[:40]

    if not _settle(order, result, "paid", extra):
        return result  # egy párhuzamos hívás már lekezelte — nem küldünk még egy emailt

    paid_order = {**order, "orderStatus": "paid", **extra}
    _notify(send_customer_confirmation, paid_order, "customer confirmation")
    _notify(send_admin_notification, paid_order, "admin notification")
    return result


def _settle(order: dict, result: dict, new_status: str, extra: dict) -> bool:
    """Feltételes státuszváltás. True, ha tényleg most változott."""
    # A célállapotot kihagyjuk a feltételből: ha a rendelés már ebben az
    # állapotban van, az írás elbukik, és nem megy ki még egy email ugyanarról
    # a sikertelen fizetésről. (A Barion ötször is újrahívhatja a callbacket.)
    from_statuses = [s for s in OPEN_STATUSES if s != new_status]
    try:
        transition_order_status(order["orderId"], new_status, from_statuses, extra)
    except StatusAlreadySet:
        fresh = get_order(order["orderId"]) or order
        result["orderStatus"] = fresh.get("orderStatus", result["orderStatus"])
        return False
    result["orderStatus"] = new_status
    result["changed"] = True
    return True
