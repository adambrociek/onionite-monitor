# Onionite product monitor

Small monitor for:

https://onionite.pl/83-szafa-ziemniaka-wyprzedaz

It watches the category page for newly listed products, saves a local snapshot, and can open new product pages in your browser immediately.

## Run

```powershell
cd "C:\Users\kubam\Documents\New project\onionite-monitor"
.\run.cmd --open-browser
```

By default it checks every 30 seconds. Existing products are saved on the first run and are not treated as new unless you pass `--alert-existing`.

## Useful options

```powershell
.\run.cmd --interval 15 --open-browser
.\run.cmd --once --alert-existing
.\run.cmd --show-all
```

## Telegram alerts

The monitor supports Telegram notifications through a bot.

1. In Telegram, message `@BotFather` and create a bot.
2. Copy the bot token.
3. Send any message to your new bot.
4. Set the token in PowerShell and find your chat ID:

```powershell
$env:TELEGRAM_BOT_TOKEN = "123456789:replace_with_your_bot_token"
.\telegram-chat-id.cmd
```

5. Set the chat ID:

```powershell
$env:TELEGRAM_CHAT_ID = "123456789"
```

Then run:

```powershell
.\run.cmd --interval 15 --open-browser --telegram
```

There is also a template file at `telegram-env.example.ps1`.

If you prefer PowerShell flags, this also works on machines that allow scripts:

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1 -OpenBrowser
```

## Notes

- Keep the interval polite. The default is intentionally modest.
- This app alerts you and opens the normal product page. It does not bypass login, checkout, payment, rate limits, or the shop's normal purchase flow.
- Snapshot data is stored in `state\seen_products.json`.
