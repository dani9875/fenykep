"""
Local test server. Zero dependencies — standard library only.

What this does:
  - Serves frontend/ as static files.
  - Fakes every Lambda endpoint in memory (no DynamoDB, no S3).
  - Fakes the Barion gateway with a local page where you can pick the
    outcome: sikeres, sikertelen, megszakított, lejárt, vagy eltérő
    összegű fizetés. Így a hibás fizetések ágai is végigjárhatók anélkül,
    hogy a Barion sandboxhoz nyúlnánk.
  - Fetches the REAL Foxpost locker list from cdn.foxpost.hu, so the
    map picker works exactly like production.

What this does NOT test:
  - A valódi Barion API (aláírás, 3D Secure, IPN időzítés). Ahhoz a
    sandbox kell — lásd infra/README.md.
  - Real email delivery (SES). Confirmation emails are printed to
    this terminal instead of sent.
  - Real S3 uploads. Photos are saved to local-test/uploads/.

Run:
  cd local-test
  python3 server.py
Then open http://localhost:8787 in a browser.
"""

import http.server
import json
import os
import re
import socketserver
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

PORT = 8787
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "backend" / "lambda" / "common"))
from products import (  # noqa: E402
    COD_FEE_HUF,
    FOXPOST_SHIPPING_FEE_HUF,
    FREE_SHIPPING_THRESHOLD_HUF,
    HOME_DELIVERY_FEE_HUF,
    MAX_QTY_PER_ITEM,
    PAYMENT_METHODS,
    PRODUCTS,
    SHIPPING_METHODS,
    get_cod_fee,
    get_item_price,
    get_shipping_fee,
    is_payment_allowed,
)

ORDERS = {}  # orderId -> order dict, in memory only, resets on restart
FOXPOST_CACHE = {"lockers": None, "fetchedAt": 0}

STATUS_MESSAGES = {
    "pending_payment": "A fizetés feldolgozás alatt.",
    "paid": "A fizetés sikeres volt.",
    "pending_transfer": "A rendelést rögzítettük, várjuk az átutalást.",
    "pending_cod": "A rendelést rögzítettük, utánvéttel fizetsz átvételkor.",
    "payment_failed": "A fizetés nem sikerült.",
    "payment_canceled": "A fizetést megszakítottad.",
    "payment_expired": "A fizetési idő lejárt.",
    "payment_mismatch": "A fizetett összeg nem egyezik a rendelés végösszegével.",
}

# A mock fizetőoldal gombjai: (kulcs, felirat, rendelés-státusz, leírás)
MOCK_OUTCOMES = [
    ("success", "Sikeres fizetés", "paid", "Ahogy egy valódi, jóváhagyott kártyás tranzakció."),
    ("failed", "Sikertelen fizetés", "payment_failed", "A bank elutasítja — pl. fedezethiány."),
    ("canceled", "Megszakítom", "payment_canceled", "A vásárló kilép a Barion oldaláról."),
    ("expired", "Lejárt fizetés", "payment_expired", "Letelik a 30 perces fizetési ablak."),
    ("mismatch", "Eltérő összeg", "payment_mismatch", "A Barion más összeget igazol vissza, mint a rendelés — kézi ellenőrzés."),
]


def get_foxpost_lockers():
    if FOXPOST_CACHE["lockers"] and time.time() - FOXPOST_CACHE["fetchedAt"] < 3600:
        return FOXPOST_CACHE["lockers"]
    with urllib.request.urlopen("https://cdn.foxpost.hu/foxplus.json", timeout=15) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    lockers = [
        {
            "id": x["place_id"],
            "name": x["name"],
            "address": x["address"],
            "city": x["city"],
            "zip": x["zip"],
            "lat": x["geolat"],
            "lng": x["geolng"],
        }
        for x in raw
    ]
    FOXPOST_CACHE["lockers"] = lockers
    FOXPOST_CACHE["fetchedAt"] = time.time()
    return lockers


