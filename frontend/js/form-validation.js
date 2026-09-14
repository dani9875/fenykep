/**
 * Magyar űrlap-validáció.
 *
 * A böngésző beépített buborékja a böngésző nyelvén szól ("Please fill out
 * this field."), amit a HTML lang="hu" sem ír felül — a szöveg a felhasználó
 * böngészőjének nyelvéből jön. Ezért itt elkapjuk az `invalid` eseményt,
 * letiltjuk a natív buborékot, és a mező alá írunk ki magyar üzenetet.
 *
 * A natív validáció nem szűnik meg: a submit továbbra sem fut le, amíg
 * érvénytelen mező van — csak a megjelenítés a miénk.
 *
 * Használat: tedd be a <script>-et bármelyik űrlapot tartalmazó oldalra.
 * Extra attribútumok, ha kell:
 *   data-error-required="…"   saját "kötelező" üzenet
 *   data-error-pattern="…"    saját formátum-üzenet
 *   data-label="…"            a mező neve a hibaüzenetben
 */

(function () {
  "use strict";

  const GENERIC = "Kérjük, ellenőrizd ezt a mezőt.";

  function fieldLabel(el) {
    if (el.dataset.label) return el.dataset.label;
    const id = el.getAttribute("id");
    if (id) {
      const label = document.querySelector(`label[for="${id}"]`);
      if (label) return label.textContent.replace("*", "").trim();
    }
    const wrapping = el.closest("label");
    if (wrapping) {
      const own = wrapping.querySelector("label");
      if (own) return own.textContent.replace("*", "").trim();
    }
    const row = el.closest(".form-row, .litho-cf__field");
    const rowLabel = row && row.querySelector("label");
    if (rowLabel) return rowLabel.textContent.replace("*", "").trim();
    return "";
  }

  function requiredMessage(el) {
    if (el.dataset.errorRequired) return el.dataset.errorRequired;
    if (el.type === "checkbox") return "Ezt a jelölőnégyzetet ki kell pipálni a továbblépéshez.";
    if (el.type === "radio") return "Kérjük, válassz egy lehetőséget.";
    if (el.tagName === "SELECT") return "Kérjük, válassz egy lehetőséget.";
    const label = fieldLabel(el);
    return label ? `Kérjük, töltsd ki: ${label.toLowerCase()}.` : "Kérjük, töltsd ki ezt a mezőt.";
  }

  function messageFor(el) {
    const v = el.validity;
    if (v.valueMissing) return requiredMessage(el);
    if (v.typeMismatch) {
      if (el.type === "email") return "Kérjük, adj meg egy érvényes e-mail címet (pl. nev@email.hu).";
      if (el.type === "url") return "Kérjük, adj meg egy érvényes webcímet.";
      if (el.type === "tel") return "Kérjük, adj meg egy érvényes telefonszámot.";
      return GENERIC;
    }
    if (v.patternMismatch) {
      if (el.dataset.errorPattern) return el.dataset.errorPattern;
      if (el.type === "tel") return "Kérjük, adj meg egy érvényes telefonszámot (pl. +36 30 123 4567).";
      return "A megadott érték formátuma nem megfelelő.";
    }
    if (v.tooShort) return `Túl rövid — legalább ${el.minLength} karakter szükséges.`;
    if (v.tooLong) return `Túl hosszú — legfeljebb ${el.maxLength} karakter lehet.`;
    if (v.rangeUnderflow) return `A megadott érték túl kicsi (legalább ${el.min}).`;
    if (v.rangeOverflow) return `A megadott érték túl nagy (legfeljebb ${el.max}).`;
    if (v.stepMismatch) return "A megadott érték nem megengedett lépésköz szerinti.";
    if (v.badInput) return "A megadott érték nem értelmezhető.";
    if (v.customError) return el.validationMessage || GENERIC;
    return GENERIC;
  }

  /** A hibaüzenet helye: a mezőt tartalmazó sor/blokk vége. */
  function errorHost(el) {
    return (
      el.closest(".form-row, .litho-cf__field, .litho-cf__consent, .litho-consent-field, .litho-field") ||
      el.parentElement
    );
  }

  function showError(el, message) {
    const host = errorHost(el);
    if (!host) return;
    let box = host.querySelector(":scope > .field-error");
    if (!box) {
      box = document.createElement("span");
      box.className = "field-error";
      host.appendChild(box);
    }
    box.textContent = message;
    el.classList.add("is-invalid");
    el.setAttribute("aria-invalid", "true");
    if (!box.id) box.id = `err-${el.id || Math.random().toString(36).slice(2, 8)}`;
    el.setAttribute("aria-describedby", box.id);
  }

  function clearError(el) {
    const host = errorHost(el);
    const box = host && host.querySelector(":scope > .field-error");
    if (box) box.remove();
    el.classList.remove("is-invalid");
    el.removeAttribute("aria-invalid");
    el.removeAttribute("aria-describedby");
  }

  /**
   * Nem űrlapmezőhöz kötött hiba (pl. "válassz csomagautomatát"): ugyanaz a
   * megjelenés, de egy tetszőleges konténerre akasztva. A penztar.js hívja.
   */
  function showBlockError(container, message) {
    if (!container) return;
    let box = container.querySelector(":scope > .field-error");
    if (!box) {
      box = document.createElement("span");
      box.className = "field-error";
      container.appendChild(box);
    }
    box.textContent = message;
  }

  function clearBlockError(container) {
    const box = container && container.querySelector(":scope > .field-error");
    if (box) box.remove();
  }

  // Az `invalid` esemény nem buborékol, ezért capture fázisban figyeljük.
  document.addEventListener(
    "invalid",
    function (e) {
      const el = e.target;
      if (!(el instanceof HTMLElement) || !el.willValidate) return;
      e.preventDefault(); // natív, angol nyelvű buborék elnyomása
      showError(el, messageFor(el));

      // Az első hibás mezőre görgetünk és ráfókuszálunk. A böngésző a
      // hibás mezőket sorrendben jelenti, így az első hívás nyer.
      const form = el.form;
      if (form && !form.dataset.scrolledToError) {
        form.dataset.scrolledToError = "1";
        if (el.type !== "hidden" && el.offsetParent !== null) {
          el.scrollIntoView({ behavior: "smooth", block: "center" });
          try {
            el.focus({ preventScroll: true });
          } catch (_) {
            el.focus();
          }
        }
        setTimeout(() => delete form.dataset.scrolledToError, 0);
      }
    },
    true
  );

  // Gépelés / választás közben tűnjön el a hiba, amint érvényessé válik.
  ["input", "change"].forEach((evt) => {
    document.addEventListener(
      evt,
      function (e) {
        const el = e.target;
        if (!(el instanceof HTMLElement) || !el.willValidate) return;
        if (el.classList.contains("is-invalid") && el.checkValidity()) clearError(el);
      },
      true
    );
  });

  // Fókuszvesztéskor azonnal jelezzük a hibát — ne csak a küldésnél derüljön ki.
  document.addEventListener(
    "blur",
    function (e) {
      const el = e.target;
      if (!(el instanceof HTMLElement) || !el.willValidate) return;
      if (el.type === "checkbox" || el.type === "radio") return;
      if (el.value === "" && !el.dataset.touched) return; // üresen hagyott, még nem piszkált mező
      if (!el.checkValidity()) showError(el, messageFor(el));
    },
    true
  );

  document.addEventListener(
    "input",
    function (e) {
      if (e.target instanceof HTMLElement) e.target.dataset.touched = "1";
    },
    true
  );

  window.FormErrors = { show: showError, clear: clearError, showBlock: showBlockError, clearBlock: clearBlockError };
})();
