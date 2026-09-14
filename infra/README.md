# Lithophane Shop — telepítési útmutató

Ez a csomag ugyanazt az architektúrát követi, mint az MHA Candles oldal:
Amplify (statikus frontend) + API Gateway + Lambda (Python 3.12) + DynamoDB + SES.
Nincs saját szerver. A telepítés kézi lépésekből áll — az AWS Console-t
használd, vagy a saját CLI/CDK szkriptjeidet, ha azt preferálod.

## Amit ez a csomag tartalmaz

- `frontend/` — teljes statikus site: főoldal (videó hero),
  termékoldal, kosár, pénztár (Foxpost térképes csomagpont-választó
  ÉS házhozszállítás), köszönő-/státuszoldal, `galeria.html` az
  elkészült munkákkal, `kiprobalom.html` a 3D előnézeti eszközzel,
  és `kapcsolat.html` a teljes kapcsolatfelvételi oldallal. A
  design a meglévő `style.css`-ből jön.
- `backend/lambda/` — 7 Python 3.12 Lambda + egy közös modul-készlet.

## Amit ez a csomag NEM tartalmaz (kimaradt ebből a körből)

- A "Mi az a litofán?" szöveges/informatív oldal nincs portolva.
- Konkrét futárszolgálat-integráció (címke, feladás) nincs: a
  házhozszállítás a rendelésben rögzített cím, a csomagfeladás kézi.

## 1. DynamoDB

Hozz létre egy táblát:

- Név: `litho-orders`
- Partition key: `orderId` (String)
- Global Secondary Index: `paymentId-index`, partition key `paymentId` (String)
  — ez kell a Barion callback-hez, mert az csak a `paymentId`-t küldi vissza.

## 2. S3 (fotófeltöltés)

Hozz létre egy bucketet, pl. `litho-uploads-<accountid>`. Állítsd be a CORS-t:

```json
[
  {
    "AllowedOrigins": ["https://TE-DOMAINED.hu"],
    "AllowedMethods": ["PUT"],
    "AllowedHeaders": ["*"]
  }
]
```

A bucket maradjon privát (nincs public read). Az admin email a fotókra
S3 kulcsot ír, ne publikus URL-t — a kép megtekintéséhez a Console-ból
vagy egy presigned GET-tel érd el.

## 3. Lambda Layer a közös kódnak

Az öt fájl (`products.py`, `dynamo.py`, `barion.py`, `payments.py`,
`ses_mail.py`) egy közös Layerbe kerül, hogy ne kelljen minden
függvénybe bemásolni:

```
layer/
└── python/
    ├── products.py
    ├── dynamo.py
    ├── barion.py
    ├── payments.py
    └── ses_mail.py
```

Zippeld a `layer/` mappát, töltsd fel Lambda Layerként, és csatold
mind az 5 függvényhez.

## 4. Lambda függvények

| Függvény | Kód | Runtime | Env vars |
|---|---|---|---|
| `litho-get-products` | `backend/lambda/get_products` | Python 3.12 | — |
| `litho-get-upload-url` | `backend/lambda/get_upload_url` | Python 3.12 | `UPLOADS_BUCKET` |
| `litho-create-order` | `backend/lambda/create_order` | Python 3.12 | `ORDERS_TABLE`, `BARION_*` (lásd lent), `SITE_BASE_URL`, `SES_FROM_ADDRESS`, `ADMIN_EMAIL`, `BANK_ACCOUNT_NAME`, `BANK_ACCOUNT_NUMBER` |
| `litho-barion-callback` | `backend/lambda/barion_callback` | Python 3.12 | `ORDERS_TABLE`, `BARION_*`, `SES_FROM_ADDRESS`, `ADMIN_EMAIL`, `UPLOADS_BUCKET` |
| `litho-get-order-status` | `backend/lambda/get_order_status` | Python 3.12 | `ORDERS_TABLE`, `BARION_*`, `SES_FROM_ADDRESS`, `ADMIN_EMAIL`, `SITE_BASE_URL` |
| `litho-get-foxpost-lockers` | `backend/lambda/get_foxpost_lockers` | Python 3.12 | `CACHE_BUCKET` |
| `litho-send-contact-message` | `backend/lambda/send_contact_message` | Python 3.12 | `SES_FROM_ADDRESS`, `ADMIN_EMAIL` |

Handler minden esetben: `handler.handler`.

### IAM

