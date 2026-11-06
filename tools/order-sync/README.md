# Rendelések → Google Sheet (Raspberry Pi)

A `sync_orders.py` beolvassa a rendeléseket a DynamoDB-ből, és frissíti a
Google Sheetet. Egy sor egy tétel (egy fotó).

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
a rendeléstáblát lehet olvasni, mást semmit.

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
cd ~/order-sync                              # ide másold: sync_orders.py, requirements.txt, google-service-account.json
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
```

```bash
chmod 600 .env google-service-account.json
source .env && .venv/bin/python sync_orders.py --dry-run   # csak kiírja, mit csinálna
source .env && .venv/bin/python sync_orders.py             # élesben
```

### Automatikusan, 15 percenként

`crontab -e`:

```
*/15 * * * * cd ~/order-sync && . ./.env && .venv/bin/python sync_orders.py >> sync.log 2>&1
```

## Ha élesre váltasz

Az éles táblának más lesz a neve. Írd át az `ORDERS_TABLE`-t, és kérj
kulcsot az éles `…-order-sync` felhasználóhoz.
