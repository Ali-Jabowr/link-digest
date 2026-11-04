# 0001. Recover missed links from an export, not a Telegram user session

Date: 2026-11-04
Status: Accepted

## Context
The Bot API keeps undelivered updates for about 24 hours and cannot read chat history, so links are lost while the laptop is off, and links sent before the bot joined cannot be read at all. A user session could read that history and catch up automatically on every start, which makes it look like the obvious improvement.

## Options
- Telethon user session: automatic catch-up, but adds a dependency and a session file with access to the owner's whole Telegram account.
- Always-on relay: fixes downtime but not old messages, and adds a service to run.
- Telegram Desktop JSON export read by an `import` command: manual, with no new credential or service.

## Decision
We will recover missed and old links only from a Telegram Desktop export. This bot must never hold a credential with access to the owner's whole Telegram account.

## Consequences
Catch-up takes a manual export, so the bot announces any downtime over 24 hours and gives the command to run. Revisit only if manual imports become frequent enough to justify that credential, or if Telegram offers bots a way to read history.
