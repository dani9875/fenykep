/**
 * Közös lábléc minden oldalon.
 *
 * Egy helyen él, mert a Barion Smart Payment Bannernek minden aloldalon
 * ott kell lennie — kilenc kézzel karbantartott másolatban ez előbb-utóbb
 * szétcsúszna.
 */
(function () {
  "use strict";

  const YEAR = new Date().getFullYear();

  const HTML = `
    <div class="container">
      <div class="footer-grid">
        <div class="footer-brand">
          <a class="site-logo" href="index.html"><img class="site-logo-mark" src="assets/favicon.svg" alt="" aria-hidden="true">Fény<span class="site-logo-dot"></span>kép</a>
          <p>A kedvenc pillanataid nem a telefonodba valók, hanem az otthonodba.</p>
        </div>
        <div class="footer-col">
          <h4>Termékek</h4>
          <ul>
            <li><a href="index.html">Összes termék</a></li>
            <li><a href="galeria.html">Galéria</a></li>
            <li><a href="kiprobalom.html">3D előnézet</a></li>
            <li><a href="kosar.html">Kosár</a></li>
          </ul>
        </div>
        <div class="footer-col">
          <h4>Információ</h4>
          <ul>
            <li><a href="kapcsolat.html">Kapcsolat</a></li>
            <li><a href="aszf.html">ÁSZF</a></li>
            <li><a href="adatvedelem.html">Adatvédelem</a></li>
          </ul>
        </div>
      </div>
      <div class="footer-bottom">
        <span>&copy; ${YEAR} Fény·kép. Minden jog fenntartva.</span>
        <div class="barion-banner barion-banner--footer">
          <a href="https://www.barion.com/hu/" target="_blank" rel="noopener noreferrer"
             aria-label="Barion, biztonságos online fizetés">
            <img src="assets/barion/barion-smart-banner-light.svg"
                 alt="Barion, biztonságos bankkártyás fizetés: Mastercard, Maestro, Visa, Visa Electron, American Express"
                 width="567" height="108" loading="lazy">
          </a>
        </div>
      </div>
    </div>`;

  function renderFooter() {
    if (document.querySelector(".site-footer")) return; // kézzel írt lábléc van az oldalon
    const footer = document.createElement("footer");
    footer.className = "site-footer";
    footer.innerHTML = HTML;
    (document.querySelector(".site-wrapper") || document.body).appendChild(footer);
  }

  // Süti tájékoztató. Csak a működéshez szükséges tárolást használunk,
  // ehhez nem kell hozzájárulás (Eht. 155. § (4)), csak tájékoztatás.
  // Ezért nincs elfogadás/elutasítás, csak egy „Rendben” gomb.
  const COOKIE_NOTICE_KEY = "litho_cookie_notice_seen";

  function renderCookieNotice() {
    try {
      if (localStorage.getItem(COOKIE_NOTICE_KEY)) return;
    } catch (e) {
      return; // letiltott tárolásnál úgysem tudnánk megjegyezni, ne zavarjon minden oldalon
    }
    const box = document.createElement("div");
    box.className = "cookie-notice";
    box.setAttribute("role", "region");
    box.setAttribute("aria-label", "Sütik");
    box.innerHTML = `
      <p class="cookie-notice__title">Sütik</p>
      <p class="cookie-notice__text">A webshop a zavartalan működéshez sütiket használ, melyek elengedhetetlenek az oldal használatához.
        <a href="adatvedelem.html#sutik">Részletek</a></p>
      <button type="button" class="cookie-notice__btn">Rendben</button>`;
    box.querySelector("button").addEventListener("click", function () {
      try { localStorage.setItem(COOKIE_NOTICE_KEY, "1"); } catch (e) { /* nem kritikus */ }
      box.remove();
    });
    document.body.appendChild(box);
  }

  const ORDERS_PAUSED_TEXT =
    "A rendelések nagy száma miatt átmenetileg nem tudunk új rendelést fogadni. Hamarosan újra rendelhetsz.";

  function applyOrdersPaused() {
    if (typeof ORDERS_PAUSED === "undefined" || !ORDERS_PAUSED) return;
    document.body.classList.add("orders-paused");
    const bar = document.createElement("div");
    bar.className = "orders-paused-bar";
    bar.setAttribute("role", "status");
    bar.textContent = ORDERS_PAUSED_TEXT;
    document.body.prepend(bar);
    // A sáv magassága (telefonon két sor is lehet) tolja lejjebb a fejlécet
    // és a tartalmat, lásd .orders-paused-root a style.css-ben.
    const root = document.documentElement;
    root.classList.add("orders-paused-root");
    const measure = () => root.style.setProperty("--paused-bar-h", bar.offsetHeight + "px");
    measure();
    // A betűtípus betöltése vagy elforgatás után a sáv sortörése változhat.
    if (window.ResizeObserver) new ResizeObserver(measure).observe(bar);
    else window.addEventListener("resize", measure);
    document
      .querySelectorAll("#add-to-cart-btn, #ltoOrderBtn, .litho-checkout-submit")
      .forEach((btn) => { btn.disabled = true; });
  }

  function init() {
    renderFooter();
    renderCookieNotice();
    applyOrdersPaused();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