Minden függvénynek kell:
- `dynamodb:PutItem`, `GetItem`, `UpdateItem`, `Query` a `litho-orders` táblára és a GSI-re.
- `litho-get-upload-url`: `s3:PutObject` a bucketre (a generate_presigned_url maga nem hívja az S3-at, de a policy kelljen a jogosultsághoz).
- `litho-create-order`: `ses:SendEmail` is szükséges (előre utalás esetén ez a
  függvény küldi ki az adatokat, nem a Barion callback).
- `litho-barion-callback`: `ses:SendEmail`.
- `litho-get-order-status`: `ses:SendEmail` is kell. Ez a függvény
  akkor is lezárja a fizetést (és küldi a visszaigazolást), ha a
  Barion IPN hívása elmaradt vagy késett — lásd a 9.2 pontot.
- `litho-get-foxpost-lockers`: `s3:GetObject` és `s3:PutObject` a
  bucket `cache/foxpost-lockers.json` kulcsára (ugyanaz a bucket
  használható, mint a fotófeltöltésnél, csak külön prefix alatt).
- `litho-send-contact-message`: `ses:SendEmail`.

### Barion környezeti változók

```
BARION_API_BASE=https://api.test.barion.com      # majd élesben: https://api.barion.com
BARION_POSKEY=<a Barion admin felületről>
BARION_PAYEE=<a Barion fiókodhoz tartozó email>
BARION_CALLBACK_URL=<az API Gateway litho-barion-callback végpontja>
BARION_REDIRECT_URL=https://TE-DOMAINED.hu/koszonjuk.html
```

Először a sandbox (`api.test.barion.com`) ellen teszteld végig a teljes
folyamatot, csak utána válts éles POSKey-re és `api.barion.com`-ra.

A `BARION_CALLBACK_URL` legyen publikusan elérhető (a Barion szervere
hívja, nem a böngésző). Ha rossz vagy elérhetetlen, a fizetés attól még
sikeres lesz — csak mi nem értesülünk róla azonnal; ilyenkor a
köszönőoldal lekérdezése zárja le a rendelést (9.2).

## 5. API Gateway (HTTP API)

| Metódus | Útvonal | Lambda |
|---|---|---|
| GET | `/products` | litho-get-products |
| POST | `/uploads` | litho-get-upload-url |
| POST | `/orders` | litho-create-order |
| POST | `/barion-callback` | litho-barion-callback |
| GET | `/orders/{orderId}` | litho-get-order-status |
| GET | `/foxpost-lockers` | litho-get-foxpost-lockers |
| POST | `/contact` | litho-send-contact-message |

Kapcsold be a CORS-t a `/products`, `/uploads`, `/orders*` útvonalakon
(a `/barion-callback`-ot a Barion szerverei hívják, oda nem kell CORS).

## 6. SES

Verifikáld a domained email címét (pl. `info@lithophaneshop.hu`).
Amíg sandbox módban vagy, csak verifikált címre mehet ki email — kérj
production access-t, mielőtt valós vásárlóknak küldenél.

## 7. Amplify

Ugyanaz, mint az MHA Candles oldalnál: kösd össze a GitHub repót,
`baseDirectory: frontend`, nincs build lépés (statikus fájlok).

Telepítés után írd be a `frontend/js/config.js`-be az API Gateway
alap URL-jét.

## 8. Foxpost integráció

A pénztár most egy valódi, térképes csomagpont-választót használ
(Leaflet.js, OpenStreetMap alap, nincs API-kulcs). Ez a Foxpost
**nyilvánosan közzétett** automata-listájára épül:

- `https://cdn.foxpost.hu/foxplus.json` — folyamatosan frissülő lista
  az összes automatáról (hely, cím, koordináták). Ehhez **nem kell
  kereskedői szerződés**, bárki letöltheti.
- Dokumentáció: `https://foxpost.hu/uzleti-partnereknek/integracios-segedlet`
  ("Csomagautomata lista" szakasz).

A `litho-get-foxpost-lockers` Lambda ezt a fájlt tölti le, 24 óránként
frissítve gyorsítótárazza S3-ban, és egy lecsupaszított JSON-t ad
vissza a frontendnek. Így a checkout nem a Foxpost szerverét terheli
minden látogatónál, és nem függ attól, hogy `cdn.foxpost.hu`
engedélyezi-e a böngészőből induló CORS-kéréseket.

**Amit ez NEM ad meg:** a tényleges csomagfeladást (címke generálása,
a rendelés automatikus átadása a Foxpost rendszerének). Ahhoz
kereskedői regisztráció és a FoxWEB API kell:
- Swagger dokumentáció: `https://webapi.foxpost.hu/swagger-ui/index.html`
- Magyar leírás: `https://foxpost.hu/uzleti-partnereknek/integracios-segedlet/webapi-integracio`

