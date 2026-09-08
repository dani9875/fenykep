"""
SES email sending.

Env vars required:
  SES_FROM_ADDRESS   e.g. info@lithophaneshop.hu (must be a verified SES identity)
  ADMIN_EMAIL        where the "new order" notification goes
"""

import os
import boto3

_ses = boto3.client("ses")
FROM_ADDRESS = os.environ.get("SES_FROM_ADDRESS", "info@example.com")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", FROM_ADDRESS)


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
    for item in order["items"]:
        rows += (
            "<tr>"
            f"<td>{item['productName']}</td>"
            f"<td>{item['size']}</td>"
            f"<td>{item['qty']}</td>"
            f"<td>{item['unitPrice']:,} Ft</td>"
            "</tr>"
        )
    return rows


def send_customer_confirmation(order: dict) -> None:
    rows = _item_rows(order)
    html = f"""
    <h2>Köszönjük a rendelésedet, {order['customer']['name']}!</h2>
    <p>Rendelési szám: <strong>{order['orderId']}</strong></p>
    <table border="1" cellpadding="6" cellspacing="0">
      <tr><th>Termék</th><th>Méret</th><th>Db</th><th>Egységár</th></tr>
      {rows}
    </table>
    <p>Végösszeg: <strong>{order['totalHuf']:,} Ft</strong></p>
    <p>Szállítás: Foxpost csomagautomata — {order['shipping'].get('lockerName', '')}</p>
    <p>24 órán belül e-mailben elküldjük a digitális előnézetet.
       Csak akkor nyomtatunk, ha jóváhagyod.</p>
    """
    _send(order["customer"]["email"], "Rendelés visszaigazolás — Lithophane Shop", html)


def send_transfer_instructions(order: dict) -> None:
    account_name = os.environ.get("BANK_ACCOUNT_NAME", "Fény·kép Stúdió")
    account_number = os.environ.get("BANK_ACCOUNT_NUMBER", "IBAN NINCS BEÁLLÍTVA")
    html = f"""
    <h2>Köszönjük a rendelésedet, {order['customer']['name']}!</h2>
    <p>Rendelési szám: <strong>{order['orderId']}</strong></p>
    <p>A rendelést előre utalással választottad. Kérjük, utald át az alábbi összeget:</p>
    <table border="1" cellpadding="6" cellspacing="0">
      <tr><td>Kedvezményezett</td><td>{account_name}</td></tr>
      <tr><td>Számlaszám</td><td>{account_number}</td></tr>
      <tr><td>Összeg</td><td>{order['totalHuf']:,} Ft</td></tr>
      <tr><td>Közlemény</td><td>{order['orderId']}</td></tr>
    </table>
    <p>Az utalás beérkezése után kezdjük el a gyártást, és digitális mintát küldünk
       jóváhagyásra.</p>
    """
    _send(order["customer"]["email"], "Fizetési adatok — Fény·kép Stúdió rendelés", html)


def send_admin_notification(order: dict) -> None:
    rows = _item_rows(order)
    html = f"""
    <h2>Új fizetett rendelés: {order['orderId']}</h2>
    <p>Vásárló: {order['customer']['name']} ({order['customer']['email']},
       {order['customer'].get('phone', '')})</p>
    <p>Cím: {order['customer'].get('address', '')}</p>
    <table border="1" cellpadding="6" cellspacing="0">
      <tr><th>Termék</th><th>Méret</th><th>Db</th><th>Egységár</th></tr>
      {rows}
    </table>
    <p>Végösszeg: <strong>{order['totalHuf']:,} Ft</strong></p>
    <p>Foxpost csomagautomata: {order['shipping'].get('lockerName', '')}
       (ID: {order['shipping'].get('lockerId', '')})</p>
    <p>Feltöltött fotók:</p>
    <ul>
      {''.join(f"<li>{i['productName']} — s3://{os.environ.get('UPLOADS_BUCKET','')}/{i['photoKey']}</li>" for i in order['items'])}
    </ul>
    """
    _send(ADMIN_EMAIL, f"Új rendelés — {order['orderId']}", html)
