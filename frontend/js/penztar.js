/**
 * Pénztár.
 *
 * Szállítás: Foxpost csomagautomata vagy házhozszállítás. Házhozszállításnál
 * a szállítási cím alapból megegyezik a számlázásival — a pipa kivételekor
 * jelennek meg a külön szállítási mezők.
 *
 * Fizetés: bankkártya (Barion), előre utalás, illetve utánvét — utóbbi csak
 * házhozszállításnál, mert a csomagautomata nem fogad készpénzt. Ugyanezt a
 * szabályt a backend is ellenőrzi; itt csak azért van, hogy a vásárló ne
 * fusson bele egy hibaüzenetbe.
 *
 * A kosarat itt SOHA nem ürítjük. Egy megszakadt vagy sikertelen bankkártyás
 * fizetés után a vásárló visszakerül a pénztárba a kosarával együtt; a
 * kosár a köszönőoldalon ürül, amikor a rendelés ténylegesen létrejött.
 */

function formatHuf(n) {
  return n.toLocaleString("hu-HU") + " Ft";
}

// Tartalék értékek, ha a GET /products nem érhető el. A mérvadó forrás
// a backend katalógusa (backend/lambda/common/products.py).
const Pricing = {
  freeShippingThreshold: 20000,
  fees: { foxpost: 1490, home: 1990 },
  codFee: 0,
  labels: { foxpost: "Foxpost csomagautomata", home: "Házhozszállítás (futár)" },
};

// Az összegzőben rövid név fér el; a teljes megnevezés a katalógusból jön.
const SHORT_SHIPPING_LABELS = { foxpost: "Foxpost", home: "Házhozszállítás" };

const PRODUCT_IMAGES = {
  "lampa-nelkul": "assets/products/lampa-nelkul.jpg",
  "led-talpas": "assets/products/led-talpas.jpg",
};

