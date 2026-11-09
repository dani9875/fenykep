# Rendelések → Google Sheet, fotók → Google Drive (Raspberry Pi)

A `sync_orders.py` beolvassa a rendeléseket a DynamoDB-ből, és frissíti a
Google Sheetet. Egy sor egy tétel (egy fotó).

A fotókat az `rclone` másolja át egy Drive mappába, dátum szerinti
almappákba, beszédes névvel (rendelésszám, név, szállítási cím, tétel).
Ugyanez a fájlnév áll a Sheet „Fotó fájl” oszlopában, így a sorból a
fotó egy kereséssel megvan. Az rclone csak másol: a Drive-ból soha nem
töröl, és a már átmásolt fotót nem tölti le újra.

- A script csak a saját oszlopait írja (Tétel, Rendelésszám, Dátum, Állapot,
  Név, …, Fotó fájl). **A többi oszlop a tiéd**, azokhoz nem nyúl.
- Sort nem töröl. A meglévő sort a „Tétel” oszlop alapján találja meg,
  ezért a tábla szabadon rendezhető és szűrhető.
- Új oszlopot bárhová beszúrhatsz. A script fejléc alapján keresi a sajátjait.
  Ha egy saját oszlopát átnevezed, a következő futáskor újat hoz létre a végén.

## 1. AWS: olvasási kulcs (egyszer)

```bash
cd infra/terraform && terraform apply      # létrehozza a <prefix>-order-sync felhasználót
aws iam create-access-key --user-name litho-dev-order-sync --profile wordpress-deploy
```

Az `AccessKeyId` és a `SecretAccessKey` kell a Pi-re. Ezzel a kulccsal csak
a rendeléstáblát és a rendelések fotóit lehet olvasni, mást semmit.
A bucket nevét a `terraform output order_photos_bucket` írja ki.

## 2. Google: szolgáltatásfiók (egyszer)

1. console.cloud.google.com → új projekt (pl. „fenykep-sync”).
2. **APIs & Services → Library** → kapcsold be: **Google Sheets API** és **Google Drive API**.
3. **IAM & Admin → Service Accounts → Create** → név: `order-sync`, szerep nem kell.
4. A fiókon belül **Keys → Add key → JSON**. A letöltött fájlt nevezd át
   `google-service-account.json`-ra, és tedd a Pi-n a script mellé.
5. Nyisd meg a Sheetet → **Megosztás** → add hozzá a szolgáltatásfiók e-mail
   címét (`order-sync@….iam.gserviceaccount.com`) **Szerkesztő** joggal.

A Sheet azonosítója az URL-ben van: `docs.google.com/spreadsheets/d/`**`EZ`**`/edit`.

## 3. Raspberry Pi

```bash
sudo apt install -y python3-venv
cd ~/order-sync                              # ide másold: sync_orders.py, sync_all.sh, requirements.txt, google-service-account.json
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

`~/order-sync/.env`:

```bash
export AWS_ACCESS_KEY_ID=AKIA...
export AWS_SECRET_ACCESS_KEY=...
export AWS_REGION=eu-central-1
export ORDERS_TABLE=litho-dev-orders
export SHEET_ID=1AbC...
export SHEET_TAB=Rendelések
export ORDER_PHOTOS_BUCKET=litho-dev-uploads-0fd21d7e
export DRIVE_FOLDER="Fény·kép rendelések"
```

```bash
chmod 600 .env google-service-account.json
source .env && .venv/bin/python sync_orders.py --dry-run   # csak kiírja, mit csinálna
source .env && .venv/bin/python sync_orders.py             # élesben
```

## 4. Fotók a Google Drive-ba (rclone, egyszer)

```bash
curl https://rclone.org/install.sh | sudo bash     # az apt-os változat túl régi lehet
```

**AWS oldal** (a kulcsot a `.env`-ből veszi, nem kell újra beírni):

```bash
rclone config create aws s3 provider AWS env_auth true region eu-central-1
```

**Drive oldal.** A Pi-n nincs böngésző, ezért a Google bejelentkezés a
saját gépeden történik. A saját gépedre is telepítsd az rclone-t
(rclone.org/downloads), aztán a Pi-n:

1. `rclone config` → `n` (új) → név: `gdrive` → típus: `drive`.
2. client_id és client_secret: Enter (üresen hagyod) → scope: `drive.file`.
3. Az „Edit advanced config?” kérdésre `n`, a „Use web browser to
   automatically authenticate?” kérdésre `n`.
4. A Pi kiír egy `rclone authorize "drive" "…"` parancsot. Futtasd a
   **saját gépeden**: megnyílik a böngésző, jelentkezz be azzal a Google
   fiókkal, amelyiknek a Drive-jába a fotók kerüljenek. A végén kiír egy
   hosszú `{...}` szöveget, ezt illeszd be a Pi-n.
5. A többi kérdésre (pl. Shared Drive) `n` vagy Enter, a végén `y` és `q`.

A `drive.file` jog azt jelenti, hogy az rclone csak az általa létrehozott
mappához és fájlokhoz fér hozzá, a Drive többi részét nem látja.

Próba:

```bash
source .env && rclone copy "aws:$ORDER_PHOTOS_BUCKET/orders" "gdrive:$DRIVE_FOLDER" --s3-no-check-bucket --dry-run -v
```

A mappát (`Fény·kép rendelések`) az első futás hozza létre a Drive
gyökerében.

### Automatikusan, 15 percenként

`crontab -e`:

```
*/15 * * * * ~/order-sync/sync_all.sh >> ~/order-sync/sync.log 2>&1
```

A `sync_all.sh` előbb a Sheetet frissíti, utána a fotókat másolja.

## Ha élesre váltasz

Az éles táblának és bucketnek más lesz a neve. Írd át az `ORDERS_TABLE`-t
és az `ORDER_PHOTOS_BUCKET`-et, és kérj kulcsot az éles `…-order-sync`
felhasználóhoz.
