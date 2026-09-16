"""
Visszaélés elleni védelem a publikus végpontokon.

Fontos, hogy tisztán lássuk, mi mit ér:

  * A CORS NEM védelem. Csak a böngészőt köti; egy curl vagy szkript
    figyelmen kívül hagyja. Attól még kell, de nem erre való.
  * Az Origin/Referer fejléc ellenőrzése HAMISÍTHATÓ. Kiszűri a naiv
    szkripteket és a más oldalakba ágyazott hívásokat, de elszánt
    támadót nem állít meg. Réteg, nem határ.
  * Ami tényleg korlátoz: a kérésszám IP-nként (ez a modul), az API
    Gateway throttlingja (infra/terraform/api.tf), és az, hogy a
    drága műveletek (Barion, SES, S3) szerveroldali ellenőrzés mögött
    vannak.

Env vars:
  RATE_LIMIT_TABLE   a számlálókat tartó DynamoDB tábla neve
  ALLOWED_ORIGINS    vesszővel elválasztott origin-lista
  ENFORCE_ORIGIN     "false"-ra állítva kikapcsolható (hibakereséshez)
"""

import json
import os
import time

import boto3

_TABLE_NAME = os.environ.get("RATE_LIMIT_TABLE", "")
_dynamodb = boto3.resource("dynamodb")

ALLOWED_ORIGINS = [o.strip().rstrip("/") for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
ENFORCE_ORIGIN = os.environ.get("ENFORCE_ORIGIN", "true").lower() != "false"

# A kérés törzse JSON — pár kilobájtnál semmi sem lehet nagyobb nálunk.
MAX_BODY_BYTES = 64 * 1024


class Rejected(Exception):
    """A kérést elutasítjuk. A status_code és az üzenet megy vissza a hívónak."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message

    def response(self, headers: dict) -> dict:
        body = {"error": self.message}
        if self.status_code == 429:
            body["retryAfterSeconds"] = 60
        return {"statusCode": self.status_code, "headers": headers, "body": json.dumps(body)}


def client_ip(event) -> str:
    ctx = (event.get("requestContext") or {}).get("http") or {}
    return ctx.get("sourceIp") or "unknown"


def _header(event, name: str) -> str:
    headers = event.get("headers") or {}
    # Az API Gateway kisbetűsíti a fejléceket, de ne múljon ezen.
    for key, value in headers.items():
        if key.lower() == name:
            return value or ""
    return ""


def check_origin(event) -> None:
    """
    Böngészőből érkező kérésnél megköveteljük, hogy a saját oldalunkról jöjjön.

    Nem biztonsági határ (a fejléc hamisítható), de kiszűri az idegen
    oldalba ágyazott és a találomra szkriptelt hívásokat.
    """
    if not ENFORCE_ORIGIN or not ALLOWED_ORIGINS:
        return

    origin = _header(event, "origin").rstrip("/")
    if not origin:
        # Referer tartalék: néhány kliens csak azt küldi.
        referer = _header(event, "referer")
        if referer:
            parts = referer.split("/")
            origin = "/".join(parts[:3]) if len(parts) >= 3 else ""

    if origin not in ALLOWED_ORIGINS:
        print(f"[guard] elutasított origin: '{origin}' ip={client_ip(event)}")
        raise Rejected(403, "A kérés nem a webshop oldaláról érkezett.")


def check_body_size(event, max_bytes: int = MAX_BODY_BYTES) -> None:
    body = event.get("body") or ""
    if len(body) > max_bytes:
        raise Rejected(413, "A kérés túl nagy.")


def rate_limit(event, bucket: str, limit: int, window_seconds: int = 300) -> None:
    """
    IP-nkénti kérésszám-korlát, DynamoDB számlálóval.

    Egy ablakra egy sor jut IP-nként, TTL-lel — magától eltűnik, nincs
    takarítani való. Ha a tábla nem elérhető, ENGEDÜNK: egy adatbázishiba
    ne tegye használhatatlanná a webshopot.
    """
    if not _TABLE_NAME:
        return

    ip = client_ip(event)
    window_start = int(time.time()) // window_seconds * window_seconds
    key = f"{bucket}#{ip}#{window_start}"

    try:
        resp = _dynamodb.Table(_TABLE_NAME).update_item(
            Key={"rateKey": key},
            UpdateExpression="ADD hits :one SET expiresAt = if_not_exists(expiresAt, :exp)",
            ExpressionAttributeValues={":one": 1, ":exp": window_start + window_seconds * 2},
            ReturnValues="UPDATED_NEW",
        )
        hits = int(resp["Attributes"]["hits"])
    except Exception as exc:  # noqa: BLE001
        print(f"[guard] a rate limit nem ellenőrizhető ({bucket}): {exc}")
        return

    if hits > limit:
        print(f"[guard] rate limit túllépve: {bucket} ip={ip} hits={hits}/{limit}")
        raise Rejected(
            429,
            "Túl sok kérés érkezett rövid idő alatt. Kérjük, várj egy percet, és próbáld újra.",
        )


def protect(event, *, bucket: str, limit: int, window_seconds: int = 300, origin: bool = True,
            max_bytes: int = MAX_BODY_BYTES) -> None:
    """A szokásos ellenőrzések egyben. Rejected kivételt dob, ha elutasítjuk."""
    check_body_size(event, max_bytes)
    if origin:
        check_origin(event)
    rate_limit(event, bucket, limit, window_seconds)
