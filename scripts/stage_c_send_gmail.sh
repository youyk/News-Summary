#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/Users/yongkang/projects/skills/News-Summary"
SENDER="$ROOT_DIR/.agents/skills/hot-news-daily-brief/scripts/send_summary_gmail_api.py"
RENDERER="$ROOT_DIR/.agents/skills/hot-news-daily-brief/scripts/render_digest_html.py"
VALIDATOR="$ROOT_DIR/.agents/skills/hot-news-daily-brief/scripts/validate_digest.py"
SYNC_SOURCE_HEALTH="$ROOT_DIR/.agents/skills/hot-news-daily-brief/scripts/update_source_health_section.py"
APPLY_COMMENT_MODE="$ROOT_DIR/.agents/skills/hot-news-daily-brief/scripts/apply_comment_mode.py"
ARCHIVE_ANALYZER="$ROOT_DIR/.agents/skills/hot-news-daily-brief/scripts/analyze_archive.py"
APPLY_WEEKLY_TREND="$ROOT_DIR/.agents/skills/hot-news-daily-brief/scripts/append_weekly_trend_section.py"
ENV_FILE="$ROOT_DIR/scripts/gmail.env"

if [[ -x "/usr/bin/python3" ]]; then
  PYTHON_BIN="/usr/bin/python3"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  echo "[ERROR] python3 not found. Please install Python 3." >&2
  exit 1
fi

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

REPORT_DATE="${REPORT_DATE:-$(date +%F)}"
REPORT_PATH="$ROOT_DIR/Report/${REPORT_DATE}.md"
HTML_REPORT_PATH="$ROOT_DIR/Report/${REPORT_DATE}.html"
RECIPIENT="${NEWS_DIGEST_TO:-}"
MAIL_CONTENT_MODE="${NEWS_DIGEST_MAIL_CONTENT_MODE:-multipart}"
SKIP_VALIDATE="${NEWS_DIGEST_SKIP_VALIDATE:-0}"
MIN_ENGLISH_WORDS="${NEWS_DIGEST_MIN_ENGLISH_WORDS:-200}"
MIN_ENGLISH_NUMERIC_FACTS="${NEWS_DIGEST_MIN_ENGLISH_NUMERIC_FACTS:-0}"
COMMENT_MODE="${NEWS_DIGEST_COMMENT_MODE:-off}"
SYNC_SOURCE_HEALTH_FLAG="${NEWS_DIGEST_SYNC_SOURCE_HEALTH:-1}"
CANDIDATE_JSON_PATH="${NEWS_DIGEST_CANDIDATE_FILE:-}"

WEEKLY_TREND_ENABLED="${NEWS_DIGEST_WEEKLY_TREND_ENABLED:-1}"
WEEKLY_TREND_WEEKDAY="${NEWS_DIGEST_WEEKLY_TREND_WEEKDAY:-7}"
WEEKLY_TREND_WINDOWS="${NEWS_DIGEST_WEEKLY_TREND_WINDOWS:-7,30,90,180,360}"
WEEKLY_TREND_FORCE="${NEWS_DIGEST_WEEKLY_TREND_FORCE:-0}"
WEEKLY_TREND_TOP_EXAMPLES="${NEWS_DIGEST_WEEKLY_TOP_EXAMPLES:-3}"
WEEKLY_TREND_TOP_SOURCES="${NEWS_DIGEST_WEEKLY_TOP_SOURCES:-3}"
WEEKLY_TREND_TOP_KEYWORDS="${NEWS_DIGEST_WEEKLY_TOP_KEYWORDS:-6}"
WEEKLY_TREND_TOP_EVENTS="${NEWS_DIGEST_WEEKLY_TOP_EVENTS:-2}"
ARCHIVE_ROOT="${NEWS_DIGEST_ARCHIVE_ROOT:-$ROOT_DIR/data/archive/by_date_source}"
ARCHIVE_ANALYSIS_OUT_DIR="${NEWS_DIGEST_ARCHIVE_ANALYSIS_OUT_DIR:-$ROOT_DIR/Report/archive-analysis}"

if [[ "$MAIL_CONTENT_MODE" != "plain" && "$MAIL_CONTENT_MODE" != "multipart" && "$MAIL_CONTENT_MODE" != "html-only" ]]; then
  echo "[ERROR] Unsupported NEWS_DIGEST_MAIL_CONTENT_MODE: $MAIL_CONTENT_MODE" >&2
  echo "Allowed values: plain | multipart | html-only" >&2
  exit 1
fi

if [[ "$COMMENT_MODE" != "off" && "$COMMENT_MODE" != "on" ]]; then
  echo "[ERROR] Unsupported NEWS_DIGEST_COMMENT_MODE: $COMMENT_MODE" >&2
  echo "Allowed values: off | on" >&2
  exit 1
fi

if [[ -z "$RECIPIENT" ]]; then
  echo "[ERROR] Missing NEWS_DIGEST_TO in environment or $ENV_FILE" >&2
  exit 1
