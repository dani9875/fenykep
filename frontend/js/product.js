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
    <div class="litho-single-grid">
      <img class="litho-single-photo" src="${productImage}" alt="${product.name}">
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
            <img class="litho-dropzone__preview" id="litho-preview" alt="" hidden />
            <span class="litho-dropzone__text" id="litho-dropzone-text">Húzd ide a fényképet, vagy kattints</span>
            <span class="litho-dropzone__sub" id="litho-filename">Portrét, tájképet, kedvenc pillanatot</span>
            <input type="file" id="litho_photo" name="litho_photo" accept="image/jpeg,image/png" required />
          </label>
        </div>
      </div>

      <button id="add-to-cart-btn" class="litho-btn-solid litho-add-btn">Kosárba teszem</button>
      <p id="product-error" class="litho-form-error" hidden></p>
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
  const dropzone = document.getElementById("litho-dropzone");
  const previewEl = document.getElementById("litho-preview");
  const dropzoneText = document.getElementById("litho-dropzone-text");

  // Built once on selection and reused after upload, so the cart can show
  // the customer their own photo rather than the generic product shot.
  let previewDataUrl = null;

  fileInput.addEventListener("change", async () => {
    const file = fileInput.files[0];
    previewDataUrl = null;
    if (!file) {
      dropzone.classList.remove("litho-dropzone--selected");
      previewEl.hidden = true;
      dropzoneText.textContent = "Húzd ide a fényképet, vagy kattints";
      filenameEl.textContent = "Portrét, tájképet, kedvenc pillanatot";
      return;
    }

    dropzone.classList.add("litho-dropzone--selected");
    dropzoneText.textContent = "Csere másik fényképre";
    filenameEl.textContent = file.name + " · " + Math.round(file.size / 1024) + " kB";

    try {
      previewDataUrl = await PhotoStore.makePreview(file);
      previewEl.src = previewDataUrl;
      previewEl.hidden = false;
    } catch (e) {
      previewEl.hidden = true; // preview is a nicety; the upload still works
    }
  });

  // Dragging onto the label works natively, but only the highlight tells
  // the visitor that — the file input itself never sees a dragover.
  ["dragenter", "dragover"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.add("litho-dropzone--dragging");
    })
  );
  ["dragleave", "drop"].forEach((evt) =>
    dropzone.addEventListener(evt, () => dropzone.classList.remove("litho-dropzone--dragging"))
  );
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    const dropped = e.dataTransfer && e.dataTransfer.files[0];
    if (!dropped) return;
    const dt = new DataTransfer();
    dt.items.add(dropped);
    fileInput.files = dt.files;
    fileInput.dispatchEvent(new Event("change"));
  });

  document.getElementById("add-to-cart-btn").addEventListener("click", async () => {
    const errorEl = document.getElementById("product-error");
    errorEl.hidden = true;

    const sizeInput = document.querySelector('input[name="litho_size"]:checked');
    const file = fileInput.files[0];

    if (!sizeInput || !file) {
      errorEl.textContent = "Válassz méretet, és tölts fel egy fotót.";
      errorEl.hidden = false;
      return;
    }

    const btn = document.getElementById("add-to-cart-btn");
    btn.disabled = true;
    btn.textContent = "Feltöltés…";

    try {
      const photoKey = await Api.uploadPhoto(file);
      PhotoStore.save(photoKey, previewDataUrl);
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
      errorEl.hidden = false;
      btn.disabled = false;
      btn.textContent = "Kosárba teszem";
    }
  });
}

document.addEventListener("DOMContentLoaded", initProductPage);
