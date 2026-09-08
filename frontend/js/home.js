const PRODUCT_IMAGES = {
  "lampa-nelkul": "assets/products/lampa-nelkul.jpg",
  "led-talpas": "assets/products/led-talpas.jpg",
};

async function renderProductGrid() {
  const grid = document.getElementById("product-grid");
  try {
    const { products } = await Api.getProducts();
    grid.innerHTML = Object.entries(products)
      .map(([id, p]) => {
        const fromPrice = p.base_price_huf;
        const img = PRODUCT_IMAGES[id] || "";
        return `
          <a class="product-card" href="termek.html?p=${id}" style="display:block; border:1px solid var(--border); border-radius:12px; overflow:hidden; text-decoration:none; color:inherit;">
            <div style="aspect-ratio:1; background:var(--sand) url('${img}') center/cover no-repeat;"></div>
            <div style="padding:1.2rem;">
              <h3 style="font-family:var(--font-serif); margin:0 0 0.4rem;">${p.name}</h3>
              <p style="color:var(--text-muted); margin:0;">${fromPrice.toLocaleString("hu-HU")} Ft-tól</p>
            </div>
          </a>`;
      })
      .join("");
  } catch (e) {
    grid.innerHTML = `<p>Nem sikerült betölteni a termékeket. ${e.message}</p>`;
  }
}

document.addEventListener("DOMContentLoaded", renderProductGrid);
