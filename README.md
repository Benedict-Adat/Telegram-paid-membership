# Telegram paid-membership bot

Flask receives Telegram and Coinbase Commerce webhooks, while SQLAlchemy stores users, groups, and memberships. The project now defaults to SQLite for local work; PostgreSQL can be selected with `DATABASE_URL`.

## Local setup

Use Python 3.11 or newer (the current code was validated with Python 3.14). Copy `.env.example` to `.env`, then fill in the required values. Do not commit `.env` or send secrets in chat. Generate random values for `FLASK_SECRET_KEY`, `TELEGRAM_WEBHOOK_SECRET`, and `DAILY_TASKS_TOKEN`; enter your Telegram and Coinbase credentials through the local `.env` file.

`PLATFORM_SHARE` is the fraction of each subscription paid to the group administrator (between `0` and `1`). Confirm the intended rate and minimum withdrawal before enabling real payments. The code uses `TELEGRAM_BOT_USERNAME` (not `TELEGRAM_USERNAME`), singular `ADMIN_CHAT_ID` and `STORAGE_CHAT_ID` (comma-separated ID lists are not supported), and `PERMISSIONS_PHOTO_ID` (not `PERMISSION_PHOTO_MESSAGE_ID`). The admin and storage IDs identify the operator's admin chat and storage photo; groups are registered by each group admin inside the bot, so there is no single hard-coded target group ID. The previously missing `application.data` module is replaced with a minimal set of menu keyboards and message builders; customize it if you need the original UI.

In PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env locally with your real values.
flask --app wsgi:app run --host 127.0.0.1 --port 5000
```

The local health endpoint is `http://127.0.0.1:5000/healthz`. It executes `SELECT 1` against the configured database and returns `503` if the database cannot be reached; it does not validate Telegram or Coinbase credentials. The application does not register a Telegram webhook unless `TELEGRAM_WEBHOOK_URL` is set; when set, use the full HTTPS URL including the `TELEGRAM_WEBHOOK_PATH`. Telegram and Coinbase webhooks require a reachable HTTPS deployment URL; configure Coinbase to call the configured Coinbase path. Telegram requests are checked against `TELEGRAM_WEBHOOK_SECRET`, Coinbase requests against `COINBASE_WEBHOOK_SECRET`. The daily-membership task is a `POST /triggerdailytasks` endpoint protected by a bearer token configured as `DAILY_TASKS_TOKEN`.

`DATABASE_URL` accepts a SQLite URL such as `sqlite:///membership.db` or a PostgreSQL URL. PostgreSQL support uses the included psycopg driver.

## Container deployment

The repository includes a Dockerfile and Compose file for container-based deployment. Build and run locally with Docker Desktop or another container engine:

```powershell
docker build -t telegram-paid-membership-bot .
docker run --rm -p 5000:5000 --env-file .env telegram-paid-membership-bot
```

Or with Compose:

```powershell
docker compose up --build
```

For a managed hosting provider such as Render, Railway, DigitalOcean App Platform, or ECS/Fargate, set the same environment variables from `.env.example` in the platform’s secret manager. The container will expose port `5000` and run `gunicorn` against `wsgi:app`.

For production persistence, use a managed PostgreSQL database and set `DATABASE_URL` to that connection string. SQLite is only suitable for local/offline tests.

### Render deployment

This repository includes a Render Blueprint at [render.yaml](./render.yaml). It provisions a web service and a PostgreSQL database in Oregon. Both currently use Render's free plan so you can validate without authorizing a paid service; Render free instances are not suitable for production, and free PostgreSQL has a limited lifetime. Upgrade both to paid plans before relying on this bot or processing real payments. You may change both `region` values together if another Render region is more appropriate.

To deploy:

1. Push the repo to GitHub.
2. Sign in to your Render account, choose **New > Blueprint**, and connect your GitHub repository. (Render Web Services can connect GitHub repositories; this project uses its Blueprint to create both the web service and database.)
3. Review the Blueprint's service and PostgreSQL resources. Confirm the free plans for an initial test, or select paid plans only after reviewing Render's current pricing.
4. Enter the prompted secret and site-specific values from `.env.example` in Render. Do not put credentials in `render.yaml` or the repository. `DATABASE_URL` is linked to the provisioned database automatically. For the initial deployment only, set `COINBASE_WEBHOOK_SECRET` to a securely generated temporary value; the app requires a non-empty secret to start. Render's `RENDER_EXTERNAL_URL` is used to derive Telegram's webhook and Coinbase's payment redirect URLs.
5. Deploy the backend first. The public `https://<your-service>.onrender.com` hostname is assigned by Render after deployment; you cannot know the actual webhook URL before then. The app registers Telegram's webhook using Render's hostname and `TELEGRAM_WEBHOOK_PATH` when it starts.
6. In Coinbase Commerce, add a webhook endpoint for `https://<your-service>.onrender.com/coinbase-webhook`. Copy that endpoint's signing secret into Render, replacing the temporary value in `COINBASE_WEBHOOK_SECRET`, then redeploy or restart the service so it loads the real secret.
7. Verify `https://<your-service>.onrender.com/healthz` returns HTTP `200` with `{ "status": "ok", "database": "ok" }`. A database error returns HTTP `503`.
8. For a paid production deployment, upgrade both the web service and database and confirm the database is backed up before handling real funds.

## Local ngrok stress test

Before switching to the real production host, validate the full flow locally against a public URL:

```powershell
# Terminal 1: run the app locally
flask --app wsgi:app run --host 0.0.0.0 --port 5000

# Terminal 2: expose it publicly
ngrok http 5000
```

Then set:

- `TELEGRAM_WEBHOOK_URL` to the ngrok HTTPS URL plus `/telegram-webhook`
- `COINBASE_WEBHOOK_SECRET` and the Coinbase webhook target to the ngrok HTTPS URL plus `/coinbase-webhook`

Trigger a mocked subscription or payment event and verify it updates the database and the bot state. Once that loop is stable, deploy the same configuration to Render and replace the temporary ngrok URL with the Render URL.

## MVP validation

Run the offline tests with:

```powershell
python -m unittest discover -s tests -v
```

Deposit attempts are persisted in the `payments` table before the Coinbase request. Each receives a local UUID reference that is sent in Coinbase charge metadata and saved with the returned charge code. The webhook verifies Coinbase's signature, looks up and locks the local payment record, then atomically marks it processed and credits the wallet. Unique constraints on the local reference and charge code, plus the processed-state check, prevent a repeated confirmation webhook from crediting twice. If charge creation has an ambiguous network failure, the attempt stays pending so a later signed webhook can be correlated by metadata; do not automatically retry a pending attempt as a new charge.

The tests mock the Coinbase API and Telegram calls; they do not create live charges or require real credentials. The suite covers database health, webhook guards, mock payment crediting and duplicate delivery, subscription debits, renewals, membership removal, and Coinbase charge handling. `db.create_all()` creates new tables on startup but does not migrate existing tables; back up the database and use a migration tool before future schema changes. Coinbase Commerce charge metadata is used as the local request reference; the app does not assume that Coinbase supports the generic `Idempotency-Key` header. Passing mocked tests is not a substitute for validating payment webhook retries and Telegram group access/revocation before enabling production payments.
