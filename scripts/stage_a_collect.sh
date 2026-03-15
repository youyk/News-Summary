#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/Users/yongkang/projects/skills/News-Summary"
COLLECTOR="$ROOT_DIR/.agents/skills/hot-news-daily-brief/scripts/collect_news.py"
XHS_PLAYWRIGHT_COLLECTOR="$ROOT_DIR/.agents/skills/hot-news-daily-brief/scripts/collect_xiaohongshu_playwright.py"
SOCIAL_PLAYWRIGHT_COLLECTOR="$ROOT_DIR/.agents/skills/hot-news-daily-brief/scripts/collect_social_playwright.py"
OUT_DIR="$ROOT_DIR/data/inbox"
MANUAL_GLOB="$ROOT_DIR/data/inbox/manual/*.json"
XHS_PLAYWRIGHT_OUT="$ROOT_DIR/data/inbox/manual/xiaohongshu_playwright.json"
SOCIAL_PLAYWRIGHT_OUT="$ROOT_DIR/data/inbox/manual/social_playwright.json"
NEWS_ENV_FILE="$ROOT_DIR/scripts/news_sources.env"
PYTHON_BIN="${NEWS_SUMMARY_PYTHON_BIN:-python3}"
PLAYWRIGHT_PYTHON_BIN="${NEWS_SUMMARY_PLAYWRIGHT_PYTHON_BIN:-$PYTHON_BIN}"
DEFAULT_SOCIAL_PLAYWRIGHT_PROFILE="$ROOT_DIR/.cache/news-summary/social-playwright-profile"
DEFAULT_XHS_PLAYWRIGHT_PROFILE="$ROOT_DIR/.cache/news-summary/xhs-playwright-profile"
EFFECTIVE_MANUAL_GLOB="$MANUAL_GLOB"
FILTERED_MANUAL_DIR=""

