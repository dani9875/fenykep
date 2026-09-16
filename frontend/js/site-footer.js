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
          <a class="site-logo" href="index.html">Fény·kép Stúdió</a>
          <p>Egyedi, kézzel utómunkált 3D lithophane ajándékok a kedvenc fényképeidből.</p>
        </div>
        <div class="footer-col">
          <h4>Termékek</h4>
          <ul>
            <li><a href="index.html">Összes termék</a></li>
            <li><a href="galeria.html">Elkészült munkák</a></li>
            <li><a href="kiprobalom.html">Próbáld ki 3D-ben</a></li>
            <li><a href="kosar.html">Kosár</a></li>
          </ul>
        </div>
        <div class="footer-col">
          <h4>Stúdió</h4>
          <ul>
            <li><a href="kapcsolat.html">Kapcsolat</a></li>
            <li><a href="aszf.html">ÁSZF</a></li>
            <li><a href="adatvedelem.html">Adatvédelem</a></li>
          </ul>
        </div>
      </div>
      <div class="footer-bottom">
        <span>&copy; ${YEAR} Fény·kép Stúdió — Minden jog fenntartva</span>
        <div class="barion-banner barion-banner--footer">
          <a href="https://www.barion.com/hu/" target="_blank" rel="noopener noreferrer"
             aria-label="Barion — biztonságos online fizetés">
            <img src="assets/barion/barion-smart-banner-light.svg"
                 alt="Barion — biztonságos bankkártyás fizetés: Mastercard, Maestro, Visa, Visa Electron, American Express"
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

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", renderFooter);
  } else {
    renderFooter();
  }
})();
