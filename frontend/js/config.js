/**
 * Futtatókörnyezet-függő beállítások.
 *
 * Helyben (localhost) mindig a local-test/server.py-t hívjuk. Deploykor a
 * scripts/deploy-frontend.sh kicseréli a __API_URL__ helyőrzőt az API
 * Gateway URL-jére — a fájl egy ideiglenes másolatában, tehát a repóban
 * lévő példány érintetlen marad, és a helyi tesztelés nem törik el.
 *
 * Így nincs a repóban egyetlen környezetfüggő URL sem, amit deploy előtt
 * át kellene írni és utána vissza.
 */

const LOCAL_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0", "[::1]", ""];

// Ezt a sort írja át a deploy szkript. Helyben soha nem használjuk.
const DEPLOYED_API_URL = "__API_URL__";

const isLocal = LOCAL_HOSTS.includes(window.location.hostname);
window.API_URL = isLocal ? "http://localhost:8787" : DEPLOYED_API_URL;

if (!isLocal && window.API_URL.indexOf("__API_URL__") !== -1) {
  // Ilyenkor a statikus fájlokat a deploy szkript megkerülésével töltötték
  // fel. Jobb hangosan elhasalni, mint néma 404-ekkel csendben hibázni.
  console.error(
    "Nincs beállítva az API URL. Deployolj a scripts/deploy-frontend.sh scripttel, " +
      "vagy add meg kézzel az API_URL-t a js/config.js-ben."
  );
}

// Bumped whenever the CSS/JS changes; the HTML pages carry it as a ?v=
// query on every asset URL so a browser cannot keep serving an old copy.
// Printing it makes "which version am I actually looking at?" a one-glance
// question in the console.
window.ASSET_VERSION = "20260914a";
console.info("Fény·kép build " + window.ASSET_VERSION + " · API: " + window.API_URL);
