#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Tuple
import math

FIELDS = [
    "description",
    "language",
    "locale",
    "gender",
    "age",
    "accent",
    "category",
    "descriptive",
    "use_case",
]
CAT_FIELDS = [f for f in FIELDS if f != "description"]

CONCEPT_SYNONYMS = {
    "professional": {"professional", "formal", "corporate"},
    "calm": {"calm", "gentle", "soft", "relaxed", "soothing"},
    "energetic": {"energetic", "excited", "upbeat", "dynamic"},
    "deep": {"deep", "low", "resonant"},
    "clear": {"clear", "crisp", "clean"},
    "warm": {"warm", "friendly"},
    "mature": {"mature", "middle_aged", "middle-aged", "senior", "old"},
    "young": {"young", "youthful"},
    "narrative_story": {"story", "storytelling", "narrative"},
    "informative_educational": {"educational", "informative", "explain", "knowledge", "news"},
    "advertisement": {"advertisement", "commercial", "promo", "marketing"},
    "conversational": {"conversational", "chatty", "dialogue"},
    "social_media": {"social", "media", "tiktok", "youtube", "shorts"},
    "entertainment_tv": {"entertainment", "tv", "show"},
    "characters_animation": {"character", "animation", "cartoon"},
    "podcast": {"podcast"},
    "voiceover": {"voiceover", "narration"},
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="tools/elevenlabs_voices_vi.csv")
    p.add_argument("--pred", default="tools/elevenlabs_voices_vi_gemini.csv")
    p.add_argument("--out-json", default="tools/report_compare_semantic.json")
    p.add_argument("--out-md", default="tools/report_compare_semantic.md")
    p.add_argument("--desc-threshold", type=float, default=0.72)
    p.add_argument(
        "--semantic-method",
        choices=["heuristic", "embedding"],
        default="embedding",
        help="Description semantic matching method",
    )
    p.add_argument(
        "--embedding-threshold",
        type=float,
        default=0.72,
        help="Cosine threshold for embedding semantic match",
    )
    p.add_argument(
        "--embedding-model",
        default="sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
        help="SentenceTransformer model name",
    )
    return p.parse_args()


def load_csv(path: Path) -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            vid = (row.get("voice_id") or "").strip()
            if vid:
                out[vid] = row
    return out


def norm_text(s: str) -> str:
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("-", "_")
    s = re.sub(r"\s+", " ", s)
    return s


def clean_description_for_voice_style(s: str) -> str:
    """Keep voice-style content; drop speaker intro/name-heavy fragments."""
    text = (s or "").strip()
    if not text:
        return ""
    # Remove obvious "Name - description" / "Name: description" prefixes.
    text = re.sub(r"^[^:.\n-]{1,80}\s*[-:]\s*(?=[A-Za-z])", "", text).strip()

    # Normalize punctuation for sentence splitting.
    text = text.replace("—", ". ").replace("–", ". ")
    parts = re.split(r"[.!?]\s+|\n+", text)
    kept: List[str] = []

    # Style-oriented cues we want to keep.
    keep_cues = (
        "voice",
        "tone",
        "accent",
        "speaks",
        "speaking",
        "pronunciation",
        "delivery",
        "clear",
        "warm",
        "calm",
        "gentle",
        "deep",
        "soft",
        "energetic",
        "professional",
        "narration",
        "storytelling",
        "podcast",
        "educational",
        "commercial",
        "audiobook",
        "use",
        "suitable",
        "ideal",
        "best for",
    )
    # Intro/bio-like cues we want to remove.
    drop_cues = (
        "name is",
        "i am",
        "i'm",
        "from ",
        "writer",
        "actor",
        "singer",
        "mc ",
        "host ",
        "my channel",
    )

    for raw in parts:
        sent = raw.strip(" ,;:-")
        if not sent:
            continue
        low = sent.lower()

        if any(c in low for c in keep_cues):
            kept.append(sent)
            continue

        # Drop short intro fragments at head if they look like bio/name.
        if any(c in low for c in drop_cues):
            continue
        if ":" in sent and len(sent.split()) <= 8:
            # e.g. "Ca Dao - Literary writer from Hue"
            continue
        if "-" in sent and len(sent.split()) <= 8:
            continue

    if kept:
        return ". ".join(kept).strip()

    # Fallback: remove leading "Name - " / "Name: " pattern.
    fallback = re.sub(r"^[^-:]{1,80}\s*[-:]\s*", "", text).strip()
    return fallback or text


