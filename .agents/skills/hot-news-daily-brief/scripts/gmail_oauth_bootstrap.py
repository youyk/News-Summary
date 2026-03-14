#!/usr/bin/env python3
"""
Bootstrap Gmail OAuth credentials for API sending.

Two steps:
1) Print authorization URL and open it in browser.
2) Exchange returned auth code for access/refresh token JSON.
"""

from __future__ import annotations

import argparse
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any


AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
DEFAULT_SCOPE = "https://www.googleapis.com/auth/gmail.send"
DEFAULT_REDIRECT_URI = "http://localhost:8765/callback"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gmail OAuth bootstrap helper.")
    sub = parser.add_subparsers(dest="command", required=True)

    auth = sub.add_parser("auth-url", help="Generate OAuth authorization URL")
    auth.add_argument("--client-id", required=True, help="Google OAuth client id")
    auth.add_argument(
        "--redirect-uri",
        default=DEFAULT_REDIRECT_URI,
        help=f"OAuth redirect URI (default: {DEFAULT_REDIRECT_URI})",
    )
    auth.add_argument(
        "--scope",
        default=DEFAULT_SCOPE,
        help=f"OAuth scope (default: {DEFAULT_SCOPE})",
    )
    auth.add_argument(
        "--state",
        default="",
        help="Optional CSRF state value (auto-generated if omitted)",
    )
    auth.add_argument(
        "--open",
        action="store_true",
        help="Open the generated URL in the default browser",
    )

    exchange = sub.add_parser("exchange-code", help="Exchange auth code for tokens")
    exchange.add_argument("--client-id", required=True, help="Google OAuth client id")
    exchange.add_argument("--client-secret", required=True, help="Google OAuth client secret")
    exchange.add_argument("--code", required=True, help="Authorization code from callback URL")
    exchange.add_argument(
        "--redirect-uri",
        default=DEFAULT_REDIRECT_URI,
        help=f"OAuth redirect URI (must match auth-url step, default: {DEFAULT_REDIRECT_URI})",
    )
    exchange.add_argument(
        "--token-url",
        default=TOKEN_URL,
        help=f"Token endpoint (default: {TOKEN_URL})",
    )
    exchange.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON when --show-raw-response is used",
    )
    exchange.add_argument(
        "--show-raw-response",
        action="store_true",
        help="Print full token endpoint JSON response (may include secrets)",
    )
    exchange.add_argument(
        "--write-env-file",
        default="",
        help="Optional path to write env exports (for example: ./scripts/gmail.env)",
    )
    exchange.add_argument(
        "--from-email",
        default="",
        help="Optional GMAIL_FROM value to include when writing env file",
    )
    exchange.add_argument(
        "--recipient-email",
        default="",
        help="Optional NEWS_DIGEST_TO value to include when writing env file",
    )
    return parser.parse_args()


def build_auth_url(client_id: str, redirect_uri: str, scope: str, state: str) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"


def post_form(url: str, form: dict[str, str]) -> dict[str, Any]:
    data = urllib.parse.urlencode(form).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        body = response.read().decode(charset, errors="replace")
    return json.loads(body)


def error_text(exc: urllib.error.HTTPError) -> str:
    try:
        payload = exc.read().decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        payload = ""
    if payload.strip():
        return payload
    return exc.reason if isinstance(exc.reason, str) else str(exc)


def run_auth_url(args: argparse.Namespace) -> int:
    state = args.state.strip() or secrets.token_urlsafe(16)
    url = build_auth_url(
        client_id=args.client_id.strip(),
        redirect_uri=args.redirect_uri.strip(),
        scope=args.scope.strip(),
        state=state,
    )
    print("Authorization URL:")
    print(url)
    print()
    print(f"State: {state}")
    print("After consent, copy 'code' from the callback URL and run exchange-code.")
    if args.open:
        webbrowser.open(url)
        print("Opened in browser.")
    return 0


def run_exchange(args: argparse.Namespace) -> int:
    payload = {
        "client_id": args.client_id.strip(),
        "client_secret": args.client_secret.strip(),
        "code": args.code.strip(),
        "grant_type": "authorization_code",
        "redirect_uri": args.redirect_uri.strip(),
    }
    try:
        response = post_form(args.token_url.strip(), payload)
    except urllib.error.HTTPError as exc:
        detail = error_text(exc)
        print(f"[ERROR] Token exchange failed (HTTP {exc.code}): {detail}")
        print("Likely causes: expired/used code, redirect_uri mismatch, wrong client id/secret.")
        return 1
    access = str(response.get("access_token", "")).strip()
    refresh = str(response.get("refresh_token", "")).strip()

    if args.show_raw_response and args.pretty:
        print(json.dumps(response, ensure_ascii=False, indent=2))
    elif args.show_raw_response:
        print(json.dumps(response, ensure_ascii=False))
    else:
        print("[OK] Token exchange request completed.")
        print(f"access_token: {'present' if access else 'missing'}")
        print(f"refresh_token: {'present' if refresh else 'missing'}")
        if "scope" in response:
            print(f"scope: {response.get('scope')}")
        if "expires_in" in response:
            print(f"expires_in: {response.get('expires_in')}")
        if "error" in response:
            print(f"error: {response.get('error')}")
        if "error_description" in response:
            print(f"error_description: {response.get('error_description')}")
    print()

    if refresh:
        if args.write_env_file.strip():
            env_path = Path(args.write_env_file.strip()).expanduser()
            lines = [
                f'export GMAIL_CLIENT_ID="{args.client_id.strip()}"',
                f'export GMAIL_CLIENT_SECRET="{args.client_secret.strip()}"',
                f'export GMAIL_REFRESH_TOKEN="{refresh}"',
            ]
            if args.from_email.strip():
                lines.append(f'export GMAIL_FROM="{args.from_email.strip()}"')
            if args.recipient_email.strip():
                lines.append(f'export NEWS_DIGEST_TO="{args.recipient_email.strip()}"')
            env_path.parent.mkdir(parents=True, exist_ok=True)
            env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            try:
                env_path.chmod(0o600)
            except OSError:
                pass
            print(f"[OK] Wrote env file: {env_path}")
            print("Keep this file local and out of git.")
        else:
            print("Refresh token obtained.")
            print("Use --write-env-file to save credentials locally without printing full secrets.")
    else:
        print("No refresh_token in response. Ensure prompt=consent and access_type=offline.")
    return 0


def main() -> int:
    args = parse_args()
    if args.command == "auth-url":
        return run_auth_url(args)
    if args.command == "exchange-code":
        return run_exchange(args)
    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