if [[ -f "$NEWS_ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$NEWS_ENV_FILE"
fi

mkdir -p "$OUT_DIR" "$ROOT_DIR/data/inbox/manual"
mkdir -p "$ROOT_DIR/.cache/news-summary"

cleanup() {
  if [[ -n "$FILTERED_MANUAL_DIR" && -d "$FILTERED_MANUAL_DIR" ]]; then
    rm -rf "$FILTERED_MANUAL_DIR"
  fi
}
trap cleanup EXIT

# In baseline mode (Playwright disabled), avoid ingesting stale auto-generated
# manual files from previous recovery runs unless explicitly requested.
if [[ "${PLAYWRIGHT_USE_LAST_MANUAL_FILES:-0}" != "1" ]]; then
  EXCLUDE_MANUAL_FILES=()
  if [[ "${ENABLE_SOCIAL_PLAYWRIGHT:-0}" != "1" ]]; then
    EXCLUDE_MANUAL_FILES+=("social_playwright*.json")
  fi
  if [[ "${ENABLE_XHS_PLAYWRIGHT:-0}" != "1" ]]; then
    EXCLUDE_MANUAL_FILES+=("xiaohongshu_playwright*.json")
  fi

  if [[ ${#EXCLUDE_MANUAL_FILES[@]} -gt 0 ]]; then
    FILTERED_MANUAL_DIR="$(mktemp -d "$ROOT_DIR/.cache/news-summary/manual-filter.XXXXXX")"
    while IFS= read -r -d '' src; do
      base="$(basename "$src")"
      skip=0
      for excluded in "${EXCLUDE_MANUAL_FILES[@]}"; do
        if [[ "$base" == $excluded ]]; then
          skip=1
          break
        fi
      done
      if [[ "$skip" -eq 0 ]]; then
        ln -s "$src" "$FILTERED_MANUAL_DIR/$base"
      fi
    done < <(find "$ROOT_DIR/data/inbox/manual" -maxdepth 1 -type f -name '*.json' -print0)
    EFFECTIVE_MANUAL_GLOB="$FILTERED_MANUAL_DIR/*.json"
  fi
fi

if [[ "${ENABLE_SOCIAL_PLAYWRIGHT:-0}" == "1" ]]; then
  SOCIAL_CMD=("$PLAYWRIGHT_PYTHON_BIN" "$SOCIAL_PLAYWRIGHT_COLLECTOR" --out-file "$SOCIAL_PLAYWRIGHT_OUT")
  if [[ -n "${REDDIT_PLAYWRIGHT_SUBREDDITS:-}" ]]; then
    SOCIAL_CMD+=(--reddit-subreddits "$REDDIT_PLAYWRIGHT_SUBREDDITS")
  fi
  if [[ -n "${X_PLAYWRIGHT_HANDLES:-}" ]]; then
    SOCIAL_CMD+=(--x-handles "$X_PLAYWRIGHT_HANDLES")
  fi
  SOCIAL_PROFILE_DIR="${SOCIAL_PLAYWRIGHT_USER_DATA_DIR:-$DEFAULT_SOCIAL_PLAYWRIGHT_PROFILE}"
  SOCIAL_CMD+=(--user-data-dir "$SOCIAL_PROFILE_DIR")
  if [[ -n "${SOCIAL_PLAYWRIGHT_LOGIN_WAIT_SECONDS:-}" ]]; then
    SOCIAL_CMD+=(--login-wait-seconds "$SOCIAL_PLAYWRIGHT_LOGIN_WAIT_SECONDS")
  fi
  if [[ -n "${SOCIAL_PLAYWRIGHT_MAX_PER_SOURCE:-}" ]]; then
    SOCIAL_CMD+=(--max-per-source "$SOCIAL_PLAYWRIGHT_MAX_PER_SOURCE")
  fi
  if [[ -n "${SOCIAL_PLAYWRIGHT_DELAY_MIN_SECONDS:-}" ]]; then
    SOCIAL_CMD+=(--human-delay-min-seconds "$SOCIAL_PLAYWRIGHT_DELAY_MIN_SECONDS")
  fi
  if [[ -n "${SOCIAL_PLAYWRIGHT_DELAY_MAX_SECONDS:-}" ]]; then
    SOCIAL_CMD+=(--human-delay-max-seconds "$SOCIAL_PLAYWRIGHT_DELAY_MAX_SECONDS")
  fi
  if [[ -n "${SOCIAL_PLAYWRIGHT_SOURCE_COOLDOWN_SECONDS:-}" ]]; then
    SOCIAL_CMD+=(--source-cooldown-seconds "$SOCIAL_PLAYWRIGHT_SOURCE_COOLDOWN_SECONDS")
  fi
  if [[ -n "${SOCIAL_PLAYWRIGHT_REQUIRE_REDDIT_ITEMS:-}" ]]; then
    SOCIAL_CMD+=(--require-reddit-items "$SOCIAL_PLAYWRIGHT_REQUIRE_REDDIT_ITEMS")
  elif [[ "${SOCIAL_PLAYWRIGHT_REQUIRED:-0}" == "1" ]]; then
    SOCIAL_CMD+=(--require-reddit-items 1)
  fi
  if [[ -n "${SOCIAL_PLAYWRIGHT_REQUIRE_X_ITEMS:-}" ]]; then
    SOCIAL_CMD+=(--require-x-items "$SOCIAL_PLAYWRIGHT_REQUIRE_X_ITEMS")
  elif [[ "${SOCIAL_PLAYWRIGHT_REQUIRED:-0}" == "1" && -n "${X_PLAYWRIGHT_HANDLES:-}" ]]; then
    SOCIAL_CMD+=(--require-x-items 1)
  fi
  if [[ -n "${SOCIAL_PLAYWRIGHT_CHANNEL:-}" ]]; then
    SOCIAL_CMD+=(--channel "$SOCIAL_PLAYWRIGHT_CHANNEL")
  fi
  if [[ -n "${SOCIAL_PLAYWRIGHT_EXECUTABLE_PATH:-}" ]]; then
    SOCIAL_CMD+=(--executable-path "$SOCIAL_PLAYWRIGHT_EXECUTABLE_PATH")
  fi
  if [[ "${SOCIAL_PLAYWRIGHT_STEALTH_LOGIN:-0}" == "1" ]]; then
    SOCIAL_CMD+=(--stealth-login)
  fi
  if [[ "${SOCIAL_PLAYWRIGHT_HEADLESS:-0}" == "1" ]]; then
    SOCIAL_CMD+=(--headless)
  fi

  if ! "${SOCIAL_CMD[@]}"; then
    if [[ "${SOCIAL_PLAYWRIGHT_REQUIRED:-0}" == "1" ]]; then
      echo "[ERROR] Social Playwright collector failed and is required." >&2
      exit 1
    fi
    echo "[WARN] Social Playwright collector failed. Continuing without it." >&2
  fi
fi

if [[ "${ENABLE_XHS_PLAYWRIGHT:-0}" == "1" ]]; then
  XHS_CMD=("$PLAYWRIGHT_PYTHON_BIN" "$XHS_PLAYWRIGHT_COLLECTOR" --out-file "$XHS_PLAYWRIGHT_OUT")
  if [[ -n "${XIAOHONGSHU_SHARE_URLS:-}" ]]; then
    XHS_CMD+=(--urls "$XIAOHONGSHU_SHARE_URLS")
  fi
  if [[ -n "${XIAOHONGSHU_URLS_FILE:-}" ]]; then
    XHS_CMD+=(--urls-file "$XIAOHONGSHU_URLS_FILE")
  fi
  XHS_PROFILE_DIR="${XHS_PLAYWRIGHT_USER_DATA_DIR:-$DEFAULT_XHS_PLAYWRIGHT_PROFILE}"
  XHS_CMD+=(--user-data-dir "$XHS_PROFILE_DIR")
  if [[ -n "${XHS_LOGIN_WAIT_SECONDS:-}" ]]; then
    XHS_CMD+=(--login-wait-seconds "$XHS_LOGIN_WAIT_SECONDS")
  fi
  if [[ -n "${XHS_MAX_ITEMS:-}" ]]; then
    XHS_CMD+=(--max-items "$XHS_MAX_ITEMS")
  fi
  if [[ -n "${XHS_PLAYWRIGHT_CHANNEL:-}" ]]; then
    XHS_CMD+=(--channel "$XHS_PLAYWRIGHT_CHANNEL")
  fi
  if [[ -n "${XHS_PLAYWRIGHT_EXECUTABLE_PATH:-}" ]]; then
    XHS_CMD+=(--executable-path "$XHS_PLAYWRIGHT_EXECUTABLE_PATH")
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

"$PYTHON_BIN" "$COLLECTOR" \
  --out-dir "$OUT_DIR" \
  --window-hours 24 \
  --manual-glob "$EFFECTIVE_MANUAL_GLOB"
