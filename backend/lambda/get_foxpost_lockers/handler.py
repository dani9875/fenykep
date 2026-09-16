"""
Serves the Foxpost locker list to the frontend map picker.

Foxpost publishes every automata's location in one public JSON file,
no merchant account needed:
  https://cdn.foxpost.hu/foxplus.json
(documented at https://foxpost.hu/uzleti-partnereknek/integracios-segedlet
 under "Csomagautomata lista")

That file is large and updates continuously, so this Lambda fetches it
at most once per CACHE_TTL_SECONDS and caches a trimmed copy in S3.
Every request reads the S3 cache, so the frontend never waits on
cdn.foxpost.hu directly and Foxpost's servers only see one request
per cache window.

Once you have a real Foxpost merchant contract, this Lambda does not
need to change — signing up only affects package hand-off (the
FoxWEB API), not this public location list.
"""

import json
import os
import time
import urllib.request
import boto3
from botocore.exceptions import ClientError

import guard

s3 = boto3.client("s3")
BUCKET = os.environ.get("CACHE_BUCKET", "litho-uploads")
CACHE_KEY = "cache/foxpost-lockers.json"
CACHE_TTL_SECONDS = 24 * 60 * 60
SOURCE_URL = "https://cdn.foxpost.hu/foxplus.json"

HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
}


def _trim(raw_locker: dict) -> dict:
    """Keep only the fields the map picker needs — the full feed carries
    depot/logistics data that is irrelevant to a customer."""
    return {
        "id": raw_locker["place_id"],
        "name": raw_locker["name"],
        "address": raw_locker["address"],
        "city": raw_locker["city"],
        "zip": raw_locker["zip"],
        "lat": raw_locker["geolat"],
        "lng": raw_locker["geolng"],
    }


def _fetch_and_cache() -> list[dict]:
    with urllib.request.urlopen(SOURCE_URL, timeout=15) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    trimmed = [_trim(x) for x in raw]
    body = json.dumps({"fetchedAt": int(time.time()), "lockers": trimmed})
    s3.put_object(Bucket=BUCKET, Key=CACHE_KEY, Body=body, ContentType="application/json")
    return trimmed


# Hiányzó cache-nek számít. Az AccessDenied azért van itt, mert az S3 egy
# nem létező kulcsra ezt adja vissza, ha a hívónak nincs ListBucket joga a
# bucketre — ilyenkor is a letöltés a helyes viselkedés, nem a hibázás.
# (A jogot az infra/terraform/iam.tf megadja; ez az öv a nadrágtartó mellé.)
_CACHE_MISS_CODES = ("NoSuchKey", "404", "AccessDenied", "403")


def _read_cache() -> list[dict] | None:
    try:
        obj = s3.get_object(Bucket=BUCKET, Key=CACHE_KEY)
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code in _CACHE_MISS_CODES:
            print(f"[foxpost] nincs használható cache ({code}), letöltés a forrásból")
            return None
        raise
    data = json.loads(obj["Body"].read().decode("utf-8"))
    if time.time() - data["fetchedAt"] > CACHE_TTL_SECONDS:
        return None
    return data["lockers"]


def handler(event, context):
    # A térkép mozgatása sok kérést szül, ezért tág a keret — de nem végtelen.
    try:
        guard.rate_limit(event, "foxpost", limit=200, window_seconds=300)
    except guard.Rejected as rejection:
        return rejection.response(HEADERS)

    # A cache olvasása is beletartozik: egy váratlan S3 hiba se nyers 500-at
    # adjon a hívónak, hanem olvasható üzenetet, amiből kiderül, mi a baj.
    try:
        lockers = _read_cache()
        if lockers is None:
            lockers = _fetch_and_cache()
    except Exception as exc:  # noqa: BLE001
        print(f"[foxpost] list unavailable: {type(exc).__name__}: {exc}")
        return {
            "statusCode": 502,
            "headers": HEADERS,
            "body": json.dumps({"error": f"Foxpost list unavailable: {exc}"}),
        }

    params = (event.get("queryStringParameters") or {})

    city_filter = params.get("city", "").strip().lower()
    if city_filter:
        lockers = [l for l in lockers if city_filter in l["city"].lower() or city_filter in l["address"].lower()]

    try:
        min_lat = float(params["minLat"]) if "minLat" in params else None
        max_lat = float(params["maxLat"]) if "maxLat" in params else None
        min_lng = float(params["minLng"]) if "minLng" in params else None
        max_lng = float(params["maxLng"]) if "maxLng" in params else None
    except ValueError:
        return {"statusCode": 400, "headers": HEADERS, "body": json.dumps({"error": "Bad bbox params"})}

    if None not in (min_lat, max_lat, min_lng, max_lng):
        lockers = [
            l for l in lockers
            if min_lat <= l["lat"] <= max_lat and min_lng <= l["lng"] <= max_lng
        ]

    # A bbox at country-wide zoom can still hold thousands of points —
    # cap what we ever send down in one response.
    lockers = lockers[:300]

    return {"statusCode": 200, "headers": HEADERS, "body": json.dumps({"lockers": lockers})}
