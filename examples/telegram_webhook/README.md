# Telegram webhook example

Use a dedicated path secret and Telegram's optional webhook secret token.
Do not embed the bot token in the webhook route, and do not persist it in app state.

## Suggested environment variables

```bash
export ACGS_TELEGRAM_WEBHOOK_PATH_SECRET="replace-with-random-path-secret"
export ACGS_TELEGRAM_SECRET_TOKEN="replace-with-random-header-secret"
export TELEGRAM_BOT_TOKEN="123456:replace-with-real-bot-token"
export PUBLIC_BASE_URL="https://governance.example.com"
```

## App wiring

```python
import os

from acgs_lite.server import create_governance_app

app = create_governance_app(
    include_telegram=True,
    telegram_webhook_path_secret=os.environ["ACGS_TELEGRAM_WEBHOOK_PATH_SECRET"],
    telegram_secret_token=os.environ.get("ACGS_TELEGRAM_SECRET_TOKEN"),
)
```

## Safe webhook registration

Telegram delivers the configured `secret_token` back to your app as the
`X-Telegram-Bot-Api-Secret-Token` header on each webhook request.

```bash
curl -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -d "url=${PUBLIC_BASE_URL}/telegram/webhook/${ACGS_TELEGRAM_WEBHOOK_PATH_SECRET}" \
  -d "secret_token=${ACGS_TELEGRAM_SECRET_TOKEN}"
```
