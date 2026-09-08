import json

from dynamo import get_order, get_order_by_payment_id, update_order_status
import barion
from ses_mail import send_customer_confirmation, send_admin_notification

HEADERS = {"Content-Type": "application/json"}


def handler(event, context):
    """
    Barion calls this URL (the CallbackUrl) whenever a payment's state
    changes. It sends the paymentId as a query parameter. Always return
    200 quickly, even on a business-logic rejection, or Barion retries.
    """
    params = event.get("queryStringParameters") or {}
    payment_id = params.get("paymentId")
    if not payment_id:
        return {"statusCode": 400, "headers": HEADERS, "body": "Missing paymentId"}

    order = get_order_by_payment_id(payment_id)
    if not order:
        return {"statusCode": 200, "headers": HEADERS, "body": "Unknown order, ignored"}

    # Already handled — Barion can call the same callback more than once.
    if order["orderStatus"] in ("paid", "failed"):
        return {"statusCode": 200, "headers": HEADERS, "body": "Already processed"}

    state = barion.get_payment_state(payment_id)
    status = state.get("Status")

    if status == "Succeeded":
        update_order_status(order["orderId"], "paid")
        order["orderStatus"] = "paid"
        send_customer_confirmation(order)
        send_admin_notification(order)
    elif status in ("Failed", "Expired", "Canceled"):
        update_order_status(order["orderId"], "failed")

    return {"statusCode": 200, "headers": HEADERS, "body": "OK"}
