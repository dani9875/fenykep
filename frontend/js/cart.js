/**
 * Cart storage.
 *
 * The cart lives in one cookie, not localStorage. A cookie survives
 * the visitor leaving the site and coming back, same as localStorage,
 * but the site only needs this one cookie and it is strictly
 * necessary for the checkout to work. That means no cookie-consent
 * banner is required for it under GDPR — just mention it in the
 * privacy policy.
 */

const CART_COOKIE = "litho_cart";
const CART_MAX_AGE_DAYS = 30;

function readCart() {
  const match = document.cookie.match(new RegExp("(?:^|; )" + CART_COOKIE + "=([^;]*)"));
  if (!match) return [];
  try {
    return JSON.parse(decodeURIComponent(match[1]));
  } catch (e) {
    return [];
  }
}

function writeCart(items) {
  const maxAge = CART_MAX_AGE_DAYS * 24 * 60 * 60;
  document.cookie =
    CART_COOKIE + "=" + encodeURIComponent(JSON.stringify(items)) +
    "; path=/; max-age=" + maxAge + "; SameSite=Lax";
}

const Cart = {
  getItems() {
    return readCart();
  },

  addItem(item) {
    const items = readCart();
    item.cartItemId = crypto.randomUUID();
    item.qty = item.qty || 1;
    items.push(item);
    writeCart(items);
    return items;
  },

  removeItem(cartItemId) {
    const items = readCart().filter((i) => i.cartItemId !== cartItemId);
    writeCart(items);
    return items;
  },

  clear() {
    writeCart([]);
  },

  count() {
    return readCart().reduce((sum, i) => sum + i.qty, 0);
  },

  subtotal() {
    return readCart().reduce((sum, i) => sum + i.unitPrice * i.qty, 0);
  },
};

// Update every cart-count badge on the page (header icon).
function renderCartBadge() {
  document.querySelectorAll(".cart-count").forEach((el) => {
    el.textContent = Cart.count();
  });
}
document.addEventListener("DOMContentLoaded", renderCartBadge);