function escapeHtml(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function selectedShippingMethod() {
  const el = document.querySelector('input[name="shipping_method"]:checked');
  return el ? el.value : "foxpost";
}

function selectedPaymentMethod() {
  const el = document.querySelector('input[name="payment_method"]:checked');
  return el ? el.value : "barion";
}

function sameAsBilling() {
  const el = document.getElementById("f-same-address");
  return !el || el.checked;
}

/* ---------- összegzés ---------- */

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
        <span class="litho-ri__thumb"><img src="${escapeHtml(PhotoStore.get(i.photoKey) || PRODUCT_IMAGES[i.productId] || "")}" alt="${escapeHtml(i.productName)}"></span>
        <div>
          <span class="litho-ri__name">${escapeHtml(i.productName)}</span>
          <span class="litho-ri__meta">${escapeHtml(i.size)} · ${i.qty} db</span>
        </div>
        <div class="litho-ri__price">${formatHuf(i.unitPrice * i.qty)}</div>
      </div>`
    )
    .join("");

  const method = selectedShippingMethod();
  const payment = selectedPaymentMethod();
  const subtotal = Cart.subtotal();
  const shippingFee = subtotal >= Pricing.freeShippingThreshold ? 0 : Pricing.fees[method] || 0;
  const codFee = payment === "cod" ? Pricing.codFee : 0;
  const total = subtotal + shippingFee + codFee;

  const codRow = codFee
    ? `<div class="litho-rt__row">
         <span class="litho-rt__label">Utánvét kezelési díj</span>
         <span class="litho-rt__value">${formatHuf(codFee)}</span>
       </div>`
    : "";

  totalsEl.innerHTML = `
    <div class="litho-rt__row">
      <span class="litho-rt__label">Részösszeg</span>
      <span class="litho-rt__value">${formatHuf(subtotal)}</span>
    </div>
    <div class="litho-rt__row">
      <span class="litho-rt__label">Szállítás (${escapeHtml(SHORT_SHIPPING_LABELS[method] || method)})</span>
      <span class="litho-rt__value">${shippingFee === 0 ? "Ingyenes" : formatHuf(shippingFee)}</span>
    </div>
    ${codRow}
    <div class="litho-rt__divider"></div>
    <div class="litho-rt__row litho-rt__row--total">
      <span class="litho-rt__label">Összesen</span>
      <span class="litho-rt__value litho-rt__total">${formatHuf(total)}</span>
    </div>`;
}

/* ---------- szállítási mód váltása ---------- */

function applyShippingMethod() {
  const method = selectedShippingMethod();
  const foxpostBlock = document.getElementById("shipping-foxpost");
  const homeBlock = document.getElementById("shipping-home");

  foxpostBlock.hidden = method !== "foxpost";
  homeBlock.hidden = method !== "home";

  if (method === "foxpost" && typeof FoxpostPicker !== "undefined") {
    // A Leaflet rossz méretet számol, ha a térkép rejtve volt, amikor
    // felépült — újra meg kell mérnie magát, amint láthatóvá válik.
    FoxpostPicker.refresh();
  }

  applyShippingAddressFields();
  applyPaymentAvailability();
  renderReview();
}

function applyShippingAddressFields() {
  const method = selectedShippingMethod();
  const fields = document.getElementById("shipping-address-fields");
  const preview = document.getElementById("shipping-address-preview");
  const separate = method === "home" && !sameAsBilling();

  fields.hidden = !separate;
  // A rejtett mezők tiltva vannak, különben a böngésző kötelezőként
  // kérné őket, miközben nem is látszanak.
  fields.querySelectorAll("input").forEach((input) => {
    input.disabled = !separate;
    if (!separate) {
      input.classList.remove("is-invalid");
      if (window.FormErrors) FormErrors.clear(input);
    }
  });

  if (method === "home" && !separate) {
    const billing = readBillingAddress();
    preview.innerHTML = billing.address
      ? `<strong>Szállítási cím:</strong><br>${escapeHtml(billing.name)}<br>${escapeHtml(billing.zip)} ${escapeHtml(billing.city)}, ${escapeHtml(billing.address)}`
      : "A számlázási adatok kitöltése után itt jelenik meg a szállítási cím.";
    preview.hidden = false;
  } else {
    preview.hidden = true;
  }
}

function readBillingAddress() {
  return {
    name: document.getElementById("f-name").value.trim(),
    address: document.getElementById("f-address").value.trim(),
    city: document.getElementById("f-city").value.trim(),
    zip: document.getElementById("f-zip").value.trim(),
  };
}

/* ---------- fizetési módok elérhetősége ---------- */

function applyPaymentAvailability() {
  const method = selectedShippingMethod();
  const codOption = document.getElementById("pay-cod-opt");
  const codRadio = codOption.querySelector("input");
  const codAllowed = method === "home";

  codRadio.disabled = !codAllowed;
  codOption.classList.toggle("litho-size-opt--disabled", !codAllowed);
  codOption.title = codAllowed ? "" : "A Foxpost csomagautomaták nem fogadnak készpénzt.";
  codOption.querySelector("small").textContent = codAllowed
    ? "Fizetés a futárnál"
    : "Csak házhozszállításnál";

  if (!codAllowed && codRadio.checked) {
    document.querySelector('input[name="payment_method"][value="barion"]').checked = true;
  }
  applyPaymentNote();
}

/** A szállítási opciók díja a katalógusból jön, nem a HTML-ből. */
function applyShippingLabels() {
  const free = Cart.subtotal() >= Pricing.freeShippingThreshold;
  document.querySelectorAll('input[name="shipping_method"]').forEach((radio) => {
    const small = radio.closest(".litho-size-opt").querySelector("small");
    const base = radio.value === "foxpost" ? "Csomagautomata" : "Futárral";
    const fee = Pricing.fees[radio.value];
    small.textContent = free ? `${base} · ingyenes` : `${base} · ${formatHuf(fee || 0)}`;
  });
}

function applyPaymentNote() {
  const note = document.getElementById("payment-method-note");
  const value = selectedPaymentMethod();
  if (value === "transfer") {
    note.textContent = "A „Rendelés leadása” után e-mailben küldjük az utaláshoz szükséges adatokat. A gyártás az utalás beérkezése után indul.";
  } else if (value === "cod") {
    note.textContent = "A végösszeget a futárnál fizeted kiszállításkor.";
  } else {
    note.textContent = "A „Rendelés leadása” gomb átirányít a biztonságos Barion fizetőoldalra. A kártyaadataidat a Barion kezeli, hozzánk nem jutnak el.";
  }
}

/* ---------- piszkozat ---------- */

let draftSaveTimer;
function scheduleDraftSave() {
  clearTimeout(draftSaveTimer);
  draftSaveTimer = setTimeout(() => CheckoutDraft.save(), 400);
}

/** A korábban megadott adatok visszatöltése (pl. sikertelen fizetés után). */
function restoreDraft() {
  const values = CheckoutDraft.restore();
  if (!values) return;

  // A csomagautomatát a picker jeleníti meg, mert a rejtett mező önmagában
  // nem látszik sehol.
  if (values["f-locker-id"] && typeof FoxpostPicker !== "undefined") {
    FoxpostPicker.showRestored(values["f-locker-id"], values["f-locker-name"]);
  }

  const note = document.getElementById("draft-restored");
  if (note) note.hidden = false;
}

/* ---------- beküldés ---------- */

function showCheckoutError(message) {
  const errorEl = document.getElementById("checkout-error");
  errorEl.textContent = message;
  errorEl.style.display = "block";
  errorEl.scrollIntoView({ behavior: "smooth", block: "center" });
}

function hideCheckoutError() {
  const errorEl = document.getElementById("checkout-error");
  errorEl.style.display = "none";
  errorEl.textContent = "";
}

document.getElementById("checkout-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  hideCheckoutError();

  const items = Cart.getItems();
  if (items.length === 0) {
    window.location.href = "kosar.html";
    return;
  }

  const shippingMethod = selectedShippingMethod();
  const paymentMethod = selectedPaymentMethod();

  // A csomagautomata nem űrlapmező, ezért a natív validáció nem látja.
  const lockerId = document.getElementById("f-locker-id").value;
  const foxpostErrorHost = document.getElementById("foxpost-error-host");
  if (window.FormErrors) FormErrors.clearBlock(foxpostErrorHost);
  if (shippingMethod === "foxpost" && !lockerId) {
    if (window.FormErrors) {
      FormErrors.showBlock(foxpostErrorHost, "Válassz egy Foxpost csomagautomatát a térképen vagy a listából.");
    }
    document.getElementById("fp-map").scrollIntoView({ behavior: "smooth", block: "center" });
    showCheckoutError("Válassz egy Foxpost csomagautomatát a szállításhoz.");
    return;
  }

  const shipping = { method: shippingMethod };
  if (shippingMethod === "foxpost") {
    shipping.lockerId = lockerId;
    shipping.lockerName = document.getElementById("f-locker-name").value.trim();
  } else {
    shipping.sameAsBilling = sameAsBilling();
    shipping.address = shipping.sameAsBilling
      ? readBillingAddress()
      : {
          name: document.getElementById("f-ship-name").value.trim(),
          address: document.getElementById("f-ship-address").value.trim(),
          city: document.getElementById("f-ship-city").value.trim(),
          zip: document.getElementById("f-ship-zip").value.trim(),
        };
  }

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
    shipping,
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

  // Mentés közvetlenül a beküldés előtt: ha a fizetés félbeszakad, minden
  // megvan, ami most a képernyőn van.
  CheckoutDraft.save();

  const btn = e.target.querySelector('button[type="submit"]');
  btn.disabled = true;
  btn.textContent = paymentMethod === "barion" ? "Átirányítás a fizetéshez…" : "Feldolgozás…";

  try {
    const data = await Api.createOrder(payload);
    // A kosár szándékosan megmarad: ha a fizetés félbeszakad, a vásárló
    // ne egy üres kosárral térjen vissza. A köszönőoldal üríti, amint a
    // rendelés státusza megerősíti, hogy létrejött.
    const target = data.gatewayUrl || data.redirectUrl || `koszonjuk.html?orderId=${encodeURIComponent(data.orderId)}`;
    window.location.href = target;
  } catch (err) {
    showCheckoutError(err.message || "A rendelés leadása nem sikerült. Kérjük, próbáld újra.");
    btn.disabled = false;
    btn.textContent = "Rendelés leadása";
  }
});

/* ---------- indulás ---------- */

async function loadPricing() {
  try {
    const data = await Api.getProducts();
    if (typeof data.freeShippingThresholdHuf === "number") {
      Pricing.freeShippingThreshold = data.freeShippingThresholdHuf;
    }
    if (data.shippingMethods) {
      Object.entries(data.shippingMethods).forEach(([key, value]) => {
        Pricing.fees[key] = value.fee_huf;
        Pricing.labels[key] = value.label;
      });
    }
    if (typeof data.codFeeHuf === "number") Pricing.codFee = data.codFeeHuf;
  } catch (e) {
    // A tartalék árak maradnak. A végösszeget úgyis a backend számolja.
  }
  applyShippingLabels();
  renderReview();
}

document.addEventListener("DOMContentLoaded", () => {
  // A visszatöltés a UI-állapot beállítása ELŐTT fut, hogy a szállítási és
  // fizetési mód, valamint a címmezők a mentett értékek szerint jelenjenek meg.
  restoreDraft();

  renderReview();
  applyShippingLabels();
  applyShippingMethod();
  loadPricing();

  // Minden változást mentünk, hogy egy megszakadt fizetés után ne kelljen
  // újra begépelni semmit.
  const form = document.getElementById("checkout-form");
  form.addEventListener("input", scheduleDraftSave);
  form.addEventListener("change", scheduleDraftSave);

  document.querySelectorAll('input[name="shipping_method"]').forEach((radio) => {
    radio.addEventListener("change", applyShippingMethod);
  });

  document.querySelectorAll('input[name="payment_method"]').forEach((radio) => {
    radio.addEventListener("change", () => {
      applyPaymentNote();
      renderReview();
    });
  });

  document.getElementById("f-same-address").addEventListener("change", applyShippingAddressFields);

  // A "megegyezik a számlázási címmel" előnézet kövesse a számlázási mezőket.
  ["f-name", "f-address", "f-city", "f-zip"].forEach((id) => {
    document.getElementById(id).addEventListener("input", () => {
      if (selectedShippingMethod() === "home" && sameAsBilling()) applyShippingAddressFields();
    });
  });
});
