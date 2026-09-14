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
HOME_DELIVERY_FEE_HUF = 1990

# Utánvét kezelési költség. Csak házhozszállításnál választható
# (csomagautomata nem fogad készpénzt).
COD_FEE_HUF = 0

# Egy tételből ennyinél többet nem lehet kosárba tenni. Az elgépelt vagy
# szándékosan felnagyított darabszám ellen véd, mielőtt Barion felé
# indulna a fizetés.
MAX_QTY_PER_ITEM = 20
MAX_ITEMS_PER_ORDER = 20

SHIPPING_METHODS = {
    "foxpost": {"label": "Foxpost csomagautomata", "fee_huf": FOXPOST_SHIPPING_FEE_HUF},
    "home": {"label": "Házhozszállítás (futár)", "fee_huf": HOME_DELIVERY_FEE_HUF},
}

# Melyik fizetési mód melyik szállítási móddal használható.
PAYMENT_METHODS = {
    "barion": {"label": "Bankkártya (Barion)", "shipping": ("foxpost", "home")},
    "transfer": {"label": "Előre utalás", "shipping": ("foxpost", "home")},
    "cod": {"label": "Utánvét", "shipping": ("home",)},
}


def get_item_price(product_id: str, size_code: str) -> int:
    """Return the price in HUF for one unit. Raise ValueError on a bad id."""
    product = PRODUCTS.get(product_id)
    if not product:
        raise ValueError(f"Unknown product: {product_id}")
    size = product["sizes"].get(size_code)
    if not size:
        raise ValueError(f"Unknown size '{size_code}' for product '{product_id}'")
    return product["base_price_huf"] + size["delta_huf"]


def get_shipping_fee(subtotal_huf: int, method: str = "foxpost") -> int:
    """Shipping fee for the chosen method, or 0 above the free-shipping threshold."""
    if subtotal_huf >= FREE_SHIPPING_THRESHOLD_HUF:
        return 0
    entry = SHIPPING_METHODS.get(method)
    if not entry:
        raise ValueError(f"Unknown shipping method: {method}")
    return entry["fee_huf"]


def get_cod_fee(payment_method: str) -> int:
    """Cash-on-delivery handling fee, 0 for every other payment method."""
    return COD_FEE_HUF if payment_method == "cod" else 0


def is_payment_allowed(payment_method: str, shipping_method: str) -> bool:
    entry = PAYMENT_METHODS.get(payment_method)
    if not entry:
        return False
    return shipping_method in entry["shipping"]