fi

if [[ ! -f "$REPORT_PATH" ]]; then
  echo "[ERROR] Report not found: $REPORT_PATH" >&2
  exit 1
fi

if [[ "$SYNC_SOURCE_HEALTH_FLAG" == "1" || "$SYNC_SOURCE_HEALTH_FLAG" == "true" || "$SYNC_SOURCE_HEALTH_FLAG" == "TRUE" ]]; then
  SYNC_CMD=("$PYTHON_BIN" "$SYNC_SOURCE_HEALTH" --report "$REPORT_PATH" --inbox-dir "$ROOT_DIR/data/inbox")
  if [[ -n "$CANDIDATE_JSON_PATH" ]]; then
    SYNC_CMD+=(--candidate-json "$CANDIDATE_JSON_PATH")
  fi
  "${SYNC_CMD[@]}"
else
  echo "[WARN] Skip source-health sync because NEWS_DIGEST_SYNC_SOURCE_HEALTH=$SYNC_SOURCE_HEALTH_FLAG"
fi

if [[ "$WEEKLY_TREND_ENABLED" == "1" || "$WEEKLY_TREND_ENABLED" == "true" || "$WEEKLY_TREND_ENABLED" == "TRUE" ]]; then
  WEEKLY_CMD=(
    "$PYTHON_BIN" "$APPLY_WEEKLY_TREND"
    --report "$REPORT_PATH"
    --report-date "$REPORT_DATE"
    --archive-root "$ARCHIVE_ROOT"
    --analysis-script "$ARCHIVE_ANALYZER"
    --analysis-out-dir "$ARCHIVE_ANALYSIS_OUT_DIR"
    --windows "$WEEKLY_TREND_WINDOWS"
    --only-weekday "$WEEKLY_TREND_WEEKDAY"
    --top-examples "$WEEKLY_TREND_TOP_EXAMPLES"
    --top-sources "$WEEKLY_TREND_TOP_SOURCES"
    --top-keywords "$WEEKLY_TREND_TOP_KEYWORDS"
    --top-events "$WEEKLY_TREND_TOP_EVENTS"
  )
  if [[ "$WEEKLY_TREND_FORCE" == "1" || "$WEEKLY_TREND_FORCE" == "true" || "$WEEKLY_TREND_FORCE" == "TRUE" ]]; then
    WEEKLY_CMD+=(--force)
  fi
  "${WEEKLY_CMD[@]}"
else
  echo "[WARN] Skip weekly-trend injection because NEWS_DIGEST_WEEKLY_TREND_ENABLED=$WEEKLY_TREND_ENABLED"
fi

"$PYTHON_BIN" "$APPLY_COMMENT_MODE" \
  --input "$REPORT_PATH" \
  --mode "$COMMENT_MODE"

if [[ "$SKIP_VALIDATE" == "1" || "$SKIP_VALIDATE" == "true" || "$SKIP_VALIDATE" == "TRUE" ]]; then
  echo "[WARN] Skip digest validation because NEWS_DIGEST_SKIP_VALIDATE=$SKIP_VALIDATE"
else
  VALIDATE_CMD=(
    "$PYTHON_BIN" "$VALIDATOR"
    --input "$REPORT_PATH"
    --min-english-words "$MIN_ENGLISH_WORDS"
    --min-english-numeric-facts "$MIN_ENGLISH_NUMERIC_FACTS"
  )
  if [[ "$COMMENT_MODE" == "on" ]]; then
    VALIDATE_CMD+=(--require-comment)
  fi
  "${VALIDATE_CMD[@]}"
fi

if [[ "$MAIL_CONTENT_MODE" == "multipart" || "$MAIL_CONTENT_MODE" == "html-only" ]]; then
  "$PYTHON_BIN" "$RENDERER" \
    --input "$REPORT_PATH" \
    --output "$HTML_REPORT_PATH" \
    --title "Daily Hot News Digest - ${REPORT_DATE}"
fi

if [[ "$MAIL_CONTENT_MODE" == "plain" ]]; then
  "$PYTHON_BIN" "$SENDER" \
    --to "$RECIPIENT" \
    --subject "Daily Hot News Digest - ${REPORT_DATE}" \
    --body-file "$REPORT_PATH" \
    "$@"
elif [[ "$MAIL_CONTENT_MODE" == "html-only" ]]; then
  "$PYTHON_BIN" "$SENDER" \
    --to "$RECIPIENT" \
    --subject "Daily Hot News Digest - ${REPORT_DATE}" \
    --html-file "$HTML_REPORT_PATH" \
    --html-only \
    "$@"
else
  "$PYTHON_BIN" "$SENDER" \
    --to "$RECIPIENT" \
    --subject "Daily Hot News Digest - ${REPORT_DATE}" \
    --body-file "$REPORT_PATH" \
    --html-file "$HTML_REPORT_PATH" \
    "$@"
fi
