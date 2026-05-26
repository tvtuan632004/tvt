import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests


ROOT = Path(__file__).resolve().parent


def load_config(config_path):
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_ffmpeg_on_path():
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    try:
        import imageio_ffmpeg
    except ImportError:
        return

    ffmpeg_exe = Path(imageio_ffmpeg.get_ffmpeg_exe())
    os.environ["PATH"] = str(ffmpeg_exe.parent) + os.pathsep + os.environ.get("PATH", "")
    os.environ["IMAGEIO_FFMPEG_EXE"] = str(ffmpeg_exe)
    print(f"[SETUP] ffmpeg: {ffmpeg_exe}")


def run_command(args, cwd=ROOT):
    print("[RUN] " + " ".join(str(a) for a in args))
    subprocess.run([str(a) for a in args], cwd=str(cwd), check=True, env=os.environ.copy())


def write_keywords(cfg):
    save_dir = Path(cfg["save_dir"])
    domain = cfg["domain"]
    asset_dir = save_dir / f"MMSData{domain}" / "asset"
    asset_dir.mkdir(parents=True, exist_ok=True)

    keywords_path = asset_dir / "keywords.txt"
    keywords = cfg.get("keywords", [])
    if not isinstance(keywords, list):
        keywords = [keywords]

    with open(keywords_path, "w", encoding="utf-8") as f:
        for keyword in keywords:
            keyword = str(keyword).strip()
            if keyword:
                f.write(keyword + "\n")

    print(f"[SETUP] keywords: {keywords_path}")
    return asset_dir, keywords_path


def service_is_ready(base_url):
    try:
        res = requests.get(f"{base_url.rstrip('/')}/list_downloaded_videos", timeout=2)
        return res.status_code == 200
    except requests.RequestException:
        return False


def start_tracking_service(base_url, asset_dir, data_file=None, seed_file=None):
    parsed = urlparse(base_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8020

    if host not in {"127.0.0.1", "localhost"}:
        print(f"[TRACK] using remote tracking service: {base_url}")
        return None

    if service_is_ready(base_url):
        print(f"[TRACK] already running: {base_url}")
        return None

    data_file = Path(data_file) if data_file else asset_dir / "downloaded_videos.json"
    if not data_file.is_absolute():
        data_file = ROOT / data_file
    data_file.parent.mkdir(parents=True, exist_ok=True)
    args = [
        sys.executable,
        ROOT / "tools" / "check_download_video" / "check_download_video_api.py",
        "-d",
        data_file,
        "-p",
        str(port),
    ]
    if seed_file:
        args.extend(["--seed", seed_file])

    print(f"[TRACK] starting local service: {base_url}")
    proc = subprocess.Popen([str(a) for a in args], cwd=str(ROOT), env=os.environ.copy())
    for _ in range(30):
        if service_is_ready(base_url):
            return proc
        time.sleep(0.5)

    proc.terminate()
    raise RuntimeError(f"Tracking service did not start at {base_url}")


def run_search(cfg, keywords_path, asset_dir):
    search_cfg = cfg.get("search_config", {})
    lang = search_cfg.get("lang", "vi")
    region = search_cfg.get("region", "VN")
    json_dir = asset_dir / "json"
    mark_dir = asset_dir / "mark"

    for search_type, limit_key, default_limit in [
        ("video", "video_limit", 10),
        ("channel", "channel_limit", 2),
    ]:
        limit = int(search_cfg.get(limit_key, default_limit))
        if limit <= 0:
            print(f"[SEARCH] skip {search_type}: {limit_key}=0")
            continue

        run_command(
            [
                sys.executable,
                ROOT / "tools" / "crawl_async.py",
                "--keyword",
                keywords_path,
                "--search",
                search_type,
                "--output",
                json_dir,
                "--mark",
                mark_dir,
                "--limit",
                str(limit),
                "--lang",
                lang,
                "--region",
                region,
            ]
        )


def run_download(config_path):
    run_command([sys.executable, ROOT / "S02_download.py", config_path])


def main():
    parser = argparse.ArgumentParser(description="Run YouTube crawl/download on Windows without bash.")
    parser.add_argument("--config", default="config/youtube_crawl_local.json")
    parser.add_argument("--search-only", action="store_true")
    parser.add_argument("--download-only", action="store_true")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = ROOT / config_path

    ensure_ffmpeg_on_path()
    cfg = load_config(config_path)
    asset_dir, keywords_path = write_keywords(cfg)

    tracking_proc = None
    try:
        tracking_url = cfg.get("download_config", {}).get("check_downloaded_video_url")
        if tracking_url and not args.search_only:
            tracking_proc = start_tracking_service(
                tracking_url,
                asset_dir,
                seed_file=cfg.get("download_config", {}).get("download_registry_file"),
            )

        status = cfg.get("status", {})
        if not args.download_only and status.get("search", True):
            run_search(cfg, keywords_path, asset_dir)

        if not args.search_only and status.get("download", True):
            run_download(config_path)

        print("[DONE] YouTube crawl pipeline finished.")
    finally:
        if tracking_proc is not None:
            tracking_proc.terminate()
            tracking_proc.wait(timeout=10)


if __name__ == "__main__":
    main()
