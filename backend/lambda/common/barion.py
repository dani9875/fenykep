"""
Barion Smart Gateway kliens.

Dokumentáció, amire ez épül:
  https://docs.barion.com/Payment-Start-v2        — fizetés indítása
  https://docs.barion.com/Payment-PaymentState-v4 — állapotlekérdezés (ez az ajánlott,
                                                    a v2 GetPaymentState deprecated)
  https://docs.barion.com/Callback_mechanism      — IPN

Fontos szabályok a dokumentációból, amiket ez a modul betart:
  * A callback csak JELZÉS. Soha nem hisszük el, amit tartalmaz — a
    tényleges állapotot mindig a PaymentState hívás adja meg.
  * A PaymentState végpont dobja a 429-et, ha ugyanarra a PaymentId-ra
    5 másodpercen belül kétszer kérdezünk rá. Erre külön hibaosztály van,
    hogy a hívó tudjon várni és újrapróbálni.
  * Az összeget a válaszból ellenőrizni kell: a Barionban lévő összegnek
    egyeznie kell a nálunk tárolt végösszeggel, különben a rendelés nem
    teljesíthető.

Env vars (minden Lambdán, ami importálja):
  BARION_POSKEY         Privát API kulcs a Barion kereskedői admin felületről.
  BARION_PAYEE          A Barion email cím, ami a pénzt kapja.
  BARION_API_BASE       https://api.test.barion.com (sandbox) vagy
                        https://api.barion.com (éles).
  BARION_CALLBACK_URL   A barion_callback Lambda API Gateway URL-je.
  BARION_REDIRECT_URL   A frontend "köszönjük" oldalának URL-je.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

API_BASE = os.environ.get("BARION_API_BASE", "https://api.test.barion.com").rstrip("/")
POSKEY = os.environ.get("BARION_POSKEY", "")
PAYEE = os.environ.get("BARION_PAYEE", "")
CALLBACK_URL = os.environ.get("BARION_CALLBACK_URL", "")
REDIRECT_URL = os.environ.get("BARION_REDIRECT_URL", "")

TIMEOUT_SECONDS = 15

# https://docs.barion.com/PaymentStatus
STATUS_PREPARED = "Prepared"
STATUS_STARTED = "Started"
STATUS_IN_PROGRESS = "InProgress"
STATUS_WAITING = "Waiting"
STATUS_RESERVED = "Reserved"
STATUS_AUTHORIZED = "Authorized"
STATUS_CANCELED = "Canceled"
STATUS_SUCCEEDED = "Succeeded"
STATUS_FAILED = "Failed"
STATUS_PARTIALLY_SUCCEEDED = "PartiallySucceeded"
STATUS_EXPIRED = "Expired"

# A fizetés még folyamatban van, a vásárló épp a Barion oldalán jár.
PENDING_STATUSES = frozenset(
    {STATUS_PREPARED, STATUS_STARTED, STATUS_IN_PROGRESS, STATUS_WAITING, STATUS_RESERVED, STATUS_AUTHORIZED}
)
# Végállapotok, ahonnan már nem lesz sikeres fizetés.
UNSUCCESSFUL_STATUSES = frozenset({STATUS_CANCELED, STATUS_FAILED, STATUS_EXPIRED})

# Barion státusz -> a mi rendelés-státuszunk. A PartiallySucceeded szándékosan
# nincs benne: az kézi vizsgálatot igényel (lásd barion_callback).
ORDER_STATUS_BY_PAYMENT_STATUS = {
    STATUS_SUCCEEDED: "paid",
    STATUS_CANCELED: "payment_canceled",
    STATUS_FAILED: "payment_failed",
    STATUS_EXPIRED: "payment_expired",
}


class BarionError(Exception):
    """A Barion API hibát adott vissza, vagy nem sikerült elérni."""

    def __init__(self, message: str, *, status_code: int | None = None, errors: list | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.errors = errors or []

    @property
    def error_codes(self) -> list[str]:
        return [e.get("ErrorCode", "") for e in self.errors if isinstance(e, dict)]


class BarionThrottledError(BarionError):
    """HTTP 429 — ugyanarra a PaymentId-ra 5 másodpercen belül kérdeztünk rá kétszer."""


def _format_errors(errors: list) -> str:
    parts = []
    for err in errors:
        if isinstance(err, dict):
            code = err.get("ErrorCode", "")
            title = err.get("Title") or err.get("Description") or ""
            parts.append(f"{code}: {title}".strip(": "))
        else:
            parts.append(str(err))
    return "; ".join(p for p in parts if p)


def _request(method: str, path: str, *, body: dict | None = None, headers: dict | None = None) -> dict:
    """
    Egy Barion API hívás. Hibánál BarionError-t dob, a válasz törzsében
    lévő Errors tömbbel együtt — urllib alapból eldobná a hibatörzset,
    és csak egy csupasz "HTTP Error 400" maradna.
    """
    url = f"{API_BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req_headers = {"Accept": "application/json"}
    if data is not None:
        req_headers["Content-Type"] = "application/json"
    req_headers.update(headers or {})

    req = urllib.request.Request(url=url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw = ""
        try:
            raw = exc.read().decode("utf-8")
        except Exception:  # noqa: BLE001 - a hibatörzs olvasása maga is elszállhat
            pass
        errors = []
        try:
            payload = json.loads(raw) if raw else {}
            errors = payload.get("Errors") or []
        except json.JSONDecodeError:
            pass
        message = _format_errors(errors) or raw[:300] or str(exc)
        if exc.code == 429:
            raise BarionThrottledError(message, status_code=429, errors=errors) from exc
        raise BarionError(message, status_code=exc.code, errors=errors) from exc
    except urllib.error.URLError as exc:
        raise BarionError(f"Nem sikerült elérni a Barion API-t: {exc.reason}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BarionError(f"Értelmezhetetlen Barion válasz: {raw[:300]}") from exc

    # A Barion 200-nal is visszaadhat üzleti hibát az Errors tömbben.
    errors = payload.get("Errors") or []
    if errors:
        raise BarionError(_format_errors(errors), status_code=200, errors=errors)
    return payload


def _phone_for_barion(raw: str | None) -> str:
    """
    A Barion a telefonszámot országhívóval, jelek nélkül várja: 36301234567.
    Üres vagy nem értelmezhető szám esetén üres stringet adunk vissza —
    az opcionális mező, nem akadályozhatja meg a fizetés indítását.
    """
    if not raw:
        return ""
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return ""
    if digits.startswith("00"):
        digits = digits[2:]
    elif digits.startswith("06"):
        digits = "36" + digits[2:]
    elif len(digits) in (8, 9) and not digits.startswith("36"):
        # helyi formátum országhívó nélkül (pl. 301234567)
        digits = "36" + digits
    return digits[:30]


def _address(source: dict | None, *, with_name: bool = False) -> dict | None:
    """
    Cím a Barion 3D Secure adatszolgáltatásához. Minél többet adunk meg,
    annál nagyobb eséllyel megy át a fizetés súrlódásmentesen.
    """
    if not source:
        return None
    address = {
        "Country": source.get("country", "HU"),
        "City": source.get("city", ""),
        "Zip": source.get("zip", ""),
        "Street": source.get("address", "") or source.get("street", ""),
    }
    if with_name and source.get("name"):
        address["FullName"] = source["name"][:45]
    return {k: v for k, v in address.items() if v}


def start_payment(
    order_id: str,
    items: list[dict],
    total_huf: int,
    *,
    customer: dict | None = None,
    shipping_address: dict | None = None,
    order_number: str | None = None,
) -> dict:
    """
    Fizetés indítása. A válasz tartalmazza a GatewayUrl-t (ide kell
    átirányítani a vásárlót) és a PaymentId-t (ezt kell a rendelésre menteni).

    Hibánál BarionError-t dob — a hívó dönti el, mit mutat a vásárlónak.
    """
    if not POSKEY or not PAYEE:
        raise BarionError("Hiányzó Barion konfiguráció (BARION_POSKEY / BARION_PAYEE).")

    item_sum = sum(int(i["unit_price"]) * int(i["qty"]) for i in items)
    if item_sum != int(total_huf):
        # A Barion elutasítaná; jobb itt megfogni, ahol értelmes üzenetet tudunk adni.
        raise BarionError(
            f"A tételek összege ({item_sum} Ft) nem egyezik a végösszeggel ({total_huf} Ft)."
        )

    transaction = {
        "POSTransactionId": order_id,
        "Payee": PAYEE,
        "Total": int(total_huf),
        "Currency": "HUF",
        "Items": [
            {
                "Name": str(item["name"])[:250],
                "Description": str(item.get("description") or item["name"])[:500],
                "Quantity": int(item["qty"]),
                "Unit": item.get("unit", "db"),
                "UnitPrice": int(item["unit_price"]),
                "ItemTotal": int(item["unit_price"]) * int(item["qty"]),
                **({"SKU": str(item["sku"])[:100]} if item.get("sku") else {}),
            }
            for item in items
        ],
    }

    customer = customer or {}
    body = {
        "POSKey": POSKEY,
        "PaymentType": "Immediate",
        "GuestCheckOut": True,
        "FundingSources": ["All"],
        "PaymentRequestId": order_id,
        "OrderNumber": (order_number or order_id)[:100],
        # 30 perc a Barion alapértelmezése is; kiírva látszik, mihez képest
        # jár le a fizetés, és a callback Expired ága mikor jöhet.
        "PaymentWindow": "00:30:00",
        "PayerHint": customer.get("email", "")[:256],
        "CardHolderNameHint": customer.get("name", "")[:45],
        "Currency": "HUF",
        "Transactions": [transaction],
        "RedirectUrl": f"{REDIRECT_URL}?orderId={urllib.parse.quote(order_id)}",
        "CallbackUrl": CALLBACK_URL,
        "Locale": "hu-HU",
    }

    payer_phone = _phone_for_barion(customer.get("phone"))
    if payer_phone:
        body["PayerPhoneNumber"] = payer_phone

    billing = _address(customer)
    if billing:
        body["BillingAddress"] = billing
    shipping = _address(shipping_address or customer, with_name=True)
    if shipping:
        body["ShippingAddress"] = shipping

    response = _request("POST", "/v2/Payment/Start", body=body)

    if not response.get("PaymentId") or not response.get("GatewayUrl"):
        raise BarionError(f"Hiányos Barion válasz: {json.dumps(response)[:300]}")
    return response


def get_payment_state(payment_id: str) -> dict:
    """
    A fizetés aktuális állapota a v4 PaymentState végpontról.

    A POSKey itt HTTP fejlécben megy (x-pos-key) — a régi v2
    GetPaymentState query stringben várta, és deprecated.
    429-nél BarionThrottledError-t dob (5 mp-en belüli ismételt kérdés).
    """
    if not POSKEY:
        raise BarionError("Hiányzó Barion konfiguráció (BARION_POSKEY).")
    path = f"/v4/Payment/{urllib.parse.quote(payment_id)}/PaymentState"
    return _request("GET", path, headers={"x-pos-key": POSKEY})


def payment_total(state: dict) -> int | None:
    """
    A Barionban nyilvántartott végösszeg a state válaszból.

    Elsőként a fizetés Total mezőjét nézzük; ha az hiányzik, a tranzakciók
    összegét adjuk vissza. None, ha egyik sem olvasható ki — ilyenkor a
    hívó nem tud összeghasonlítást végezni, és ezt jeleznie kell.
    """
    total = state.get("Total")
    if isinstance(total, (int, float)):
        return int(round(total))

    transactions = state.get("Transactions") or []
    amounts = [t.get("Total") for t in transactions if isinstance(t, dict)]
    amounts = [a for a in amounts if isinstance(a, (int, float))]
    if amounts:
        return int(round(sum(amounts)))
    return None


def payment_currency(state: dict) -> str | None:
    currency = state.get("Currency")
    if currency:
        return currency
    for transaction in state.get("Transactions") or []:
        if isinstance(transaction, dict) and transaction.get("Currency"):
            return transaction["Currency"]
    return None


def card_summary(state: dict) -> str:
    """Rövid, naplózható leírás a fizetőeszközről — teljes kártyaszám soha."""
    info = state.get("FundingInformation") or {}
    card = info.get("BankCard") or {}
    masked = card.get("MaskedPan")
    card_type = card.get("BankCardType")
    parts = [p for p in (card_type, masked) if p]
    return " ".join(parts) or (state.get("FundingSource") or "")
