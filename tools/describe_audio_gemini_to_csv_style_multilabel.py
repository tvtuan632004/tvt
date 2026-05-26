#!/usr/bin/env python3
"""Describe audio previews with Gemini and export CSV (descriptive + use_case)."""

from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

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

DESCRIPTIVE_CLASSES = {
    "calm",
    "casual",
    "chill",
    "classy",
    "confident",
    "crisp",
    "cute",
    "deep",
    "excited",
    "formal",
    "gentle",
    "mature",
    "meditative",
    "neutral",
    "pleasant",
    "professional",
    "relaxed",
    "sad",
    "serious",
    "soft",
    "upbeat",
    "wise",
}

USE_CASE_CLASSES = {
    "advertisement",
    "characters_animation",
    "conversational",
    "entertainment_tv",
    "informative_educational",
    "narrative_story",
    "social_media",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Describe audio files from CSV preview_url with Gemini and export CSV."
    )
    parser.add_argument("--input-csv", default="tools/outputs/elevenlabs_voices_vi.csv", help="Input CSV path")
    parser.add_argument(
        "--output-csv",
        default="tools/elevenlabs_voices_vi_gemini_style_multilabel.csv",
        help="Output CSV path",
    )
    parser.add_argument("--model", default="gemini-3.1-flash-lite", help="Gemini model name")
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
    parser.add_argument(
        "--fewshot-dir",
        default="tools/outputs/style_class_samples_30",
        help="Folder containing class subfolders with exemplar audios",
    )
    parser.add_argument(
        "--fewshot-per-class",
        type=int,
        default=1,
        help="How many exemplar audios to take per class folder",
    )
    parser.add_argument(
        "--fewshot-max-total",
        type=int,
        default=20,
        help="Safety cap for total few-shot exemplars",
    )
    return parser.parse_args()


