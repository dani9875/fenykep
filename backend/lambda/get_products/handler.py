import json

# products.py comes from the shared Lambda Layer. See infra/README.md
# for how to build and attach that layer.
from products import (
    COD_FEE_HUF,
    FOXPOST_SHIPPING_FEE_HUF,
    FREE_SHIPPING_THRESHOLD_HUF,
    HOME_DELIVERY_FEE_HUF,
    PAYMENT_METHODS,
    PRODUCTS,
    SHIPPING_METHODS,
)

HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
}


def handler(event, context):
    body = {
        "products": PRODUCTS,
        "freeShippingThresholdHuf": FREE_SHIPPING_THRESHOLD_HUF,
        "foxpostShippingFeeHuf": FOXPOST_SHIPPING_FEE_HUF,
        "homeDeliveryFeeHuf": HOME_DELIVERY_FEE_HUF,
        "codFeeHuf": COD_FEE_HUF,
        "shippingMethods": SHIPPING_METHODS,
        # A frontend ebből tudja, melyik fizetési mód melyik szállításnál
        # választható — a szabály egy helyen, a katalógusban él.
        "paymentMethods": {k: {"label": v["label"], "shipping": list(v["shipping"])} for k, v in PAYMENT_METHODS.items()},
    }
    return {"statusCode": 200, "headers": HEADERS, "body": json.dumps(body)}
