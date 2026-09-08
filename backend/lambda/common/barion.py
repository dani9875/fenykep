"""
Barion Smart Gateway client.

Env vars required on the Lambdas that import this module:
  BARION_POSKEY      Private API key from the Barion merchant admin.
  BARION_PAYEE       The Barion email address that receives the money.
  BARION_API_BASE    https://api.test.barion.com for the sandbox,
                      https://api.barion.com for production.
  BARION_CALLBACK_URL   API Gateway URL of the barion_callback Lambda.
  BARION_REDIRECT_URL   Frontend "köszönjük" page URL.
"""

import os
import urllib.request
import json

API_BASE = os.environ["BARION_API_BASE"]
POSKEY = os.environ["BARION_POSKEY"]
PAYEE = os.environ["BARION_PAYEE"]
CALLBACK_URL = os.environ["BARION_CALLBACK_URL"]
REDIRECT_URL = os.environ["BARION_REDIRECT_URL"]


def _post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        url=f"{API_BASE}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get(path: str) -> dict:
    req = urllib.request.Request(url=f"{API_BASE}{path}", method="GET")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def start_payment(order_id: str, items: list[dict], total_huf: int) -> dict:
    """
    Start a Barion payment. Returns the Barion response, which includes
    GatewayUrl (redirect the customer here) and PaymentId (store this
    on the order).
    """
    transaction = {
        "POSTransactionId": order_id,
        "Payee": PAYEE,
        "Total": total_huf,
        "Items": [
            {
                "Name": item["name"][:250],
                "Description": item.get("description", "")[:500],
                "Quantity": item["qty"],
                "Unit": "db",
                "UnitPrice": item["unit_price"],
                "ItemTotal": item["unit_price"] * item["qty"],
            }
            for item in items
        ],
    }
    body = {
        "POSKey": POSKEY,
        "PaymentType": "Immediate",
        "GuestCheckout": True,
        "FundingSources": ["All"],
        "PaymentRequestId": order_id,
        "PayerHint": "",
        "Currency": "HUF",
        "Transactions": [transaction],
        "RedirectUrl": f"{REDIRECT_URL}?orderId={order_id}",
        "CallbackUrl": CALLBACK_URL,
        "Locale": "hu-HU",
    }
    return _post("/v2/Payment/Start", body)


def get_payment_state(payment_id: str) -> dict:
    return _get(f"/v2/Payment/GetPaymentState?PaymentId={payment_id}")
