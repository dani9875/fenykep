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


class StatusAlreadySet(Exception):
    """A rendelés már ebben (vagy egy későbbi) állapotban van — nincs teendő."""


def table():
    return _dynamodb.Table(_TABLE_NAME)


def put_order(order: dict) -> None:
    now = int(time.time())
    order.setdefault("createdAt", now)
    order["updatedAt"] = now
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


def update_order_status(order_id: str, status: str, extra: dict | None = None) -> None:
    """Státusz felülírása. Ahol a duplikált feldolgozás számít, használd a
    transition_order_status-t helyette."""
    names = {"#s": "orderStatus"}
    values = {":s": status, ":t": int(time.time())}
    sets = ["#s = :s", "updatedAt = :t"]
    for i, (key, value) in enumerate((extra or {}).items()):
        names[f"#e{i}"] = key
        values[f":e{i}"] = value
        sets.append(f"#e{i} = :e{i}")
    table().update_item(
        Key={"orderId": order_id},
        UpdateExpression="SET " + ", ".join(sets),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def set_order_attributes(order_id: str, attrs: dict) -> None:
    """Mezők írása a rendelésre, a státusz érintése nélkül.

    Azért nem az update_order_status-t használjuk erre, mert az a státuszt is
    felülírná — egy párhuzamos feldolgozás közben ez visszaírhatna egy elavult
    értéket.
    """
    if not attrs:
        return
    names, values, sets = {}, {":t": int(time.time())}, ["updatedAt = :t"]
    for i, (key, value) in enumerate(attrs.items()):
        names[f"#a{i}"] = key
        values[f":a{i}"] = value
        sets.append(f"#a{i} = :a{i}")
    table().update_item(
        Key={"orderId": order_id},
        UpdateExpression="SET " + ", ".join(sets),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def transition_order_status(order_id: str, new_status: str, from_statuses: list[str], extra: dict | None = None) -> None:
    """
    Státuszváltás, ami csak akkor megy végbe, ha a rendelés még a megadott
    állapotok valamelyikében van.

    Ez adja az idempotenciát a Barion callbackhez: a Barion ugyanazt a
    hívást ötször is elküldheti, és két hívás párhuzamosan is futhat. A
    feltétel a DynamoDB oldalán dől el, így a "fizetve" ág — és a
    visszaigazoló email — pontosan egyszer fut le.

    StatusAlreadySet-et dob, ha a feltétel nem teljesül.
    """
    names = {"#s": "orderStatus"}
    values = {":s": new_status, ":t": int(time.time())}
    sets = ["#s = :s", "updatedAt = :t"]
    for i, (key, value) in enumerate((extra or {}).items()):
        names[f"#e{i}"] = key
        values[f":e{i}"] = value
        sets.append(f"#e{i} = :e{i}")

    allowed = {}
    for i, status in enumerate(from_statuses):
        allowed[f":f{i}"] = status
    values.update(allowed)

    try:
        table().update_item(
            Key={"orderId": order_id},
            UpdateExpression="SET " + ", ".join(sets),
            ConditionExpression="#s IN (" + ", ".join(allowed.keys()) + ")",
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )
    except _dynamodb.meta.client.exceptions.ConditionalCheckFailedException as exc:
        raise StatusAlreadySet(f"{order_id} nincs a(z) {from_statuses} állapotok egyikében sem") from exc
