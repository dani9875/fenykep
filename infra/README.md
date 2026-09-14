# Lithophane Shop — telepítési útmutató

Architektúra: **Cloudflare Pages** (statikus frontend) + **API Gateway +
Lambda (Python 3.12) + DynamoDB + S3 + SES** (AWS, eu-central-1). Nincs
saját szerver.

> **A telepítés lépésről lépésre: [DEPLOY.md](DEPLOY.md).**
> Ott vannak a konkrét parancsok, ebben a sorrendben, a `wordpress-deploy`
> profillal. Ez a fájl a *miért*-eket és a működés részleteit írja le.

Az AWS oldalt **Terraform** hozza létre (`infra/terraform/`), kézi
Console-kattintgatás nincs. A frontend a `scripts/deploy-frontend.sh`
szkripttel megy ki a Cloudflare-re.

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

## 1. Infrastruktúra (Terraform)

Minden AWS erőforrás az `infra/terraform/` állományból jön létre. A
fájlok szerepe:

| Fájl | Mi van benne |
|---|---|
| `versions.tf` | provider- és Terraform-verziók, state megjegyzések |
| `variables.tf` | minden hangolható érték (profil, régió, URL-ek, kulcsok) |
| `storage.tf` | DynamoDB tábla + `paymentId-index`, S3 bucket (privát, CORS, lifecycle) |
| `lambda.tf` | a közös Layer, a 7 függvény, log csoportok, env változók |
| `iam.tf` | függvényenként külön szerep, csak a szükséges jogokkal |
| `api.tf` | HTTP API, útvonalak, CORS, throttling |
| `ses.tf` | e-mail identity-k (sandbox hitelesítés) |
| `outputs.tf` | API URL, bucket- és táblanév, teendők az apply után |

Amit tudni érdemes róla:

- **Nincs külön build lépés.** A Lambda zipeket és a Layert maga a
  Terraform állítja elő a `backend/lambda/` forrásokból (`archive_file`),
  a hash alapján. Ha egy `.py` fájl változik, a következő `apply` csak
  az érintett függvényt frissíti.
- **A közös modulok Layerként** mennek fel (`python/products.py`,
  `python/barion.py`, …), így minden függvény `import barion`-nal éri el
  őket. A `common/` bármelyik fájljának változása a Layer új verzióját
  hozza létre, és mindegyik függvény átáll rá.
- **A Barion callback URL-jét a Terraform drótozza be**: az API
  `api_endpoint`-jából számolja, és env változóként adja a függvényeknek.
  Kézzel sehol nem kell URL-t másolgatni.
- **A `$default` stage auto-deploy** módban van, tehát az API URL-je
  végleges (nincs `/prod` utótag), és nincs külön „deploy" lépés.
- **Az S3 bucket neve véletlen utótagot kap** (`random_id`), mert a
  bucketnevek globálisan egyediek.

Új környezethez (pl. staging) ne másold a mappát: adj más `name_prefix`-et
és külön state-et.

## 2. Környezeti változók (mit mire használ a kód)

Ezeket a Terraform állítja be, kézzel nem kell velük foglalkozni. Itt
csak azért vannak felsorolva, hogy tudd, melyik változó mit vezérel.

| Változó | Hol kell | Mire való |
|---|---|---|
| `ORDERS_TABLE` | create_order, barion_callback, get_order_status | a rendelések DynamoDB táblája |
| `UPLOADS_BUCKET` | get_upload_url + a rendeléses függvények | a fotók bucketje (az admin e-mail az S3 kulcsot írja ki) |
| `CACHE_BUCKET` | get_foxpost_lockers | a Foxpost lista napi cache-e (`cache/` prefix) |
| `SITE_BASE_URL` | a rendeléses függvények | a köszönőoldal és az e-mailek linkjei |
| `SES_FROM_ADDRESS`, `ADMIN_EMAIL` | mindenhol, ahol e-mail megy | feladó és az admin értesítések címzettje |
| `BANK_ACCOUNT_NAME`, `BANK_ACCOUNT_NUMBER` | create_order | az utalásos fizetés e-mailjéhez |
| `BARION_API_BASE` | a rendeléses függvények | sandbox vagy éles Barion API |
| `BARION_POSKEY`, `BARION_PAYEE` | ugyanott | a shop azonosítása, a pénz címzettje |
| `BARION_CALLBACK_URL` | ugyanott | ezt kapja meg a Barion az IPN-hez |
| `BARION_REDIRECT_URL` | ugyanott | ide tér vissza a vásárló a fizetés után |