def canonicalize(value: str, allowed: List[str], canonical_by_norm: Dict[str, str]) -> str:
    v = norm_text(value)
    if not v:
        return ""
    if v in canonical_by_norm:
        return canonical_by_norm[v]

    # sửa lỗi chính tả/format nhẹ bằng fuzzy match
    best = None
    best_score = -1.0
    allowed_norm = [norm_text(a) for a in allowed]
    for cand_raw, cand_norm in zip(allowed, allowed_norm):
        score = SequenceMatcher(None, v, cand_norm).ratio()
        if score > best_score:
            best_score = score
            best = cand_raw

    # Ngưỡng tương đối chặt để tránh map sai nghĩa
    if best is not None and best_score >= 0.86:
        return best
    return value.strip()


def extract_concepts(s: str) -> set[str]:
    t = set(re.findall(r"[a-z_]+", norm_text(s)))
    concepts = set()
    for concept, syns in CONCEPT_SYNONYMS.items():
        if t & syns:
            concepts.add(concept)
    return concepts


def description_semantic_match(a: str, b: str, threshold: float) -> Tuple[bool, float, float]:
    na = norm_text(a)
    nb = norm_text(b)

    # similarity ký tự tổng quát
    ratio = SequenceMatcher(None, na, nb).ratio()

    # overlap theo concept ngữ nghĩa
    ca = extract_concepts(na)
    cb = extract_concepts(nb)
    if not ca and not cb:
        concept_j = 0.0
    else:
        concept_j = len(ca & cb) / max(1, len(ca | cb))

    # chấp nhận nếu một trong hai điều kiện mạnh thỏa
    ok = (ratio >= threshold) or (concept_j >= 0.40) or (concept_j >= 0.25 and ratio >= 0.45)
    return ok, ratio, concept_j


def cosine(u: List[float], v: List[float]) -> float:
    dot = sum(x * y for x, y in zip(u, v))
    nu = math.sqrt(sum(x * x for x in u))
    nv = math.sqrt(sum(y * y for y in v))
    if nu == 0.0 or nv == 0.0:
        return 0.0
    return dot / (nu * nv)


