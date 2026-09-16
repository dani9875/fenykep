/**
 * A pénztár űrlapjának piszkozata.
 *
 * Miért kell: egy megszakadt vagy sikertelen bankkártyás fizetés után a
 * vásárló visszakerül a pénztárba. A kosarát megtartjuk — értelmetlen
 * lenne a nevét, címét és a csomagautomatát újra begépeltetni vele.
 *
 * Hol tárol: localStorage, a látogató saját böngészőjében. Nem megy
 * szerverre, és nem is kell hozzá: a rendelés adatai a leadáskor amúgy is
 * átmennek. A piszkozat a sikeres rendeléskor törlődik, azon kívül
 * legfeljebb MAX_AGE_DAYS napig él.
 *
 * Amit SZÁNDÉKOSAN nem tárol: az ÁSZF és az adatvédelmi tájékoztató
 * elfogadása. Azt minden rendelésnél tudatosan kell megtenni, nem
 * örökölhető egy korábbi kísérletből.
 */

const CheckoutDraft = (function () {
  "use strict";

  const KEY = "litho_checkout_draft";
  const MAX_AGE_DAYS = 7;

  // id -> hogyan olvassuk/írjuk
  const TEXT_FIELDS = [
    "f-name", "f-email", "f-phone", "f-address", "f-city", "f-zip", "f-notes",
    "f-ship-name", "f-ship-address", "f-ship-city", "f-ship-zip",
    "f-locker-id", "f-locker-name",
  ];
  const CHECKBOX_FIELDS = ["f-same-address"];
  const RADIO_GROUPS = ["shipping_method", "payment_method"];

  function read() {
    try {
      const raw = localStorage.getItem(KEY);
      if (!raw) return null;
      const draft = JSON.parse(raw);
      if (!draft || !draft.savedAt) return null;
      if (Date.now() - draft.savedAt > MAX_AGE_DAYS * 24 * 60 * 60 * 1000) {
        localStorage.removeItem(KEY);
        return null;
      }
      return draft;
    } catch (e) {
      return null; // sérült vagy letiltott localStorage — nem kritikus
    }
  }

  return {
    save() {
      const values = {};
      TEXT_FIELDS.forEach((id) => {
        const el = document.getElementById(id);
        if (el && el.value) values[id] = el.value;
      });
      CHECKBOX_FIELDS.forEach((id) => {
        const el = document.getElementById(id);
        if (el) values[id] = el.checked;
      });
      RADIO_GROUPS.forEach((name) => {
        const el = document.querySelector(`input[name="${name}"]:checked`);
        if (el) values[name] = el.value;
      });

      try {
        localStorage.setItem(KEY, JSON.stringify({ savedAt: Date.now(), values }));
      } catch (e) {
        // Tele a tároló vagy privát mód: a piszkozat elmarad, az űrlap működik.
      }
    },

    /**
     * Visszatölti a mentett értékeket. A visszatérés megmondja, volt-e
     * mit visszatölteni — a hívó ebből tud üzenetet mutatni.
     */
    restore() {
      const draft = read();
      if (!draft) return null;
      const values = draft.values || {};
      let restoredAnything = false;

      TEXT_FIELDS.forEach((id) => {
        const el = document.getElementById(id);
        if (el && values[id]) {
          el.value = values[id];
          restoredAnything = true;
        }
      });
      CHECKBOX_FIELDS.forEach((id) => {
        const el = document.getElementById(id);
        if (el && typeof values[id] === "boolean") el.checked = values[id];
      });
      RADIO_GROUPS.forEach((name) => {
        if (!values[name]) return;
        const el = document.querySelector(`input[name="${name}"][value="${values[name]}"]`);
        if (el && !el.disabled) el.checked = true;
      });

      return restoredAnything ? values : null;
    },

    clear() {
      try {
        localStorage.removeItem(KEY);
      } catch (e) {
        /* ignoráljuk */
      }
    },
  };
})();
