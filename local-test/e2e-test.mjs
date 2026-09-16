/**
 * Végigkattintó teszt a helyi szerver ellen (opcionális).
 *
 * Előfeltétel: fusson a `python3 local-test/server.py`.
 *
 * Telepítés (egyszer, a repo gyökerében — a node_modules gitignore-olt):
 *     npm install playwright
 *     npx playwright install chromium
 *
 * Futtatás:
 *     node local-test/e2e-test.mjs
 *
 * Mit ellenőriz: magyar űrlaphibák, szállítási módok és a "megegyezik a
 * számlázási címmel" pipa, Barion banner helye, galéria/kipróbálás fülek,
 * és a fizetés mindhárom kimenete a mock Barion oldalon.
 */

import { chromium } from 'playwright';

const BASE = 'http://localhost:8787';
const results = [];
const check = (name, ok, detail = '') => {
  results.push({ name, ok, detail });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? ' — ' + detail : ''}`);
};

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });

// kosár cookie beállítása
await ctx.addCookies([{
  name: 'litho_cart',
  value: encodeURIComponent(JSON.stringify([{
    cartItemId: 'c1', productId: 'lampa-nelkul', productName: 'Litofán – Lámpa nélkül',
    size: '15cm', qty: 1, unitPrice: 9990, photoKey: 'test.jpg',
  }])),
  url: BASE,
}]);

const page = await ctx.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(String(e)));
page.on('console', (m) => { if (m.type() === 'error') errors.push('console: ' + m.text()); });

/* ---------- index ---------- */
await page.goto(`${BASE}/index.html`);
check('index: nincs "Ugyanaz a kép" szekció', !(await page.content()).includes('Ugyanaz a kép'));
// A banner a lap alján van, lusta betöltéssel — le kell görgetni hozzá.
await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
await page.waitForTimeout(400);
check('index: Barion banner a footerben', await page.locator('.barion-banner--footer img').isVisible());
check('index: nav "Elkészült munkák"', /elkészült munkák/i.test(await page.locator('.site-nav a[href="galeria.html"]').innerText()));
check('index: nav "Próbáld ki" fül', await page.locator('.site-nav a[href="kiprobalom.html"]').count() === 1);

/* ---------- galéria ---------- */
await page.goto(`${BASE}/galeria.html`);
check('galéria: cím "Elkészült munkák"', (await page.locator('h1.section-title').innerText()).includes('Elkészült munkák'));
check('galéria: 9 kép', await page.locator('.gallery-thumb').count() === 9);
check('galéria: aktív fül', /elkészült munkák/i.test(await page.locator('.page-tab.is-active').innerText()));
check('galéria: nincs 3D próbáló', await page.locator('#ltoCanvas').count() === 0);

/* ---------- kipróbálom ---------- */
await page.goto(`${BASE}/kiprobalom.html`);
check('kipróbálom: 3D vászon jelen van', await page.locator('#ltoCanvas').count() === 1);
check('kipróbálom: aktív fül', /próbáld ki/i.test(await page.locator('.page-tab.is-active').innerText()));
check('kipróbálom: three.js betöltött', await page.evaluate(() => typeof window.THREE !== 'undefined'));

/* ---------- kipróbálom: kosárba tétel egy lépésben ---------- */
await ctx.clearCookies();
await page.goto(`${BASE}/kiprobalom.html`);
await page.waitForTimeout(1200);
const [chooser] = await Promise.all([
  page.waitForEvent('filechooser'),
  page.locator('#ltoUpload').click(),
]);
await chooser.setFiles('frontend/assets/gallery/g2-csaladikep.jpg');
// A panel becsúszó animációja miatt a Playwright "visible" heurisztikája
// nem nyugszik meg; az app által kapcsolt osztályra várunk.
await page.waitForFunction(
  () => document.getElementById('ltoOrderPanel')?.classList.contains('visible'),
  null, { timeout: 30000 });
await page.waitForTimeout(3000); // a 3D modell felépítése

check('kipróbálom: a gombon látszik az ár',
  /kosárba teszem · [\d\s]+ ft/i.test(await page.locator('#ltoOrderBtnText').innerText()),
  await page.locator('#ltoOrderBtnText').innerText());

// A folyamatosan rajzoló WebGL-vászon mellett a Playwright kattintása nem
// ül le ezeken az 1px-es, vizuálisan rejtett rádiógombokon — az app a
// change eseményre figyel, azt váltjuk ki közvetlenül.
await page.evaluate(() => {
  for (const value of ['led-talpas', '20cm']) {
    const radio = document.querySelector(`input[value="${value}"]`);
    radio.checked = true;
    radio.dispatchEvent(new Event('change', { bubbles: true }));
  }
});
await page.waitForTimeout(200);
const btnText = await page.locator('#ltoOrderBtnText').innerText();
check('kipróbálom: az ár követi a termék- és méretváltást', /17\s?990/.test(btnText), btnText);

// Közvetlen DOM-kattintás: a folyamatosan rajzoló 3D vászon mellett a
// Playwright "scroll into view" lépése nem ül le ezen az oldalon.
await page.evaluate(() => document.getElementById('ltoOrderBtn').click());
await page.waitForURL(/kosar/, { timeout: 20000 });
const cartText = await page.locator('.litho-cart-items').innerText();
check('kipróbálom: egyenesen a kosárba kerül, újratöltés nélkül',
  /LED talppal/.test(cartText) && /20CM|20cm/i.test(cartText),
  cartText.split('\n').slice(0, 3).join(' · '));
check('kipróbálom: a feltöltött kép előnézete is megvan a kosárban',
  await page.locator('.litho-cart-items img').first().getAttribute('src').then(src => !!src && src.startsWith('data:')));

/* ---------- pénztár: magyar validáció ---------- */
await page.goto(`${BASE}/penztar.html`);
check('pénztár: Barion banner a fizetési kártyán', await page.locator('.barion-banner--checkout img').isVisible());

await page.locator('button.litho-checkout-submit').click();
await page.waitForTimeout(400);
const firstErr = await page.locator('.field-error').first().innerText();
check('pénztár: magyar hibaüzenet üres mezőre', /Kérjük, töltsd ki/.test(firstErr), firstErr);
check('pénztár: több mező hibás', (await page.locator('.field-error').count()) >= 1);

await page.fill('#f-email', 'nem-email');
await page.locator('button.litho-checkout-submit').click();
await page.waitForTimeout(300);
const emailErr = await page.locator('#f-email').evaluate((el) => {
  const box = el.closest('.form-row').querySelector('.field-error');
  return box ? box.textContent : '';
});
check('pénztár: magyar e-mail hibaüzenet', /érvényes e-mail/.test(emailErr), emailErr);

/* ---------- pénztár: szállítási módok ---------- */
check('pénztár: utánvét tiltva Foxpostnál', await page.locator('#pay-cod-opt input').isDisabled());
await page.check('input[name="shipping_method"][value="home"]');
await page.waitForTimeout(200);
check('pénztár: házhozszállításnál eltűnik a térkép', await page.locator('#shipping-foxpost').isHidden());
check('pénztár: "megegyezik a számlázási címmel" alapból bepipálva', await page.locator('#f-same-address').isChecked());
check('pénztár: külön szállítási mezők rejtve', await page.locator('#shipping-address-fields').isHidden());
check('pénztár: utánvét engedélyezve házhozszállításnál', !(await page.locator('#pay-cod-opt input').isDisabled()));

await page.uncheck('#f-same-address');
await page.waitForTimeout(200);
check('pénztár: pipa kivétele megnyitja a szállítási mezőket', await page.locator('#shipping-address-fields').isVisible());
check('pénztár: szállítási mezők engedélyezettek', !(await page.locator('#f-ship-name').isDisabled()));

await page.check('#f-same-address');
await page.waitForTimeout(200);
check('pénztár: visszapipálva a mezők tiltottak', await page.locator('#f-ship-name').isDisabled());

await page.fill('#f-name', 'Teszt Elek');
await page.fill('#f-address', 'Fő utca 1');
await page.fill('#f-city', 'Budapest');
await page.fill('#f-zip', '1053');
await page.waitForTimeout(200);
const preview = await page.locator('#shipping-address-preview').innerText();
check('pénztár: szállítási cím előnézet a számlázásiból', preview.includes('Fő utca 1') && preview.includes('1053'), preview.replace(/\n/g, ' | '));

/* ---------- pénztár: szállítási díj a összegzőben ---------- */
const totals = await page.locator('#review-totals').innerText();
check('pénztár: házhozszállítás díja az összegzőben', /1\s?990 Ft/.test(totals), totals.replace(/\n/g, ' | '));

/* ---------- teljes rendelés: sikertelen fizetés ---------- */
await page.check('input[name="shipping_method"][value="foxpost"]');
await page.fill('#f-email', 'teszt@example.com');
await page.fill('#f-phone', '+36 30 123 4567');
await page.check('#f-aszf');
await page.check('#f-privacy');
await page.locator('button.litho-checkout-submit').click();
await page.waitForTimeout(400);
const lockerErr = await page.locator('#foxpost-error-host .field-error').innerText();
check('pénztár: automata hiánya magyarul szól', /csomagautomatát/.test(lockerErr), lockerErr);

// automata beállítása közvetlenül (a térkép interakciója külön kérdés)
await page.evaluate(() => {
  document.getElementById('f-locker-id').value = 'HU-TEST-1';
  document.getElementById('f-locker-name').value = 'Teszt automata — Fő utca 1';
});
await page.locator('button.litho-checkout-submit').click();
await page.waitForURL(/mock-barion/, { timeout: 5000 });
check('fizetés: átirányítás a (mock) Barion oldalra', page.url().includes('/mock-barion'));

await page.locator('button.outcome--failed').click();
await page.waitForURL(/koszonjuk/, { timeout: 5000 });
await page.waitForTimeout(1200);
const failText = await page.locator('#status-root').innerText();
check('köszönjük: sikertelen fizetés magyarul', /A fizetés nem sikerült/.test(failText), failText.split('\n')[1]);
check('köszönjük: újrapróbálás gomb', await page.locator('a[href="penztar.html"]').count() > 0);
const cartAfterFail = await ctx.cookies().then((cs) => cs.find((c) => c.name === 'litho_cart'));
check('köszönjük: sikertelen fizetés után megmarad a kosár',
  JSON.parse(decodeURIComponent(cartAfterFail.value)).length > 0);

/* ---------- piszkozat: újrapróbálásnál ne kelljen újra gépelni ---------- */
await page.locator('a[href="penztar.html"]').first().click();
await page.waitForURL(/penztar/, { timeout: 5000 });
await page.waitForTimeout(600);
check('újrapróbálás: a számlázási adatok visszatöltődtek',
  (await page.inputValue('#f-name')) === 'Teszt Elek' &&
  (await page.inputValue('#f-email')) === 'teszt@example.com' &&
  (await page.inputValue('#f-zip')) === '1053');
check('újrapróbálás: a csomagautomata is megmaradt',
  (await page.inputValue('#f-locker-id')) === 'HU-TEST-1' &&
  await page.locator('#fp-selected').isVisible());
check('újrapróbálás: az ÁSZF pipát újra be kell tenni',
  !(await page.locator('#f-aszf').isChecked()));
check('újrapróbálás: jelezzük, hogy visszatöltöttük az adatokat',
  await page.locator('#draft-restored').isVisible());

/* ---------- teljes rendelés: sikeres fizetés ---------- */
await page.goto(`${BASE}/penztar.html`);
await page.fill('#f-name', 'Teszt Elek');
await page.fill('#f-email', 'teszt@example.com');
await page.fill('#f-phone', '+36 30 123 4567');
await page.fill('#f-address', 'Fő utca 1');
await page.fill('#f-city', 'Budapest');
await page.fill('#f-zip', '1053');
await page.check('#f-aszf');
await page.check('#f-privacy');
await page.evaluate(() => {
  document.getElementById('f-locker-id').value = 'HU-TEST-1';
  document.getElementById('f-locker-name').value = 'Teszt automata';
});
await page.locator('button.litho-checkout-submit').click();
await page.waitForURL(/mock-barion/, { timeout: 5000 });
await page.locator('button.outcome--success').click();
await page.waitForURL(/koszonjuk/, { timeout: 5000 });
await page.waitForTimeout(1200);
const okText = await page.locator('#status-root').innerText();
check('köszönjük: sikeres fizetés magyarul', /Köszönjük a rendelésedet/.test(okText), okText.split('\n')[1]);
const cartAfterOk = await ctx.cookies().then((cs) => cs.find((c) => c.name === 'litho_cart'));
check('köszönjük: sikeres fizetés után ürül a kosár',
  !cartAfterOk || !decodeURIComponent(cartAfterOk.value).includes('lampa-nelkul'));

/* ---------- eltérő összeg ---------- */
await ctx.addCookies([{
  name: 'litho_cart',
  value: encodeURIComponent(JSON.stringify([{
    cartItemId: 'c1', productId: 'lampa-nelkul', productName: 'Litofán', size: '15cm',
    qty: 1, unitPrice: 9990, photoKey: 'test.jpg',
  }])),
  url: BASE,
}]);
await page.goto(`${BASE}/penztar.html`);
await page.fill('#f-name', 'Teszt Elek');
await page.fill('#f-email', 'teszt@example.com');
await page.fill('#f-phone', '+36301234567');
await page.fill('#f-address', 'Fő utca 1');
await page.fill('#f-city', 'Budapest');
await page.fill('#f-zip', '1053');
await page.check('#f-aszf');
await page.check('#f-privacy');
await page.evaluate(() => { document.getElementById('f-locker-id').value = 'HU-TEST-1'; });
await page.locator('button.litho-checkout-submit').click();
await page.waitForURL(/mock-barion/, { timeout: 5000 });
await page.locator('button.outcome--mismatch').click();
await page.waitForURL(/koszonjuk/, { timeout: 5000 });
await page.waitForTimeout(1200);
const mismatchText = await page.locator('#status-root').innerText();
check('köszönjük: eltérő összeg kézi ellenőrzésre megy', /ellenőrizzük|ellenőrzi/.test(mismatchText), mismatchText.split('\n')[1]);

/* ---------- kapcsolat űrlap magyar hibái ---------- */
await page.goto(`${BASE}/kapcsolat.html`);
await page.locator('#cf-submit').click();
await page.waitForTimeout(300);
const cfErr = await page.locator('.field-error').first().innerText();
check('kapcsolat: magyar hibaüzenet', /Kérjük/.test(cfErr), cfErr);

/* ---------- Foxpost automata kiválasztása ---------- */
// Ez a valódi Foxpost listát használja a helyi szerveren keresztül.
await page.goto(`${BASE}/penztar.html`);
await page.fill('#fp-search', 'Szeged');
await page.waitForSelector('#fp-list .fp-list-item', { timeout: 15000 });
const firstLocker = page.locator('#fp-list .fp-list-item').first();
const lockerLabel = (await firstLocker.innerText()).split('\n')[0];
await firstLocker.click();
await page.waitForTimeout(400);

check('foxpost: kattintásra bekerül a rejtett mezőbe',
  (await page.inputValue('#f-locker-id')).length > 0, lockerLabel);
check('foxpost: látszik a "Kiválasztva" visszajelzés',
  await page.locator('#fp-selected').isVisible() &&
  /Kiválasztva/.test(await page.locator('#fp-selected').innerText()));
check('foxpost: a kiválasztott sor ki van emelve',
  await page.locator('#fp-list .fp-list-item.is-selected').count() === 1);

// A kiválasztás térképmozgást vált ki; a rá következő újratöltés NEM
// törölheti a visszajelzést (korábban pont ez volt a hiba).
await page.waitForTimeout(1800);
check('foxpost: a kiválasztás túléli a térkép újratöltését',
  await page.locator('#fp-selected').isVisible() &&
  (await page.inputValue('#f-locker-id')).length > 0,
  'még mindig kiválasztva');

/* ---------- mobil nézet ---------- */
const mobile = await ctx.newPage();
await mobile.setViewportSize({ width: 390, height: 780 });
await mobile.goto(`${BASE}/penztar.html`);
const bannerBox = await mobile.locator('.barion-banner--checkout img').boundingBox();
check('mobil: Barion banner nem lóg ki', bannerBox && bannerBox.width <= 390, JSON.stringify(bannerBox));
const scrollW = await mobile.evaluate(() => document.documentElement.scrollWidth);
check('mobil: nincs vízszintes görgetés a pénztárban', scrollW <= 400, 'scrollWidth=' + scrollW);

console.log('\nJS hibák:', errors.length ? errors : 'nincs');
const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} teszt zöld`);
await browser.close();
process.exit(failed.length ? 1 : 0);
