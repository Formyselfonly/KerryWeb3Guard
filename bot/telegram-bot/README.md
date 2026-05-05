# KerryWeb3Guard Telegram Bot (MVP)

Project Creator: Telegram `@kerryzheng`

This is a minimal Telegram bot that connects to KerryWeb3Guard backend APIs.

## Supported Commands

- `/start`
- `/help`
- `/lang <en|zh-CN>`
- `/contract <chain> <contract_address>`
- `/link <url>`
- `/chat <text>`

## Setup

```bash
cp .env.example .env
```

Fill `.env`:

- `TELEGRAM_BOT_TOKEN`
- `API_BASE_URL` (default `http://127.0.0.1:8000`)
- `DEFAULT_RESPONSE_LANGUAGE` (`en` or `zh-CN`)

## Multi-Bot Reuse (Single Codebase)

You can run Chinese and English bots using the same codebase:

1. Create two env files:
   - `.env.zh` (Chinese default)
   - `.env.en` (English default)
2. Set different `TELEGRAM_BOT_TOKEN` in each file.
3. Start two processes, each loading one env file.

Example env files:

`.env.zh`

```env
TELEGRAM_BOT_TOKEN=<zh_bot_token>
API_BASE_URL=http://127.0.0.1:8000
DEFAULT_RESPONSE_LANGUAGE=zh-CN
```

`.env.en`

```env
TELEGRAM_BOT_TOKEN=<en_bot_token>
API_BASE_URL=http://127.0.0.1:8000
DEFAULT_RESPONSE_LANGUAGE=en
```

This gives you two bots with shared logic and minimal maintenance cost.

Install dependencies and run:

```bash
uv sync
uv run python main.py
```

## Requirements

- KerryWeb3Guard backend running (`backend/risk-service`)
- Valid API keys configured in backend `.env`
