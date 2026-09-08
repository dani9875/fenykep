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

function selectLocker(locker) {
  document.getElementById("f-locker-id").value = locker.id;
  document.getElementById("f-locker-name").value = `${locker.name} — ${locker.address}`;
  document.getElementById("fp-selected").innerHTML =
    `<strong>Kiválasztva:</strong> ${locker.name}<br>${locker.address}`;
}

function renderFpList(lockers) {
  const listEl = document.getElementById("fp-list");
  listEl.innerHTML = lockers
    .slice(0, 30)
    .map(
      (l) => `
      <div class="fp-list-item" data-id="${l.id}" style="padding:0.5rem; border-bottom:1px solid var(--border); cursor:pointer;">
        <strong>${l.name}</strong><br>
        <span style="font-size:0.8rem; color:var(--text-muted);">${l.address}</span>
      </div>`
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
}

function renderFpMarkers(lockers) {
  fpMarkers.forEach((m) => fpMap.removeLayer(m));
  fpMarkers = lockers.map((l) => {
    const marker = L.marker([l.lat, l.lng]).addTo(fpMap);
    marker.bindPopup(`<strong>${l.name}</strong><br>${l.address}`);
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

  fpHintEl = document.getElementById("fp-selected");
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
