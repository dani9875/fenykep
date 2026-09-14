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

  const rows = items.map(renderRow).join("");
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
        <a href="penztar.html" class="litho-btn-solid litho-totals__cta">Tovább a pénztárhoz</a>
      </div>
    </div>`;

  bindRowActions(root);
}

function renderRow(item) {
  const preview = PhotoStore.get(item.photoKey);
  const thumb = preview || PRODUCT_IMAGES[item.productId] || "";
  const fileName = item.photoFileName || "Feltöltött fotó";

  // The thumbnail already shows the uploaded photo, so it doubles as the
  // zoom target. Without a stored preview there is nothing to enlarge, so
  // it stays a plain image rather than pretending to be clickable.
  const thumbCell = preview
    ? `<button type="button" class="litho-ci__thumb litho-ci__thumb--zoom" data-zoom="${escapeAttr(item.photoKey)}"
               aria-label="Fénykép nagyítása: ${escapeAttr(fileName)}">
         <img class="litho-ci__thumb-img" src="${escapeAttr(preview)}" alt="">
         <span class="litho-ci__zoom-badge" aria-hidden="true">
           <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
             <circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5M11 8.5v5M8.5 11h5"/>
           </svg>
         </span>
       </button>`
    : `<span class="litho-ci__thumb"><img class="litho-ci__thumb-img" src="${escapeAttr(thumb)}" alt="${escapeAttr(item.productName)}"></span>`;

  return `
    <div class="litho-ci cart_item">
      ${thumbCell}
      <div class="litho-ci__info">
        <span class="litho-ci__name">${escapeHtml(item.productName)}</span>
        <span class="litho-ci__meta">
          <span class="litho-ci__size">${escapeHtml(item.size)}</span>
          <span class="litho-ci__file" title="${escapeAttr(fileName)}">${escapeHtml(fileName)}</span>
        </span>
        ${preview ? "" : `<span class="litho-ci__no-preview">Az előnézet ezen a gépen nem érhető el — a feltöltött fotó rendben megvan.</span>`}
      </div>
      <div class="litho-qty" role="group" aria-label="Példányszám">
        <button type="button" class="litho-qty__btn" data-qty-step="-1" data-id="${item.cartItemId}"
                aria-label="Eggyel kevesebb" ${item.qty <= 1 ? "disabled" : ""}>−</button>
        <input class="litho-qty__input" type="number" inputmode="numeric" min="1" max="99"
               value="${item.qty}" data-qty-input data-id="${item.cartItemId}" aria-label="Példányszám">
        <button type="button" class="litho-qty__btn" data-qty-step="1" data-id="${item.cartItemId}"
                aria-label="Eggyel több" ${item.qty >= 99 ? "disabled" : ""}>+</button>
      </div>
      <div class="litho-ci__price">
        ${formatHuf(item.unitPrice * item.qty)}
        ${item.qty > 1 ? `<small class="litho-ci__unit">${formatHuf(item.unitPrice)} / db</small>` : ""}
      </div>
      <button type="button" class="litho-ci__del-btn" data-id="${item.cartItemId}" aria-label="Eltávolítás a kosárból">✕</button>
    </div>`;
}

function bindRowActions(root) {
  const refresh = () => {
    renderCartPage();
    renderCartBadge();
  };

  root.querySelectorAll(".litho-ci__del-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      Cart.removeItem(btn.dataset.id);
      refresh();
    });
  });

  root.querySelectorAll("[data-qty-step]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const input = root.querySelector(`[data-qty-input][data-id="${btn.dataset.id}"]`);
      Cart.setQty(btn.dataset.id, parseInt(input.value, 10) + parseInt(btn.dataset.qtyStep, 10));
      refresh();
    });
  });

  root.querySelectorAll("[data-qty-input]").forEach((input) => {
    // Re-render on change (not input) so typing "12" isn't clamped at "1".
    input.addEventListener("change", () => {
      Cart.setQty(input.dataset.id, parseInt(input.value, 10));
      refresh();
    });
  });

  root.querySelectorAll("[data-zoom]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const src = PhotoStore.get(btn.dataset.zoom);
      if (src) openLightbox(src, btn.getAttribute("aria-label"));
    });
  });
}

/* ── Lightbox ─────────────────────────────────────────────────────── */

function openLightbox(src, alt) {
  let box = document.getElementById("litho-lightbox");
  if (!box) {
    box = document.createElement("div");
    box.id = "litho-lightbox";
    box.className = "litho-lightbox";
    box.innerHTML = `
      <button type="button" class="litho-lightbox__close" aria-label="Bezárás">✕</button>
      <img alt="">`;
    document.body.appendChild(box);

    // Clicking the backdrop closes; clicking the photo itself must not.
    box.addEventListener("click", (e) => {
      if (e.target.tagName !== "IMG") closeLightbox();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeLightbox();
    });
  }

  const img = box.querySelector("img");
  img.src = src;
  img.alt = alt || "";
  box.classList.add("active");
  document.body.classList.add("litho-noscroll");
  box.querySelector(".litho-lightbox__close").focus();
}

function closeLightbox() {
  const box = document.getElementById("litho-lightbox");
  if (!box) return;
  box.classList.remove("active");
  document.body.classList.remove("litho-noscroll");
}

/* ── Escaping ─────────────────────────────────────────────────────────
   File names come from the visitor's own disk and land straight in this
   markup, so they get escaped rather than trusted. */

function escapeHtml(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

const escapeAttr = escapeHtml;

document.addEventListener("DOMContentLoaded", renderCartPage);
