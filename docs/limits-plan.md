# Plan: fixing the known limits

Decided 2026-11-04. Terms are defined in `CONTEXT.md`. The bot has not run in production yet, so these limits come from reading the code, not from real use.

## Decisions

| Limit | Decision |
| --- | --- |
| 1. Links lost after 24 hours off | Import from a Telegram Desktop export (ADR 0001). The bot records a timestamp each poll. If over 24 hours have passed at startup, it posts the offline period and the `import --since` command to run. |
| 2. Old messages can't be imported | The same Import. It previews the Link count and accepts `--since DATE`. New Links run first, imported ones run newest first, at most 5 imported a day (`--per-day`). New Links have no cap. |
| 3. Threads and in-post links | The whole same-author Thread goes in one Report with continuous `[¶n]`, and quoted posts become labelled paragraphs. A linked video post stays a video Source, with the Thread text in `post_text`. If the thread lookup fails, report the single post and say so in the summary. A Wrapper post (up to 280 characters, one Link) is digested from the linked page. Other posts list their Links at the end of the Report. |
| 4. Articles outside X | `trafilatura`, HTML only. Known video hosts go to yt-dlp. Everything else tries article extraction first, then yt-dlp if there is too little text. Paywalled or JavaScript-only pages get a clear failure message. |
| 5. FxTwitter sees lookups | Accepted: posts are public and Anthropic already sees their text. All FxTwitter calls stay in `x.py`, so the official X API remains the way out. |
| 6. Pro limits | Survive limits first. After a Claude failure, a tiny probe prompt tells the cases apart. If the probe fails, pause the queue, tell the group once, count no attempt, and probe again every 15 minutes. If it succeeds, the job counts an attempt. Retries reuse the fetched Source. Log prompt size, Report size and run time, then decide on Haiku or a cap from that data. |
| 7. Failed delivery reruns the job | Separate Digest from Delivery: save the result and record each sent step, so a retry only resends what is missing. Network errors and 429s keep retrying, backing off up to 5 minutes. Other Telegram rejections stop after 3 tries and leave the Report on disk. Send with `allow_sending_without_reply`. |

Also decided:
- Resending a failed Link queues it again. Done Links stay deduplicated.
- Read Links hidden behind words (`text_link` entities) in both the bot and the Import.
- Only the owner posts in the group, so there is no sender allowlist.

## Tickets

The spec is issue #2, and the tickets are the GitHub issues below. Each is one branch and one PR, tests first.

- **#3 Save the Digest and resend only what's missing** (limit 7): includes the DB migration.
- **#4 Keep Delivery retrying through outages** (limit 7). Needs #3.
- **#5 Deliver after the original message is deleted** (limit 7): changes two approved tests, with the owner's approval.
- **#6 Resend a failed Link to retry it.** Needs #3.
- **#7 Read hidden Links.**
- **#8 Reuse the Source on retry** (limit 6).
- **#9 Log Digest sizes** (limit 6).
- **#10 Pause when Claude is unavailable** (limit 6). Needs #8.
- **#11 Import from a Telegram Desktop export** (limit 2). Needs #7.
- **#12 Imported Links wait their turn** (limit 2): queue priority and the daily cap. Needs #11.
- **#13 Offline notice** (limit 1). Needs #11.
- **#14 Articles outside X** (limit 4): adds the `trafilatura` dependency.
- **#15 Whole Threads** (limit 3).
- **#16 Wrapper posts and listed Links** (limit 3). Needs #14.

## To verify when building

- The Telegram Desktop export format against a real export (#11).
- `/2/thread` on a real long Thread: it worked on one short post and looks undocumented (#15).
- Whether FxTwitter returns expanded URLs or `t.co` links (#16).
- `queue.fail` semantics are pinned by approved tests, so a paused job needs a separate path that leaves `attempts` unchanged (#10).
- `--output-format text` is pinned by an approved test, so the probe must not change `build_command` (#10).
