"""
SES email sending.

Minden vásárlói adat `html.escape`-en megy át, mielőtt a HTML törzsbe
kerülne — a név, a megjegyzés és a cím a vásárlótól jön, tehát nem
kerülhet nyersen a levélbe.

A levelek a weboldal stílusát követik (homok háttér, fehér kártya,
serif címek, sötét gomb). E-mail kliensekben csak a táblázatos,
soron belüli (inline) stílusú HTML működik megbízhatóan, ezért nincs
<style> blokk, flexbox vagy webfont: a Cormorant és a Jost helyett
Georgia és Helvetica a tartalék betűtípus.

Env vars required:
  SES_FROM_ADDRESS   e.g. info@feny-kep.hu (must be a verified SES identity)
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
CONTACT_EMAIL = "info@feny-kep.hu"

LEAD_TIME_TEXT = "Átlagos elkészítési idő: nagyjából 7 munkanap."

# A weboldal színei (frontend/css/style.css :root).
SAND = "#f5ede0"
SAND_MID = "#ecddd0"
WARM_WHITE = "#fdfaf6"
CHARCOAL = "#1c1917"
TEXT = "#1c1917"
TEXT_MUTED = "#6b5f55"
TEXT_LIGHT = "#a09080"
BORDER = "#eadfd2"
AMBER = "#E39A2D"
ALERT = "#b94030"

SERIF = "'Cormorant Garamond', Georgia, 'Times New Roman', serif"
SANS = "'Jost', 'Helvetica Neue', Helvetica, Arial, sans-serif"


def _e(value) -> str:
    return html.escape(str(value if value is not None else ""))


def _e_multiline(value) -> str:
    """Escape, majd a sortöréseket <br>-re cseréli (üzenet, megjegyzés)."""
    return _e(value).replace("\r\n", "\n").replace("\n", "<br>")


def _huf(amount) -> str:
    try:
        return f"{int(amount):,}".replace(",", " ") + " Ft"
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


# ── építőelemek ──────────────────────────────────────────────────────────

def _layout(title: str, body: str, preheader: str = "") -> str:
    """A teljes levél: homok háttér, logó, fehér kártya, lábléc."""
    shop = SITE_BASE_URL or "https://www.feny-kep.hu"
    hidden_preheader = (
        f'<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{_e(preheader)}</div>'
        if preheader else ""
    )
    return f"""<!DOCTYPE html>
<html lang="hu">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>{_e(title)}</title>
</head>
<body style="margin:0;padding:0;background:{SAND};">
{hidden_preheader}
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{SAND};">
  <tr><td align="center" style="padding:32px 16px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;">
      <tr><td style="padding:0 8px 20px;font-family:{SANS};font-size:24px;font-weight:500;letter-spacing:-0.02em;color:{CHARCOAL};">
        <a href="{_e(shop)}" style="color:{CHARCOAL};text-decoration:none;">Fény<span style="color:{AMBER};">·</span>kép</a>
      </td></tr>
      <tr><td style="background:{WARM_WHITE};border:1px solid {BORDER};border-radius:20px;padding:36px 32px;font-family:{SANS};font-size:15px;line-height:1.6;color:{TEXT};">
        {body}
      </td></tr>
      <tr><td style="padding:24px 8px 0;font-family:{SANS};font-size:12px;line-height:1.6;color:{TEXT_LIGHT};text-align:center;">
        Fény·kép · <a href="{_e(shop)}" style="color:{TEXT_LIGHT};">feny-kep.hu</a> · <a href="mailto:{CONTACT_EMAIL}" style="color:{TEXT_LIGHT};">{CONTACT_EMAIL}</a>
      </td></tr>
    </table>
  </td></tr>
