"""
DynamoDB access for the litho-orders table.

Table schema (create this table by hand, see infra/README.md):
  Partition key: orderId (String)
  GSI: paymentId-index, partition key paymentId (String)
"""

import os
import time
import boto3
from boto3.dynamodb.conditions import Key

_TABLE_NAME = os.environ.get("ORDERS_TABLE", "litho-orders")
_dynamodb = boto3.resource("dynamodb")


def table():
    return _dynamodb.Table(_TABLE_NAME)


def put_order(order: dict) -> None:
    order["updatedAt"] = int(time.time())
    table().put_item(Item=order)


def get_order(order_id: str) -> dict | None:
    resp = table().get_item(Key={"orderId": order_id})
    return resp.get("Item")


def get_order_by_payment_id(payment_id: str) -> dict | None:
    resp = table().query(
        IndexName="paymentId-index",
        KeyConditionExpression=Key("paymentId").eq(payment_id),
    )
    items = resp.get("Items", [])
    return items[0] if items else None


def update_order_status(order_id: str, status: str) -> None:
    table().update_item(
        Key={"orderId": order_id},
        UpdateExpression="SET orderStatus = :s, updatedAt = :t",
        ExpressionAttributeValues={":s": status, ":t": int(time.time())},
    )
