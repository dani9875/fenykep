import json
import os
import re
import uuid
import boto3

s3 = boto3.client("s3")
BUCKET = os.environ["UPLOADS_BUCKET"]

HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
}

ALLOWED_TYPES = {"image/jpeg", "image/png"}


def _safe_name(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    return name[:100] or "photo"


def handler(event, context):
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

    key = f"uploads/{uuid.uuid4()}-{file_name}"

    upload_url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=300,
    )

    return {
        "statusCode": 200,
        "headers": HEADERS,
        "body": json.dumps({"uploadUrl": upload_url, "key": key}),
    }
