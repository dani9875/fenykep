function formatHuf(n) {
  return n.toLocaleString("hu-HU") + " Ft";
}

const PRODUCT_IMAGES = {
  "lampa-nelkul": "assets/products/lampa-nelkul.jpg",
  "led-talpas": "assets/products/led-talpas.jpg",
};

function renderCartPage() {
  const root = document.getElementById("cart-root");
  const items = Cart.getItems();

  if (items.length === 0) {
    root.innerHTML = `
      <div class="litho-empty-cart">
        <div class="litho-empty-cart__icon">
          <svg viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect x="16" y="10" width="48" height="44" rx="5" stroke="currentColor" stroke-width="2.2" fill="none"/>
            <rect x="24" y="18" width="32" height="28" rx="3" stroke="currentColor" stroke-width="1.5" stroke-dasharray="3 2.5" fill="none" opacity="0.45"/>
            <text x="40" y="37" text-anchor="middle" font-family="Georgia, serif" font-size="14" fill="currentColor" opacity="0.35">?</text>
            <line x1="40" y1="54" x2="40" y2="66" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>
            <ellipse cx="40" cy="67" rx="10" ry="3" stroke="currentColor" stroke-width="1.8" fill="none"/>
            <line x1="28" y1="50" x2="23" y2="44" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" opacity="0.3"/>
            <line x1="52" y1="50" x2="57" y2="44" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" opacity="0.3"/>
            <line x1="40" y1="48" x2="40" y2="41" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" opacity="0.3"/>
          </svg>
        </div>
        <h2 class="litho-empty-cart__title">A kosár üres</h2>
        <p class="litho-empty-cart__sub">Még nem választottál lithofán képet.<br>Töltsd fel a kedvenc fotódat, és varázsolj belőle egyedi emléket.</p>
        <a href="index.html" class="litho-empty-cart__btn">Termékek megtekintése</a>
      </div>`;
    return;
  }

  const rows = items
    .map((item) => {
      const img = PRODUCT_IMAGES[item.productId] || "";
      return `
      <div class="litho-ci cart_item">
        <span class="litho-ci__thumb"><img class="litho-ci__thumb-img" src="${img}" alt="${item.productName}"></span>
        <div class="litho-ci__info">
          <span class="litho-ci__name">${item.productName}</span>
          <span class="litho-ci__size">${item.size}</span>
        </div>
        <span class="litho-ci__photo-pill"><span>${item.photoFileName || "Feltöltött fotó"}</span></span>
        <div class="litho-ci__price">${formatHuf(item.unitPrice * item.qty)}</div>
        <button class="litho-ci__del-btn" data-id="${item.cartItemId}" aria-label="Eltávolítás">✕</button>
      </div>`;
    })
    .join("");

  const subtotal = Cart.subtotal();

  root.innerHTML = `
    <div class="litho-cart-wrap">
      <div class="litho-cart-items">${rows}</div>
      <div class="litho-totals">
        <h2 class="litho-totals__title">Összesítő</h2>
        <div class="litho-totals__row litho-totals__row--sub">
          <span class="litho-totals__label">Részösszeg</span>
          <span class="litho-totals__value">${formatHuf(subtotal)}</span>
        </div>
        <div class="litho-totals__divider"></div>
        <p class="litho-totals__note">A szállítási díj a következő lépésben kerül meghatározásra.</p>
        <a href="penztar.html" class="single_add_to_cart_button" style="display:block; text-align:center; margin-top:1rem;">Tovább a pénztárhoz</a>
      </div>
    </div>`;

  root.querySelectorAll(".litho-ci__del-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      Cart.removeItem(btn.dataset.id);
      renderCartPage();
      renderCartBadge();
    });
  });
}

document.addEventListener("DOMContentLoaded", renderCartPage);
