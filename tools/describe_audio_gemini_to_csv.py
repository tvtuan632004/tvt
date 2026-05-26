#!/usr/bin/env python3
"""Describe audio previews with Gemini and export rows to CSV."""

from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

import requests
from google import genai
from google.genai import types


OUTPUT_COLUMNS = [
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Describe audio files from CSV preview_url with Gemini and export CSV."
    )
    parser.add_argument(
        "--input-csv",
        default="tools/elevenlabs_voices_vi.csv",
        help="Input CSV path",
    )
    parser.add_argument(
        "--output-csv",
        default="tools/elevenlabs_voices_vi_gemini.csv",
        help="Output CSV path",
    )
    parser.add_argument(
        "--model",
        default="gemini-3.1-flash-lite",
        help="Gemini model name",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("GEMINI_API_KEY"),
        help="Gemini API key (default from GEMINI_API_KEY)",
    )
    parser.add_argument("--limit", type=int, default=0, help="Only process first N rows (0=all)")
    parser.add_argument("--start-index", type=int, default=0, help="Start row index from input CSV")
    parser.add_argument("--timeout", type=int, default=60, help="HTTP timeout seconds for preview URL")
    parser.add_argument("--sleep", type=float, default=0.2, help="Delay between requests")
    parser.add_argument("--retries", type=int, default=3, help="Retries per row on failure")
    return parser.parse_args()


def read_rows(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def download_audio(url: str, timeout: int) -> str:
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    suffix = ".mp3"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        f.write(resp.content)
        return f.name


def build_schema() -> types.Schema:
    return types.Schema(
        type=types.Type.OBJECT,
        properties={
            "description": types.Schema(type=types.Type.STRING),
            "language": types.Schema(type=types.Type.STRING),
            "locale": types.Schema(type=types.Type.STRING),
            "gender": types.Schema(type=types.Type.STRING),
            "age": types.Schema(type=types.Type.STRING),
            "accent": types.Schema(type=types.Type.STRING),
            "category": types.Schema(type=types.Type.STRING),
            "descriptive": types.Schema(type=types.Type.STRING),
            "use_case": types.Schema(type=types.Type.STRING),
        },
        required=[
            "description",
            "language",
            "locale",
            "gender",
            "age",
            "accent",
            "category",
            "descriptive",
            "use_case",
        ],
    )


def describe_audio(client: genai.Client, model: str, file_path: str) -> Dict[str, Any]:
    uploaded = client.files.upload(file=file_path)
    prompt = (
        "Analyze this voice sample and return metadata in JSON. "
        "Output exactly these keys: description, language, locale, gender, age, accent, category, descriptive, use_case. "
        "Use concise values compatible with the existing CSV taxonomy. "
        "Choose values from these closed class lists (no new labels): "
        "language: en, vi. "
        "locale: en-GB, en-US, vi-VN. "
        "gender: female, male, neutral. "
        "age: middle-aged, middle_aged, old, young. "
        "accent: american, british, central, northern, southern, standard. "
        "category: high_quality, professional. "
        "descriptive: calm, casual, chill, classy, confident, crisp, cute, deep, excited, formal, gentle, mature, meditative, neutral, pleasant, professional, relaxed, sad, serious, soft, upbeat, wise. "
        "use_case: advertisement, characters_animation, conversational, entertainment_tv, informative_educational, narrative_story, social_media. "
        "For description, write one natural sentence summarizing voice quality, tone, and suitable use cases."
    )
    response = client.models.generate_content(
        model=model,
        contents=[prompt, uploaded],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=build_schema(),
        ),
    )
    text = (response.text or "").strip()
    if not text:
        raise RuntimeError("Empty response text from Gemini")
    return json.loads(text)


def map_output_row(src: Dict[str, str], pred: Dict[str, Any]) -> Dict[str, str]:
    row = {
        "voice_id": src.get("voice_id", ""),
        "name": src.get("name", ""),
        "preview_url": src.get("preview_url", ""),
    }
    for k in (
        "description",
        "language",
        "locale",
        "gender",
        "age",
        "accent",
        "category",
        "descriptive",
        "use_case",
    ):
        row[k] = str(pred.get(k, "")).strip()
    return {col: row.get(col, "") for col in OUTPUT_COLUMNS}


def main() -> int:
    args = parse_args()
    if not args.api_key:
        raise SystemExit("Missing API key. Set GEMINI_API_KEY or pass --api-key.")

    rows = read_rows(Path(args.input_csv))
    if args.start_index:
        rows = rows[args.start_index :]
    if args.limit > 0:
        rows = rows[: args.limit]

    client = genai.Client(api_key=args.api_key)
    out_rows: List[Dict[str, str]] = []

    for idx, row in enumerate(rows, start=1):
        url = (row.get("preview_url") or "").strip()
        if not url:
            print(f"[{idx}] skip: missing preview_url")
            continue

        error: Exception | None = None
        result: Dict[str, Any] | None = None
        for attempt in range(1, args.retries + 1):
            tmp_path = None
            try:
                tmp_path = download_audio(url, timeout=args.timeout)
                result = describe_audio(client, args.model, tmp_path)
                break
            except Exception as exc:  # noqa: BLE001
                error = exc
                print(f"[{idx}] attempt {attempt}/{args.retries} failed: {exc}")
                time.sleep(min(2.0 * attempt, 5.0))
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    os.remove(tmp_path)

        if result is None:
            print(f"[{idx}] failed: {error}")
            continue

        out_rows.append(map_output_row(row, result))
        print(f"[{idx}] ok voice_id={row.get('voice_id','')}")
        time.sleep(args.sleep)

    out_path = Path(args.output_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"Saved {len(out_rows)} rows to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
