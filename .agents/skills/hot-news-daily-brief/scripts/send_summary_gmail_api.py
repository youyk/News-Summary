#!/usr/bin/env python3
"""
Send a summary email through Gmail API (OAuth), without SMTP.

Auth modes:
1) Direct access token:
   - GMAIL_ACCESS_TOKEN
2) Refresh token exchange:
   - GMAIL_CLIENT_ID
   - GMAIL_CLIENT_SECRET
   - GMAIL_REFRESH_TOKEN

Content modes:
- plain text only
- HTML only
- multipart/alternative (plain + HTML)
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage
from pathlib import Path
from typing import Any


GMAIL_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send summary email via Gmail API.")
    parser.add_argument("--to", required=True, help="Recipient email address")
    parser.add_argument("--subject", required=True, help="Email subject")

    parser.add_argument("--body-file", help="Path to UTF-8 plain/markdown body file")
    parser.add_argument("--body", help="Inline plain text body")

    parser.add_argument("--html-file", help="Path to UTF-8 HTML body file")
    parser.add_argument("--html", help="Inline HTML body")
    parser.add_argument(
        "--html-only",
        action="store_true",
        help="Send HTML-only email instead of multipart/alternative",
    )

    parser.add_argument(
        "--from",
        dest="sender",
        default="",
        help="Optional From header. Defaults to GMAIL_FROM or omitted.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate config and message encoding without sending",
    )
    return parser.parse_args()


def read_file(path: str) -> str:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    return file_path.read_text(encoding="utf-8")


def read_plain_body(args: argparse.Namespace) -> str:
    if args.body_file:
        return read_file(args.body_file)
    if args.body:
        return args.body
    if not args.html_file and not args.html and not sys.stdin.isatty():
        content = sys.stdin.read()
        if content.strip():
            return content
    return ""


def read_html_body(args: argparse.Namespace) -> str:
    if args.html_file:
        return read_file(args.html_file)
    if args.html:
        return args.html
    return ""


def html_to_text(content: str) -> str:
    # Minimal fallback for multipart plain part when only HTML was provided.
    text = re.sub(r"<style[\s\S]*?</style>", " ", content, flags=re.IGNORECASE)
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def resolve_bodies(args: argparse.Namespace) -> tuple[str, str]:
    plain_body = read_plain_body(args)
    html_body = read_html_body(args)

    if args.html_only and not html_body:
        raise ValueError("--html-only requires --html or --html-file")

    if html_body and not plain_body and not args.html_only:
        plain_body = html_to_text(html_body)

    if not plain_body and not html_body:
        raise ValueError(
            "No body provided. Use --body-file/--body, or --html-file/--html, or stdin."
        )

    return plain_body, html_body


def request_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    encoded = json.dumps(payload).encode("utf-8")
    req_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if headers:
        req_headers.update(headers)
    request = urllib.request.Request(url, data=encoded, headers=req_headers, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        text = response.read().decode(charset, errors="replace")
    return json.loads(text)


def request_form(url: str, form: dict[str, str]) -> dict[str, Any]:
    body = urllib.parse.urlencode(form).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        text = response.read().decode(charset, errors="replace")
    return json.loads(text)


def access_token_from_env() -> str:
    token = os.getenv("GMAIL_ACCESS_TOKEN", "").strip()
    if token:
        return token

    client_id = os.getenv("GMAIL_CLIENT_ID", "").strip()
    client_secret = os.getenv("GMAIL_CLIENT_SECRET", "").strip()
    refresh_token = os.getenv("GMAIL_REFRESH_TOKEN", "").strip()
    token_url = os.getenv("GMAIL_TOKEN_URL", GMAIL_TOKEN_URL).strip() or GMAIL_TOKEN_URL

    if not (client_id and client_secret and refresh_token):
        raise ValueError(
            "Missing Gmail API auth. Set GMAIL_ACCESS_TOKEN, "
            "or set GMAIL_CLIENT_ID/GMAIL_CLIENT_SECRET/GMAIL_REFRESH_TOKEN."
        )

    response = request_form(
        token_url,
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
    )
    token = str(response.get("access_token", "")).strip()
    if not token:
        raise ValueError(f"Failed to fetch access token: {response}")
    return token


def encode_message(
    sender: str,
    recipient: str,
    subject: str,
    plain_body: str,
    html_body: str,
    html_only: bool,
) -> str:
    message = EmailMessage()
    if sender:
        message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject

    if html_body and html_only:
        message.set_content(html_body, subtype="html", charset="utf-8")
    elif html_body:
        message.set_content(plain_body or "(See HTML part)", subtype="plain", charset="utf-8")
        message.add_alternative(html_body, subtype="html", charset="utf-8")
    else:
        message.set_content(plain_body, subtype="plain", charset="utf-8")

    raw_bytes = message.as_bytes()
    return base64.urlsafe_b64encode(raw_bytes).decode("utf-8")


def send_via_gmail_api(access_token: str, raw_message: str) -> dict[str, Any]:
    return request_json(
        GMAIL_SEND_URL,
        {"raw": raw_message},
        headers={"Authorization": f"Bearer {access_token}"},
    )


def content_mode(plain_body: str, html_body: str, html_only: bool) -> str:
    if html_body and html_only:
        return "html-only"
    if html_body and plain_body:
        return "multipart"
    return "plain"


def main() -> int:
    try:
        args = parse_args()
        plain_body, html_body = resolve_bodies(args)
        sender = args.sender.strip() or os.getenv("GMAIL_FROM", "").strip()
        raw_message = encode_message(
            sender=sender,
            recipient=args.to,
            subject=args.subject,
            plain_body=plain_body,
            html_body=html_body,
            html_only=args.html_only,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    mode = content_mode(plain_body, html_body, args.html_only)

    if args.dry_run:
        auth_mode = "GMAIL_ACCESS_TOKEN" if os.getenv("GMAIL_ACCESS_TOKEN") else "refresh_token"
        print("[OK] Dry run passed.")
        print(f"To: {args.to}")
        print(f"Subject: {args.subject}")
        print(f"From: {sender or '(default Gmail user)'}")
        print(f"Auth mode: {auth_mode}")
        print(f"Content mode: {mode}")
        print(f"Plain length: {len(plain_body)}")
        print(f"HTML length: {len(html_body)}")
        print(f"Raw MIME bytes(base64url) length: {len(raw_message)}")
        return 0

    try:
        token = access_token_from_env()
        response = send_via_gmail_api(token, raw_message)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"[ERROR] Gmail API HTTP {exc.code}: {detail}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    msg_id = response.get("id", "")
    thread_id = response.get("threadId", "")
    print("[OK] Gmail API send succeeded.")
    print(f"Content mode: {mode}")
    if msg_id:
        print(f"Message ID: {msg_id}")
    if thread_id:
        print(f"Thread ID: {thread_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