Amíg nincs meg ez a szerződés, a rendelés a `litho-orders` táblában
megvan a kiválasztott automata ID-jával és nevével együtt — a
csomagfeladást egyelőre kézzel, a Foxpost saját felületén intézed.
Ha megvan a szerződés, egy új Lambda (`litho-foxpost-submit`) tudja
majd automatizálni ezt is; szólj, ha ez kell.

**Házhozszállítás:** a pénztárban választható, a cím a rendeléssel
együtt eltárolódik (alapból a számlázási cím, de külön is megadható).
Futárszolgálati API-integráció (GLS/MPL címke, feladás) nincs — a
csomagfeladás egyelőre kézi. Szólj, ha melyiket kössük be.

## 9. Fizetés

### 9.1 Fizetési és szállítási módok

| Fizetés | Csomagautomata | Házhozszállítás | Rendelés státusza induláskor |
|---|---|---|---|
| Bankkártya (Barion) | ✔ | ✔ | `pending_payment` |
| Előre utalás | ✔ | ✔ | `pending_transfer` |
| Utánvét | ✖ | ✔ | `pending_cod` |

A párosítások egyetlen helyen, a `products.py` `PAYMENT_METHODS`
táblájában élnek. A frontend a `GET /products` válaszából tudja, mit
engedjen választani; a `create_order` ugyanezt újra ellenőrzi, tehát a
felület megkerülése sem visz át tiltott kombinációt.

- **Utánvét**: csomagautomatánál fizikailag sem működne (nem fogad
  készpénzt), ezért csak házhozszállításnál választható. Kezelési díja
  a `COD_FEE_HUF` (alapértelmezésben 0).
- **Előre utalás**: a vásárló azonnal emailt kap a `BANK_ACCOUNT_*`
  env változókban megadott számlaadatokkal. A beérkezést **kézzel**
  kell ellenőrizni, és a rendelés státuszát átállítani (nincs admin
  felület, DynamoDB Console-ból írható).
- **Szállítási díjak**: `FOXPOST_SHIPPING_FEE_HUF`,
  `HOME_DELIVERY_FEE_HUF`; `FREE_SHIPPING_THRESHOLD_HUF` felett
  mindkettő ingyenes. A házhozszállítás díja jelenleg 1990 Ft — ezt a
  tényleges futárszolgálati szerződés szerint kell átírni.

### 9.2 A bankkártyás fizetés útja

1. `create_order` kiszámolja az árat a katalógusból (a böngészőtől
   kapott árat soha nem fogadjuk el), elmenti a rendelést
   `payment_init` státusszal, majd hívja a Barion `/v2/Payment/Start`-ot.
2. Sikeres indítás után a rendelés `pending_payment`, a `paymentId`
   rákerül, és a vásárló a Barion `GatewayUrl`-jére megy.
3. A Barion minden állapotváltozásnál meghívja a
   `litho-barion-callback` végpontot (csak a `paymentId`-t küldi).
4. A callback **nem hiszi el** a hívás tényét: a
   `/v4/Payment/{id}/PaymentState` végpontról kérdezi le a valós
   állapotot (`x-pos-key` fejléccel), és az alapján zár.
5. A köszönőoldal a `GET /orders/{orderId}`-t kérdezi. Ha a rendelés
   még nyitott, ez a függvény is egyeztet a Barionnal — így egy
   elmaradt vagy késő IPN sem hagyja félbe a rendelést.

### 9.3 Hibás és elmaradt fizetések kezelése

| Barion `Status` | Rendelés státusza | Mi történik |
|---|---|---|
| `Succeeded` + egyező összeg | `paid` | Visszaigazoló email a vásárlónak, értesítés az adminnak. |
| `Succeeded` + eltérő összeg vagy pénznem | `payment_mismatch` | **Nem** teljesítjük. Admin értesítést kap, a vásárló azt látja, hogy ellenőrizzük. |
| `Failed` | `payment_failed` | Sikertelen-fizetés email, a vásárló újrapróbálhatja. |
| `Canceled` | `payment_canceled` | Ugyanaz, "megszakítottad" szöveggel. |
| `Expired` | `payment_expired` | Ugyanaz, lejárt fizetési ablak. |
| `PartiallySucceeded` | `payment_review` | Egy kedvezményezettnél rendellenes — kézi ellenőrzés, admin értesítés. |
| `Prepared` / `Started` / `InProgress` / `Waiting` / `Reserved` / `Authorized` | változatlan | A vásárló még a fizetőoldalon van. |
| a Barion API nem elérhető | változatlan | Naplózzuk; a következő callback vagy státuszlekérdezés újrapróbálja. |
| a Barion Start hívás hibázik | `payment_start_failed` | A vásárló magyar hibaüzenetet kap, a kísérlet nyoma megmarad. |

