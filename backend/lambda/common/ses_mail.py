"""
SES email sending.

Minden vásárlói adat `html.escape`-en megy át, mielőtt a HTML törzsbe
kerülne — a név, a megjegyzés és a cím a vásárlótól jön, tehát nem
kerülhet nyersen a levélbe.

Env vars required:
  SES_FROM_ADDRESS   e.g. info@lithophaneshop.hu (must be a verified SES identity)
  ADMIN_EMAIL        where the "new order" notification goes
  SITE_BASE_URL      a webshop nyitóoldala (a levelekben lévő linkekhez)
"""

import html
import os
import boto3

_ses = boto3.client("ses")
FROM_ADDRESS = os.environ.get("SES_FROM_ADDRESS", "info@example.com")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", FROM_ADDRESS)
SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "").rstrip("/")


def _e(value) -> str:
    return html.escape(str(value if value is not None else ""))


def _huf(amount) -> str:
    try:
        return f"{int(amount):,}".replace(",", " ") + " Ft"
    except (TypeError, ValueError):
        return f"{amount} Ft"


def _send(to_address: str, subject: str, html_body: str, reply_to: str | None = None) -> None:
    kwargs = {
        "Source": FROM_ADDRESS,
        "Destination": {"ToAddresses": [to_address]},
        "Message": {
            "Subject": {"Data": subject, "Charset": "UTF-8"},
            "Body": {"Html": {"Data": html_body, "Charset": "UTF-8"}},
        },
    }
    if reply_to:
        kwargs["ReplyToAddresses"] = [reply_to]
    _ses.send_email(**kwargs)


def _item_rows(order: dict) -> str:
    rows = ""
    for item in order.get("items", []):
        rows += (
            "<tr>"
            f"<td>{_e(item.get('productName'))}</td>"
            f"<td>{_e(item.get('size'))}</td>"
            f"<td>{_e(item.get('qty'))}</td>"
            f"<td>{_huf(item.get('unitPrice', 0))}</td>"
            "</tr>"
        )
    return rows


def _totals_rows(order: dict) -> str:
    rows = f"<tr><td>Részösszeg</td><td>{_huf(order.get('subtotalHuf', 0))}</td></tr>"
    shipping_fee = order.get("shippingFeeHuf", (order.get("shipping") or {}).get("feeHuf", 0))
    rows += (
        f"<tr><td>Szállítás</td><td>{'Ingyenes' if not shipping_fee else _huf(shipping_fee)}</td></tr>"
    )
    if order.get("codFeeHuf"):
        rows += f"<tr><td>Utánvét kezelési díj</td><td>{_huf(order['codFeeHuf'])}</td></tr>"
    rows += f"<tr><td><strong>Végösszeg</strong></td><td><strong>{_huf(order.get('totalHuf', 0))}</strong></td></tr>"
    return rows


def shipping_summary(order: dict) -> str:
    """Egy soros, emberi leírás a szállításról — mindkét szállítási módra."""
    shipping = order.get("shipping") or {}
    if shipping.get("method") == "home":
        address = shipping.get("address") or {}
        return (
            "Házhozszállítás — "
            f"{_e(address.get('name'))}, {_e(address.get('zip'))} {_e(address.get('city'))}, "
            f"{_e(address.get('address'))}"
        )
    locker = shipping.get("lockerName") or shipping.get("lockerId") or ""
    return f"Foxpost csomagautomata — {_e(locker)}"


def _order_table(order: dict) -> str:
    return f"""
    <table border="1" cellpadding="6" cellspacing="0">
      <tr><th>Termék</th><th>Méret</th><th>Db</th><th>Egységár</th></tr>
      {_item_rows(order)}
    </table>
    <table border="0" cellpadding="4" cellspacing="0" style="margin-top:10px;">
      {_totals_rows(order)}
    </table>
    <p>{shipping_summary(order)}</p>
    """


def send_customer_confirmation(order: dict) -> None:
    html_body = f"""
    <h2>Köszönjük a rendelésedet, {_e(order['customer']['name'])}!</h2>
    <p>Rendelési szám: <strong>{_e(order['orderId'])}</strong></p>
    <p>A fizetés sikeresen megérkezett.</p>
    {_order_table(order)}
    <p>24 órán belül e-mailben elküldjük a digitális előnézetet.
       Csak akkor nyomtatunk, ha jóváhagyod.</p>
    """
    _send(order["customer"]["email"], "Rendelés visszaigazolás — Fény·kép Stúdió", html_body)


