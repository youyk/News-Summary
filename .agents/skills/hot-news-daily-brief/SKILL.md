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
- If Reddit endpoints are blocked, configure OAuth in local `scripts/news_sources.env`:
  - `REDDIT_CLIENT_ID`
  - `REDDIT_CLIENT_SECRET`
- Social-source options in local `scripts/news_sources.env`:
  - Weibo hot search: `WEIBO_COOKIE` (optional)
  - Toutiao hot board: `TOUTIAO_COOKIE` (optional)
  - X via Nitter RSS: `X_HANDLES`, `X_NITTER_INSTANCES`
  - RSS bridge (RSSHub, etc.): `X_RSS_URLS`, `XIAOHONGSHU_RSS_URLS`
  - Xiaohongshu Playwright mode: `ENABLE_XHS_PLAYWRIGHT=1`, `XIAOHONGSHU_SHARE_URLS` (or `XIAOHONGSHU_URLS_FILE`)

## Stage B (Offline Codex Summarizer)

Run this stage in Codex automation even when internet is blocked.

1. Load latest local candidate file from `./data/inbox/`.
2. Keep only items from past 24 hours using source timestamp fields.
3. Score hotness using `references/hotness-scoring.md`.
4. De-duplicate same-event stories.
5. Produce final digest in this exact order:
   - `Top 5 Most Important`
   - `当日总体总结（约300字）`
   - `数据源抓取与有效性（过去24小时）`
   - `[时政]`
   - `[金融]`
   - `[科技-AI]`
   - `[科技-其他]`
6. Save to:
   - `./Report/YYYY-MM-DD.md`

Use `references/two-stage-automation.md` for prompt templates.

Ranking rules:
- Each category section (`[时政]`, `[金融]`, `[科技-AI]`, `[科技-其他]`) should output Top3 stories by hotness whenever enough reliable candidates exist.
- `Top 5 Most Important` should be composed from section champions:
  - include Top1 from each of the four sections (4 items total),
  - plus one wildcard item (highest remaining hotness across all sections).

## Story Requirements

For every output story, include:
- `Title`
- `Why hot` (one sentence)
- `English summary` (single long-form paragraph, **at least 200 English words**)
- `中文总结` (4-6 bullets, covering facts, context, impact, and uncertainty)
- `English word count` (explicit number, must be `>= 200`)
- `Source URL` (1-3 links)
- `Published time` (absolute date/time with timezone)

Quality gates:
- Mark inference clearly when not directly supported by source facts.
- Keep neutral tone.
- Add a self-check before finalizing: if any story's English summary is under 200 words, expand it before output.
- Add `数据源抓取与有效性（过去24小时）` section based on `fetch_report` in latest candidate JSON:
  - list successful sources that entered filtering
  - list failed/unavailable sources for troubleshooting
- If a section has no reliable candidates, output `无可信高热度新闻`.

## Output Format

Use this exact top-level layout:

```markdown
# Daily Hot News Digest (YYYY-MM-DD)

## Top 5 Most Important (Cross-Category)
1. [时政] Section Top1 title
2. [金融] Section Top1 title
3. [科技-AI] Section Top1 title
4. [科技-其他] Section Top1 title
5. [Category] Wildcard next-best title

## 当日总体总结（约300字）
...

## 数据源抓取与有效性（过去24小时）
- 数据窗口: ...
### 成功抓取（本次进入候选池并参与筛选）
- ...
### 抓取失败或不可用（建议排查）
- ...

## [时政]
### 1) Story title
- Why hot: ...
- English summary (>= 200 words):
  ...
- 中文总结:
  - ...
  - ...
  - ...
  - ...
- English word count: 2xx words
- Source URL:
  - ...
- Published time: YYYY-MM-DD HH:MM (TZ)

### 2) Story title
...

### 3) Story title
...

## [金融]
...

## [科技-AI]
...

## [科技-其他]
...
```

Formatting rules:
- Put Top 5 before all sections.
- Top 5 must include one Top1 from each section, plus one wildcard item.
- Each section should provide Top3 stories when enough candidates exist; if fewer than 3 reliable items exist, explain with `无可信高热度新闻` for missing slots.
- Keep `当日总体总结` at around 300 Chinese characters.
- `数据源抓取与有效性` must reflect actual `fetch_report` results from local candidate file.
- Keep one story per heading.
- `English summary` must be long-form and information-dense; do not compress into short bullets.
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
   - This script validates digest quality before sending (word count, overall summary, source health section).
5. If Gmail API credentials are missing, optionally fall back to SMTP:
   - `python3 .agents/skills/hot-news-daily-brief/scripts/send_summary_email.py ...`

## Resources

- `references/source-universe.md`: source coverage checklist and fallback guidance.
- `references/hotness-scoring.md`: scoring rubric and tie-break rules.
- `references/two-stage-automation.md`: online/offline automation templates.
- `references/social-platform-access.md`: X/微博/小红书/头条 access options.
- `references/gmail-api-auth.md`: OAuth and token setup for Gmail API sending.
- `scripts/collect_news.py`: online collector that writes local candidate JSON.
- `scripts/gmail_oauth_bootstrap.py`: one-time helper to obtain OAuth refresh token.
- `scripts/render_digest_html.py`: render markdown digest into styled HTML email body.
- `scripts/send_summary_gmail_api.py`: Gmail API sender (OAuth refresh token).
- `scripts/send_summary_email.py`: SMTP fallback sender.
- `scripts/validate_digest.py`: pre-send quality gate validator.
