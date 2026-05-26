import argparse
import json
import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import yt_dlp


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def parse_time(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_train_json(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("train.json must be a JSON object")
    if "audios" not in data or not isinstance(data["audios"], list):
        raise ValueError("train.json must contain `audios` as a list")

    return data


def download_audio_mp3(aid, url, out_dir, proxy_url=None, retries=3, timeout=20):
    ensure_dir(out_dir)
    final_path = os.path.join(out_dir, f"{aid}.mp3")

    if os.path.exists(final_path) and os.path.getsize(final_path) > 0:
        return final_path

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(out_dir, f"{aid}.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": timeout,
        "retries": retries,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }
    if proxy_url:
        ydl_opts["proxy"] = proxy_url

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    if not os.path.exists(final_path) or os.path.getsize(final_path) == 0:
        raise RuntimeError(f"Downloaded file missing or empty: {final_path}")

    return final_path


def cut_segment_to_mp3(ffmpeg_bin, src_audio, segment, out_dir, overwrite=False):
    sid = segment.get("sid")
    begin = parse_time(segment.get("begin_time"))
    end = parse_time(segment.get("end_time"))

    if not sid:
        return False, "missing sid", None
    if begin is None or end is None or end <= begin:
        return False, f"invalid timestamp: begin={segment.get('begin_time')} end={segment.get('end_time')}", None

    ensure_dir(out_dir)
    out_path = os.path.join(out_dir, f"{sid}.mp3")

    if os.path.exists(out_path) and os.path.getsize(out_path) > 0 and not overwrite:
        return True, "exists", out_path

    cmd = [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y" if overwrite else "-n",
        "-ss",
        f"{begin:.3f}",
        "-to",
        f"{end:.3f}",
        "-i",
        src_audio,
        "-vn",
        "-c:a",
        "libmp3lame",
        "-q:a",
        "2",
        out_path,
    ]

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        return False, proc.stderr.strip() or "ffmpeg failed", None

    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        return False, "empty output", None

    return True, "ok", out_path


def process_one_audio(audio_item, cfg):
    aid = audio_item.get("aid")
    url = audio_item.get("url")
    segments = audio_item.get("segments", [])

    if not aid or not url:
        return {
            "aid": aid or "UNKNOWN",
            "status": "error",
            "error": "missing aid/url",
            "segments_total": len(segments) if isinstance(segments, list) else 0,
            "segments_ok": 0,
        }

    if not isinstance(segments, list):
        return {
            "aid": aid,
            "status": "error",
            "error": "segments must be a list",
            "segments_total": 0,
            "segments_ok": 0,
        }

    try:
        audio_path = download_audio_mp3(
            aid=aid,
            url=url,
            out_dir=cfg["full_audio_dir"],
            proxy_url=cfg["proxy_url"],
            retries=cfg["retries"],
            timeout=cfg["timeout"],
        )
    except Exception as e:
        return {
            "aid": aid,
            "status": "error",
            "error": f"download failed: {e}",
            "segments_total": len(segments),
            "segments_ok": 0,
        }

    seg_ok = 0
    seg_errors = []
    kept_segments = []

    for seg in segments:
        ok, msg, seg_path = cut_segment_to_mp3(
            ffmpeg_bin=cfg["ffmpeg_bin"],
            src_audio=audio_path,
            segment=seg,
            out_dir=cfg["segments_dir"],
            overwrite=cfg["overwrite"],
        )
        if ok:
            seg_ok += 1
            seg_record = {
                "sid": seg.get("sid"),
                "begin_time": str(seg.get("begin_time")),
                "end_time": str(seg.get("end_time")),
                "text_tn": seg.get("text_tn", ""),
                "audio_file": os.path.relpath(seg_path, cfg["output_dir"]),
            }
            kept_segments.append(seg_record)
        else:
            seg_errors.append(
                {
                    "sid": seg.get("sid"),
                    "begin_time": seg.get("begin_time"),
                    "end_time": seg.get("end_time"),
                    "error": msg,
                }
            )

    manifest = {
        "aid": aid,
        "url": url,
        "audio_file": os.path.relpath(audio_path, cfg["output_dir"]),
        "segments_total": len(segments),
        "segments_ok": seg_ok,
        "segments": kept_segments,
    }

    if seg_errors:
        manifest["segment_errors"] = seg_errors

    manifest_path = os.path.join(cfg["manifests_dir"], f"{aid}.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    return {
        "aid": aid,
        "status": "ok",
        "error": "",
        "segments_total": len(segments),
        "segments_ok": seg_ok,
    }


def build_arg_parser():
    parser = argparse.ArgumentParser(
        description="Download audio from train.json and cut segments to sid.mp3 files."
    )
    parser.add_argument("--train-json", required=True, help="Path to train.json")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--num-workers", type=int, default=6, help="Thread workers")
    parser.add_argument("--proxy-url", default="", help="HTTP proxy URL (optional)")
    parser.add_argument("--ffmpeg-bin", default="ffmpeg", help="Path to ffmpeg binary")
    parser.add_argument("--retries", type=int, default=3, help="Download retries")
    parser.add_argument("--timeout", type=int, default=20, help="Download socket timeout")
    parser.add_argument("--limit", type=int, default=0, help="Only process first N audios (0 = all)")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing sid.mp3 files")
    return parser


def main():
    args = build_arg_parser().parse_args()

    data = load_train_json(args.train_json)
    audios = data["audios"]

    if args.limit > 0:
        audios = audios[: args.limit]

    ensure_dir(args.output_dir)
    full_audio_dir = os.path.join(args.output_dir, "full_audio_mp3")
    segments_dir = os.path.join(args.output_dir, "segments_mp3")
    manifests_dir = os.path.join(args.output_dir, "manifests")
    ensure_dir(full_audio_dir)
    ensure_dir(segments_dir)
    ensure_dir(manifests_dir)

    cfg = {
        "output_dir": args.output_dir,
        "full_audio_dir": full_audio_dir,
        "segments_dir": segments_dir,
        "manifests_dir": manifests_dir,
        "proxy_url": args.proxy_url or None,
        "ffmpeg_bin": args.ffmpeg_bin,
        "retries": args.retries,
        "timeout": args.timeout,
        "overwrite": args.overwrite,
    }

    total = len(audios)
    done = 0
    ok_audio = 0
    total_segments = 0
    ok_segments = 0
    lock = threading.Lock()

    print(f"Total audios: {total}")
    start = time.time()

    results = []
    with ThreadPoolExecutor(max_workers=max(1, args.num_workers)) as ex:
        futures = [ex.submit(process_one_audio, a, cfg) for a in audios]

        for fut in as_completed(futures):
            result = fut.result()
            results.append(result)

            with lock:
                done += 1
                total_segments += result.get("segments_total", 0)
                ok_segments += result.get("segments_ok", 0)
                if result.get("status") == "ok":
                    ok_audio += 1
                elapsed = time.time() - start
                speed = done / elapsed if elapsed > 0 else 0
                eta = (total - done) / speed if speed > 0 else 0

            aid = result.get("aid")
            if result.get("status") == "ok":
                print(
                    f"[OK] {aid} | segments {result.get('segments_ok')}/{result.get('segments_total')} "
                    f"| {done}/{total} | ETA {eta:.1f}s"
                )
            else:
                print(f"[ERR] {aid} | {result.get('error')} | {done}/{total} | ETA {eta:.1f}s")

    summary = {
        "dataset": data.get("dataset"),
        "language": data.get("language"),
        "version": data.get("version"),
        "train_json": os.path.abspath(args.train_json),
        "output_dir": os.path.abspath(args.output_dir),
        "total_audios": total,
        "ok_audios": ok_audio,
        "failed_audios": total - ok_audio,
        "total_segments": total_segments,
        "ok_segments": ok_segments,
        "failed_segments": total_segments - ok_segments,
        "elapsed_sec": round(time.time() - start, 2),
    }

    with open(os.path.join(args.output_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    with open(os.path.join(args.output_dir, "audio_results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("Done.")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
