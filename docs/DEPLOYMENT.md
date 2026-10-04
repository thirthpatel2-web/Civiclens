# Deploying CivicLens

A step-by-step guide for putting CivicLens on a public server. Every step below was run end to end on a
clean clone: a fresh database, `docker compose up --build`, the seed scripts, the judgment-metadata
load, and the full demo flow from the video.

## What you need

| | Minimum | Notes |
|---|---|---|
| Server | 2 vCPU, 4 GB RAM, 20 GB disk, Ubuntu 22.04/24.04 | 8 GB RAM if you also run a local chat model in Ollama |
| Domain | a DNS **A record** pointing at the server | HTTPS is required for the microphone: browsers only allow it on `https://` or `localhost` |
| Ports | 80 and 443 open | nothing else needs to be public |
| Groq API key | for AI answers and voice (Whisper) | without it, the app still works and says which features are off |

## 1. Install Docker and get the code

```bash
curl -fsSL https://get.docker.com | sh
git clone https://github.com/thirthpatel2-web/Civiclens.git && cd Civiclens
cp .env.example .env
```

## 2. Fill in `.env`

Generate secrets with `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`.

| Setting | Value |
|---|---|
| `APP_ENV` | `production` |
| `APP_SECRET_KEY`, `SESSION_SECRET` | two different long random strings |
| `POSTGRES_PASSWORD` | a long random string (used by `docker-compose.prod.yml`) |
| `CIVICLENS_DOMAIN` | e.g. `civiclens.example.org` |
| `PUBLIC_BASE_URL` | `https://civiclens.example.org` - also marks the session cookie *Secure* |
| `GROQ_API_KEY`, `GROQ_MODEL` | e.g. `openai/gpt-oss-120b` |
| `STT_PROVIDER` | **`groq_whisper`** for voice. The default `auto` means "Bhashini if configured, otherwise no voice" |
| `GROQ_WHISPER_MODEL` | `whisper-large-v3` (best for Indian languages) or `whisper-large-v3-turbo` |
| `OLLAMA_EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS` | `nomic-embed-text`, `768` (semantic search over uploaded documents) |
| `ADMIN_SETUP_TOKEN` | a random string, used once to create the first administrator |
| `SMTP_*` | optional - without it, password-reset and update e-mails are recorded as "not sent", never faked |
| `RTI_PDF_FONT` | optional - a Unicode `.ttf` so RTI drafts in Indian scripts can be exported as PDF |

## 3. Start everything with HTTPS

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose exec ollama ollama pull nomic-embed-text
```

This starts Postgres (pgvector), Redis, Ollama, a one-shot migration job, the app, the background worker,
and Caddy, which obtains and renews the Let's Encrypt certificate on its own. Database migrations run
automatically before the app starts.

## 4. Load reference data (once)

```bash
docker compose exec app python scripts/seed.py                        # departments, cities, routing rules, helplines
docker compose exec app python scripts/ingest_legal_metadata_bulk.py  # 38,238 Supreme Court judgment records (public S3, ~5 min)
docker compose exec app python scripts/create_admin.py --email you@example.org --name "Your Name"
```

**For a demo deployment only** (judges, showcases), also create the demo accounts and sample complaints
that `docs/DEMO_GUIDE.md` and the demo video use:

```bash
docker compose exec -e DEMO_PASSWORD='choose-one' app python scripts/seed_demo.py
```

Never run `seed_demo.py` on a database that holds real citizens' data.

## 5. Check it

- `https://<your domain>/health` returns `200`.
- The landing page loads with a padlock; sign in; open the Voice Assistant and tap the mic (HTTPS needed).
- `docker compose logs -f app worker` shows no errors.

## Running it without Docker

Follow "Run it locally" in the README on a VM (Python 3.12, PostgreSQL 16+ with pgvector, Redis), set the same
`.env`, run `alembic upgrade head`, the scripts in step 4, then `python run.py` under a process manager
(systemd). Put Caddy or nginx in front for HTTPS, proxying to port 8080 with WebSocket upgrade enabled, and set
`FORWARDED_ALLOW_IPS` to the proxy's address.

## Operating it

- **Backups:** `python scripts/backup_database.py backup --out backups/` (schedule it daily), plus the
  `uploads` volume. Restore with `python scripts/backup_database.py restore <file> --yes`.
- **Updates:** `git pull && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`
  (the migration job runs first).
- **Never run the test suite against a production database.** Several tests write to whatever database
  `DATABASE_URL` points at.
- **Error tracking:** set `SENTRY_DSN` to collect errors (no personal data is sent).

## Security notes

- Two-factor sign-in is optional per account and enforced on the web sign-in for accounts that turn it on.
- The UI framework, NiceGUI 2.24, has published advisories fixed in the 3.x line. The ones that apply to
  CivicLens's usage are mitigated in the app (AI text is escaped before markdown, external payloads are shown as
  code, uploads are stored under generated names). Upgrading to NiceGUI 3.x is the planned follow-up.
- The three department systems are realistic **demo** systems; real departments need an MoU and real
  connector credentials (see `docs/CONNECTOR_GUIDE.md`).
