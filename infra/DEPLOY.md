# Dev deploy: frontend Cloudflare Pages, API AWS (Terraform)

Ez a doksi a **fejlesztői** környezetet állítja fel, végig parancsokból.
Kézi AWS Console-kattintgatás nincs benne — minden AWS erőforrást a
`infra/terraform/` állomány hoz létre.

```
  Cloudflare Pages                    AWS (eu-central-1)
  ┌────────────────┐   fetch   ┌──────────────────────────────┐
  │ statikus site  │ ────────► │ API Gateway (HTTP API)       │
  │ fenykep.pages  │           │   └─ 7 Lambda (python3.12)   │
  │      .dev      │           │        ├─ DynamoDB (orders)  │
  └────────────────┘           │        ├─ S3 (fotók + cache) │
         ▲                     │        └─ SES (e-mailek)     │
         │ redirect            └──────────────────────────────┘
         │                                   ▲
    Barion fizetőoldal ────────────────────── callback (IPN)
```

Amit használunk: **`wordpress-deploy`** AWS profil, **eu-central-1** régió,
**wrangler CLI** a Cloudflare-hez, **SES sandbox** e-mail cím hitelesítéssel.

---

## 0. Előfeltételek (egyszer)

```bash
# Hol állsz: a repo gyökerében
cd ~/Documents/source/fenykep

# Van-e AWS CLI és látja-e a profilt?
aws --version
aws sts get-caller-identity --profile wordpress-deploy
#   -> ha "Unable to locate credentials": aws configure --profile wordpress-deploy

# Terraform (ha még nincs)
#   Debian/Ubuntu:
wget -O - https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update && sudo apt install terraform
terraform version        # >= 1.5

# Node (a wranglerhez, npx-szel fut, nem kell külön telepíteni)
node --version           # >= 18
```

A `wordpress-deploy` profilnak ezekhez kell joga: IAM, Lambda, API Gateway,
DynamoDB, S3, SES, CloudWatch Logs. Ha korlátozott a profil, előbb ezt
intézd el — minden további lépés ezen áll vagy bukik.

---

## 1. Barion sandbox kulcs

1. Regisztrálj a **https://test.barion.com** oldalon (ez a sandbox, külön
   fiók az élestől).
2. Kereskedői fiók → **Shopok** → új shop → a **POSKey** kimásolása.
3. Jegyezd fel a fiókhoz tartozó e-mail címet is (ez lesz a `barion_payee`).

A callback és a redirect URL-t **nem kell** a Barion felületén beállítani:
minden fizetésindításkor átadjuk. A Terraform ezeket magától bedrótozza.

---

## 2. Cloudflare bejelentkezés

```bash
npx --yes wrangler@3 login          # böngészőt nyit, engedélyezed
npx --yes wrangler@3 whoami         # ellenőrzés
```

CI-ben vagy böngésző nélküli gépen ehelyett:
`export CLOUDFLARE_API_TOKEN=...` (Pages:Edit joggal).

---

## 3. Pages projekt létrehozása (ettől lesz URL-ed)

Ez azért van a Terraform **előtt**, mert a Barion visszairányításhoz és a
CORS-hoz már az apply pillanatában tudni kell a site URL-jét.

```bash
npx --yes wrangler@3 pages project create fenykep --production-branch main
```

Az URL: **`https://fenykep.pages.dev`**. Ha a név foglalt, a parancs szól —
válassz mást (pl. `fenykep-dev`), és azzal számolj a továbbiakban:

```bash
export CF_PAGES_PROJECT=fenykep-dev      # ha nem "fenykep" lett a neve
```

---

## 4. Terraform változók

```bash
cd infra/terraform
cp dev.auto.tfvars.example dev.auto.tfvars
${EDITOR:-nano} dev.auto.tfvars
```

Amit ki kell tölteni:

| Változó | Mit írj bele |
|---|---|
| `site_url` | `https://fenykep.pages.dev` (a 3. lépésből, záró `/` nélkül) |
| `barion_poskey` | a sandbox POSKey (1. lépés) |
| `barion_payee` | a Barion fiókod e-mail címe |
| `ses_from_address` | feladó cím, pl. `info@a-domained.hu` |
| `admin_email` | ide jönnek az „új rendelés" értesítők |
| `ses_verified_recipients` | **azok a teszt e-mail címek, amikkel rendelni fogsz** |
| `bank_account_number` | az utalásos e-mailhez |

A `dev.auto.tfvars` **gitignore-olt** — a POSKey nem kerül a repóba.
(A `terraform.tfstate` viszont tartalmazza, ezért az is ignorálva van;
ne másold máshová, és ne tedd publikus helyre.)