</table>
</body>
</html>"""


def _h1(text: str) -> str:
    return (
        f'<h1 style="margin:0 0 12px;font-family:{SERIF};font-size:30px;font-weight:400;'
        f'line-height:1.2;color:{TEXT};">{text}</h1>'
    )


def _p(text: str, muted: bool = False, small: bool = False) -> str:
    color = TEXT_MUTED if muted else TEXT
    size = "13px" if small else "15px"
    return f'<p style="margin:0 0 14px;font-size:{size};color:{color};">{text}</p>'


def _section_title(text: str) -> str:
    return (
        f'<p style="margin:28px 0 10px;font-size:11px;letter-spacing:0.16em;text-transform:uppercase;'
        f'color:{TEXT_LIGHT};">{_e(text)}</p>'
    )


def _rows_table(rows: list[tuple[str, str]], strong_last: bool = False) -> str:
    """Kétoszlopos címke–érték táblázat. A címke és az érték már escape-elt HTML."""
    out = ""
    for index, (label, value) in enumerate(rows):
        last = strong_last and index == len(rows) - 1
        weight = "font-weight:600;" if last else ""
        top = f"border-top:1px solid {BORDER};" if last else ""
        out += (
            f'<tr><td style="padding:7px 0;{top}color:{TEXT_MUTED};font-size:14px;vertical-align:top;">{label}</td>'
            f'<td style="padding:7px 0 7px 16px;{top}{weight}text-align:right;font-size:14px;vertical-align:top;">{value}</td></tr>'
        )
    return f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">{out}</table>'


def _button(href: str, label: str) -> str:
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:24px 0 4px;">'
        f'<tr><td style="background:{CHARCOAL};border-radius:30px;">'
        f'<a href="{_e(href)}" style="display:inline-block;padding:13px 28px;font-family:{SANS};font-size:12px;'
        f'letter-spacing:0.16em;text-transform:uppercase;color:{WARM_WHITE};text-decoration:none;">{_e(label)}</a>'
        f'</td></tr></table>'
    )


def _notice(text: str, color: str = ALERT) -> str:
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 18px;">'
        f'<tr><td style="background:{SAND};border-left:3px solid {color};border-radius:8px;padding:12px 16px;'
        f'font-size:14px;color:{color};font-weight:600;">{text}</td></tr></table>'
    )


def _order_number(order: dict) -> str:
    return _p(f'Rendelésszám: <strong>{_e(order["orderId"])}</strong>', muted=True)


# ── rendelés részei ──────────────────────────────────────────────────────

def _items_table(order: dict) -> str:
    rows = ""
    for item in order.get("items", []):
        qty = item.get("qty", 1)
        rows += (
            f'<tr><td style="padding:12px 0;border-bottom:1px solid {BORDER};vertical-align:top;">'
            f'<div style="font-family:{SERIF};font-size:18px;color:{TEXT};">{_e(item.get("productName"))}</div>'
            f'<div style="font-size:13px;color:{TEXT_MUTED};">{_e(item.get("size"))} · {_e(qty)} db</div>'
            f'</td><td style="padding:12px 0 12px 16px;border-bottom:1px solid {BORDER};text-align:right;'
            f'vertical-align:top;font-size:15px;white-space:nowrap;">{_huf(item.get("unitPrice", 0) * int(qty or 1))}</td></tr>'
        )
    return f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">{rows}</table>'


def _totals_table(order: dict) -> str:
    shipping_fee = order.get("shippingFeeHuf", (order.get("shipping") or {}).get("feeHuf", 0))
    return _rows_table([
        ("Részösszeg", _huf(order.get("subtotalHuf", 0))),
        ("Szállítás", "Ingyenes" if not shipping_fee else _huf(shipping_fee)),
        ("Végösszeg", _huf(order.get("totalHuf", 0))),
    ], strong_last=True)


def shipping_summary(order: dict) -> str:
    """Egy soros, emberi leírás a szállításról, minden szállítási módra."""
    shipping = order.get("shipping") or {}
    if shipping.get("method") in ("home", "mpl"):
        address = shipping.get("address") or {}
        label = "MPL házhozszállítás" if shipping.get("method") == "mpl" else "Házhozszállítás (Foxpost futár)"
        return (
            f"{label}: "
            f"{_e(address.get('name'))}, {_e(address.get('zip'))} {_e(address.get('city'))}, "
            f"{_e(address.get('address'))}"
        )
    locker = shipping.get("lockerName") or shipping.get("lockerId") or ""
    return f"Foxpost csomagautomata: {_e(locker)}"


def _order_block(order: dict, title: str = "A rendelésed") -> str:
    return (
        _section_title(title)
        + _items_table(order)
        + '<div style="height:8px;"></div>'
        + _totals_table(order)
        + _section_title("Szállítás")
        + _p(shipping_summary(order))
    )


# ── vásárlói levelek ─────────────────────────────────────────────────────

def send_customer_confirmation(order: dict) -> None:
    name = _e(order["customer"]["name"])
    body = (
        _h1(f"Köszönjük a rendelésed, {name}!")
        + _order_number(order)
        + _p("A fizetés rendben megérkezett, a 3D fotódat elkezdjük elkészíteni.")
        + _order_block(order)
        + _p(LEAD_TIME_TEXT, muted=True, small=True)
        + _p(f'Kérdésed van? Írj nekünk: <a href="mailto:{CONTACT_EMAIL}" style="color:{TEXT};">{CONTACT_EMAIL}</a>',
             muted=True, small=True)
    )
    _send(
        order["customer"]["email"],
        "Rendelés visszaigazolás | Fény·kép",
        _layout("Rendelés visszaigazolás", body, preheader=f"Rendelésszám: {order['orderId']}"),
    )


def send_transfer_instructions(order: dict) -> None:
    account_name = os.environ.get("BANK_ACCOUNT_NAME", "Fény·kép")
    account_number = os.environ.get("BANK_ACCOUNT_NUMBER", "IBAN NINCS BEÁLLÍTVA")
    name = _e(order["customer"]["name"])
    transfer = (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:6px 0 4px;">'
        f'<tr><td style="background:{SAND};border-radius:12px;padding:16px 20px;">'
        + _rows_table([
            ("Kedvezményezett", _e(account_name)),
            ("Számlaszám", f"<strong>{_e(account_number)}</strong>"),
            ("Összeg", f"<strong>{_huf(order.get('totalHuf', 0))}</strong>"),
            ("Közlemény", f"<strong>{_e(order['orderId'])}</strong>"),
        ])
        + "</td></tr></table>"
    )
    body = (
        _h1(f"Köszönjük a rendelésed, {name}!")
        + _order_number(order)
        + _p("Előre utalást választottál. Kérjük, utald át a végösszeget az alábbi adatokkal. "
             "A közleménybe a rendelésszámot írd.")
        + transfer
        + _p("A gyártás az utalás beérkezése után indul.", muted=True, small=True)
        + _order_block(order)
        + _p(LEAD_TIME_TEXT, muted=True, small=True)
    )
    _send(
        order["customer"]["email"],
        "Fizetési adatok | Fény·kép",
        _layout("Fizetési adatok", body, preheader=f"Utalás: {_huf(order.get('totalHuf', 0))}"),
    )


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
    body = (
        _h1(f"Szia {_e(order['customer']['name'])}!")
        + _p(f"{_e(reason)} A rendelésedet ezért nem indítottuk el.")
        + _order_number(order)
        + _p("A kártyádról nem vontunk le semmit. A kosaradat megtartottuk, így a rendelést "
             "bármikor újraindíthatod. A pénztárban előre utalást is választhatsz.")
        + (_button(f"{SITE_BASE_URL}/kosar.html", "Vissza a kosárhoz") if SITE_BASE_URL else "")
        + _p("Ha többször is elakadsz, válaszolj erre a levélre, és segítünk.", muted=True, small=True)
    )
    _send(
        order["customer"]["email"],
        "Sikertelen fizetés | Fény·kép",
        _layout("Sikertelen fizetés", body),
    )


# ── neked szóló levelek ──────────────────────────────────────────────────

PAYMENT_LABELS = {"barion": "Bankkártya (Barion)", "transfer": "Előre utalás"}


def send_admin_notification(order: dict) -> None:
    status = order.get("orderStatus", "")
    headline = {
        "paid": "Új fizetett rendelés",
        "pending_transfer": "Új rendelés, utalásra vár",
        "payment_mismatch": "Figyelem: eltérő fizetett összeg",
        "payment_review": "Figyelem: kézi ellenőrzést igénylő fizetés",
    }.get(status, f"Rendelés állapota: {status}")

    note = order.get("paymentNote")
    customer = order.get("customer", {})
    photos = "".join(
        f'<tr><td style="padding:6px 0;font-size:13px;color:{TEXT_MUTED};">{_e(i.get("productName"))}, {_e(i.get("size"))}</td></tr>'
        f'<tr><td style="padding:0 0 10px;font-family:Menlo,Consolas,monospace;font-size:12px;color:{TEXT};word-break:break-all;">'
        f'{_e((i.get("photoFile") or i.get("photoKey") or "").rsplit("/", 1)[-1])}</td></tr>'
        for i in order.get("items", [])
    )
    body = (
        _h1(_e(headline))
        + _order_number(order)
        + (_notice(_e(note)) if note else "")
        + _section_title("Vásárló")
        + _rows_table([
            ("Név", _e(customer.get("name"))),
            ("E-mail", f'<a href="mailto:{_e(customer.get("email"))}" style="color:{TEXT};">{_e(customer.get("email"))}</a>'),
            ("Telefon", _e(customer.get("phone"))),
            ("Számlázási cím", f"{_e(customer.get('zip'))} {_e(customer.get('city'))}, {_e(customer.get('address'))}"),
            ("Fizetés", _e(PAYMENT_LABELS.get(order.get("paymentMethod", ""), order.get("paymentMethod", "")))),
        ])
        + _order_block(order, title="Tételek")
        + _section_title("Megjegyzés")
        + _p(_e_multiline(customer.get("notes")) or "Nincs.", muted=not customer.get("notes"))
        + _section_title("Fotók")
        + f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">{photos}</table>'
    )
    _send(
        ADMIN_EMAIL,
        f"{headline}: {order['orderId']}",
        _layout(headline, body),
        reply_to=customer.get("email") or None,
    )


def send_contact_message(full_name: str, email: str, phone: str, subject: str, message: str) -> None:
    """A kapcsolat űrlapról érkező üzenet. A válasz egyenesen a küldőnek megy."""
    body = (
        _h1("Új üzenet a weboldalról")
        + _p(_e(subject), muted=True)
        + _rows_table([
            ("Név", _e(full_name)),
            ("E-mail", f'<a href="mailto:{_e(email)}" style="color:{TEXT};">{_e(email)}</a>'),
            ("Telefon", _e(phone) or "Nincs megadva"),
        ])
        + _section_title("Üzenet")
        + f'<div style="background:{SAND};border-radius:12px;padding:16px 20px;font-size:15px;line-height:1.6;color:{TEXT};">'
          f'{_e_multiline(message)}</div>'
    )
    _send(ADMIN_EMAIL, f"Kapcsolat űrlap: {subject}", _layout("Új üzenet", body), reply_to=email)
