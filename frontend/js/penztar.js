function formatHuf(n) {
  return n.toLocaleString("hu-HU") + " Ft";
}

const FREE_SHIPPING_THRESHOLD = 20000; // keep in sync with backend/lambda/common/products.py
const FOXPOST_FEE = 1490;

const PRODUCT_IMAGES = {
  "lampa-nelkul": "assets/products/lampa-nelkul.jpg",
  "led-talpas": "assets/products/led-talpas.jpg",
};

function renderReview() {
  const items = Cart.getItems();
  const itemsEl = document.getElementById("review-items");
  const totalsEl = document.getElementById("review-totals");

  if (items.length === 0) {
    window.location.href = "kosar.html";
    return;
  }

  itemsEl.innerHTML = items
    .map(
      (i) => `
      <div class="litho-ri">
        <span class="litho-ri__thumb"><img src="${PRODUCT_IMAGES[i.productId] || ""}" alt="${i.productName}"></span>
        <div>
          <span class="litho-ri__name">${i.productName}</span>
          <span class="litho-ri__meta">${i.size} · ${i.qty} db</span>
        </div>
        <div class="litho-ri__price">${formatHuf(i.unitPrice * i.qty)}</div>
      </div>`
    )
    .join("");

  const subtotal = Cart.subtotal();
  const shippingFee = subtotal >= FREE_SHIPPING_THRESHOLD ? 0 : FOXPOST_FEE;
  const total = subtotal + shippingFee;

  totalsEl.innerHTML = `
    <div class="litho-rt__row">
      <span class="litho-rt__label">Részösszeg</span>
      <span class="litho-rt__value">${formatHuf(subtotal)}</span>
    </div>
    <div class="litho-rt__row">
      <span class="litho-rt__label">Szállítás (Foxpost)</span>
      <span class="litho-rt__value">${shippingFee === 0 ? "Ingyenes" : formatHuf(shippingFee)}</span>
    </div>
    <div class="litho-rt__divider"></div>
    <div class="litho-rt__row litho-rt__row--total">
      <span class="litho-rt__label">Összesen</span>
      <span class="litho-rt__value litho-rt__total">${formatHuf(total)}</span>
    </div>`;
}

document.getElementById("checkout-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errorEl = document.getElementById("checkout-error");
  errorEl.style.display = "none";

  const items = Cart.getItems();
  if (items.length === 0) return;

  const lockerId = document.getElementById("f-locker-id").value;
  if (!lockerId) {
    errorEl.textContent = "Válassz egy Foxpost csomagautomatát a térképen.";
    errorEl.style.display = "block";
    return;
  }

  const shippingMethod = document.querySelector('input[name="shipping_method"]:checked').value;

  const paymentMethod = document.querySelector('input[name="payment_method"]:checked').value;

  const payload = {
    customer: {
      name: document.getElementById("f-name").value.trim(),
      email: document.getElementById("f-email").value.trim(),
      phone: document.getElementById("f-phone").value.trim(),
      address: document.getElementById("f-address").value.trim(),
      city: document.getElementById("f-city").value.trim(),
      zip: document.getElementById("f-zip").value.trim(),
      notes: document.getElementById("f-notes").value.trim(),
    },
    shipping: {
      method: shippingMethod,
      lockerId: lockerId,
      lockerName: document.getElementById("f-locker-name").value.trim(),
    },
    consents: {
      aszf: document.getElementById("f-aszf").checked,
      privacy: document.getElementById("f-privacy").checked,
    },
    paymentMethod,
    items: items.map((i) => ({
      productId: i.productId,
      productName: i.productName,
      size: i.size,
      qty: i.qty,
      photoKey: i.photoKey,
    })),
  };

  const btn = e.target.querySelector('button[type="submit"]');
  btn.disabled = true;
  btn.textContent = "Feldolgozás…";

  try {
    const { gatewayUrl } = await Api.createOrder(payload);
    Cart.clear();
    window.location.href = gatewayUrl;
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.style.display = "block";
    btn.disabled = false;
    btn.textContent = "Rendelés leadása";
  }
});

document.addEventListener("DOMContentLoaded", renderReview);

document.querySelectorAll('input[name="payment_method"]').forEach((r) => {
  r.addEventListener("change", () => {
    const note = document.getElementById("payment-method-note");
    note.textContent =
      r.value === "transfer"
        ? 'A "Rendelés leadása" után emailben küldjük az utaláshoz szükséges adatokat.'
        : 'A "Rendelés leadása" gomb átirányít a biztonságos Barion fizetőoldalra.';
  });
});
