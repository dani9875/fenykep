# Helyi tesztelés (AWS deploy nélkül)

Ez a mód a teljes felhasználói folyamatot tesztelhetővé teszi a
böngészőben, mielőtt bármit telepítenél AWS-re. Nem valós fizetés,
nem valós email, nem valós S3 — de a kosár, méretválasztás,
fotófeltöltés, Foxpost térkép és a checkout logika mind él.

## Indítás

```
cd local-test
python3 server.py
```

Nyisd meg: http://localhost:8787

A `frontend/js/config.js` localhoston magától ezt a szervert hívja —
nincs mit átírni, és deploy után sem kell visszaállítani semmit: az
éles API URL-t a `scripts/deploy-frontend.sh` helyettesíti be egy
ideiglenes másolatban (lásd `infra/DEPLOY.md`).

## Mit tesztelhetsz ezzel

- Végigmenni a teljes vásárlói úton: termékválasztás → méret →
  fotófeltöltés → kosár → pénztár → Foxpost automata kiválasztása
  térképen → rendelés leadása → köszönőoldal.
- Szállítási módok: Foxpost csomagautomata (térképes választó) és
  házhozszállítás. Házhozszállításnál a "szállítási cím megegyezik a
  számlázási címmel" pipa kivételekor külön címmezők jönnek elő.
- Fizetési módok: bankkártya (Barion), előre utalás, és utánvét —
  az utánvét csak házhozszállításnál választható, csomagautomatánál
  a felület és a backend is tiltja.
- A "Rendelés leadása" gomb bankkártyás fizetésnél egy **helyi mock
  Barion oldalra** visz, ahol te döntöd el, mi történjen:
  sikeres · sikertelen · megszakított · lejárt · eltérő összegű fizetés.
  Így a hibás fizetések ágai (magyar hibaoldal, megmaradó kosár,
  kézi ellenőrzésre küldött rendelés) is végigjárhatók.
- A kosár csak sikeres rendelés után ürül. Megszakított fizetés után
  a vásárló a kosarával együtt tér vissza.
- A feltöltött fotók a `local-test/uploads/` mappába kerülnek.
- A "kiküldött" email szövege a terminálba íródik ki, nem megy sehova.
- A Foxpost térkép a valós, élő automata-listát tölti be
  (`cdn.foxpost.hu`), tehát internetkapcsolat kell hozzá.

## Automata tesztek

```
python3 backend/tests/test_payments.py     # fizetés-egyeztetés, AWS nélkül
node local-test/e2e-test.mjs               # végigkattintó teszt
```

Az e2e teszthez egyszer telepíteni kell a Playwrightot a repo gyökerében:
`npm install playwright && npx playwright install chromium`.

Az első a Barion-válaszok minden ágát végigjárja (sikeres, eltérő összegű,
sikertelen, megszakított, lejárt, ismételt callback) memóriabeli
DynamoDB/SES helyettesítőkkel. A második a böngészőben kattint végig a
teljes vásárláson a futó `server.py` ellen.

## Amit ez NEM tesztel

- Valódi Barion fizetést — a mock oldal csak a mi oldalunk ágait
  gyakorolja. A valódi kártyaelfogadás, a 3D Secure és az IPN
  (callback) időzítése csak a Barion sandboxban látszik; lásd
  `infra/README.md`.
- Valódi email kézbesítést (SES).
- AWS-specifikus dolgokat: IAM jogosultságok, DynamoDB teljesítmény,
  Lambda hidegindítás, API Gateway CORS a valós domainen.

## Amikor kész vagy a helyi teszteléssel

Kövesd az `infra/README.md`-t a valós AWS erőforrások
létrehozásához, majd a Barion sandbox-szal teszteld végig a fizetést
is, mielőtt élesbe váltanál.
