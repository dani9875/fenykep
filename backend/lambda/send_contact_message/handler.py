import json

from ses_mail import _send, ADMIN_EMAIL

HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
}

REQUIRED_FIELDS = ["firstName", "email", "message"]


def _error(msg: str, code: int = 400):
    return {"statusCode": code, "headers": HEADERS, "body": json.dumps({"error": msg})}


def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _error("Bad JSON")

    for field in REQUIRED_FIELDS:
        if not body.get(field):
            return _error(f"Missing field: {field}")

    full_name = f"{body['firstName']} {body.get('lastName', '')}".strip()
    subject = body.get("subject") or "Kapcsolatfelvétel a weboldalról"

    html = f"""
    <h2>Új üzenet a kapcsolat űrlapról</h2>
    <p><strong>Név:</strong> {full_name}</p>
    <p><strong>E-mail:</strong> {body['email']}</p>
    <p><strong>Telefon:</strong> {body.get('phone', '—')}</p>
    <p><strong>Tárgy:</strong> {subject}</p>
    <p><strong>Üzenet:</strong></p>
    <p>{body['message']}</p>
    """

    try:
        _send(ADMIN_EMAIL, f"Kapcsolat űrlap: {subject}", html, reply_to=body["email"])
    except Exception as exc:  # noqa: BLE001
        return _error(f"Email küldési hiba: {exc}", code=502)

    return {"statusCode": 200, "headers": HEADERS, "body": json.dumps({"ok": True})}
