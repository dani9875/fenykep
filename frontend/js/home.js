// A két változat a saját fényében: lámpa nélkül nappal, LED talppal este.
const PRODUCT_IMAGES = {
  "lampa-nelkul": "assets/gallery/g9-termeszetesfeny3.jpg",
  "led-talpas": "assets/gallery/g2-csaladikep.jpg",
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
              <p style="color:var(--text-muted); margin:0;">${String(fromPrice).replace(/\B(?=(\d{3})+(?!\d))/g, "\u00a0")} Ft-tól</p>
            </div>
          </a>`;
      })
      .join("");
  } catch (e) {
    grid.innerHTML = `<p>Nem sikerült betölteni a termékeket. ${e.message}</p>`;
  }
}

/* A főoldali videó: magától indul, kivéve ha a látogató mozgáscsökkentést
   kért. A gomb megállítja és újraindítja. */
function initHomeFilm() {
  const video = document.getElementById("home-film-video");
  const toggle = document.getElementById("home-film-toggle");
  if (!video || !toggle) return;

  const sync = () => {
    const playing = !video.paused;
    toggle.classList.toggle("is-paused", !playing);
    toggle.setAttribute("aria-label", playing ? "Videó megállítása" : "Videó lejátszása");
  };
  video.addEventListener("play", sync);
  video.addEventListener("pause", sync);
  toggle.addEventListener("click", () => (video.paused ? video.play() : video.pause()));

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!reduceMotion) video.play().catch(sync);
  sync();
}

document.addEventListener("DOMContentLoaded", () => {
  renderProductGrid();
  initHomeFilm();
});
