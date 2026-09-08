"""
Local test server. Zero dependencies — standard library only.

What this does:
  - Serves frontend/ as static files.
  - Fakes every Lambda endpoint in memory (no DynamoDB, no S3).
  - Skips Barion entirely. "Rendelés leadása" jumps straight to the
    thank-you page as if the payment already succeeded.
  - Fetches the REAL Foxpost locker list from cdn.foxpost.hu, so the
    map picker works exactly like production.

What this does NOT test:
  - Real payment. Barion sandbox testing is a separate step — see
    infra/README.md.
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
from products import get_item_price, get_shipping_fee, PRODUCTS, FREE_SHIPPING_THRESHOLD_HUF, FOXPOST_SHIPPING_FEE_HUF  # noqa: E402

ORDERS = {}  # orderId -> order dict, in memory only, resets on restart
FOXPOST_CACHE = {"lockers": None, "fetchedAt": 0}


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


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def _json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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

        m = re.match(r"^/orders/([\w-]+)$", self.path)
        if m:
            order = ORDERS.get(m.group(1))
            if not order:
                return self._json(404, {"error": "Not found"})
            return self._json(200, {
                "orderId": order["orderId"],
                "status": order["orderStatus"],
                "totalHuf": order["totalHuf"],
                "paymentMethod": order.get("paymentMethod", "barion"),
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
            body = self._read_json_body()
            try:
                payment_method = body.get("paymentMethod", "barion")
                if payment_method == "cod" and body["shipping"].get("method") == "foxpost":
                    return self._json(400, {"error": "Utánvét nem választható Foxpost csomagautomatánál."})

                items = []
                subtotal = 0
                for raw in body["items"]:
                    price = get_item_price(raw["productId"], raw["size"])
                    qty = int(raw.get("qty", 1))
                    subtotal += price * qty
                    items.append({**raw, "unitPrice": price})
                fee = get_shipping_fee(subtotal)
                total = subtotal + fee
                order_id = str(uuid.uuid4())
                order_status = "pending_transfer" if payment_method == "transfer" else "paid"
                order = {
                    "orderId": order_id,
                    "orderStatus": order_status,  # mock: skip Barion, mark card orders paid immediately
                    "paymentMethod": payment_method,
                    "customer": body["customer"],
                    "shipping": {**body["shipping"], "feeHuf": fee},
                    "items": items,
                    "subtotalHuf": subtotal,
                    "totalHuf": total,
                }
                ORDERS[order_id] = order

                if payment_method == "transfer":
                    print(f"\n[MOCK EMAIL] Transfer instructions to {order['customer']['email']}: "
                          f"order {order_id}, total {total} Ft, account IBAN NINCS BEÁLLÍTVA\n")
                else:
                    print(f"\n[MOCK EMAIL] Order confirmation to {order['customer']['email']}: "
                          f"order {order_id}, total {total} Ft\n")

                suffix = "&method=transfer" if payment_method == "transfer" else ""
                return self._json(200, {
                    "orderId": order_id,
                    "gatewayUrl": f"http://localhost:{PORT}/koszonjuk.html?orderId={order_id}{suffix}",
                })
            except (KeyError, ValueError) as exc:
                return self._json(400, {"error": str(exc)})

        m = re.match(r"^/mock-upload/([\w.\-]+)$", self.path)
        if m:
            length = int(self.headers.get("Content-Length", 0))
            data = self.rfile.read(length)
            (UPLOAD_DIR / m.group(1)).write_bytes(data)
            return self._json(200, {"ok": True})

        return self._json(404, {"error": "Unknown route"})

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
    with socketserver.ThreadingTCPServer(("", PORT), Handler) as httpd:
        print(f"Local test server: http://localhost:{PORT}")
        print("Barion és SES ki van kapcsolva ebben a módban — lásd a fájl elején lévő megjegyzést.")
        httpd.serve_forever()