---

## 5. AWS oldal felhúzása

```bash
# még mindig: infra/terraform
terraform init
terraform plan        # nézd át: ~70 erőforrás jön létre
terraform apply       # "yes"
```

A profilt a Terraform a `dev.auto.tfvars`-ból veszi (`aws_profile =
"wordpress-deploy"`), nem kell `--profile` kapcsoló. Ha mégis felül akarod
írni egy parancsra:

```bash
terraform apply -var 'aws_profile=masik-profil'
```

Az apply végén megkapod az outputokat:

```bash
terraform output api_base_url          # https://xxxx.execute-api.eu-central-1.amazonaws.com
terraform output barion_callback_url
terraform output ses_identities_to_verify
terraform output next_steps
```

**Mit hozott létre:** DynamoDB tábla + `paymentId-index` GSI, S3 bucket
(privát, CORS a Pages domainre), Lambda Layer a közös modulokból, 7 Lambda
külön IAM szereppel, HTTP API a 7 útvonallal, CloudWatch log csoportok
14 napos megőrzéssel, és az SES identity-k.

---

## 6. SES e-mail címek hitelesítése

Az apply után az AWS küld egy-egy megerősítő levelet minden címre, ami a
`ses_identities_to_verify` outputban szerepel. **Kattints mindegyikben a
linkre**, különben nem megy ki egyetlen e-mail sem.

```bash
terraform output -json ses_identities_to_verify

aws ses get-identity-verification-attributes \
  --identities info@a-domained.hu te@example.com \
  --profile wordpress-deploy --region eu-central-1
# amit látni akarsz: "VerificationStatus": "Success"
```

> **SES sandbox szabály:** csak hitelesített címre lehet levelet küldeni.
> Ha egy teszt-rendelést olyan e-mail címmel adsz le, ami nincs
> hitelesítve, a rendelés létrejön és a fizetés is lemegy, de a
> visszaigazoló levél elhasal (a log `MessageRejected: Email address is
> not verified` sort ír). Ezért tedd be a teszt-címeidet a
> `ses_verified_recipients` listába, és futtass újra `terraform apply`-t.

---

## 7. Frontend kideployolása

```bash
cd ../..                      # vissza a repo gyökerébe
./scripts/deploy-frontend.sh
```

A szkript kiolvassa az API URL-t a Terraform outputból, egy ideiglenes
másolatban behelyettesíti a `js/config.js` `__API_URL__` helyőrzőjét, és
feltölti a wranglerrel. **A repóban lévő fájlok nem változnak**, tehát a
helyi tesztelés továbbra is a `localhost:8787`-re megy.

Preview deployhoz (külön, nem publikus URL):

```bash
./scripts/deploy-frontend.sh --preview
```

Ha a preview URL-ről is akarsz rendelést leadni, vedd fel az URL-t a
`extra_allowed_origins` listába, és futtass `terraform apply`-t —
különben a CORS elutasítja.

---

## 8. Végigtesztelés

```bash
API=$(terraform -chdir=infra/terraform output -raw api_base_url)

# 1) Katalógus
curl -s "$API/products" | head -c 300

# 2) Foxpost lista (első hívás lassabb: letölti és cache-eli S3-ba)
curl -s "$API/foxpost-lockers?city=Szeged" | head -c 300

# 3) Rendelés hibás adattal — magyar hibaüzenetet kell kapni
curl -s -X POST "$API/orders" -H 'content-type: application/json' -d '{}'
# {"error": "Hiányzó adat: teljes név."}
```

