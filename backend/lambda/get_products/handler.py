import json

# products.py comes from the shared Lambda Layer. See infra/README.md
# for how to build and attach that layer.
from products import PRODUCTS, FREE_SHIPPING_THRESHOLD_HUF, FOXPOST_SHIPPING_FEE_HUF

HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
}


def handler(event, context):
    body = {
        "products": PRODUCTS,
        "freeShippingThresholdHuf": FREE_SHIPPING_THRESHOLD_HUF,
        "foxpostShippingFeeHuf": FOXPOST_SHIPPING_FEE_HUF,
    }
    return {"statusCode": 200, "headers": HEADERS, "body": json.dumps(body)}
