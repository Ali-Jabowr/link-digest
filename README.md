# Link Digest

Turns a saved video or article link into a detailed report where every point cites
its source. Python 3.12, managed with uv.

## CLI

```sh
uv run link-digest <URL or local file> [--notes-dir DIR] [--html-dir DIR]
```

It takes X videos, X articles, X text posts, and videos from any other site yt-dlp
supports. Articles and text posts are cited by paragraph (`[¶3]`), videos by
timestamp.

X articles and text posts are read through the third-party public FxTwitter API
(`api.fxtwitter.com`), which sees the ids of the posts you read. Only the post
itself is read: threads and links inside a post are not followed.

It writes a Markdown note and an HTML report, and prints their paths and the
citation counts. `./scripts/smoke.sh` runs the whole thing with the real tools on a
known clip. `./.claude/verify.sh` is the full check (format, lint, types, tests).

## Telegram bot

The bot watches one Telegram group. Each new link in it is queued, digested, and
answered with a short summary and the HTML report. A link that was sent before is
not processed again, unless it failed: sending a failed link again retries it, and
reuses its report if one was already made.

1. Create a bot with BotFather (`/newbot`) and copy its token.
2. Turn off privacy mode with `/setprivacy` in BotFather, so the bot sees every
   message in the group.
3. Add the bot to the group.
4. Copy `deploy/env.example` to `~/.config/link-digest/env`, put the token after
   `TELEGRAM_BOT_TOKEN=`, and run `chmod 600 ~/.config/link-digest/env`.
5. Send any message in the group.
6. Run `link-digest-bot --print-chats` with the token in the environment, for
   example `set -a; . ~/.config/link-digest/env; set +a; uv run link-digest-bot
   --print-chats`. It prints `<chat id> <title>` for each chat the bot has seen.
7. Put the group's id after `LINK_DIGEST_CHAT_ID=` in the env file.
8. Copy `deploy/link-digest-bot.service` to `~/.config/systemd/user/`, then run
   `systemctl --user enable --now link-digest-bot`.

The unit expects the repo at `~/PROJECTS/link-digest` with its `.venv` built.
The queue lives in `~/.local/share/link-digest/queue.db`.