## 3. Jogosultságok

Minden Lambdának saját IAM szerepe van, és csak azt kapja meg, amire
szüksége van:

| Függvény | Jogok |
|---|---|
| `get-products` | csak log |
| `get-upload-url` | `s3:PutObject` a `uploads/` prefixre (a presigned URL aláírásához) |
| `get-foxpost-lockers` | `s3:GetObject`/`PutObject` a `cache/` prefixre |
| `create-order`, `barion-callback`, `get-order-status` | DynamoDB olvasás/írás a táblára és az indexre + `ses:SendEmail` a saját feladó címről |
| `send-contact-message` | `ses:SendEmail` |

Az SES jogot egy `ses:FromAddress` feltétel is szűkíti, tehát akkor sem
mehet levél más feladóval, ha a kód rosszul hívná.

## 4. Frontend (Cloudflare Pages)

A `frontend/js/config.js` nem tartalmaz környezetfüggő URL-t: localhoston
a `local-test/server.py`-t hívja, máshol a `__API_URL__` helyőrzőt, amit a
`scripts/deploy-frontend.sh` cserél ki deploykor egy ideiglenes
másolatban. Így a repóban nincs olyan fájl, amit deploy előtt át kellene
írni, és a helyi fejlesztés sem törik el egy deploy után.

## 5. SES

Dev: e-mail cím hitelesítés (sandbox). Az AWS küld egy megerősítő linket
minden címre — kattintás nélkül nem megy ki levél, és sandboxban a
**címzettnek** is hitelesítettnek kell lennie. Részletek és a production
access kérése: [DEPLOY.md](DEPLOY.md) 6. és 10. lépés.

## 6. Foxpost integráció

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

## 7. Fizetés

### 7.1 Fizetési és szállítási módok

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

### 7.2 A bankkártyás fizetés útja

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

### 7.3 Hibás és elmaradt fizetések kezelése

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

### 7.4 Barion Smart Payment Banner

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

### 7.5 Tesztelés

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

## 8. Foxpost térkép teljesítmény

A térkép nem tölti be az egész országos listát egyszerre — az induláskor
üres, csak egy útmutató szöveg látszik. Két esemény tölt be adatot:
- **Keresés** (`?city=`) — bármikor működik, zoom szinttől függetlenül.
- **Zoom/pan a térképen**, ha a zoom szint eléri a 12-t — ekkor a
  látható terület (`bbox`) alapján kér le automatákat.
Mindkét út a backend cache-elt listáját szűri, és legfeljebb 300
találatot ad vissza egyszerre, hogy a böngésző soha ne kapjon
több ezer markert egyben.

## Telepítési sorrend

Részletes parancsokkal: **[DEPLOY.md](DEPLOY.md)**. Dióhéjban:

1. `aws sts get-caller-identity --profile wordpress-deploy` — van-e hozzáférés.
2. Barion sandbox POSKey beszerzése.
3. `npx wrangler pages project create fenykep` — ettől lesz `site_url`-öd.
4. `infra/terraform/dev.auto.tfvars` kitöltése.
5. `terraform init && terraform apply`.
6. SES megerősítő linkek kikattintása.
7. `./scripts/deploy-frontend.sh`.
8. Végigrendelés a Barion sandbox tesztkártyáival — sikeres ÉS
   megszakított/sikertelen fizetéssel is (7.3).
9. Élesítés: éles POSKey + `api.barion.com`, SES production access,
   saját domain, ÁSZF/adatvédelem kitöltése.