További garanciák:

- **Idempotencia.** A "fizetve" állapotba lépés feltételes DynamoDB
  írás (`transition_order_status`), ezért a Barion ötszöri
  újrahívásából is pontosan egy visszaigazoló email lesz.
- **Összegellenőrzés.** A Barionnál nyilvántartott végösszeget
  összevetjük a rendelés végösszegével; eltérésnél a rendelés nem
  teljesül, hanem kézi ellenőrzésre kerül.
- **Throttling.** A PaymentState végpont 429-et ad, ha ugyanarra a
  `PaymentId`-ra 5 másodpercen belül kétszer kérdezünk. Ezt külön
  kezeljük (`BarionThrottledError`): a státuszlekérdezés csak 6
  másodpercenként egyeztet, a köszönőoldal 3 másodpercenként kérdez.
- **Mindig 200.** A callback üzleti elutasításnál is 200-at ad, hogy a
  Barion ne induljon el újrapróbálkozási körre. Csak adatbázishibánál
  adunk 500-at, ott az újrahívás a helyes viselkedés.
- **A kosár nem vész el.** A frontend a rendelés leadásakor nem üríti a
  kosarat, csak a köszönőoldalon, sikeres rendelés után. Megszakított
  fizetés után a vásárló teli kosárral tér vissza.

### 9.4 Barion Smart Payment Banner

A Barion fejlesztői útmutatója (`infra/barion-smart-banner-dev-guide.pdf`)
előírja, hogy a bannernek változatlanul meg kell jelennie a shop
**nyitóoldalán és a fizetési oldalon** — ez a shop jóváhagyásának
feltétele. Ahol most van:

- `index.html` — footer,
- `penztar.html` — közvetlenül a fizetési módok alatt, görgetés nélkül
  látható helyen.

A fájlok: `frontend/assets/barion/` (SVG light/dark + PNG small/medium/
large mindkét módban). Világos háttérre a light változat való. A kép
arányt tart (`width:100%; height:auto`), nincs nyújtva vagy vágva, és
legalább 8px hely marad körülötte — mindezt a `.barion-banner`
osztály biztosítja a `style.css`-ben.

### 9.5 Tesztelés

- Automata teszt: `python3 backend/tests/test_payments.py` — a
  `payments.py` minden ága (sikeres, eltérő összegű, sikertelen,
  megszakított, lejárt, részben sikeres, ismételt callback, Barion
  hiba, throttling) AWS nélkül, memóriabeli DynamoDB/SES mellett.
- Helyben: `local-test/server.py` egy mock Barion oldalt szolgál ki,
  ahol a fizetés kimenete (sikeres / sikertelen / megszakított /
  lejárt / eltérő összegű) gombbal választható. Lásd
  `local-test/README.md`.
- Sandboxban: `api.test.barion.com` + a Barion tesztkártyái
  (`https://docs.barion.com/Making_a_test_payment`). A callback
  fogadásához a `BARION_CALLBACK_URL`-nek kívülről elérhetőnek kell
  lennie.

## 10. Foxpost térkép teljesítmény

A térkép nem tölti be az egész országos listát egyszerre — az induláskor
üres, csak egy útmutató szöveg látszik. Két esemény tölt be adatot:
- **Keresés** (`?city=`) — bármikor működik, zoom szinttől függetlenül.
- **Zoom/pan a térképen**, ha a zoom szint eléri a 12-t — ekkor a
  látható terület (`bbox`) alapján kér le automatákat.
Mindkét út a backend cache-elt listáját szűri, és legfeljebb 300
találatot ad vissza egyszerre, hogy a böngésző soha ne kapjon
több ezer markert egyben.

## Tesztelési sorrend

1. DynamoDB tábla + GSI létrehozása.
2. S3 bucket + CORS.
3. Lambda Layer feltöltése.
4. 7 Lambda létrehozása, env vars kitöltése (Barion sandbox kulccsal).
5. API Gateway route-ok bekötése, CORS bekapcsolása.
6. `config.js` frissítése az API URL-lel.
7. Amplify deploy.
8. Végigrendelés tesztelése a Barion sandbox tesztkártyáival —
   sikeres ÉS megszakított/sikertelen fizetéssel is (9.3).
9. Éles Barion POSKey-re váltás, SES production access, Foxpost szerződés.
