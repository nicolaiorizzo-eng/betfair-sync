# Betfair → Google Sheets Auto-Sync

Runs daily on GitHub Actions. No PC needed, no manual token pasting.

---

## One-time setup (takes ~10 minutes)

### Step 1 — Create a free GitHub account
Go to https://github.com and sign up if you don't have one.

### Step 2 — Create a new private repository
- Click **New repository**
- Name it e.g. `betfair-sync`
- Set it to **Private**
- Upload these 3 files:
  - `sync_engine.py`
  - `requirements.txt`
  - `.github/workflows/daily_sync.yml`

### Step 3 — Add your secrets
In your repo go to **Settings → Secrets and variables → Actions → New repository secret**

Add each of these:

| Secret name              | Value                                          |
|--------------------------|------------------------------------------------|
| `BETFAIR_APP_KEY`        | Your Betfair app key                           |
| `BETFAIR_USERNAME`       | Your Betfair email/username                    |
| `BETFAIR_PASSWORD`       | Your Betfair password                          |
| `GOOGLE_SHEET_NAME`      | Exact name of your Google Sheet                |
| `GOOGLE_CREDENTIALS_JSON`| The full contents of your service account JSON |

> For `GOOGLE_CREDENTIALS_JSON`: open your `.json` credentials file in a text editor,
> select all, copy, and paste the entire thing as the secret value.

### Step 4 — Test it manually
Go to **Actions → Betfair Daily Sync → Run workflow**
Click the green **Run workflow** button. Watch the logs — it should complete in under 30 seconds.

### Step 5 — You're done
It will now run automatically every day at 08:00 UTC.
You can change the time in `.github/workflows/daily_sync.yml` (the `cron` line).

---

## Changing the schedule
Edit the cron line in `daily_sync.yml`:
```
"0 8 * * *"   → 08:00 UTC daily
"0 6 * * *"   → 06:00 UTC daily
"0 20 * * *"  → 20:00 UTC daily
```
Use https://crontab.guru to build any schedule you want.

## Changing how many days to look back
Edit `DAYS_TO_FETCH: "2"` in `daily_sync.yml`.
The default is 2 days per run (safe overlap to catch any timezone edge cases).