def mock_gateway_page(order: dict) -> bytes:
    """A Barion fizetőoldalának helyi mása, kimenet-választóval."""
    buttons = "".join(
        f"""
        <form method="get" action="/mock-barion/finish">
          <input type="hidden" name="orderId" value="{order['orderId']}">
          <input type="hidden" name="outcome" value="{key}">
          <button type="submit" class="outcome outcome--{key}">
            <strong>{label}</strong>
            <small>{description}</small>
          </button>
        </form>"""
        for key, label, _status, description in MOCK_OUTCOMES
    )
    html = f"""<!DOCTYPE html>
<html lang="hu"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MOCK Barion fizetőoldal</title>
<style>
  body {{ font-family: system-ui, sans-serif; background:#f5ede0; margin:0; padding:2rem; color:#1c1917; }}
  .card {{ max-width:620px; margin:2rem auto; background:#fff; border-radius:16px; padding:2rem; box-shadow:0 10px 40px rgba(0,0,0,0.08); }}
  h1 {{ font-size:1.25rem; margin:0 0 0.35rem; }}
  .warn {{ background:#fff4d6; border:1px solid #e3c877; border-radius:8px; padding:0.75rem 1rem; font-size:0.85rem; margin-bottom:1.5rem; }}
  dl {{ display:grid; grid-template-columns:auto 1fr; gap:0.35rem 1rem; font-size:0.9rem; margin:0 0 1.5rem; }}
  dt {{ color:#6b5f55; }}
  .outcome {{ display:block; width:100%; text-align:left; background:#fff; border:1.5px solid #ddd0c0;
             border-radius:10px; padding:0.8rem 1rem; margin-bottom:0.6rem; cursor:pointer; font:inherit; }}
  .outcome:hover {{ border-color:#1c1917; }}
  .outcome small {{ display:block; color:#6b5f55; font-size:0.78rem; margin-top:0.15rem; }}
  .outcome--success {{ border-color:#4a7a44; }}
</style></head>
<body><div class="card">
  <h1>MOCK Barion fizetőoldal</h1>
  <div class="warn">Ez nem a Barion. A helyi teszt-szerver oldala, hogy a fizetés
    mindegyik kimenetét ki lehessen próbálni. Éles és sandbox környezetben
    a vásárló a valódi Barion felületére kerül.</div>
  <dl>
    <dt>Rendelési szám</dt><dd>{order['orderId']}</dd>
    <dt>Fizetendő</dt><dd>{order['totalHuf']:,} Ft</dd>
    <dt>PaymentId</dt><dd>{order.get('paymentId', '')}</dd>
  </dl>
  <p><strong>Válaszd ki, mi történjen:</strong></p>
  {buttons}
</div></body></html>"""
    return html.encode("utf-8")


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def end_headers(self):
        """Never let the browser cache anything from the test server.

        SimpleHTTPRequestHandler answers a conditional request with 304,
        so after editing CSS or JS the browser keeps serving its old copy
        and you review changes that are not on the page. A new script tag
        in an HTML file is not even fetched. Not a concern in production,
        where each deploy gets fresh URLs.
        """
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

    def send_head(self):
        # Drop the validators the 304 path relies on, so a static file is
        # always sent in full.
        for header in ("If-Modified-Since", "If-None-Match"):
            while header in self.headers:
                del self.headers[header]
        return super().send_head()

    def _json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, status, body: bytes):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str):
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw or b"{}")

    # ---- GET ----
    def do_GET(self):
        if self.path.startswith("/products"):
            return self._json(200, {
                "products": PRODUCTS,
                "freeShippingThresholdHuf": FREE_SHIPPING_THRESHOLD_HUF,
                "foxpostShippingFeeHuf": FOXPOST_SHIPPING_FEE_HUF,
                "homeDeliveryFeeHuf": HOME_DELIVERY_FEE_HUF,
                "codFeeHuf": COD_FEE_HUF,
                "shippingMethods": SHIPPING_METHODS,
                "paymentMethods": {
                    k: {"label": v["label"], "shipping": list(v["shipping"])}
                    for k, v in PAYMENT_METHODS.items()
                },
            })

        if self.path.startswith("/foxpost-lockers"):
            try:
                lockers = get_foxpost_lockers()
            except Exception as exc:  # noqa: BLE001
                return self._json(502, {"error": str(exc)})

            qs = urllib.parse.urlsplit(self.path).query
            params = urllib.parse.parse_qs(qs)
            city = (params.get("city", [""])[0]).strip().lower()
            if city:
                lockers = [l for l in lockers if city in l["city"].lower() or city in l["address"].lower()]
            if all(k in params for k in ("minLat", "maxLat", "minLng", "maxLng")):
                min_lat, max_lat = float(params["minLat"][0]), float(params["maxLat"][0])
                min_lng, max_lng = float(params["minLng"][0]), float(params["maxLng"][0])
                lockers = [l for l in lockers if min_lat <= l["lat"] <= max_lat and min_lng <= l["lng"] <= max_lng]
            return self._json(200, {"lockers": lockers[:300]})

        # --- mock Barion fizetőoldal ---
        split = urllib.parse.urlsplit(self.path)
        params = urllib.parse.parse_qs(split.query)

        if split.path == "/mock-barion":
            order = ORDERS.get(params.get("orderId", [""])[0])
            if not order:
                return self._html(404, b"<h1>Ismeretlen rendeles</h1>")
            return self._html(200, mock_gateway_page(order))

        if split.path == "/mock-barion/finish":
            order = ORDERS.get(params.get("orderId", [""])[0])
            outcome = params.get("outcome", ["success"])[0]
            if not order:
                return self._html(404, b"<h1>Ismeretlen rendeles</h1>")
            status = next((s for key, _l, s, _d in MOCK_OUTCOMES if key == outcome), "paid")
            order["orderStatus"] = status
            order["updatedAt"] = int(time.time())
            if status == "paid":
                print(f"\n[MOCK EMAIL] Order confirmation to {order['customer']['email']}: "
                      f"order {order['orderId']}, total {order['totalHuf']} Ft\n")
            elif status == "payment_mismatch":
                order["paidTotalHuf"] = order["totalHuf"] - 500
                print(f"\n[MOCK ADMIN] AMOUNT MISMATCH on {order['orderId']}: "
                      f"paid {order['paidTotalHuf']} vs expected {order['totalHuf']}\n")
            else:
                print(f"\n[MOCK EMAIL] Payment failure notice to {order['customer']['email']}: "
                      f"order {order['orderId']} → {status}\n")
            return self._redirect(f"/koszonjuk.html?orderId={order['orderId']}")

        m = re.match(r"^/orders/([\w-]+)$", split.path)
        if m:
            order = ORDERS.get(m.group(1))
            if not order:
                return self._json(404, {"error": "Not found"})
            status = order["orderStatus"]
            return self._json(200, {
                "orderId": order["orderId"],
                "status": status,
                "message": STATUS_MESSAGES.get(status, ""),
                "totalHuf": order["totalHuf"],
                "paymentMethod": order.get("paymentMethod", "barion"),
                "shippingMethod": order.get("shipping", {}).get("method", ""),
            })

        return super().do_GET()  # static files

    # ---- POST ----
    def do_POST(self):
        if self.path == "/uploads":
            body = self._read_json_body()
            name = re.sub(r"[^A-Za-z0-9._-]", "_", body.get("fileName", "photo.jpg"))
            key = f"{uuid.uuid4()}-{name}"
            return self._json(200, {
                "uploadUrl": f"http://localhost:{PORT}/mock-upload/{key}",
                "key": key,
            })

        if self.path == "/contact":
            body = self._read_json_body()
            for field in ("firstName", "email", "message"):
                if not body.get(field):
                    return self._json(400, {"error": f"Missing field: {field}"})
            print(f"\n[MOCK EMAIL] Contact form from {body['firstName']} <{body['email']}>: "
                  f"{body.get('subject', '(nincs tárgy)')}\n{body['message']}\n")
            return self._json(200, {"ok": True})

        if self.path == "/orders":
            return self._create_order()

        m = re.match(r"^/mock-upload/([\w.\-]+)$", self.path)
        if m:
            length = int(self.headers.get("Content-Length", 0))
            data = self.rfile.read(length)
            (UPLOAD_DIR / m.group(1)).write_bytes(data)
            return self._json(200, {"ok": True})

        return self._json(404, {"error": "Unknown route"})

    def _create_order(self):
        """A create_order Lambda egyszerűsített mása — ugyanazokkal a szabályokkal."""
        body = self._read_json_body()
        try:
            customer = body.get("customer") or {}
            for field in ("name", "email", "phone", "address", "city", "zip"):
                if not customer.get(field):
                    return self._json(400, {"error": f"Hiányzó adat: {field}."})

            consents = body.get("consents") or {}
            if not consents.get("aszf") or not consents.get("privacy"):
                return self._json(400, {"error": "Az ÁSZF és az adatvédelmi tájékoztató elfogadása kötelező."})

            shipping = dict(body.get("shipping") or {})
            shipping_method = shipping.get("method")
            if shipping_method not in SHIPPING_METHODS:
                return self._json(400, {"error": "Ismeretlen szállítási mód."})
            if shipping_method == "foxpost" and not shipping.get("lockerId"):
                return self._json(400, {"error": "Válassz egy Foxpost csomagautomatát."})
            if shipping_method == "home":
                if shipping.get("sameAsBilling"):
                    shipping["address"] = {
                        "name": customer["name"],
                        "address": customer["address"],
                        "city": customer["city"],
                        "zip": customer["zip"],
                    }
                address = shipping.get("address") or {}
                for field in ("name", "address", "city", "zip"):
                    if not address.get(field):
                        return self._json(400, {"error": f"Hiányzó szállítási adat: {field}."})

            payment_method = body.get("paymentMethod", "barion")
            if not is_payment_allowed(payment_method, shipping_method):
                return self._json(400, {
                    "error": "Utánvét csak házhozszállításnál választható — a csomagautomata nem fogad készpénzt."
                    if payment_method == "cod"
                    else "A választott fizetési mód nem használható ezzel a szállítási móddal."
                })

            items = []
            subtotal = 0
            for raw in body.get("items") or []:
                price = get_item_price(raw["productId"], raw["size"])
                qty = int(raw.get("qty", 1))
                if qty < 1 or qty > MAX_QTY_PER_ITEM:
                    return self._json(400, {"error": f"A darabszám 1 és {MAX_QTY_PER_ITEM} között lehet."})
                subtotal += price * qty
                items.append({**raw, "unitPrice": price, "qty": qty})
            if not items:
                return self._json(400, {"error": "A kosár üres."})

            fee = get_shipping_fee(subtotal, shipping_method)
            cod_fee = get_cod_fee(payment_method)
            total = subtotal + fee + cod_fee
            order_id = str(uuid.uuid4())

            status = {
                "transfer": "pending_transfer",
                "cod": "pending_cod",
            }.get(payment_method, "pending_payment")

            order = {
                "orderId": order_id,
                "orderStatus": status,
                "paymentMethod": payment_method,
                "customer": customer,
                "shipping": {**shipping, "feeHuf": fee},
                "items": items,
                "subtotalHuf": subtotal,
                "shippingFeeHuf": fee,
                "codFeeHuf": cod_fee,
                "totalHuf": total,
                "updatedAt": int(time.time()),
            }
            ORDERS[order_id] = order

            if payment_method == "transfer":
                print(f"\n[MOCK EMAIL] Transfer instructions to {customer['email']}: "
                      f"order {order_id}, total {total} Ft, account IBAN NINCS BEÁLLÍTVA\n")
                return self._json(200, {
                    "orderId": order_id,
                    "paymentMethod": payment_method,
                    "redirectUrl": f"http://localhost:{PORT}/koszonjuk.html?orderId={order_id}",
                })

            if payment_method == "cod":
                print(f"\n[MOCK EMAIL] COD confirmation to {customer['email']}: "
                      f"order {order_id}, total {total} Ft\n")
                return self._json(200, {
                    "orderId": order_id,
                    "paymentMethod": payment_method,
                    "redirectUrl": f"http://localhost:{PORT}/koszonjuk.html?orderId={order_id}",
                })

            # Bankkártya: a mock fizetőoldalra megyünk, ott dől el a kimenet.
            order["paymentId"] = uuid.uuid4().hex
            return self._json(200, {
                "orderId": order_id,
                "paymentMethod": payment_method,
                "gatewayUrl": f"http://localhost:{PORT}/mock-barion?orderId={order_id}",
            })
        except (KeyError, ValueError) as exc:
            return self._json(400, {"error": str(exc)})

    def do_PUT(self):
        # The real API uses PUT for the presigned S3 upload.
        m = re.match(r"^/mock-upload/([\w.\-]+)$", self.path)
        if m:
            length = int(self.headers.get("Content-Length", 0))
            data = self.rfile.read(length)
            (UPLOAD_DIR / m.group(1)).write_bytes(data)
            return self._json(200, {"ok": True})
        return self._json(404, {"error": "Unknown route"})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


if __name__ == "__main__":
    # Without this a restart right after Ctrl+C fails with
    # "Address already in use" while the old socket sits in TIME_WAIT.
    socketserver.ThreadingTCPServer.allow_reuse_address = True

    with socketserver.ThreadingTCPServer(("", PORT), Handler) as httpd:
        print(f"Local test server: http://localhost:{PORT}")
        print("A Barion helyett egy helyi mock fizetőoldal fut — ott választhatod ki,")
        print("hogy a fizetés sikeres, sikertelen, megszakított, lejárt vagy eltérő összegű legyen.")
        print("Az SES emailek a terminálra íródnak ki.")
        httpd.serve_forever()
