"""
Product and price catalog.

This is the single source of truth for prices. The frontend calls
GET /products to read these values. It never sends its own prices
to the backend. create_order always recomputes the total from here.

Edit prices here only. Redeploy get_products and create_order after
any change.
"""

PRODUCTS = {
    "lampa-nelkul": {
        "name": "Litofán – Lámpa nélkül",
        "base_price_huf": 9990,
        "sizes": {
            "15cm": {"label": "15 cm · Klasszikus", "delta_huf": 0},
            "20cm": {"label": "20 cm · Nagy", "delta_huf": 3000},
        },
    },
    "led-talpas": {
        "name": "Litofán – LED talppal",
        "base_price_huf": 14990,
        "sizes": {
            "15cm": {"label": "15 cm · Klasszikus", "delta_huf": 0},
            "20cm": {"label": "20 cm · Nagy", "delta_huf": 3000},
        },
    },
}

FREE_SHIPPING_THRESHOLD_HUF = 20000
FOXPOST_SHIPPING_FEE_HUF = 1490


def get_item_price(product_id: str, size_code: str) -> int:
    """Return the price in HUF for one unit. Raise ValueError on a bad id."""
    product = PRODUCTS.get(product_id)
    if not product:
        raise ValueError(f"Unknown product: {product_id}")
    size = product["sizes"].get(size_code)
    if not size:
        raise ValueError(f"Unknown size '{size_code}' for product '{product_id}'")
    return product["base_price_huf"] + size["delta_huf"]


def get_shipping_fee(subtotal_huf: int) -> int:
    """Foxpost fee, or 0 above the free-shipping threshold."""
    if subtotal_huf >= FREE_SHIPPING_THRESHOLD_HUF:
        return 0
    return FOXPOST_SHIPPING_FEE_HUF
