"""
A rendeléshez tartozó fotók beszédes nevű másolata.

A vásárló a fotót még a rendelés előtt tölti fel, ezért a feltöltés
kulcsa véletlen (uploads/<uuid>-<fájlnév>). Rendeléskor minden tétel
fotóját átmásoljuk ide:

    orders/<ÉÉÉÉ-HH-NN>/<ID>_<Név>_<Szállítási cím>_<n>-<termék>-<méret>.<kiterjesztés>

Az ID a rendelésazonosító első 8 karaktere (nagybetűvel), így a fájl
neve alapján a rendelés is megtalálható. A dátumos mappa miatt a
rendelések időrendben követhetők, a mappán belül az ID szerint
rendeződnek. A nevekből az ékezetek és a különleges karakterek
kimaradnak, hogy minden letöltő- és tömörítőprogram kezelje őket.

Az eredeti feltöltés megmarad: ha a fizetés indítása elbukik, a vásárló
ugyanazzal a kosárral újra próbálkozhat.
"""

import os
import re
import time
import unicodedata

UPLOAD_PREFIX = "uploads/"
ORDER_PREFIX = "orders/"

MAX_NAME_LEN = 40
MAX_ADDRESS_LEN = 70

PRODUCT_SHORT = {
    "lampa-nelkul": "lampa-nelkul",
    "led-talpas": "LED",
}


def _ascii_slug(text: str, max_len: int) -> str:
    """'Kovács Éva, 1105 Bp.' -> 'Kovacs-Eva-1105-Bp'"""
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")
    return text[:max_len].rstrip("-")


def short_order_id(order_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", order_id)[:8].upper()


def shipping_address_text(order: dict) -> str:
    shipping = order.get("shipping") or {}
    if shipping.get("method") == "foxpost":
        return f"Foxpost {shipping.get('lockerName') or shipping.get('lockerId') or ''}"
    address = shipping.get("address") or {}
    return f"{address.get('zip', '')} {address.get('city', '')} {address.get('address', '')}"


def photo_file_key(order: dict, index: int, item: dict, now: float | None = None) -> str:
    """Az index 1-től számol: a rendelés hányadik tétele."""
    day = time.strftime("%Y-%m-%d", time.gmtime(now if now is not None else time.time()))
    ext = os.path.splitext(item.get("photoKey", ""))[1].lower()
    if ext not in (".jpg", ".jpeg", ".png"):
        ext = ".jpg"

    name = _ascii_slug((order.get("customer") or {}).get("name"), MAX_NAME_LEN) or "nev-nelkul"
    address = _ascii_slug(shipping_address_text(order), MAX_ADDRESS_LEN) or "cim-nelkul"
    product = PRODUCT_SHORT.get(item.get("productId"), _ascii_slug(item.get("productId"), 20))
    size = _ascii_slug(item.get("size"), 10)

    file_name = f"{short_order_id(order['orderId'])}_{name}_{address}_{index}-{product}-{size}{ext}"
    return f"{ORDER_PREFIX}{day}/{file_name}"


class PhotoMissing(Exception):
    """A tételhez megadott feltöltés nem létezik (vagy nem a mi feltöltésünk)."""


def archive_order_photos(order: dict, s3_client, bucket: str) -> None:
    """Átmásolja a tételek fotóit, és minden tételbe beírja a `photoFile` kulcsot."""
    for index, item in enumerate(order.get("items") or [], start=1):
        source = item.get("photoKey") or ""
        if not source.startswith(UPLOAD_PREFIX) or ".." in source:
            raise PhotoMissing(source)
        target = photo_file_key(order, index, item)
        try:
            s3_client.copy_object(
                Bucket=bucket,
                Key=target,
                CopySource={"Bucket": bucket, "Key": source},
                MetadataDirective="COPY",
            )
        except Exception as exc:  # noqa: BLE001
            code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
            if code in ("NoSuchKey", "404", "AccessDenied"):
                raise PhotoMissing(source) from exc
            raise
        item["photoFile"] = target
