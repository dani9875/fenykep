import json

from ses_mail import send_contact_message
import guard

HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
}

REQUIRED_FIELDS = ["firstName", "email", "message"]


def _error(msg: str, code: int = 400):
    return {"statusCode": code, "headers": HEADERS, "body": json.dumps({"error": msg})}


def handler(event, context):
    # Kapcsolati űrlap: minden hívás egy e-mail, ezért ez a legszűkebb korlát.
    try:
        guard.protect(event, bucket="contact", limit=5, window_seconds=3600)
    except guard.Rejected as rejection:
        return rejection.response(HEADERS)

    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _error("Bad JSON")

    # Mézesbödön: a rejtett mezőt ember nem tölti ki, robot igen.
    # Sikert jelzünk vissza, hogy a spammer ne tudja, hogy lebukott.
    if body.get("website"):
        print(f"[contact] honeypot kifogta, ip={guard.client_ip(event)}")
        return {"statusCode": 200, "headers": HEADERS, "body": json.dumps({"ok": True})}

    for field in REQUIRED_FIELDS:
        if not body.get(field):
            return _error(f"Missing field: {field}")

    full_name = f"{body['firstName']} {body.get('lastName', '')}".strip()
    subject = body.get("subject") or "Kapcsolatfelvétel a weboldalról"

    # A levélbe minden mező escape-elve kerül (ses_mail.send_contact_message).
    try:
        send_contact_message(full_name, body["email"], body.get("phone", ""), subject, body["message"])
    except Exception as exc:  # noqa: BLE001
        return _error(f"Email küldési hiba: {exc}", code=502)

    return {"statusCode": 200, "headers": HEADERS, "body": json.dumps({"ok": True})}
