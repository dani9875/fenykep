const GALLERY_IMAGES = [
  "assets/gallery/g2-csaladikep.jpg",
  "assets/gallery/g3-magzatkep.jpg",
  "assets/gallery/g4-magzatkep-vilagit.jpg",
  "assets/gallery/g1-babakep3.jpg",
  "assets/gallery/g5-parkep.jpg",
  "assets/gallery/g6-keret3.jpg",
  "assets/gallery/g7-topografia.jpg",
  "assets/gallery/g8-kisbabakep5.jpg",
  "assets/gallery/g9-termeszetesfeny3.jpg",
];

function renderGalleryGrid() {
  const grid = document.getElementById("gallery-grid");
  if (!grid) return;

  grid.innerHTML = GALLERY_IMAGES.map(
    (src) => `
    <button type="button" class="gallery-thumb" data-src="${src}" aria-label="Kép nagyítása">
      <img src="${src}" alt="Elkészült litofán" loading="lazy" style="width:100%; height:100%; object-fit:cover; display:block; transition:transform 0.3s;">
    </button>`
  ).join("");

  const lightbox = document.createElement("div");
  lightbox.id = "gallery-lightbox";
  lightbox.style.cssText =
    "display:none; position:fixed; inset:0; background:rgba(28,25,23,0.92); z-index:10000; align-items:center; justify-content:center; padding:2rem;";
  lightbox.innerHTML = `<img id="gallery-lightbox-img" alt="Elkészült litofán, nagyítva" style="max-width:90vw; max-height:90vh; border-radius:8px;">`;

  function closeLightbox() {
    lightbox.style.display = "none";
  }
  lightbox.addEventListener("click", closeLightbox);
  // Esc-re is záruljon — egérrel a képre kattintva könnyű elvéteni a hátteret.
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeLightbox();
  });
  document.body.appendChild(lightbox);

  grid.querySelectorAll(".gallery-thumb").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.getElementById("gallery-lightbox-img").src = btn.dataset.src;
      lightbox.style.display = "flex";
    });
  });
}

document.addEventListener("DOMContentLoaded", renderGalleryGrid);