def main() -> int:
    args = parse_args()
    base = load_csv(Path(args.base))
    pred = load_csv(Path(args.pred))

    common = sorted(set(base) & set(pred))
    only_base = sorted(set(base) - set(pred))
    only_pred = sorted(set(pred) - set(base))

    allowed_by_field: Dict[str, List[str]] = {}
    canonical_norm_by_field: Dict[str, Dict[str, str]] = {}
    for f in CAT_FIELDS:
        vals = [(base[v].get(f) or "").strip() for v in common if (base[v].get(f) or "").strip()]
        allowed_by_field[f] = sorted(set(vals))
        freq = Counter(vals)
        by_norm: Dict[str, List[Tuple[str, int]]] = {}
        for raw, c in freq.items():
            by_norm.setdefault(norm_text(raw), []).append((raw, c))
        canonical_norm_by_field[f] = {
            k: sorted(v, key=lambda x: x[1], reverse=True)[0][0] for k, v in by_norm.items()
        }

    report = {
        "base_rows": len(base),
        "pred_rows": len(pred),
        "overlap": len(common),
        "only_base": len(only_base),
        "only_pred": len(only_pred),
        "desc_threshold": args.desc_threshold,
        "semantic_method": args.semantic_method,
        "embedding_threshold": args.embedding_threshold,
        "embedding_model": args.embedding_model,
        "fields": {},
        "normalization_changes": {f: [] for f in CAT_FIELDS},
    }

    for f in CAT_FIELDS:
        exact = 0
        mism = []
        tr = Counter()
        base_dist = Counter()
        pred_dist = Counter()

        allowed = allowed_by_field[f]
        for vid in common:
            bv = (base[vid].get(f) or "").strip()
            pv_raw = (pred[vid].get(f) or "").strip()
            pv = canonicalize(pv_raw, allowed, canonical_norm_by_field[f])

            if pv != pv_raw:
                report["normalization_changes"][f].append({
                    "voice_id": vid,
                    "from": pv_raw,
                    "to": pv,
                })

            base_dist[bv] += 1
            pred_dist[pv] += 1
            if bv == pv:
                exact += 1
            else:
                mism.append((vid, bv, pv))
                tr[(bv, pv)] += 1

        total = len(common)
        report["fields"][f] = {
            "match": exact,
            "total": total,
            "match_rate": (exact / total if total else 0.0),
            "top_base": base_dist.most_common(12),
            "top_pred_norm": pred_dist.most_common(12),
            "top_transitions": [
                {"base": k[0], "pred": k[1], "count": v} for k, v in tr.most_common(12)
            ],
            "sample_mismatch": mism[:20],
        }

    # description semantic compare
    d_ok = 0
    bad_samples = []
    all_samples = []
    if args.semantic_method == "embedding":
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise SystemExit(
                "Missing sentence-transformers. Install with: "
                "python -m pip install -U sentence-transformers"
            ) from exc

        texts_a = [
            clean_description_for_voice_style((base[vid].get("description") or "").strip())
            for vid in common
        ]
        texts_b = [
            clean_description_for_voice_style((pred[vid].get("description") or "").strip())
            for vid in common
        ]
        model = SentenceTransformer(args.embedding_model)
        emb_a = model.encode(texts_a, normalize_embeddings=True)
        emb_b = model.encode(texts_b, normalize_embeddings=True)
        sims: List[float] = []
        for i, vid in enumerate(common):
            sim = float(cosine(emb_a[i], emb_b[i]))
            sims.append(sim)
            ok = sim >= args.embedding_threshold
            all_samples.append(
                {
                    "voice_id": vid,
                    "match": ok,
                    "cosine": round(sim, 4),
                    "base_clean": texts_a[i],
                    "pred_clean": texts_b[i],
                    "base_raw": (base[vid].get("description") or "").strip(),
                    "pred_raw": (pred[vid].get("description") or "").strip(),
                }
            )
            if ok:
                d_ok += 1
            elif len(bad_samples) < 20:
                bad_samples.append(
                    {
                        "voice_id": vid,
                        "cosine": round(sim, 4),
                        "base_clean": texts_a[i],
                        "pred_clean": texts_b[i],
                        "base_raw": (base[vid].get("description") or "").strip(),
                        "pred_raw": (pred[vid].get("description") or "").strip(),
                    }
                )
        report["fields"]["description"] = {
            "semantic_match": d_ok,
            "total": len(common),
            "semantic_match_rate": (d_ok / len(common) if common else 0.0),
            "avg_cosine": (sum(sims) / len(sims) if sims else 0.0),
            "all_samples": all_samples,
            "bad_samples": bad_samples,
        }
    else:
        ratios = []
        keyjs = []
        for vid in common:
            a = (base[vid].get("description") or "").strip()
            b = (pred[vid].get("description") or "").strip()
            ac = clean_description_for_voice_style(a)
            bc = clean_description_for_voice_style(b)
            ok, ratio, keyj = description_semantic_match(ac, bc, args.desc_threshold)
            ratios.append(ratio)
            keyjs.append(keyj)
            all_samples.append(
                {
                    "voice_id": vid,
                    "match": ok,
                    "ratio": round(ratio, 4),
                    "keyword_jaccard": round(keyj, 4),
                    "base_clean": ac,
                    "pred_clean": bc,
                    "base_raw": a,
                    "pred_raw": b,
                }
            )
            if ok:
                d_ok += 1
            elif len(bad_samples) < 20:
                bad_samples.append({
                    "voice_id": vid,
                    "ratio": round(ratio, 3),
                    "keyword_jaccard": round(keyj, 3),
                    "base_clean": ac,
                    "pred_clean": bc,
                    "base_raw": a,
                    "pred_raw": b,
                })

        report["fields"]["description"] = {
            "semantic_match": d_ok,
            "total": len(common),
            "semantic_match_rate": (d_ok / len(common) if common else 0.0),
            "avg_ratio": (sum(ratios) / len(ratios) if ratios else 0.0),
            "avg_keyword_jaccard": (sum(keyjs) / len(keyjs) if keyjs else 0.0),
            "all_samples": all_samples,
            "bad_samples": bad_samples,
        }

    Path(args.out_json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = []
    lines.append("# Report so sánh có chuẩn hóa lỗi chính tả + semantic description")
    lines.append("")
    lines.append(f"- Base: `{args.base}`")
    lines.append(f"- Pred: `{args.pred}`")
    lines.append(f"- Overlap voice_id: {len(common)}")
    lines.append(f"- Chỉ ở base: {len(only_base)} | Chỉ ở pred: {len(only_pred)}")
    lines.append("")
    lines.append("## Match rate sau chuẩn hóa")
    lines.append("")
    lines.append("| Field | Match | Total | Rate |")
    lines.append("|---|---:|---:|---:|")
    for f in CAT_FIELDS:
        d = report["fields"][f]
        lines.append(f"| {f} | {d['match']} | {d['total']} | {d['match_rate']*100:.2f}% |")
    dd = report["fields"]["description"]
    lines.append(f"| description (semantic) | {dd['semantic_match']} | {dd['total']} | {dd['semantic_match_rate']*100:.2f}% |")

    lines.append("")
    lines.append("## Sửa lỗi chính tả/format đã áp dụng")
    for f in CAT_FIELDS:
        changes = report["normalization_changes"][f]
        if not changes:
            continue
        pair_count = Counter((c["from"], c["to"]) for c in changes)
        lines.append("")
        lines.append(f"### `{f}`")
        for (a, b), c in pair_count.most_common(10):
            lines.append(f"- `{a}` -> `{b}`: {c}")

    Path(args.out_md).write_text("\n".join(lines), encoding="utf-8")
    print(args.out_json)
    print(args.out_md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