def send_transfer_instructions(order: dict) -> None:
    account_name = os.environ.get("BANK_ACCOUNT_NAME", "Fény·kép Stúdió")
    account_number = os.environ.get("BANK_ACCOUNT_NUMBER", "IBAN NINCS BEÁLLÍTVA")
    html_body = f"""
    <h2>Köszönjük a rendelésedet, {_e(order['customer']['name'])}!</h2>
    <p>Rendelési szám: <strong>{_e(order['orderId'])}</strong></p>
    <p>A rendelést előre utalással választottad. Kérjük, utald át az alábbi összeget:</p>
    <table border="1" cellpadding="6" cellspacing="0">
      <tr><td>Kedvezményezett</td><td>{_e(account_name)}</td></tr>
      <tr><td>Számlaszám</td><td>{_e(account_number)}</td></tr>
      <tr><td>Összeg</td><td>{_huf(order.get('totalHuf', 0))}</td></tr>
      <tr><td>Közlemény</td><td>{_e(order['orderId'])}</td></tr>
    </table>
    {_order_table(order)}
    <p>Az utalás beérkezése után kezdjük el a gyártást, és digitális mintát küldünk
       jóváhagyásra.</p>
    """
    _send(order["customer"]["email"], "Fizetési adatok — Fény·kép Stúdió rendelés", html_body)


def send_cod_confirmation(order: dict) -> None:
    html_body = f"""
    <h2>Köszönjük a rendelésedet, {_e(order['customer']['name'])}!</h2>
    <p>Rendelési szám: <strong>{_e(order['orderId'])}</strong></p>
    <p>Utánvétes fizetést választottál: a végösszeget a futárnál kell
       kiegyenlítened átvételkor.</p>
    {_order_table(order)}
    <p>24 órán belül e-mailben elküldjük a digitális előnézetet.
       Csak akkor nyomtatunk, ha jóváhagyod.</p>
    """
    _send(order["customer"]["email"], "Rendelés visszaigazolás — Fény·kép Stúdió", html_body)


def send_payment_failed_notice(order: dict) -> None:
    """
    Sikertelen, megszakított vagy lejárt bankkártyás fizetés.

    A rendelés megmarad a rendszerben, de nem teljesítjük — a vásárló
    egy kattintással újraindíthatja a vásárlást.
    """
    reasons = {
        "payment_failed": "A bankkártyás fizetés nem sikerült.",
        "payment_canceled": "A bankkártyás fizetést megszakítottad.",
        "payment_expired": "A fizetésre szánt idő lejárt.",
    }
    reason = reasons.get(order.get("orderStatus", ""), "A bankkártyás fizetés nem fejeződött be.")
    shop_link = f'<p><a href="{SITE_BASE_URL}/index.html">Vissza a webshopba</a></p>' if SITE_BASE_URL else ""
    html_body = f"""
    <h2>Szia {_e(order['customer']['name'])}!</h2>
    <p>{_e(reason)} A rendelésedet ezért nem indítottuk el.</p>
    <p>Rendelési szám: <strong>{_e(order['orderId'])}</strong></p>
    <p>Nem vontunk le semmit a kártyádról. Ha szeretnéd, indítsd újra a
       rendelést — a kosaradat megtartottuk. Előre utalást is választhatsz
       a pénztárban.</p>
    {shop_link}
    <p>Ha többször is elakadsz, írj vissza erre a levélre, és segítünk.</p>
    """
    _send(order["customer"]["email"], "Sikertelen fizetés — Fény·kép Stúdió", html_body)


def send_admin_notification(order: dict) -> None:
    status = order.get("orderStatus", "")
    headline = {
        "paid": "Új fizetett rendelés",
        "pending_transfer": "Új rendelés — előre utalásra vár",
        "pending_cod": "Új rendelés — utánvét",
        "payment_mismatch": "FIGYELEM: eltérő fizetett összeg",
        "payment_review": "FIGYELEM: kézi ellenőrzést igénylő fizetés",
    }.get(status, f"Rendelés státusz: {status}")

    note = order.get("paymentNote")
    note_html = f"<p style='color:#b94030'><strong>{_e(note)}</strong></p>" if note else ""
    bucket = os.environ.get("UPLOADS_BUCKET", "")
    photos = "".join(
        f"<li>{_e(i.get('productName'))} — s3://{_e(bucket)}/{_e(i.get('photoKey'))}</li>"
        for i in order.get("items", [])
    )
    customer = order.get("customer", {})
    html_body = f"""
    <h2>{_e(headline)}: {_e(order['orderId'])}</h2>
    {note_html}
    <p>Fizetési mód: {_e(order.get('paymentMethod', ''))} — státusz: {_e(status)}</p>
    <p>Vásárló: {_e(customer.get('name'))} ({_e(customer.get('email'))}, {_e(customer.get('phone'))})</p>
    <p>Számlázási cím: {_e(customer.get('zip'))} {_e(customer.get('city'))}, {_e(customer.get('address'))}</p>
    {_order_table(order)}
    <p>Megjegyzés: {_e(customer.get('notes')) or '—'}</p>
    <p>Feltöltött fotók:</p>
    <ul>{photos}</ul>
    """
    _send(ADMIN_EMAIL, f"{headline} — {_e(order['orderId'])}", html_body)
