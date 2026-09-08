import json

from dynamo import get_order

HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
}


def handler(event, context):
    order_id = (event.get("pathParameters") or {}).get("orderId")
    if not order_id:
        return {"statusCode": 400, "headers": HEADERS, "body": json.dumps({"error": "Missing orderId"})}

    order = get_order(order_id)
    if not order:
        return {"statusCode": 404, "headers": HEADERS, "body": json.dumps({"error": "Not found"})}

    return {
        "statusCode": 200,
        "headers": HEADERS,
        "body": json.dumps(
            {
                "orderId": order["orderId"],
                "status": order["orderStatus"],
                "totalHuf": order["totalHuf"],
                "paymentMethod": order.get("paymentMethod", "barion"),
            }
        ),
    }
