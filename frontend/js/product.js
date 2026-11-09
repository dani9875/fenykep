function getParam(name) {
  return new URLSearchParams(window.location.search).get(name);
}

async function initProductPage() {
  const productId = document.body.dataset.product || getParam("p");
  const root = document.getElementById("product-root");
  const { products } = await Api.getProducts();
  const product = products[productId];

  if (!product) {
    root.innerHTML = "<p>Ez a termék nem található.</p>";
    return;
  }

  // Az első kép a nagy kép, a többi alatta bélyegképként; kattintásra cserélődnek.
  const PRODUCT_GALLERY = {
    "lampa-nelkul": [
      { src: "assets/gallery/g9-termeszetesfeny3.jpg", alt: "3D fotó lámpa nélkül, nappali fényben" },
      { src: "assets/products/lampa-nelkul.jpg", alt: "Babafotó lámpa nélkül, az állványon" },
      { src: "assets/gallery/g5-parkep.jpg", alt: "Páros fotó lámpa nélkül" },
      { src: "assets/gallery/g3-magzatkep.jpg", alt: "Ultrahangkép lámpa nélkül" },
      { src: "assets/day-night-nappal.jpg", alt: "Családi fotó lámpa nélkül" },
    ],
    "led-vilagitassal": [
      { src: "assets/products/led-vilagitassal.jpg", alt: "3D fotó LED világítással, bekapcsolva" },
      { src: "assets/gallery/g2-csaladikep.jpg", alt: "Családi fotó LED világítással, esti fényben" },
      { src: "assets/day-night-este.jpg", alt: "Családi fotó LED világítással" },
      { src: "assets/gallery/g4-magzatkep-vilagit.jpg", alt: "Ultrahangkép LED világítással" },
      { src: "assets/gallery/g8-kisbabakep5.jpg", alt: "Babafotó LED világítással, polcon" },
    ],
  };
  const gallery = PRODUCT_GALLERY[productId] || [];

  document.title = `${product.name} | Fény·kép`;
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

  // A hu-HU formázás a négyjegyű számot nem tagolja (9990, de 14 990),
  // ezért kézzel tesszük be a nem törő szóközt.
  const huf = (n) => String(Math.round(Number(n))).replace(/\B(?=(\d{3})+(?!\d))/g, "\u00a0") + " Ft";

  root.innerHTML = `
    <div class="litho-single-grid">
      <div class="litho-single-gallery">
        <img class="litho-single-photo" id="litho-main-photo" src="${gallery[0] ? gallery[0].src : ""}" alt="${gallery[0] ? gallery[0].alt : product.name}">
        <div class="litho-thumbs">
          ${gallery
            .map(
              (g, i) => `<button type="button" class="litho-thumb${i === 0 ? " is-active" : ""}" data-index="${i}" aria-label="${g.alt}">
                <img src="${g.src}" alt="" loading="lazy">
              </button>`
            )
            .join("")}
        </div>
      </div>
      <div class="product-summary">
      <h1 style="font-family:var(--font-serif);">${product.name}</h1>
      <p class="litho-price" id="litho-price" style="font-size:1.4rem;">${huf(product.base_price_huf)}</p>

      <div class="litho-fields">
        <div class="litho-size-wrap">
          <div class="litho-field-label">Méret <span class="label-hint">(a leghosszabb oldal mérete)</span></div>
          <div class="litho-size-options">${sizeButtons}</div>
        </div>

        <div class="litho-upload-wrap">
          <p class="litho-upload-hint">JPG vagy PNG, legalább 1000×1000 px.</p>
          <label for="litho_photo" class="litho-dropzone" id="litho-dropzone">
            <img class="litho-dropzone__preview" id="litho-preview" alt="" hidden />
            <span class="litho-dropzone__text" id="litho-dropzone-text">Húzd ide a fényképet, vagy kattints</span>
            <span class="litho-dropzone__sub" id="litho-filename"></span>
            <input type="file" id="litho_photo" name="litho_photo" accept="image/jpeg,image/png" required />
          </label>
          <p id="product-photo-warning" class="litho-photo-warning" role="status" hidden></p>
        </div>
      </div>

      <button id="add-to-cart-btn" class="litho-btn-solid litho-add-btn" ${ORDERS_PAUSED ? "disabled" : ""}>Kosárba teszem</button>
      <p id="product-error" class="litho-form-error" hidden></p>
      </div>
    </div>
  `;

  const mainPhoto = document.getElementById("litho-main-photo");
  const thumbs = document.querySelectorAll(".litho-thumb");
  thumbs.forEach((t) =>
    t.addEventListener("click", () => {
      const g = gallery[Number(t.dataset.index)];
      mainPhoto.src = g.src;
      mainPhoto.alt = g.alt;
      thumbs.forEach((x) => x.classList.toggle("is-active", x === t));
    })
  );

  const priceEl = document.getElementById("litho-price");
  document.querySelectorAll('input[name="litho_size"]').forEach((r) => {
    r.addEventListener("change", () => {
      const delta = parseInt(r.dataset.delta, 10);
      priceEl.textContent = huf(product.base_price_huf + delta);
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

  // Ennél kisebb fotóból a kész 3D fotó elmosódott lesz. Nem tiltjuk,
  // csak szólunk, a vásárló dönt.
  const MIN_PHOTO_PX = 1000;
  const warningEl = document.getElementById("product-photo-warning");

  fileInput.addEventListener("change", async () => {
    const file = fileInput.files[0];
    previewDataUrl = null;
    warningEl.hidden = true;
    if (!file) {
      dropzone.classList.remove("litho-dropzone--selected");
      previewEl.hidden = true;
      dropzoneText.textContent = "Húzd ide a fényképet, vagy kattints";
      filenameEl.textContent = "";
      return;
    }

    dropzone.classList.add("litho-dropzone--selected");
    dropzoneText.textContent = "Csere másik fényképre";
    filenameEl.textContent = file.name + " · " + Math.round(file.size / 1024) + " kB";

    const errorEl = document.getElementById("product-error");
    errorEl.hidden = true;

    try {
      const preview = await PhotoStore.makePreviewWithSize(file);
      previewDataUrl = preview.dataUrl;
      previewEl.src = previewDataUrl;
      previewEl.hidden = false;
      if (preview.width < MIN_PHOTO_PX || preview.height < MIN_PHOTO_PX) {
        warningEl.textContent =
          `A fotó minősége alacsony (${preview.width}×${preview.height} px). ` +
          "Előfordulhat, hogy nem tudjuk megfelelő minőségben felhasználni a 3D fotó elkészítéséhez. " +
          "Kérjük, tölts fel nagyobb felbontású képet.";
        warningEl.hidden = false;
      }
    } catch (e) {
      // Régebben ez némán elrejtette az előnézetet: a vásárló csak annyit
      // látott, hogy "nem jelent meg a kép". Telefonon a leggyakoribb ok a
      // nem támogatott formátum (pl. iPhone HEIC).
      previewEl.hidden = true;
      errorEl.textContent =
        "A képet nem sikerült megjeleníteni. Ha iPhone-ról töltöd fel, " +
        "állítsd a Beállítások → Kamera → Formátumok menüben a " +
        "„Legnagyobb kompatibilitás" + String.fromCharCode(8221) + " opciót, vagy tölts fel JPG/PNG fájlt.";
      errorEl.hidden = false;
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
    if (ORDERS_PAUSED) return;

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
