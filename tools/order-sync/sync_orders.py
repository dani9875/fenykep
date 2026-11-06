#!/usr/bin/env python3
"""
Rendelések szinkronja a DynamoDB-ből egy Google Sheetbe.

Egy sor = egy tétel (egy fotó). A sorokat a "Tétel" oszlop azonosítja
(<rendelésszám>#<sorszám>), ezért a táblát szabadon lehet rendezni és
szűrni, a szinkron mindig a megfelelő sort frissíti.

A script CSAK a saját oszlopaihoz nyúl (a MANAGED_COLUMNS listában
lévő fejlécűekhez, bárhol is állnak). Minden más oszlop a tiéd: azokat
soha nem írja és nem törli. Sort sem töröl, csak frissít vagy újat ad
hozzá a tábla végére.

Futtatás:
    python3 sync_orders.py              # egyszeri szinkron
    python3 sync_orders.py --dry-run    # csak kiírja, mit csinálna

Beállítás: lásd README.md.
"""

import argparse
import os
import sys
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import boto3
import gspread

# ── beállítások (környezeti változóból vagy .env-szerűen exportálva) ─────
ORDERS_TABLE = os.environ.get("ORDERS_TABLE", "litho-dev-orders")
AWS_REGION = os.environ.get("AWS_REGION", "eu-central-1")
SHEET_ID = os.environ.get("SHEET_ID", "")            # a Sheet URL-jéből: /d/<EZ>/edit
SHEET_TAB = os.environ.get("SHEET_TAB", "Rendelések")
GOOGLE_CREDENTIALS = os.environ.get(
    "GOOGLE_CREDENTIALS", os.path.join(os.path.dirname(__file__), "google-service-account.json")
)
TZ = ZoneInfo("Europe/Budapest")

STATUS_LABELS = {
    "pending_payment": "Fizetésre vár (Barion)",
    "pending_transfer": "Utalásra vár",
    "paid": "Fizetve",
    "payment_review": "Fizetés ellenőrzendő",
    "payment_mismatch": "Eltérő összeg, ellenőrzendő",
    "payment_failed": "Sikertelen fizetés",
    "payment_canceled": "Fizetés megszakítva",
    "payment_expired": "Fizetés lejárt",
    "payment_init": "Fizetés indul",
    "payment_start_failed": "Fizetés nem indult el",
    "fulfilled": "Teljesítve",
    "canceled": "Törölve",
}

KEY_COLUMN = "Tétel"

# A script által kezelt oszlopok, ebben a sorrendben jönnek létre egy
# üres táblán. Ha átnevezel egyet, a script újat hoz létre helyette.
MANAGED_COLUMNS = [
    KEY_COLUMN,
    "Rendelésszám",
    "Dátum",
    "Állapot",
    "Név",
    "E-mail",
    "Telefon",
    "Szállítás",
    "Szállítási cím",
    "Termék",
    "Méret",
    "Db",
    "Tétel ára (Ft)",
    "Rendelés végösszege (Ft)",
    "Fizetési mód",
    "Megjegyzés (vásárló)",
    "Fotó fájl",
]


