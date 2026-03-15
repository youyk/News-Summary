#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/Users/yongkang/projects/skills/News-Summary"
COLLECTOR="$ROOT_DIR/.agents/skills/hot-news-daily-brief/scripts/collect_news.py"
XHS_PLAYWRIGHT_COLLECTOR="$ROOT_DIR/.agents/skills/hot-news-daily-brief/scripts/collect_xiaohongshu_playwright.py"
OUT_DIR="$ROOT_DIR/data/inbox"
MANUAL_GLOB="$ROOT_DIR/data/inbox/manual/*.json"
XHS_PLAYWRIGHT_OUT="$ROOT_DIR/data/inbox/manual/xiaohongshu_playwright.json"
NEWS_ENV_FILE="$ROOT_DIR/scripts/news_sources.env"

if [[ -f "$NEWS_ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$NEWS_ENV_FILE"
fi

mkdir -p "$OUT_DIR" "$ROOT_DIR/data/inbox/manual"

if [[ "${ENABLE_XHS_PLAYWRIGHT:-0}" == "1" ]]; then
  XHS_CMD=(python3 "$XHS_PLAYWRIGHT_COLLECTOR" --out-file "$XHS_PLAYWRIGHT_OUT")
  if [[ -n "${XIAOHONGSHU_SHARE_URLS:-}" ]]; then
    XHS_CMD+=(--urls "$XIAOHONGSHU_SHARE_URLS")
  fi
  if [[ -n "${XIAOHONGSHU_URLS_FILE:-}" ]]; then
    XHS_CMD+=(--urls-file "$XIAOHONGSHU_URLS_FILE")
  fi
  if [[ -n "${XHS_PLAYWRIGHT_USER_DATA_DIR:-}" ]]; then
    XHS_CMD+=(--user-data-dir "$XHS_PLAYWRIGHT_USER_DATA_DIR")
  fi
  if [[ -n "${XHS_LOGIN_WAIT_SECONDS:-}" ]]; then
    XHS_CMD+=(--login-wait-seconds "$XHS_LOGIN_WAIT_SECONDS")
  fi
  if [[ -n "${XHS_MAX_ITEMS:-}" ]]; then
    XHS_CMD+=(--max-items "$XHS_MAX_ITEMS")
  fi
  if [[ "${XHS_PLAYWRIGHT_HEADLESS:-0}" == "1" ]]; then
    XHS_CMD+=(--headless)
  fi

  if ! "${XHS_CMD[@]}"; then
    if [[ "${XHS_PLAYWRIGHT_REQUIRED:-0}" == "1" ]]; then
      echo "[ERROR] Xiaohongshu Playwright collector failed and is required." >&2
      exit 1
    fi
    echo "[WARN] Xiaohongshu Playwright collector failed. Continuing without it." >&2
  fi
fi

python3 "$COLLECTOR" \
  --out-dir "$OUT_DIR" \
  --window-hours 24 \
  --manual-glob "$MANUAL_GLOB"
