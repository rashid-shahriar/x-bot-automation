# X Auto-Post Bot (Python)

Automates posting on X (Twitter) **10 times per day** and checks the official developer guideline page for updates.

## Important note about credentials

Do **not** hardcode API keys in code. Use a local `.env` file (ignored by git).

Also, posting requires **user-context credentials**:

- `X_ACCESS_TOKEN`
- `X_ACCESS_TOKEN_SECRET`

A bearer token alone cannot publish tweets.

## Setup

1. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create `.env` from `.env.example` and fill values.

4. Add post content in `posts.txt` (one post per line).

## Run

```bash
.venv/bin/python bot.py
```

## How it works

- Posts are spread evenly across 24h based on `POSTS_PER_DAY` (default `10`).
- Next post text is loaded from `posts.txt` using round-robin order.
- Last used post index is persisted in `state/post_index.txt`.
- Guideline page hash is checked every `GUIDELINES_CHECK_HOURS` (default `6`).
- If the guideline page changes, a warning is logged.

## Config

See `.env.example` for all options:

- `POSTS_PER_DAY` (1-24)
- `TIMEZONE` (e.g. `UTC`, `Asia/Jakarta`)
- `GUIDELINES_URL`
- `GUIDELINES_CHECK_HOURS`
- `STATE_DIR`

## Next improvements

- Add retry + backoff for posting failures.
- Load content from templates + variables.
- Add media upload support.
- Send guideline-change alerts to email/Slack.
