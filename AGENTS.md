# AGENTS.md: setting up Birthday Bot for a user

You are helping a human run their own copy of this bot on their machine.
Read README.md for the user-facing version. Here are the essentials.

## What it is

Three Docker Compose services: `db` (Postgres 16, named volume `db-data`), `api`
(FastAPI web UI + REST API on `${API_BIND:-127.0.0.1}:${API_PORT:-8000}`),
`bot` (python-telegram-bot, long-polling, talks to `http://api:8000`). Config
comes from `.env` (template: `.env.example`, every variable documented there).

## Ask the human for these (you can't get them yourself)

1. **Bot token** from @BotFather (`/newbot`). Treat it as a secret: don't echo it back, log it or paste it in commit messages.
2. **Telegram chat id**: a number, from @userinfobot or from
   `https://api.telegram.org/bot<TOKEN>/getUpdates` after they press Start on their bot.
3. **Timezone** as an IANA name (e.g. `Europe/London`).
4. Optional: whether the web UI should be reachable from other devices on
   their LAN (`API_BIND=0.0.0.0` + `WEB_APP_URL`), and a different reminder hour.

Generate `POSTGRES_PASSWORD` yourself (e.g. `openssl rand -hex 16`) unless
they already have a database. Never change it on an existing volume.

## Steps

```bash
cp .env.example .env            # then set BIRTHDAY_BOT_TOKEN, BIRTHDAY_BOT_CHAT_ID, TZ, POSTGRES_PASSWORD
docker compose up -d --build
```

Load data only if the user asks:

```bash
# sample (10 fictional people)
docker compose exec api python /scripts/import_birthdays.py /samples/sample-birthdays.csv
# their own CSV (name,birthday[YYYY-MM-DD],notes,gift_ideas[;-separated]) placed in ./data/
docker compose exec api python /scripts/import_birthdays.py /data/<file>.csv
```

## Verify

```bash
docker compose ps                                  # db + api "(healthy)", bot "Up" (not Restarting)
curl -fsS http://localhost:${API_PORT:-8000}/health    # {"status":"ok"}
curl -fsS http://localhost:${API_PORT:-8000}/api/dashboard
docker compose logs --tail=50 bot                  # expect "scheduler started" + no InvalidToken
```

Then ask the human to send `/start` to their bot in Telegram and confirm the
menu appears. `ignored message from unauthorized chat_id=N` in the bot log
means `BIRTHDAY_BOT_CHAT_ID` is wrong; N is the right value.

Tests:

```bash
docker compose run --rm --no-deps bot python -m unittest discover -s tests
docker compose run --rm --no-deps api sh -c "pip install -q httpx==0.27.2 && python -m unittest discover -s tests"
```

## Rules

- **Never commit `.env`, CSV/XLSX files with real people, database dumps or `backups/`.** `.gitignore` covers these, so don't override it with `git add -f`.
- **Never push personal data** (names, birthdays, chat ids, tokens) to any remote, issue, PR, paste site or log you share.
- **Never run `docker compose down -v`** on a real install without explicit confirmation: it deletes all data. Back up first (README, "Backing up your data").
- **The web UI has no authentication.** Don't bind it to a public interface or set up port forwarding. If remote access is wanted, recommend a VPN (e.g. Tailscale) or an authenticating proxy.
- Optional integrations (`HEALTHCHECKS_API_KEY`, SMTP, VAPID) must stay optional: blank means off, with no errors.
- Sample data must stay obviously fictional.
