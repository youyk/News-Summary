#!/usr/bin/env python3
"""
Send a news summary email through SMTP.

Environment variables:
- SMTP_HOST (required)
- SMTP_PORT (optional, default: 587)
- SMTP_USER (optional but usually required)
- SMTP_PASS (optional but usually required)
- SMTP_FROM (optional, defaults to SMTP_USER)
- SMTP_USE_TLS (optional, default: true)
"""

from __future__ import annotations

import argparse
import html
import os
import re
import smtplib
import ssl
import sys
from email.message import EmailMessage
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send summary email via SMTP.")
    parser.add_argument("--to", required=True, help="Recipient email address")
    parser.add_argument("--subject", required=True, help="Email subject")
    parser.add_argument("--body-file", help="Path to a UTF-8 text/markdown plain body file")
    parser.add_argument("--body", help="Inline email plain text body")
    parser.add_argument("--html-file", help="Path to a UTF-8 HTML body file")
    parser.add_argument("--html", help="Inline HTML body")
    parser.add_argument(
        "--html-only",
        action="store_true",
        help="Send HTML-only email instead of multipart/alternative",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs and print config without sending",
    )
    return parser.parse_args()


def read_file(path: str) -> str:
    body_path = Path(path)
    if not body_path.exists():
        raise FileNotFoundError(f"File not found: {body_path}")
    return body_path.read_text(encoding="utf-8")


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


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def load_smtp_config() -> dict[str, object]:
    host = os.getenv("SMTP_HOST", "").strip()
    port_raw = os.getenv("SMTP_PORT", "587").strip()
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASS", "").strip()
    sender = os.getenv("SMTP_FROM", "").strip() or user
    use_tls = env_bool("SMTP_USE_TLS", True)

    if not host:
        raise ValueError("Missing SMTP_HOST")
    if not sender:
        raise ValueError("Missing SMTP_FROM and SMTP_USER")

    try:
        port = int(port_raw)
    except ValueError as exc:
        raise ValueError(f"Invalid SMTP_PORT: {port_raw}") from exc

    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "sender": sender,
        "use_tls": use_tls,
    }


def build_message(
    recipient: str,
    subject: str,
    plain_body: str,
    html_body: str,
    sender: str,
    html_only: bool,
) -> EmailMessage:
    message = EmailMessage()
    message["To"] = recipient
    message["From"] = sender
    message["Subject"] = subject

    if html_body and html_only:
        message.set_content(html_body, subtype="html", charset="utf-8")
    elif html_body:
        message.set_content(plain_body or "(See HTML part)", subtype="plain", charset="utf-8")
        message.add_alternative(html_body, subtype="html", charset="utf-8")
    else:
        message.set_content(plain_body, subtype="plain", charset="utf-8")

    return message


def send_message(config: dict[str, object], message: EmailMessage) -> None:
    host = str(config["host"])
    port = int(config["port"])
    user = str(config["user"])
    password = str(config["password"])
    use_tls = bool(config["use_tls"])

    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.ehlo()
        if use_tls:
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
        if user and password:
            smtp.login(user, password)
        smtp.send_message(message)


def main() -> int:
    try:
        args = parse_args()
        plain_body, html_body = resolve_bodies(args)
        config = None
        sender = os.getenv("SMTP_FROM", "").strip() or os.getenv("SMTP_USER", "").strip()
        if args.dry_run:
            if os.getenv("SMTP_HOST", "").strip():
                config = load_smtp_config()
                sender = str(config["sender"])
        else:
            config = load_smtp_config()
            sender = str(config["sender"])
        message = build_message(
            recipient=args.to,
            subject=args.subject,
            plain_body=plain_body,
            html_body=html_body,
            sender=sender,
            html_only=args.html_only,
        )
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        print("[OK] Dry run passed.")
        print(f"To: {args.to}")
        print(f"Subject: {args.subject}")
        if config:
            print(f"SMTP host: {config['host']}:{config['port']}")
            print(f"Use TLS: {config['use_tls']}")
        else:
            print("SMTP config: not set (dry-run only)")
        if html_body and args.html_only:
            mode = "html-only"
        elif html_body:
            mode = "multipart"
        else:
            mode = "plain"
        print(f"Content mode: {mode}")
        print(f"Plain length: {len(plain_body)}")
        print(f"HTML length: {len(html_body)}")
        return 0

    try:
        assert config is not None
        send_message(config, message)
    except Exception as exc:
        print(f"[ERROR] Failed to send email: {exc}", file=sys.stderr)
        return 1

    print("[OK] Email sent successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
