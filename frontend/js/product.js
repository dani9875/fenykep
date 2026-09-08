function getParam(name) {
  return new URLSearchParams(window.location.search).get(name);
}

async function initProductPage() {
  const productId = getParam("p");
  const root = document.getElementById("product-root");
  const { products } = await Api.getProducts();
  const product = products[productId];

  if (!product) {
    root.innerHTML = "<p>Ez a termék nem található.</p>";
    return;
  }

  const PRODUCT_IMAGES = {
    "lampa-nelkul": "assets/products/lampa-nelkul.jpg",
    "led-talpas": "assets/products/led-talpas.jpg",
  };
  const productImage = PRODUCT_IMAGES[productId] || "";

  document.title = `${product.name} — Fény·kép Stúdió`;
  document.getElementById("crumb-name").textContent = product.name;

  const sizeButtons = Object.entries(product.sizes)
    .map(
      ([code, s]) => `
      <label class="litho-size-opt">
        <input type="radio" name="litho_size" value="${code}" data-delta="${s.delta_huf}" required />
        <span class="litho-size-btn"><strong>${s.label.split("·")[0].trim()}</strong><small>${(s.label.split("·")[1] || "").trim()}</small></span>
      </label>`
    )
    .join("");

  root.innerHTML = `
    <div style="display:grid; grid-template-columns:1fr 1fr; gap:2.5rem; align-items:start;">
      <img src="${productImage}" alt="${product.name}" style="width:100%; border-radius:12px; display:block;">
      <div class="product-summary">
      <h1 style="font-family:var(--font-serif);">${product.name}</h1>
      <p class="litho-price" id="litho-price" style="font-size:1.4rem;">${product.base_price_huf.toLocaleString("hu-HU")} Ft</p>

      <div class="litho-fields">
        <div class="litho-size-wrap">
          <div class="litho-field-label">Méret <span class="req">*</span></div>
          <div class="litho-size-options">${sizeButtons}</div>
        </div>

        <div class="litho-upload-wrap">
          <label for="litho_photo" class="litho-field-label">Fényképed <span class="req">*</span></label>
          <p class="litho-upload-hint">JPG vagy PNG, legalább 1000×1000 px.</p>
          <label for="litho_photo" class="litho-dropzone" id="litho-dropzone">
            <span class="litho-dropzone__text">Húzd ide a fényképet, vagy kattints</span>
            <span class="litho-dropzone__sub" id="litho-filename">Portrét, tájképet, kedvenc pillanatot</span>
            <input type="file" id="litho_photo" name="litho_photo" accept="image/jpeg,image/png" required />
          </label>
        </div>
      </div>

      <button id="add-to-cart-btn" class="single_add_to_cart_button">Kosárba teszem</button>
      <p id="product-error" style="color:#b94030; display:none; margin-top:0.75rem;"></p>
      </div>
    </div>
  `;

  const priceEl = document.getElementById("litho-price");
  document.querySelectorAll('input[name="litho_size"]').forEach((r) => {
    r.addEventListener("change", () => {
      const delta = parseInt(r.dataset.delta, 10);
      priceEl.textContent = (product.base_price_huf + delta).toLocaleString("hu-HU") + " Ft";
    });
  });

  const fileInput = document.getElementById("litho_photo");
  const filenameEl = document.getElementById("litho-filename");
  fileInput.addEventListener("change", () => {
    if (fileInput.files[0]) {
      filenameEl.textContent =
        fileInput.files[0].name + " · " + Math.round(fileInput.files[0].size / 1024) + " kB";
    }
  });

  document.getElementById("add-to-cart-btn").addEventListener("click", async () => {
    const errorEl = document.getElementById("product-error");
    errorEl.style.display = "none";

    const sizeInput = document.querySelector('input[name="litho_size"]:checked');
    const file = fileInput.files[0];

    if (!sizeInput || !file) {
      errorEl.textContent = "Válassz méretet, és tölts fel egy fotót.";
      errorEl.style.display = "block";
      return;
    }

    const btn = document.getElementById("add-to-cart-btn");
    btn.disabled = true;
    btn.textContent = "Feltöltés…";

    try {
      const photoKey = await Api.uploadPhoto(file);
      const size = sizeInput.value;
      const delta = parseInt(sizeInput.dataset.delta, 10);

      Cart.addItem({
        productId,
        productName: product.name,
        size,
        unitPrice: product.base_price_huf + delta,
        photoKey,
        photoFileName: file.name,
      });

      window.location.href = "kosar.html";
    } catch (e) {
      errorEl.textContent = e.message;
      errorEl.style.display = "block";
      btn.disabled = false;
      btn.textContent = "Kosárba teszem";
    }
  });
}

document.addEventListener("DOMContentLoaded", initProductPage);
