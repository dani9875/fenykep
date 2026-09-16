/**
 * Foxpost locker picker — lazy-loaded.
 *
 * The full country list is a few thousand points. Loading and
 * rendering all of them on page load is what made the old version
 * slow. Now:
 *   - Nothing loads until the person zooms in past MIN_ZOOM or types
 *     a search — either path calls the backend with a narrow filter
 *     (bbox or city), never the full list.
 *   - Zooming back out clears the markers again.
 */

const MIN_ZOOM_FOR_MARKERS = 12;

let fpMap = null;
let fpMarkers = [];
let fpHintEl = null;
let fpSearchActive = false; // true while a search result is shown, pauses the zoom-based loader
let fpSelected = null;      // a kiválasztott automata, hogy az újrarajzolás után is megmaradjon

function escapeHtml(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

/**
 * A kiválasztás és a tippszöveg KÜLÖN elemben él.
 *
 * Korábban mindkettő a #fp-selected-be írt: a setHint() elrejtette az
 * elemet, amint volt találat, a térkép mozgása pedig (amit maga a
 * kiválasztás váltott ki) felül is írta a szöveget. A választás így
 * láthatatlan maradt, pedig a rejtett mező megkapta az értéket.
 */
function selectLocker(locker) {
  fpSelected = locker;

  document.getElementById("f-locker-id").value = locker.id;
  document.getElementById("f-locker-name").value = `${locker.name} — ${locker.address}`;

  const box = document.getElementById("fp-selected");
  box.innerHTML =
    `<strong>Kiválasztva:</strong> ${escapeHtml(locker.name)}<br>` +
    `<span class="fp-selected__address">${escapeHtml(locker.address)}</span>`;
  box.hidden = false;

  highlightSelected();

  // A "válassz automatát" hibaüzenet tűnjön el, amint van választás.
  if (window.FormErrors) FormErrors.clearBlock(document.getElementById("foxpost-error-host"));
}

/** A lista újrarajzolása után is látszódjon, melyik sor az aktuális. */
function highlightSelected() {
  document.querySelectorAll("#fp-list .fp-list-item").forEach((el) => {
    el.classList.toggle("is-selected", !!fpSelected && String(fpSelected.id) === el.dataset.id);
  });
}

function renderFpList(lockers) {
  const listEl = document.getElementById("fp-list");
  listEl.innerHTML = lockers
    .slice(0, 30)
    .map(
      (l) => `
      <button type="button" class="fp-list-item" data-id="${escapeHtml(l.id)}">
        <strong>${escapeHtml(l.name)}</strong>
        <span class="fp-list-item__address">${escapeHtml(l.address)}</span>
      </button>`
    )
    .join("");

  listEl.querySelectorAll(".fp-list-item").forEach((el) => {
    el.addEventListener("click", () => {
      const locker = lockers.find((l) => String(l.id) === el.dataset.id);
      if (!locker) return;
      selectLocker(locker);
      fpMap.setView([locker.lat, locker.lng], 15);
    });
  });

  highlightSelected();
}

function renderFpMarkers(lockers) {
  fpMarkers.forEach((m) => fpMap.removeLayer(m));
  fpMarkers = lockers.map((l) => {
    const marker = L.marker([l.lat, l.lng]).addTo(fpMap);
    marker.bindPopup(`<strong>${escapeHtml(l.name)}</strong><br>${escapeHtml(l.address)}`);
    marker.on("click", () => selectLocker(l));
    return marker;
  });
}

function setHint(text) {
  if (!fpHintEl) return;
  fpHintEl.textContent = text;
  fpHintEl.style.display = text ? "block" : "none";
}

async function loadForCurrentView() {
  if (fpSearchActive) return; // a search result is showing; don't fight it with the zoom handler
  if (fpMap.getZoom() < MIN_ZOOM_FOR_MARKERS) {
    renderFpMarkers([]);
    renderFpList([]);
    setHint("Zoomolj be egy városra, vagy keress rá fent, hogy megjelenjenek a csomagautomaták.");
    return;
  }
  const bounds = fpMap.getBounds();
  try {
    const { lockers } = await Api.getFoxpostLockers({
      minLat: bounds.getSouth(),
      maxLat: bounds.getNorth(),
      minLng: bounds.getWest(),
      maxLng: bounds.getEast(),
    });
    setHint(lockers.length ? "" : "Ezen a területen nincs Foxpost automata.");
    renderFpMarkers(lockers);
    renderFpList(lockers);
  } catch (e) {
    setHint("Nem sikerült betölteni a csomagautomatákat. " + e.message);
  }
}

// Debounce so panning/zooming doesn't fire a request per frame.
function debounce(fn, ms) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}
const debouncedLoad = debounce(loadForCurrentView, 400);

function initFoxpostPicker() {
  fpMap = L.map("fp-map").setView([47.4979, 19.0402], 7); // Budapest, whole-country default
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap közreműködők",
  }).addTo(fpMap);

  fpHintEl = document.getElementById("fp-hint");
  setHint("Zoomolj be egy városra, vagy keress rá fent, hogy megjelenjenek a csomagautomaták.");

  fpMap.on("moveend zoomend", debouncedLoad);
}

let searchDebounceTimer;
document.getElementById("fp-search").addEventListener("input", (e) => {
  clearTimeout(searchDebounceTimer);
  const q = e.target.value.trim();

  if (!q) {
    fpSearchActive = false;
    loadForCurrentView();
    return;
  }

  searchDebounceTimer = setTimeout(async () => {
    try {
      const { lockers } = await Api.getFoxpostLockers({ city: q });
      fpSearchActive = true;
      setHint(lockers.length ? "" : "Nincs találat erre a keresésre.");
      renderFpMarkers(lockers);
      renderFpList(lockers);
      if (lockers.length) fpMap.setView([lockers[0].lat, lockers[0].lng], 13);
    } catch (err) {
      setHint("Keresési hiba: " + err.message);
    }
  }, 350);
});

document.addEventListener("DOMContentLoaded", initFoxpostPicker);

/**
 * A térkép a házhozszállítás fülön rejtve van. A Leaflet a rejtett
 * konténerre 0 magasságot mér, és a visszaváltás után szürke marad, amíg
 * újra meg nem méretjük — ezt hívja meg a penztar.js módváltáskor.
 */
window.FoxpostPicker = {
  refresh() {
    if (!fpMap) return;
    setTimeout(() => fpMap.invalidateSize(), 0);
  },

  /**
   * Egy korábbi (piszkozatból visszatöltött) választás megjelenítése.
   * A teljes automata-adat nincs meg, csak az id és a kiírandó név —
   * a rendeléshez ennyi kell, a listát pedig a térkép úgyis feltölti.
   */
  showRestored(id, label) {
    if (!id) return;
    fpSelected = { id: id };
    const box = document.getElementById("fp-selected");
    box.innerHTML = `<strong>Kiválasztva:</strong> ${escapeHtml(label || id)}`;
    box.hidden = false;
    highlightSelected();
  },
};
