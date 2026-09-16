import json
import os
import re
import uuid
import boto3
from botocore.config import Config

import guard

BUCKET = os.environ["UPLOADS_BUCKET"]
REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "eu-central-1"

# A régiós végpontot kézzel adjuk meg. Alapbeállítással a presigned URL a
# globális `<bucket>.s3.amazonaws.com` címre szólhat, amit egy nem
# us-east-1-es bucketnél az S3 átirányítással válaszol meg — az
# átirányításon viszont nincsenek CORS fejlécek, így a böngésző a
# feltöltést "No 'Access-Control-Allow-Origin' header" hibával eldobja.
# Régiós címmel (`<bucket>.s3.eu-central-1.amazonaws.com`) nincs redirect.
# Az s3v4 is kötelező: Frankfurt nem fogadja el a régi aláírást.
s3 = boto3.client(
    "s3",
    region_name=REGION,
    endpoint_url=f"https://s3.{REGION}.amazonaws.com",
    config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
)

HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
}

ALLOWED_TYPES = {"image/jpeg", "image/png"}

# Egy telefonfotó 2-8 MB. A felső korlát azt akadályozza meg, hogy valaki
# a bucketünket használja tárhelynek; az alsó a hibás/üres feltöltést fogja meg.
MIN_UPLOAD_BYTES = 1024
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def _safe_name(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    return name[:100] or "photo"


def handler(event, context):
    try:
        guard.protect(event, bucket="uploads", limit=20, window_seconds=300)
    except guard.Rejected as rejection:
        return rejection.response(HEADERS)

    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return {"statusCode": 400, "headers": HEADERS, "body": json.dumps({"error": "Bad JSON"})}

    file_name = _safe_name(body.get("fileName", "photo.jpg"))
    content_type = body.get("contentType", "")

    if content_type not in ALLOWED_TYPES:
        return {
            "statusCode": 400,
            "headers": HEADERS,
            "body": json.dumps({"error": "Only JPG or PNG is allowed."}),
        }

    # A méretet aláírjuk: a feltöltés pontosan ekkora lehet, se több.
    try:
        file_size = int(body.get("fileSize", 0))
    except (TypeError, ValueError):
        file_size = 0
    if file_size and not (MIN_UPLOAD_BYTES <= file_size <= MAX_UPLOAD_BYTES):
        return {
            "statusCode": 400,
            "headers": HEADERS,
            "body": json.dumps({"error": "A fotó legfeljebb 25 MB lehet."}),
        }

    key = f"uploads/{uuid.uuid4()}-{file_name}"

    params = {"Bucket": BUCKET, "Key": key, "ContentType": content_type}
    if file_size:
        params["ContentLength"] = file_size

    upload_url = s3.generate_presigned_url("put_object", Params=params, ExpiresIn=300)

    return {
        "statusCode": 200,
        "headers": HEADERS,
        "body": json.dumps({"uploadUrl": upload_url, "key": key}),
    }
