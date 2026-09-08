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

A `frontend/js/config.js` már alapból `http://localhost:8787`-re mutat,
nincs mit átírni. Ha éles AWS-re telepítesz, ott kell majd visszaírnod
a valódi API Gateway URL-re.

## Mit tesztelhetsz ezzel

- Végigmenni a teljes vásárlói úton: termékválasztás → méret →
  fotófeltöltés → kosár → pénztár → Foxpost automata kiválasztása
  térképen → rendelés leadása → köszönőoldal.
- A "Rendelés leadása" gomb után NEM megy ki Barionhoz — azonnal a
  köszönőoldalra ugrik, "fizetve" státusszal. Ez a mock szerver
  szándékosan kihagyja a fizetést.
- A feltöltött fotók a `local-test/uploads/` mappába kerülnek.
- A "kiküldött" email szövege a terminálba íródik ki, nem megy sehova.
- A Foxpost térkép a valós, élő automata-listát tölti be
  (`cdn.foxpost.hu`), tehát internetkapcsolat kell hozzá.

## Amit ez NEM tesztel

- Valódi Barion fizetést — ahhoz a sandbox integrációt kell
  végigcsinálni (lásd `infra/README.md`), mert a kártyás fizetési
  folyamat és a callback csak Barion szerverei felől jön.
- Valódi email kézbesítést (SES).
- AWS-specifikus dolgokat: IAM jogosultságok, DynamoDB teljesítmény,
  Lambda hidegindítás, API Gateway CORS a valós domainen.

## Amikor kész vagy a helyi teszteléssel

Kövesd az `infra/README.md`-t a valós AWS erőforrások
létrehozásához, majd a Barion sandbox-szal teszteld végig a fizetést
is, mielőtt élesbe váltanál.