def read_rows(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def download_audio(url: str, timeout: int) -> str:
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
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


def load_fewshot_examples(
    client: genai.Client,
    fewshot_dir: Path,
    per_class: int,
    max_total: int,
) -> List[Tuple[str, str, Any]]:
    examples: List[Tuple[str, str, Any]] = []
    if per_class <= 0 or max_total <= 0:
        return examples
    if not fewshot_dir.exists():
        print(f"fewshot: skip, folder not found: {fewshot_dir}")
        return examples

    for class_dir in sorted([p for p in fewshot_dir.iterdir() if p.is_dir()]):
        label = class_dir.name.strip()
        if label in DESCRIPTIVE_CLASSES:
            label_type = "descriptive"
        elif label in USE_CASE_CLASSES:
            label_type = "use_case"
        else:
            continue

        files = sorted(
            [p for p in class_dir.iterdir() if p.is_file() and p.suffix.lower() in {".mp3", ".wav", ".m4a"}]
        )[:per_class]
        for f in files:
            try:
                up = client.files.upload(file=str(f))
                examples.append((label_type, label, up))
            except Exception as exc:  # noqa: BLE001
                print(f"fewshot: upload failed {f}: {exc}")
            if len(examples) >= max_total:
                return examples

    return examples


def describe_audio(
    client: genai.Client,
    model: str,
    file_path: str,
    fewshot_examples: List[Tuple[str, str, Any]],
) -> Dict[str, Any]:
    uploaded = client.files.upload(file=file_path)
    # prompt = (
    #     "Analyze this voice sample and return metadata in JSON. "
    #     "Output exactly these keys: description, language, locale, gender, age, accent, category, descriptive, use_case. "
    #     "Use concise values compatible with the existing CSV taxonomy. "
    #     "Choose values from these closed class lists (no new labels). "
    #     "language: en, vi. "
    #     "locale: en-GB, en-US, vi-VN. "
    #     "gender: female, male, neutral. "
    #     "age: middle-aged, middle_aged, old, young. "
    #     "accent: american, british, central, northern, southern, standard. "
    #     "category: high_quality, professional. "
    #     "descriptive: calm, casual, chill, classy, confident, crisp, cute, deep, excited, formal, gentle, mature, meditative, neutral, pleasant, professional, relaxed, sad, serious, soft, upbeat, wise. "
    #     "use_case: advertisement, characters_animation, conversational, entertainment_tv, informative_educational, narrative_story, social_media. "
    #     "For description, write one natural sentence summarizing based on fields above except locale and language."
    # )
    prompt = (
    "Analyze this voice sample and return metadata in JSON only. "
    "Do not include markdown, explanation, comments, or extra text. "
    "Output exactly these keys: description, language, locale, gender, age, accent, category, descriptive, use_case. "
    "All values must be concise and compatible with the existing CSV taxonomy. "
    "For all fields except description, choose exactly one value from the closed class lists below. "
    "Do not create new labels. Do not combine multiple labels. Do not output null. "
    
    "\n\nFIELD DEFINITIONS AND CLOSED CLASSES:\n"

    "\n1. language: the main spoken language in the audio.\n"
    "- en: English speech.\n"
    "- vi: Vietnamese speech.\n"

    "\n2. locale: the regional language variant.\n"
    "- en-GB: English with British or UK-style pronunciation, vocabulary, or intonation.\n"
    "- en-US: English with American or US-style pronunciation, vocabulary, or intonation.\n"
    "- vi-VN: Vietnamese spoken in Vietnam, including northern, central, or southern Vietnamese accents.\n"

    "\n3. gender: perceived speaker gender from the voice only.\n"
    "- female: voice sounds typically feminine.\n"
    "- male: voice sounds typically masculine.\n"
    "- neutral: gender is ambiguous, mixed, synthetic, or not clearly identifiable.\n"

    "\n4. age: perceived age group from vocal qualities such as pitch, tone, energy, and maturity.\n"
    "- young: youthful voice, often brighter, lighter, or energetic; likely child, teen, or young adult.\n"
    "- middle_aged: adult mature voice, stable and natural; likely working-age adult.\n"
    "- middle-aged: same meaning as middle_aged; use only if this exact legacy label is required by the dataset.\n"
    "- old: elderly or senior-sounding voice, often slower, deeper, weaker, rougher, or more aged.\n"

    "\n5. accent: perceived accent or regional pronunciation style.\n"
    "- american: American English accent.\n"
    "- british: British English accent.\n"
    "- northern: Northern Vietnamese accent, often Hanoi or northern-region pronunciation.\n"
    "- central: Central Vietnamese accent, often Hue, Da Nang, or central-region pronunciation.\n"
    "- southern: Southern Vietnamese accent, often Ho Chi Minh City or southern-region pronunciation.\n"
    "- standard: neutral or standard pronunciation with no strong regional accent, or when accent is unclear.\n"

    "\n6. category: overall production or recording quality category.\n"
    "- high_quality: clean, clear, pleasant audio with low noise and good intelligibility; may be casual or non-studio.\n"
    "- professional: polished, studio-like, broadcast-ready, commercial, presenter-style, or voice-over quality.\n"

    "\n7. descriptive: the dominant vocal style, tone, or emotional impression. Choose the best single label.\n"
    "- calm: peaceful, steady, composed, not emotional or rushed.\n"
    "- casual: informal, natural, everyday speaking style.\n"
    "- chill: relaxed, easygoing, laid-back, slightly cool or informal.\n"
    "- classy: elegant, refined, polished, sophisticated.\n"
    "- confident: assured, strong, certain, persuasive.\n"
    "- crisp: clear articulation, sharp pronunciation, clean delivery.\n"
    "- cute: sweet, playful, youthful, endearing.\n"
    "- deep: low-pitched, resonant, bass-heavy voice.\n"
    "- excited: energetic, enthusiastic, expressive, high engagement.\n"
    "- formal: serious, structured, polite, official or business-like.\n"
    "- gentle: soft, kind, warm, careful, soothing.\n"
    "- mature: adult, stable, experienced, emotionally controlled.\n"
    "- meditative: slow, soothing, reflective, suitable for relaxation or mindfulness.\n"
    "- neutral: plain, balanced, no strong emotion or style.\n"
    "- pleasant: generally nice, agreeable, easy to listen to.\n"
    "- professional: polished, clear, reliable, suitable for business or commercial use.\n"
    "- relaxed: comfortable, unhurried, natural, low tension.\n"
    "- sad: sorrowful, low energy, melancholic, emotionally down.\n"
    "- serious: firm, focused, not playful, weighty or important tone.\n"
    "- soft: quiet, light, delicate, low intensity.\n"
    "- upbeat: positive, lively, cheerful, energetic but not overly excited.\n"
    "- wise: thoughtful, experienced, calm, reflective, mentor-like.\n"

    "\n8. use_case: the most suitable application for this voice.\n"
    "- advertisement: commercials, product promotion, marketing, brand campaigns.\n"
    "- characters_animation: animated characters, games, cartoons, fictional roles, dubbing.\n"
    "- conversational: chatbots, assistants, dialogue systems, natural conversations.\n"
    "- entertainment_tv: TV shows, entertainment programs, hosting, broadcast media.\n"
    "- informative_educational: tutorials, explainers, training, e-learning, educational content.\n"
    "- narrative_story: storytelling, audiobooks, narration, documentaries, story-driven content.\n"
    "- social_media: short-form videos, reels, TikTok, YouTube Shorts, influencer-style content.\n"

    "\n\nDESCRIPTION RULE:\n"
    "For description, write one natural English sentence summarizing the voice based on gender, age, accent, category, descriptive, and use_case. "
    "Do not mention locale or language in the description. "
    "Keep the description concise, natural, and suitable for a CSV cell. "
    "Example description style: 'A calm mature female voice with a southern accent, suitable for narrative storytelling.' "

    "\n\nOUTPUT FORMAT:\n"
    "Return valid JSON only, using double quotes for all keys and string values. "
    "The JSON must follow this exact structure:\n"
    "{"
    "\"description\": \"...\", "
    "\"language\": \"...\", "
    "\"locale\": \"...\", "
    "\"gender\": \"...\", "
    "\"age\": \"...\", "
    "\"accent\": \"...\", "
    "\"category\": \"...\", "
    "\"descriptive\": \"...\", "
    "\"use_case\": \"...\""
    "}"
)
    contents: List[Any] = [prompt]
    if fewshot_examples:
        contents.append(
            "Few-shot labeled audio examples are provided below. Learn the label boundary from them."
        )
        for idx, (label_type, label, ex_audio) in enumerate(fewshot_examples, start=1):
            if label_type == "descriptive":
                contents.append(
                    f"Example {idx} label: descriptive={label}, use_case=unknown. Focus on speaking style."
                )
            else:
                contents.append(
                    f"Example {idx} label: descriptive=unknown, use_case={label}. Focus on content use case."
                )
            contents.append(ex_audio)
    contents.append(
        "Now classify the next target audio. Return one best descriptive label and one best use_case label."
    )
    contents.append(uploaded)
    response = client.models.generate_content(
        model=model,
        contents=contents,
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
        "description": str(pred.get("description", "")).strip(),
        "language": str(pred.get("language", "")).strip(),
        "locale": str(pred.get("locale", "")).strip(),
        "gender": str(pred.get("gender", "")).strip(),
        "age": str(pred.get("age", "")).strip(),
        "accent": str(pred.get("accent", "")).strip(),
        "category": str(pred.get("category", "")).strip(),
        "descriptive": str(pred.get("descriptive", "")).strip(),
        "use_case": str(pred.get("use_case", "")).strip(),
    }
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
    fewshot_examples = load_fewshot_examples(
        client=client,
        fewshot_dir=Path(args.fewshot_dir),
        per_class=args.fewshot_per_class,
        max_total=args.fewshot_max_total,
    )
    print(f"fewshot: loaded {len(fewshot_examples)} exemplar audios")
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
                result = describe_audio(client, args.model, tmp_path, fewshot_examples)
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