def _plain(value):
    """DynamoDB Decimal -> int/float, rekurzívan."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    return value


def fetch_orders():
    table = boto3.resource("dynamodb", region_name=AWS_REGION).Table(ORDERS_TABLE)
    kwargs = {}
    while True:
        page = table.scan(**kwargs)
        for item in page.get("Items", []):
            yield _plain(item)
        if "LastEvaluatedKey" not in page:
            return
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def _address(order):
    shipping = order.get("shipping") or {}
    if shipping.get("method") == "foxpost":
        return shipping.get("lockerName") or shipping.get("lockerId") or ""
    a = shipping.get("address") or {}
    return f"{a.get('zip', '')} {a.get('city', '')}, {a.get('address', '')}".strip(" ,")


def order_rows(order):
    """Egy rendelésből tételenként egy sor: {oszlopnév: érték}."""
    customer = order.get("customer") or {}
    created = order.get("createdAt")
    date = datetime.fromtimestamp(created, TZ).strftime("%Y-%m-%d %H:%M") if created else ""
    for index, item in enumerate(order.get("items") or [], start=1):
        photo = item.get("photoFile") or item.get("photoKey") or ""
        yield {
            KEY_COLUMN: f"{order['orderId']}#{index}",
            "Rendelésszám": order["orderId"],
            "Dátum": date,
            "Állapot": STATUS_LABELS.get(order.get("orderStatus"), order.get("orderStatus", "")),
            "Név": customer.get("name", ""),
            "E-mail": customer.get("email", ""),
            "Telefon": customer.get("phone", ""),
            "Szállítás": (order.get("shipping") or {}).get("label", ""),
            "Szállítási cím": _address(order),
            "Termék": item.get("productName", item.get("productId", "")),
            "Méret": item.get("size", ""),
            "Db": item.get("qty", 1),
            "Tétel ára (Ft)": item.get("unitPrice", 0) * item.get("qty", 1),
            "Rendelés végösszege (Ft)": order.get("totalHuf", ""),
            "Fizetési mód": "Bankkártya (Barion)" if order.get("paymentMethod") == "barion" else "Előre utalás",
            "Megjegyzés (vásárló)": customer.get("notes", ""),
            "Fotó fájl": photo.rsplit("/", 1)[-1],
        }


def _col_letter(n):
    """1 -> A, 27 -> AA"""
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def sync(dry_run=False):
    if not SHEET_ID:
        sys.exit("Hiányzik a SHEET_ID környezeti változó (lásd README.md).")

    sheet = gspread.service_account(filename=GOOGLE_CREDENTIALS).open_by_key(SHEET_ID)
    try:
        ws = sheet.worksheet(SHEET_TAB)
    except gspread.WorksheetNotFound:
        ws = sheet.add_worksheet(SHEET_TAB, rows=1000, cols=len(MANAGED_COLUMNS) + 10)

    values = ws.get_all_values()
    header = values[0] if values else []
    updates = []  # (range, [[value]])

    # Hiányzó kezelt oszlopok: a fejléc végére kerülnek, a te oszlopaidat nem tolják el.
    for name in MANAGED_COLUMNS:
        if name not in header:
            header.append(name)
            updates.append((f"{_col_letter(len(header))}1", [[name]]))
    col_of = {name: header.index(name) + 1 for name in MANAGED_COLUMNS}
    key_col = col_of[KEY_COLUMN] - 1

    row_of = {}
    for r, row in enumerate(values[1:], start=2):
        if len(row) > key_col and row[key_col]:
            row_of[row[key_col]] = r
    next_row = max(len(values), 1) + 1

    rows = [row for order in fetch_orders() for row in order_rows(order)]
    rows.sort(key=lambda row: (row["Dátum"], row[KEY_COLUMN]))

    changed = added = 0
    for row in rows:
        r = row_of.get(row[KEY_COLUMN])
        current = values[r - 1] if r else []
        if not r:
            r, next_row = next_row, next_row + 1
            added += 1
        row_changed = False
        for name, value in row.items():
            c = col_of[name]
            old = current[c - 1] if len(current) >= c else ""
            if str(old) != str(value):
                updates.append((f"{_col_letter(c)}{r}", [[value]]))
                row_changed = True
        if row_changed and current:
            changed += 1

    print(f"{len(rows)} tétel · {added} új sor · {changed} frissített sor · {len(updates)} cella")
    if dry_run or not updates:
        return

    needed_rows = next_row - 1
    if needed_rows > ws.row_count:
        ws.add_rows(needed_rows - ws.row_count + 100)
    if len(header) > ws.col_count:
        ws.add_cols(len(header) - ws.col_count)

    ws.batch_update(
        [{"range": rng, "values": vals} for rng, vals in updates],
        # RAW: a "+36..." telefonszám ne váljon számmá, és a vásárló
        # megjegyzésében egy "=" kezdetű szöveg ne fusson le képletként.
        value_input_option="RAW",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="csak kiírja, mit csinálna")
    sync(parser.parse_args().dry_run)
