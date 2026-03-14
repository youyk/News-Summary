---
name: hot-news-daily-brief
description: Build a two-stage daily hot-news system for environments where Codex automation cannot access the internet. Stage A (online collector) fetches last-24-hour candidates from mainstream and community sources into local JSON files. Stage B (offline Codex summarizer) reads local candidates and outputs a bilingual digest with Top 5 plus [时政], [金融], [科技-AI], and [科技-其他]. Use when users need recurring news summaries, hot-story ranking, or email-ready reports under restricted-network automation.
---

# Hot News Daily Brief

## Goal

Run a resilient two-stage workflow:
- Stage A: collect and cache news while internet is available.
- Stage B: summarize from local files without internet.

Always prioritize verifiable impact over raw virality.

## Directory Convention

Use these default paths under project root:
- `./data/inbox/`: raw candidate files from Stage A
- `./Report/`: final markdown digests from Stage B

## Stage A (Online Collector)

Run this stage in an environment with internet access (local cron, cloud runner, or GitHub Actions).

1. Collect candidates:
   - `python3 .agents/skills/hot-news-daily-brief/scripts/collect_news.py --out-dir ./data/inbox --window-hours 24`

2. Verify output:
   - A new file: `./data/inbox/news_candidates_YYYYMMDDTHHMMSSZ.json`
   - Keep `fetch_report` for source success/failure visibility.

3. Optional manual source augmentation:
   - Add extra source files (`X/Twitter`, `Xiaohongshu`, proprietary feeds) to:
     - `./data/inbox/manual/*.json`
   - Re-run collector with:
     - `--manual-glob "./data/inbox/manual/*.json"`

Notes:
- Source checklist: `references/source-universe.md`
- Hotness scoring logic: `references/hotness-scoring.md`

## Stage B (Offline Codex Summarizer)

Run this stage in Codex automation even when internet is blocked.

1. Load latest local candidate file from `./data/inbox/`.
2. Keep only items from past 24 hours using source timestamp fields.
3. Score hotness using `references/hotness-scoring.md`.
4. De-duplicate same-event stories.
5. Produce final digest in this exact order:
   - `Top 5 Most Important`
   - `[时政]`
   - `[金融]`
   - `[科技-AI]`
   - `[科技-其他]`
6. Save to:
   - `./Report/YYYY-MM-DD.md`

Use `references/two-stage-automation.md` for prompt templates.

## Story Requirements

For every output story, include:
- `Title`
- `Why hot` (one sentence)
- `English summary` (2-4 bullets)
- `中文总结` (2-4 bullets)
- `Source URL` (1-3 links)
- `Published time` (absolute date/time with timezone)

Quality gates:
- Mark inference clearly when not directly supported by source facts.
- Keep neutral tone.
- If a section has no reliable candidates, output `无可信高热度新闻`.

## Output Format

Use this exact top-level layout:

```markdown
# Daily Hot News Digest (YYYY-MM-DD)

## Top 5 Most Important (Cross-Category)
1. [Category] Story title
2. [Category] Story title
3. [Category] Story title
4. [Category] Story title
5. [Category] Story title

## [时政]
### 1) Story title
- Why hot: ...
- English summary:
  - ...
  - ...
- 中文总结:
  - ...
  - ...
- Source URL:
  - ...
- Published time: YYYY-MM-DD HH:MM (TZ)

## [金融]
...

## [科技-AI]
...

## [科技-其他]
...
```

Formatting rules:
- Put Top 5 before all sections.
- Keep one story per heading.
- Keep bullet points short and concrete.
- Include absolute dates/times, not "today/yesterday".

## Optional Email Delivery

Preferred path: Gmail API OAuth (no SMTP dependency).

1. Authorize Gmail API once (see `references/gmail-api-auth.md`).
2. Set recipient in local env file `scripts/gmail.env` as `NEWS_DIGEST_TO`.
3. Choose mail content mode:
   - `NEWS_DIGEST_MAIL_CONTENT_MODE=plain` (plain text only)
   - `NEWS_DIGEST_MAIL_CONTENT_MODE=multipart` (plain + HTML, recommended)
   - `NEWS_DIGEST_MAIL_CONTENT_MODE=html-only` (HTML only)
4. Send report using stage script (auto-renders `./Report/YYYY-MM-DD.html` when needed):
   - `/bin/zsh /Users/yongkang/projects/skills/News-Summary/scripts/stage_c_send_gmail.sh`
5. If Gmail API credentials are missing, optionally fall back to SMTP:
   - `python3 .agents/skills/hot-news-daily-brief/scripts/send_summary_email.py ...`

## Resources

- `references/source-universe.md`: source coverage checklist and fallback guidance.
- `references/hotness-scoring.md`: scoring rubric and tie-break rules.
- `references/two-stage-automation.md`: online/offline automation templates.
- `references/gmail-api-auth.md`: OAuth and token setup for Gmail API sending.
- `scripts/collect_news.py`: online collector that writes local candidate JSON.
- `scripts/gmail_oauth_bootstrap.py`: one-time helper to obtain OAuth refresh token.
- `scripts/render_digest_html.py`: render markdown digest into styled HTML email body.
- `scripts/send_summary_gmail_api.py`: Gmail API sender (OAuth refresh token).
- `scripts/send_summary_email.py`: SMTP fallback sender.
