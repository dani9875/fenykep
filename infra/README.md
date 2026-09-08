# Lithophane Shop — telepítési útmutató

Ez a csomag ugyanazt az architektúrát követi, mint az MHA Candles oldal:
Amplify (statikus frontend) + API Gateway + Lambda (Python 3.12) + DynamoDB + SES.
Nincs saját szerver. A telepítés kézi lépésekből áll — az AWS Console-t
használd, vagy a saját CLI/CDK szkriptjeidet, ha azt preferálod.

## Amit ez a csomag tartalmaz

- `frontend/` — teljes statikus site: főoldal (videó hero, nappal/este
  összehasonlítás), termékoldal, kosár, pénztár (valódi Foxpost
  térképes csomagpont-választóval), köszönőoldal, `galeria.html` a
  fotórácsból és a 3D előnézeti eszközből, és `kapcsolat.html` a
  teljes kapcsolatfelvételi oldallal (infópanel + működő űrlap). A
  design a meglévő `style.css`-ből jön, változatlanul.
- `backend/lambda/` — 7 Python 3.12 Lambda + egy közös modul-készlet.

## Amit ez a csomag NEM tartalmaz (kimaradt ebből a körből)

- A "Mi az a litofán?" szöveges/informatív oldal nincs portolva.
- GLS és Posta szállítási mód a pénztárban látszik, de le van tiltva
  ("Hamarosan") — csak Foxpost aktív.

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

A négy fájl (`products.py`, `dynamo.py`, `barion.py`, `ses_mail.py`) egy
közös Layerbe kerül, hogy ne kelljen minden függvénybe bemásolni:

```
layer/
└── python/
    ├── products.py
    ├── dynamo.py
    ├── barion.py
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
| `litho-get-order-status` | `backend/lambda/get_order_status` | Python 3.12 | `ORDERS_TABLE` |
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

**GLS és Posta:** a pénztárban már látszik a két másik szállítási mód,
de "Hamarosan" felirattal le vannak tiltva. Ha ezekhez is van
nyilvános csomagpont-lista vagy API, ugyanígy be lehet kötni őket —
szólj, melyiket építsem meg először.

## 9. Fizetési módok

Három opció van a pénztárban:

- **Bankkártya (Barion)** — a meglévő online flow, azonnali visszaigazolás.
- **Előre utalással** — nincs Barion hívás. A rendelés `pending_transfer`
  státusszal jön létre, a vásárló azonnal kap egy emailt a
  `BANK_ACCOUNT_NUMBER` / `BANK_ACCOUNT_NAME` env változókban megadott
  számlaadatokkal. A fizetés beérkezését **kézzel** kell ellenőrizni és
  a rendelés státuszát átállítani — ehhez egyelőre nincs admin felület,
  DynamoDB Console-ból írható át.
- **Utánvét (készpénz)** — a felületen látszik, de le van tiltva. Foxpost
  csomagautomata nem fogad készpénzt, ezért ez fizikailag nem működne
  ezzel az egyetlen aktív szállítási móddal. Ha később bekerül a GLS
  házhozszállítás, ott már értelmes lehet — akkor kell hozzá backend
  logika is (a `create_order` jelenleg elutasítja `cod` + `foxpost`
  kombinációt).

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
8. Végigrendelés tesztelése a Barion sandbox tesztkártyáival.
9. Éles Barion POSKey-re váltás, SES production access, Foxpost szerződés.
