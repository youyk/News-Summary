#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/Users/yongkang/projects/skills/News-Summary"
COLLECTOR="$ROOT_DIR/.agents/skills/hot-news-daily-brief/scripts/collect_news.py"
OUT_DIR="$ROOT_DIR/data/inbox"
MANUAL_GLOB="$ROOT_DIR/data/inbox/manual/*.json"

mkdir -p "$OUT_DIR" "$ROOT_DIR/data/inbox/manual"

python3 "$COLLECTOR" \
  --out-dir "$OUT_DIR" \
  --window-hours 24 \
  --manual-glob "$MANUAL_GLOB"

