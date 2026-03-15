# Social Platform Access (X / Weibo / Xiaohongshu / Toutiao)

This project now supports a mixed strategy:
- `Automatic public collectors` for sources that provide reachable public endpoints.
- `Bridge RSS collectors` for platforms that need an RSS bridge (for example RSSHub).
- `Manual local import` when platform anti-bot/auth rules block automation.

All secrets must stay local in `scripts/news_sources.env` (gitignored).

## 1) Weibo

### What works
- Built-in collector: `Weibo Hot Search` via `https://weibo.com/ajax/side/hotSearch`.
- Cookie is optional. If requests are rate-limited, add `WEIBO_COOKIE`.

### Local setup
```bash
cp /Users/yongkang/projects/skills/News-Summary/scripts/news_sources.env.example \
  /Users/yongkang/projects/skills/News-Summary/scripts/news_sources.env
```

Add:
```bash
export WEIBO_COOKIE="SUB=...; SUBP=...; ..."
```

## 2) Toutiao

### What works
- Built-in collector: `Toutiao Hot Board` via `https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc`.
- Cookie is optional. Add `TOUTIAO_COOKIE` only when needed.

### Local setup
```bash
export TOUTIAO_COOKIE="ttwid=...; ..."
```

## 3) X (Twitter)

### What works in this pipeline
- Built-in best-effort collector via Nitter RSS mirrors.
- Configure target handles:
```bash
export X_HANDLES="openai,sama,techcrunch"
export X_NITTER_INSTANCES="https://nitter.net,https://nitter.poast.org"
```

### Important limitation
- Nitter availability depends on your network and mirror health.
- If all mirrors fail, use one of these fallbacks:
  - `Playwright fallback` with logged-in browser session (newly added).
  - `X_RSS_URLS` with your own RSS bridge.
  - Manual import JSON under `data/inbox/manual/`.

Playwright mode example:
```bash
export NEWS_SUMMARY_PLAYWRIGHT_PYTHON_BIN="/Users/yongkang/projects/skills/News-Summary/.venv/bin/python"
export ENABLE_SOCIAL_PLAYWRIGHT=1
export X_PLAYWRIGHT_HANDLES="openai,sama,elonmusk"
export SOCIAL_PLAYWRIGHT_LOGIN_WAIT_SECONDS=120
export SOCIAL_PLAYWRIGHT_HEADLESS=0
export SOCIAL_PLAYWRIGHT_CHANNEL="chrome"
# Optional explicit profile dir (default is project-local .cache path)
# export SOCIAL_PLAYWRIGHT_USER_DATA_DIR="/Users/yongkang/projects/skills/News-Summary/.cache/news-summary/social-playwright-profile"
```

## 4) Xiaohongshu

### Current practical path
- No stable built-in public API collector in this project.
- Recommended paths:
  - Use `Playwright collector` with your own logged-in session (newly added).
  - Or use RSS bridge endpoint and set `XIAOHONGSHU_RSS_URLS`.
  - Or use manual local JSON import.

Example:
```bash
export XIAOHONGSHU_RSS_URLS="https://rsshub.example.com/xiaohongshu/user/..."
```

Playwright mode example:
```bash
export NEWS_SUMMARY_PLAYWRIGHT_PYTHON_BIN="/Users/yongkang/projects/skills/News-Summary/.venv/bin/python"
export ENABLE_XHS_PLAYWRIGHT=1
export XIAOHONGSHU_SHARE_URLS="https://www.xiaohongshu.com/discovery/item/69b639970000000023004d55"
export XHS_LOGIN_WAIT_SECONDS=90
export XHS_PLAYWRIGHT_HEADLESS=0
export XHS_PLAYWRIGHT_CHANNEL="chrome"
# Optional explicit profile dir (default is project-local .cache path)
# export XHS_PLAYWRIGHT_USER_DATA_DIR="/Users/yongkang/projects/skills/News-Summary/.cache/news-summary/xhs-playwright-profile"
```

Then run:
```bash
/bin/zsh /Users/yongkang/projects/skills/News-Summary/scripts/stage_a_collect.sh
```

This generates/updates:
- `/Users/yongkang/projects/skills/News-Summary/data/inbox/manual/xiaohongshu_playwright.json`

## 4.5) Reddit fallback via Playwright

When Reddit JSON/RSS is blocked, you can collect from browser-rendered pages:

```bash
export NEWS_SUMMARY_PLAYWRIGHT_PYTHON_BIN="/Users/yongkang/projects/skills/News-Summary/.venv/bin/python"
export ENABLE_SOCIAL_PLAYWRIGHT=1
export REDDIT_PLAYWRIGHT_SUBREDDITS="news,worldnews,technology,artificial"
export SOCIAL_PLAYWRIGHT_LOGIN_WAIT_SECONDS=120
export SOCIAL_PLAYWRIGHT_HEADLESS=0
export SOCIAL_PLAYWRIGHT_CHANNEL="chrome"
```

This generates/updates:
- `/Users/yongkang/projects/skills/News-Summary/data/inbox/manual/social_playwright.json`

When this file contains `Reddit (Playwright) r/...` or `X (Playwright) @...` entries,
the main collector auto-converts corresponding `Reddit r/...` / `X @...` fetch failures
into `playwright_fallback` success status in `fetch_report`.

## 5) Manual Local Import (all platforms)

Use this when API/bridge access is blocked.

Create JSON files under:
- `/Users/yongkang/projects/skills/News-Summary/data/inbox/manual/*.json`
- You can copy template from:
  - `/Users/yongkang/projects/skills/News-Summary/scripts/manual_source_template.json.example`

Supported schema:
```json
{
  "items": [
    {
      "title": "Example story title",
      "url": "https://example.com/post/1",
      "source": "X @example",
      "source_group": "social_community",
      "category_hint": "科技-AI",
      "summary_hint": "Optional short hint",
      "published_at": "2026-03-15T06:30:00+08:00",
      "hotness_signals": {
        "editorial_prominence": 4,
        "engagement_velocity": 4,
        "cross_source_pickup": null,
        "source_authority": 2,
        "public_impact_scope": null
      }
    }
  ]
}
```

## 6) Security Checklist

- Keep only placeholders in committed files.
- Never commit real values for:
  - cookies
  - API keys
  - OAuth tokens
- Confirm `.gitignore` contains `scripts/news_sources.env` and `scripts/gmail.env`.