Utána a böngészőben a `https://fenykep.pages.dev` oldalon:
kosárba tesz → pénztár → Foxpost automata → **bankkártya** → a Barion
sandbox fizetőoldalán a teszt kártyaadatokkal
(https://docs.barion.com/Making_a_test_payment) fizetsz.

Élő logok közben:

```bash
aws logs tail /aws/lambda/litho-dev-create-order --follow \
  --profile wordpress-deploy --region eu-central-1

aws logs tail /aws/lambda/litho-dev-barion-callback --follow \
  --profile wordpress-deploy --region eu-central-1
```

A callback logjában ezt kell látnod:
`[barion] order=... payment=... status=Succeeded source=callback`

Rendelés megnézése az adatbázisban:

```bash
aws dynamodb scan --table-name litho-dev-orders --max-items 5 \
  --profile wordpress-deploy --region eu-central-1 \
  --query 'Items[].{id:orderId.S,status:orderStatus.S,total:totalHuf.N}'
```

Sikertelen fizetést is próbálj ki: a Barion sandbox oldalán szakítsd meg a
fizetést, és nézd meg, hogy a köszönőoldal magyarul azt írja-e, hogy
megszakítottad, és megmarad-e a kosár.

---

## 9. A napi fejlesztési ciklus

| Mit változtattál | Mit futtass |
|---|---|
| Csak frontend (HTML/CSS/JS) | `python3 local-test/server.py` a helyi teszthez, majd `./scripts/deploy-frontend.sh` |
| Lambda handler vagy `common/*.py` | `terraform -chdir=infra/terraform apply` (a zip hash változik, csak az érintett függvény frissül) |
| Ár, szállítási díj (`products.py`) | ugyanaz az apply — és utána frontend deploy is, mert a felirat onnan jön |
| Barion kulcs, e-mail cím, site URL | `dev.auto.tfvars` szerkesztése + `apply` |
| Új API útvonal | `api.tf` `routes` map + új Lambda mappa, majd `apply` |

A legtöbb fejlesztést **nem itt** érdemes csinálni: a `local-test/server.py`
a teljes folyamatot lejátssza AWS nélkül, mock Barion fizetőoldallal
együtt (lásd `local-test/README.md`). AWS-re akkor menj ki, amikor a
valódi Barion sandboxot, az SES-t vagy a CORS-t akarod tesztelni.

---

## 10. Éles üzembe váltás (majd)

1. `terraform apply -var 'name_prefix=litho-prod' -var 'environment=prod' ...`
   — vagy külön `prod.auto.tfvars` és külön state; a dev stacket **ne**
   nevezd át, mert akkor mindent újra létrehoz.
2. `barion_api_base = "https://api.barion.com"` + éles POSKey.
3. SES **production access** kérése (enélkül csak hitelesített címre megy
   levél):
   ```bash
   aws sesv2 put-account-details \
     --production-access-enabled \
     --mail-type TRANSACTIONAL \
     --website-url https://a-domained.hu \
     --use-case-description "Webshop rendelés-visszaigazoló e-mailek" \
     --profile wordpress-deploy --region eu-central-1
   ```
   Ehhez domain hitelesítés (DKIM) is kell — szólj, és megírom hozzá a
   Terraformot a Cloudflare DNS rekordokkal együtt.
4. Saját domain a Pages projektre (Cloudflare → Pages → Custom domains),
   utána `site_url` frissítése és `apply`.
5. ÁSZF és adatvédelmi tájékoztató kitöltése — a Barion ezt kéri a shop
   jóváhagyásához.

---

## 11. Lebontás

```bash
cd infra/terraform
terraform destroy
```

Az S3 bucket csak üresen törölhető. Ha maradt benne tesztfotó:

```bash
aws s3 rm "s3://$(terraform output -raw uploads_bucket)" --recursive \
  --profile wordpress-deploy --region eu-central-1
terraform destroy
```

A Cloudflare Pages projekt külön él:

```bash
npx --yes wrangler@3 pages project delete fenykep
```

---

## 12. Ha valami nem megy

| Tünet | Ok / megoldás |
|---|---|
| `terraform apply`: `InvalidClientTokenId` | rossz vagy lejárt profil — `aws sts get-caller-identity --profile wordpress-deploy` |
| `terraform apply`: `AccessDenied` IAM-ra | a `wordpress-deploy` profilnak nincs joga szerepet létrehozni |
| Böngészőben CORS hiba | a `site_url` / `extra_allowed_origins` nem egyezik a tényleges origin-nel (a preview URL más!) → javítsd és `apply` |
| A konzol azt írja: „Nincs beállítva az API URL" | a frontend nem a `deploy-frontend.sh`-val ment ki |
| Fotófeltöltés 403 | az S3 CORS ugyanazon a `allowed_origins` listán áll — nézd meg ugyanazt, mint fent |
| Nem jön e-mail | az SES cím nincs hitelesítve (6. lépés), vagy a címzett nincs hitelesítve sandboxban |
| A fizetés lemegy, de a rendelés `pending_payment` marad | a Barion nem éri el a callbacket. A köszönőoldal így is lezárja (a státuszlekérdezés maga is egyeztet) — a callback logjában nézd meg, jött-e hívás egyáltalán |
| `Barion rejected the payment` | rossz POSKey vagy payee, illetve sandbox kulcs éles API-val (vagy fordítva) |
| Lambda `Unable to import module` | a Layer nem frissült — `terraform apply` újra; a `common/*.py` változása a layer hash-ét módosítja |
