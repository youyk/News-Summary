# Gmail API Auth Setup (No SMTP)

Use Gmail API with OAuth to avoid SMTP credentials.

## 1) Create Google Cloud OAuth credentials

1. Open Google Cloud Console.
2. Create or select a project.
3. Enable Gmail API.
4. Configure OAuth consent screen.
5. Create OAuth client credentials.
6. Add redirect URI used by bootstrap script:
   - `http://localhost:8765/callback`

Collect:
- `GMAIL_CLIENT_ID`
- `GMAIL_CLIENT_SECRET`

## 2) Get authorization URL

```bash
python3 .agents/skills/hot-news-daily-brief/scripts/gmail_oauth_bootstrap.py auth-url \
  --client-id "$GMAIL_CLIENT_ID" \
  --redirect-uri "http://localhost:8765/callback" \
  --open
```

After consent, copy `code` from callback URL:
- `http://localhost:8765/callback?code=...&scope=...&state=...`

## 3) Exchange code for refresh token

```bash
python3 .agents/skills/hot-news-daily-brief/scripts/gmail_oauth_bootstrap.py exchange-code \
  --client-id "$GMAIL_CLIENT_ID" \
  --client-secret "$GMAIL_CLIENT_SECRET" \
  --code "<PASTE_AUTH_CODE>" \
  --redirect-uri "http://localhost:8765/callback" \
  --write-env-file "/Users/yongkang/projects/skills/News-Summary/scripts/gmail.env" \
  --from-email "your-address@gmail.com" \
  --recipient-email "recipient@example.com"
```

Response contains `refresh_token` on first successful offline-consent grant.
By default, script does not print raw token JSON to reduce secret exposure.
If needed for debugging, add `--show-raw-response`.

## 4) Store environment variables

```bash
cp /Users/yongkang/projects/skills/News-Summary/scripts/gmail.env.example \
   /Users/yongkang/projects/skills/News-Summary/scripts/gmail.env
# Option A: edit gmail.env and fill real values.
# Option B: let exchange-code write gmail.env directly.
```

`gmail.env` should include:
- `GMAIL_CLIENT_ID`
- `GMAIL_CLIENT_SECRET`
- `GMAIL_REFRESH_TOKEN`
- `GMAIL_FROM`
- `NEWS_DIGEST_TO`
- `NEWS_DIGEST_MAIL_CONTENT_MODE` (`multipart` recommended)

## 5) Dry run

```bash
source /Users/yongkang/projects/skills/News-Summary/scripts/gmail.env
python3 .agents/skills/hot-news-daily-brief/scripts/send_summary_gmail_api.py \
  --to "$NEWS_DIGEST_TO" \
  --subject "Dry Run" \
  --body "Test message" \
  --dry-run
```

## 6) Send actual digest

```bash
python3 .agents/skills/hot-news-daily-brief/scripts/send_summary_gmail_api.py \
  --to "$NEWS_DIGEST_TO" \
  --subject "Daily Hot News Digest - YYYY-MM-DD" \
  --body-file ./Report/YYYY-MM-DD.md \
  --html-file ./Report/YYYY-MM-DD.html
```

If `./Report/YYYY-MM-DD.html` does not exist, generate it first:

```bash
python3 .agents/skills/hot-news-daily-brief/scripts/render_digest_html.py \
  --input ./Report/YYYY-MM-DD.md \
  --output ./Report/YYYY-MM-DD.html
```

## Optional direct access token mode

If you already have a short-lived OAuth access token:

```bash
export GMAIL_ACCESS_TOKEN="..."
```

The script will use it directly and skip refresh-token exchange.
