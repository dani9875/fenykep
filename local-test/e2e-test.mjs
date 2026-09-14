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
  decodeURIComponent(cartAfterFail.value).includes('lampa-nelkul'));

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
