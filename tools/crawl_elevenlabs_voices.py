#!/usr/bin/env python3
"""Crawl ElevenLabs Voice Library and save voices + descriptions.

Default endpoint:
https://api.elevenlabs.io/v1/shared-voices

Notes:
- Without login/auth headers, ElevenLabs currently returns at most 3 voices.
- To crawl full results, pass browser auth headers (e.g. Authorization/Cookie).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import requests

API_URL = "https://api.elevenlabs.io/v1/shared-voices"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Crawl ElevenLabs Voice Library voices and descriptions"
    )
    parser.add_argument("--language", default="vi", help="Language filter (default: vi)")
    parser.add_argument("--page-size", type=int, default=30, help="Voices per page request")
    parser.add_argument("--max-pages", type=int, default=200, help="Safety cap for pagination")
    parser.add_argument(
        "--output-json",
        default="elevenlabs_voices_vi.json",
        help="Output JSON path",
    )
    parser.add_argument(
        "--output-csv",
        default="elevenlabs_voices_vi.csv",
        help="Output CSV path",
    )
    parser.add_argument(
        "--authorization",
        default=None,
        help="Authorization header value from browser session (optional)",
    )
    parser.add_argument(
        "--cookie",
        default=None,
        help="Cookie header value from browser session (optional)",
    )
    parser.add_argument(
        "--xi-api-key",
        default=None,
        help="Optional XI API key header",
    )
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds")
    return parser.parse_args()


def build_headers(args: argparse.Namespace) -> Dict[str, str]:
    headers: Dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    }

    if args.authorization:
        headers["Authorization"] = args.authorization
    if args.cookie:
        headers["Cookie"] = args.cookie
    if args.xi_api_key:
        headers["xi-api-key"] = args.xi_api_key

    return headers


def fetch_page(
    session: requests.Session,
    headers: Dict[str, str],
    language: str,
    page_size: int,
    page: int,
    timeout: int,
) -> Dict[str, Any]:
    params = {
        "language": language,
        "page_size": page_size,
        "page": page,
    }
    resp = session.get(API_URL, headers=headers, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def normalize_voice(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "voice_id": item.get("voice_id"),
        "name": item.get("name"),
        "description": item.get("description"),
        "language": item.get("language"),
        "locale": item.get("locale"),
        "gender": item.get("gender"),
        "age": item.get("age"),
        "accent": item.get("accent"),
        "category": item.get("category"),
        "descriptive": item.get("descriptive"),
        "use_case": item.get("use_case"),
        "preview_url": item.get("preview_url"),
    }


def crawl(args: argparse.Namespace) -> List[Dict[str, Any]]:
    headers = build_headers(args)
    session = requests.Session()

    voices: List[Dict[str, Any]] = []
    seen_ids = set()

    for page in range(args.max_pages):
        payload = fetch_page(
            session=session,
            headers=headers,
            language=args.language,
            page_size=args.page_size,
            page=page,
            timeout=args.timeout,
        )

        if payload.get("detail"):
            detail = payload["detail"]
            status = detail.get("status")
            message = detail.get("message")
            raise RuntimeError(f"API error: status={status}, message={message}")

        page_voices = payload.get("voices") or []
        if not page_voices:
            break

        new_count = 0
        for raw in page_voices:
            voice_id = raw.get("voice_id")
            if not voice_id or voice_id in seen_ids:
                continue
            seen_ids.add(voice_id)
            voices.append(normalize_voice(raw))
            new_count += 1

        has_more = bool(payload.get("has_more"))
        print(
            f"page={page} fetched={len(page_voices)} new={new_count} total={len(voices)} has_more={has_more}"
        )

        if new_count == 0:
            break
        if not has_more:
            break

        time.sleep(0.2)

    return voices


def save_json(path: Path, data: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_csv(path: Path, data: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "voice_id",
        "name",
        "description",
        "language",
        "locale",
        "gender",
        "age",
        "accent",
        "category",
        "descriptive",
        "use_case",
        "preview_url",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(data)


def main() -> int:
    args = parse_args()

    try:
        voices = crawl(args)
    except requests.HTTPError as exc:
        print(f"HTTP error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    save_json(Path(args.output_json), voices)
    save_csv(Path(args.output_csv), voices)

    print(f"Saved {len(voices)} voices")
    print(f"JSON: {args.output_json}")
    print(f"CSV : {args.output_csv}")

    if len(voices) <= 3 and not (args.authorization or args.cookie or args.xi_api_key):
        print(
            "Note: unauthenticated mode is usually limited to 3 voices. "
            "Pass --authorization or --cookie to crawl full result set."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
