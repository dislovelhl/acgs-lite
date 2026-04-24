# Telegram Webhook Integration

Use ACGS as the intake governance layer for a Telegram bot without embedding the bot token in your route or source code.

## Why this path is safer

- The webhook URL uses a dedicated path secret, not the bot token.
- Telegram can also send `X-Telegram-Bot-Api-Secret-Token` on every webhook call.
- The backend validates inbound message text with `GovernanceEngine` before replying.
- The webhook response uses Telegram's inline `sendMessage` format, so the bot token is only needed when you register the webhook.

## Backend setup

```python
from acgs_lite import Constitution
from acgs_lite.server import create_governance_app

constitution = Constitution.from_template("general")

app = create_governance_app(
    api_key="dev-api-key",           # Required in v2.10.0+ (require_auth defaults to True)
    constitution=constitution,
    include_telegram=True,
    telegram_webhook_path_secret="replace-with-random-path-secret",
    telegram_secret_token="replace-with-random-header-secret",
)
```

Run with FastAPI/Uvicorn as usual:

```bash
uvicorn myapp:app --host 0.0.0.0 --port 8000
```

## Recommended environment variables

```bash
export ACGS_TELEGRAM_WEBHOOK_PATH_SECRET='replace-with-32+-char-random-value'
export ACGS_TELEGRAM_SECRET_TOKEN='replace-with-32+-char-random-value'
export TELEGRAM_BOT_TOKEN='replace-with-botfather-token'
```

Then wire them into your app:

```python
import os

app = create_governance_app(
    api_key=os.environ["ACGS_API_KEY"],
    constitution=Constitution.from_template("general"),
    include_telegram=True,
    telegram_webhook_path_secret=os.environ["ACGS_TELEGRAM_WEBHOOK_PATH_SECRET"],
    telegram_secret_token=os.environ["ACGS_TELEGRAM_SECRET_TOKEN"],
)
```

## Register the webhook safely

Do not put the bot token in your backend route.
Use it only in the one-time Bot API call to Telegram.

Production domains already present in this repo:
- `api.acgs.ai` is configured as a production custom domain in `workers/governance-proxy/wrangler.toml`
- `acgs.ai/*` is also routed there at the Cloudflare layer

If you want the Telegram bot on the dedicated API host, use:

```bash
curl -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -H 'Content-Type: application/json' \
  -d '{
    "url": "https://api.acgs.ai/telegram/webhook/'"${ACGS_TELEGRAM_WEBHOOK_PATH_SECRET}"'",
    "secret_token": "'"${ACGS_TELEGRAM_SECRET_TOKEN}"'",
    "drop_pending_updates": true,
    "allowed_updates": ["message"]
  }'
```

If you prefer to keep bot traffic under the apex domain instead, the equivalent route is:

```text
https://acgs.ai/telegram/webhook/${ACGS_TELEGRAM_WEBHOOK_PATH_SECRET}
```

## Runtime behavior

- Safe text -> Telegram receives a `sendMessage` acknowledgement.
- Blocked text -> Telegram receives a governance-blocked response.
- Missing or wrong `X-Telegram-Bot-Api-Secret-Token` -> HTTP 401.

## Verification

```bash
python -m pytest tests/test_telegram_webhook.py -q
```

## Rotation guidance

If the bot token is ever exposed:

1. Rotate the token in BotFather.
2. Re-run `setWebhook` with the new token.
3. Keep the webhook path secret and header secret independent from the bot token.
4. Rotate the path/header secrets too if you suspect the webhook URL was exposed.
