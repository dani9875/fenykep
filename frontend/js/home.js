// A két változat a saját fényében: fényforrás nélkül nappal, fényforrással este.
const PRODUCT_IMAGES = {
  "lampa-nelkul": "assets/gallery/g9-termeszetesfeny3.jpg",
  "led-vilagitassal": "assets/gallery/g2-csaladikep.jpg",
};

// Minden terméknek saját, keresők által indexelhető oldala van.
const PRODUCT_PAGES = {
  "lampa-nelkul": "3d-foto-lampa-nelkul.html",
  "led-vilagitassal": "3d-foto-led-vilagitassal.html",
};

// Rövid termékleírás a kártyán, az ár alatt.
const PRODUCT_TAGLINES = {
  "lampa-nelkul": "3D nyomtatott kép a saját fotódból, 15 vagy 20 cm-es méretben. A fotó akkor látszik jól, ha hátulról éri a fény, például az ablakon beszűrődő fény vagy egy világos helyiség.",
  "led-vilagitassal": "3D nyomtatott kép a saját fotódból, LED világítással, 15 vagy 20 cm-es méretben. A LED hátulról világítja meg, így bárhol látszik rajta a fotó.",
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
          <a class="product-card" href="${PRODUCT_PAGES[id] || `termek.html?p=${id}`}" style="display:block; border:1px solid var(--border); border-radius:12px; overflow:hidden; text-decoration:none; color:inherit;">
            <div style="aspect-ratio:1; background:var(--sand) url('${img}') center/cover no-repeat;"></div>
            <div style="padding:1.2rem;">
              <h3 style="font-family:var(--font-serif); margin:0 0 0.4rem;">${p.name}</h3>
              <p style="color:var(--text-muted); margin:0;">${String(fromPrice).replace(/\B(?=(\d{3})+(?!\d))/g, "\u00a0")} Ft-tól</p>
              ${PRODUCT_TAGLINES[id] ? `<p style="margin:0.5rem 0 0;">${PRODUCT_TAGLINES[id]}</p>` : ""}
            </div>
          </a>`;
      })
      .join("");
  } catch (e) {
    grid.innerHTML = `<p>Nem sikerült betölteni a termékeket. ${e.message}</p>`;
  }
  rescrollToHash();
}

/* Ha másik oldalról érkezünk egy horgonyra (pl. index.html#kicsomagolas),
   a böngésző még az üres terméklistánál ugrik oda. A termékek betöltése
   után a lista megnő, és a cél lejjebb csúszik, ezért újra odaugrunk. */
function rescrollToHash() {
  const id = decodeURIComponent(window.location.hash.slice(1));
  if (!id || id === "products") return;
  const target = document.getElementById(id);
  if (target) target.scrollIntoView({ behavior: "instant", block: "start" });
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
