#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/Users/yongkang/projects/skills/News-Summary"
SENDER="$ROOT_DIR/.agents/skills/hot-news-daily-brief/scripts/send_summary_gmail_api.py"
RENDERER="$ROOT_DIR/.agents/skills/hot-news-daily-brief/scripts/render_digest_html.py"
VALIDATOR="$ROOT_DIR/.agents/skills/hot-news-daily-brief/scripts/validate_digest.py"
ENV_FILE="$ROOT_DIR/scripts/gmail.env"

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

if [[ "$MAIL_CONTENT_MODE" != "plain" && "$MAIL_CONTENT_MODE" != "multipart" && "$MAIL_CONTENT_MODE" != "html-only" ]]; then
  echo "[ERROR] Unsupported NEWS_DIGEST_MAIL_CONTENT_MODE: $MAIL_CONTENT_MODE" >&2
  echo "Allowed values: plain | multipart | html-only" >&2
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

if [[ "$SKIP_VALIDATE" == "1" || "$SKIP_VALIDATE" == "true" || "$SKIP_VALIDATE" == "TRUE" ]]; then
  echo "[WARN] Skip digest validation because NEWS_DIGEST_SKIP_VALIDATE=$SKIP_VALIDATE"
else
  python3 "$VALIDATOR" \
    --input "$REPORT_PATH" \
    --min-english-words "$MIN_ENGLISH_WORDS"
fi

if [[ "$MAIL_CONTENT_MODE" == "multipart" || "$MAIL_CONTENT_MODE" == "html-only" ]]; then
  python3 "$RENDERER" \
    --input "$REPORT_PATH" \
    --output "$HTML_REPORT_PATH" \
    --title "Daily Hot News Digest - ${REPORT_DATE}"
fi

if [[ "$MAIL_CONTENT_MODE" == "plain" ]]; then
  python3 "$SENDER" \
    --to "$RECIPIENT" \
    --subject "Daily Hot News Digest - ${REPORT_DATE}" \
    --body-file "$REPORT_PATH" \
    "$@"
elif [[ "$MAIL_CONTENT_MODE" == "html-only" ]]; then
  python3 "$SENDER" \
    --to "$RECIPIENT" \
    --subject "Daily Hot News Digest - ${REPORT_DATE}" \
    --html-file "$HTML_REPORT_PATH" \
    --html-only \
    "$@"
else
  python3 "$SENDER" \
    --to "$RECIPIENT" \
    --subject "Daily Hot News Digest - ${REPORT_DATE}" \
    --body-file "$REPORT_PATH" \
    --html-file "$HTML_REPORT_PATH" \
    "$@"
fi
