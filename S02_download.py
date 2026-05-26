import os
import json
import re
import glob
import time
import random
import shutil
import sys
import requests
from functools import partial
from multiprocessing import Pool, Value
from concurrent.futures import ThreadPoolExecutor
import yt_dlp

counter = Value('i', 0)
GLOBAL_START = time.time()

def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def check_video(video_id, check_url):
    try:
        res = requests.get(f"{check_url}/check_video", params={"video_id": video_id})
        return res.status_code == 200 and res.json().get("exists", False)
    except:
        return False

def is_downloaded_ok(video_id, dataset_dir):
    status_path = os.path.join(dataset_dir, video_id, "status.json")
    if not os.path.exists(status_path):
        return False
    
    try:
        with open(status_path) as f:
            return json.load(f).get("download", False)
    except:
        return False

def add_video(video_id, check_url):
    try:
        requests.get(f"{check_url}/add_video", params={"video_id": video_id})
    except:
        pass

def reserve_video(video_id, check_url, metadata=None):
    if not check_url:
        return True
    try:
        res = requests.post(
            f"{check_url}/reserve_video",
            json={"video_id": video_id, "metadata": metadata or {}},
            timeout=5,
        )
        if res.status_code != 200:
            return True
        data = res.json()
        return bool(data.get("reserved", False))
    except Exception as e:
        print(f"[WARN] Cannot reserve {video_id}: {e}. Continuing without shared reserve.")
        return True

def complete_video(video_id, check_url, metadata=None):
    if not check_url:
        return
    try:
        requests.post(
            f"{check_url}/complete_video",
            json={"video_id": video_id, "metadata": metadata or {}},
            timeout=5,
        )
    except Exception as e:
        print(f"[WARN] Cannot complete registry record for {video_id}: {e}")

def fail_video(video_id, check_url, error):
    if not check_url:
        return
    try:
        requests.post(
            f"{check_url}/fail_video",
            json={"video_id": video_id, "error": str(error)},
            timeout=5,
        )
    except Exception:
        pass

def load_download_registry_ids(registry_file):
    if not registry_file:
        return set()
    try:
        with open(registry_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return set(str(k) for k in data.keys())
        if isinstance(data, list):
            return set(str(v) for v in data)
    except FileNotFoundError:
        print(f"[WARN] Download registry not found: {registry_file}")
    except Exception as e:
        print(f"[WARN] Cannot read download registry {registry_file}: {e}")
    return set()

def _strip_subtitle_text(raw_text):
    lines = []
    for line in raw_text.splitlines():
        s = line.strip()
        if not s or s == "WEBVTT" or s.isdigit() or "-->" in s or s.startswith(("NOTE", "STYLE", "REGION")):
            continue
        if s.startswith(("NOTE", "STYLE", "REGION", "Kind:", "Language:", "align:", "Position:")):
            continue
        s = re.sub(r"<[^>]+>", "", s)
        s = re.sub(r"^e\d+\s*", "", s)
        s = s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'").replace("&gt;", "")
        s = re.sub(r"\s+", " ", s).strip()
        if not s:
            continue

        if not lines:
            lines.append(s)
        else:
            prev = lines[-1]
            # TH1: Câu mới lặp lại y hệt câu cũ -> Bỏ qua luôn
            if s == prev:
                continue
            # TH2: Câu mới chứa câu cũ (Dạng gõ chữ Karaoke: "Tôi" -> "Tôi đi" -> "Tôi đi học")
            # -> Ghi đè câu cũ bằng câu dài nhất
            elif s.startswith(prev):
                lines[-1] = s
            # TH3: Câu cũ lại dài hơn câu mới (Lỗi bất thường của YT) -> Giữ câu cũ
            elif prev.startswith(s):
                continue
            # TH4: Một câu hoàn toàn mới -> Xuống dòng
            else:
                lines.append(s)
                
    return "\n".join(lines).strip()

def validate_video_info(json_file, config):
    # video_id = os.path.splitext(os.path.basename(json_file))[0]
    # try:
    #     with open(json_file, "r", encoding="utf-8") as f:
    #         video_info = json.load(f)

    #     sub_info = video_info.get("subtitle", {})
    #     segment_number = sub_info.get("segments", 0)
    #     languages = sub_info.get("languages", [])

    #     if not languages:
    #         if config["verbose"]: print(f"Skip ---> Can not detect language : {video_id}")
    #         return False

    #     correct_lang = any(config["lang"] in lang.get("title", "").lower() for lang in languages)
    #     if not correct_lang:
    #         if config["verbose"]: print(f"Skip ---> This is not {config['lang']} language : {video_id}")
    #         return False

    #     if segment_number <= config["min_segment"]:
    #         if config["verbose"]: print(f"Skip ---> Too short/no transcript ({segment_number}) : {video_id}")
    #         return False

    #     return True
    # except Exception as e:
    #     if config["verbose"]: print(f"Skip ---> Bad JSON {video_id}: {e}")
    #     return False
    return True

def download_video_and_sub(video_id, outdir, config):
    time.sleep(random.uniform(1.0, 3.5)) 
    
    url = f"https://www.youtube.com/watch?v={video_id}"
    langs_list = config["lang"]
    
    raw_audio_dir = os.path.join(outdir, "raw_audio")
    video_dir = os.path.join(outdir, "video")
    subtitle_dir = os.path.join(outdir, "youtube_subtitle")
    text_dir = os.path.join(subtitle_dir, "text")
    
    _ensure_dir(raw_audio_dir)
    _ensure_dir(video_dir)
    _ensure_dir(subtitle_dir)
    _ensure_dir(text_dir)

    download_video = config.get("download_video", False)

    max_height = config.get("max_video_height", 1080)
    if download_video:
        video_format = f"bestvideo[ext=mp4][height<={max_height}]+bestaudio[ext=m4a]/best[ext=mp4][height<={max_height}]/best"
    else:
        video_format = "bestaudio/best"
    def _progress_hook(d):
        if d.get("status") == "downloading":
            percent = d.get("_percent_str", "").strip()
            speed = d.get("_speed_str", "").strip()
            eta = d.get("_eta_str", "").strip()
            print(f"[DL] {video_id} {percent} {speed} ETA {eta}")
        elif d.get("status") == "finished":
            fname = d.get("filename", "")
            print(f"[DL] {video_id} Finished -> {fname}")

    ydl_opts = {
        "format": video_format,
        "outtmpl": os.path.join(raw_audio_dir, f"{video_id}.%(ext)s"),
        "noplaylist": True,
        "quiet": False,
        "no_warnings": False,
        "noprogress": False,
        "logger": None,
        "progress_hooks": [_progress_hook],

        # Bật tải Subtitle
        "writesubtitles": config.get("write_subtitles", True),
        "writeautomaticsub": config.get("write_automatic_subtitles", True),
        "subtitleslangs": langs_list,
        "subtitlesformat": "vtt/best",

        "extractor_args": {"youtube": ["player_client=tv,ios"]}, 
        "socket_timeout": 15,
        "retries": 8,
        'concurrent_fragment_downloads': 5,
        "source_address": "0.0.0.0",

        "keepvideo": download_video,
        "merge_output_format": "mp4",
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}],
        "postprocessor_args": ["-ar", "16000", "-ac", "1"]
    }

    node_path = shutil.which("node")
    if node_path:
        ydl_opts["js_runtimes"] = {"node": {"path": node_path}}
    if config.get("allow_remote_components", True):
        ydl_opts["remote_components"] = ["ejs:github"]
    if config.get("cookies_from_browser"):
        cookies_from_browser = config["cookies_from_browser"]
        if isinstance(cookies_from_browser, str):
            ydl_opts["cookiesfrombrowser"] = (cookies_from_browser,)
        else:
            ydl_opts["cookiesfrombrowser"] = tuple(cookies_from_browser)
    if config.get("cookie_file"):
        cookie_file = os.path.abspath(config["cookie_file"])
        if os.path.exists(cookie_file):
            ydl_opts["cookiefile"] = cookie_file
        else:
            print(f"[WARN] Cookie file not found: {cookie_file}")
    ffmpeg_path = os.environ.get("IMAGEIO_FFMPEG_EXE") or shutil.which("ffmpeg")
    if ffmpeg_path:
        ydl_opts["ffmpeg_location"] = ffmpeg_path
    
    def _make_ydl_opts(use_proxy, write_subtitles=True):
        opts = dict(ydl_opts)
        if use_proxy and config.get("proxy_url"):
            opts["proxy"] = config["proxy_url"]
        if not write_subtitles:
            opts["writeautomaticsub"] = False
            opts["writesubtitles"] = False
            opts.pop("subtitleslangs", None)
            opts.pop("subtitlesformat", None)
        return opts

    def _extract_info_with_proxy_fallback(write_subtitles=True):
        use_proxy = bool(config.get("proxy_url"))
        try:
            with yt_dlp.YoutubeDL(_make_ydl_opts(use_proxy, write_subtitles)) as ydl:
                return ydl.extract_info(url, download=True)
        except Exception as e:
            msg = str(e).lower()
            if use_proxy and ("proxy" in msg or "unable to connect to proxy" in msg):
                print(f"[WARN] Proxy failed for {video_id}. Retrying without proxy...")
                with yt_dlp.YoutubeDL(_make_ydl_opts(False, write_subtitles)) as ydl:
                    return ydl.extract_info(url, download=True)
            raise

    try:
        use_proxy = bool(config.get("proxy_url"))
        try:
            with yt_dlp.YoutubeDL(_make_ydl_opts(use_proxy)) as ydl:
                # Lưu lại info để lấy metadata
                info = ydl.extract_info(url, download=True)
        except Exception as e:
            msg = str(e).lower()
            if use_proxy and ("proxy" in msg or "unable to connect to proxy" in msg):
                print(f"[WARN] Proxy failed for {video_id}. Retrying without proxy...")
                with yt_dlp.YoutubeDL(_make_ydl_opts(False)) as ydl:
                    info = ydl.extract_info(url, download=True)
            else:
                raise
            
        sub_files = glob.glob(os.path.join(raw_audio_dir, "*.vtt")) + glob.glob(os.path.join(raw_audio_dir, "*.srt"))
        # has_text = False
        segment_count = 0
        
        for sub_file in sub_files:
            filename = os.path.basename(sub_file)
            new_sub_path = os.path.join(subtitle_dir, filename)
            shutil.move(sub_file, new_sub_path)
            
            with open(new_sub_path, "r", encoding="utf-8", errors="ignore") as f:
                cleaned_text = _strip_subtitle_text(f.read())
                
            if cleaned_text:
                base_name = os.path.splitext(filename)[0]
                txt_file = os.path.join(text_dir, f"{base_name}.txt")
                with open(txt_file, "w", encoding="utf-8") as f:
                    f.write(cleaned_text + "\n")
                # has_text = True
                
                segment_count = len(cleaned_text.splitlines())

        if download_video:
            video_exts = {".mp4", ".mkv", ".webm", ".mov"}
            for fpath in glob.glob(os.path.join(raw_audio_dir, f"{video_id}.*")):
                if os.path.splitext(fpath)[1].lower() in video_exts:
                    shutil.move(fpath, os.path.join(video_dir, os.path.basename(fpath)))

        # Cleanup leftover format fragments and empty audio files
        for fpath in glob.glob(os.path.join(raw_audio_dir, f"{video_id}.f*")):
            try:
                os.remove(fpath)
            except OSError:
                pass
        for fpath in glob.glob(os.path.join(raw_audio_dir, f"{video_id}.m4a")):
            try:
                if os.path.getsize(fpath) == 0:
                    os.remove(fpath)
            except OSError:
                pass
                
        audio_path = os.path.join(raw_audio_dir, f"{video_id}.wav")
        if not os.path.exists(audio_path):
            shutil.rmtree(outdir, ignore_errors=True)
            return False, None, 0

        with open(os.path.join(outdir, "status.json"), "w", encoding="utf-8") as f:
            json.dump({"download": True}, f)
            
        return True, info, segment_count

    except Exception as e:
        shutil.rmtree(outdir, ignore_errors=True)
        raise e

def crawl_video(json_file, config):
    start = time.time()
    video_id = os.path.splitext(os.path.basename(json_file))[0]
    outdir = os.path.join(config["Dataset_dir"], video_id)
    
    try:
        with open(json_file, "r", encoding="utf-8") as f:
            old_data = json.load(f)

        if not reserve_video(video_id, config["check_downloaded_video_url"], old_data):
            print(f"[SKIP Shared Registry] {video_id}")
            return

        if not validate_video_info(json_file, config):
            fail_video(video_id, config["check_downloaded_video_url"], "validation failed")
            return

        success, info, segment_count = download_video_and_sub(video_id, outdir, config)
        if not success:
            print(f"---> Failed -> Skip: {video_id}")
            fail_video(video_id, config["check_downloaded_video_url"], "download failed")
            return
            
        languages_list = []
        if segment_count > 0 and info.get('requested_subtitles'):
            first_lang_key = list(info['requested_subtitles'].keys())[0]
            sub_title = info['requested_subtitles'][first_lang_key].get('name', 'Unknown')
            languages_list.append({
                "selected": True,
                "title": sub_title
            })
        
        new_metadata = {
            "duration": info.get('duration', old_data.get('duration', 0)),
            "link": f"https://www.youtube.com/watch?v={video_id}",
            "id": video_id,
            "title": info.get('title', old_data.get('title', "")),
            "channel_name": info.get('channel', old_data.get('channel_name', "")),
            "channel_id": info.get('channel_id', old_data.get('channel_id', "")),
            "channel_link": info.get('channel_url', old_data.get('channel_link', "")),
            "subtitle": {
                "segments": segment_count,
                "languages": languages_list
            }
        }
        
        dst_json_path = os.path.join(outdir, "metadata.json")
        with open(dst_json_path, "w", encoding="utf-8") as f:
            json.dump(new_metadata, f, ensure_ascii=False, indent=4)

        complete_video(video_id, config["check_downloaded_video_url"], new_metadata)

        elapsed = time.time() - start
        with counter.get_lock():
            counter.value += 1
            done = counter.value
            total_elapsed = time.time() - GLOBAL_START
            speed = done / total_elapsed
            eta = (TOTAL_VIDEOS - done) / speed if speed > 0 else 0
            
        if segment_count > 0:
            print(f"[SUCCESS With Sub] {video_id} | {elapsed:.2f}s | {done}/{TOTAL_VIDEOS} | ETA {eta:.1f}s")
        else:
            print(f"[SUCCESS No Sub] {video_id} | {elapsed:.2f}s | {done}/{TOTAL_VIDEOS} | ETA {eta:.1f}s")

    except Exception as e:
        fail_video(video_id, config.get("check_downloaded_video_url"), e)
        print(f"[ERROR] {video_id}: {e}")
        with open("log_error.txt", "a+", encoding="utf-8") as fw:
            fw.write(f"\n{video_id} - {str(e)}\n")

def process_batch(files, config):
    with ThreadPoolExecutor(max_workers=4) as ex:
        ex.map(lambda f: crawl_video(f, config), files)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python script.py <config.json>")
        sys.exit(1)

    with open(sys.argv[1], "r", encoding="utf-8") as f:
        json_data = json.load(f)

    domain = json_data["domain"]
    mms_data_dir = json_data["save_dir"]
    download_cfg = json_data["download_config"]

    raw_lang = download_cfg.get("lang", ["vi"])
    
    if isinstance(raw_lang, str):
        langs = [l.strip().lower() for l in raw_lang.split(",")]
    elif isinstance(raw_lang, list):
        langs = [l.strip().lower() for l in raw_lang]
    else:
        langs = ["vi"]
    
    config = {
        "Dataset_dir": os.path.join(mms_data_dir, f"MMSData{domain}", "data"),
        "lang": langs,
        "min_segment": download_cfg["min_segment"],
        "verbose": download_cfg["verbose"],
        "proxy_url": download_cfg.get("proxy_url"),
        "check_downloaded_video_url": download_cfg["check_downloaded_video_url"],
        "download_video": download_cfg.get("download_video", True),
        "max_video_height": download_cfg.get("max_video_height", 1080),
        "write_subtitles": download_cfg.get("write_subtitles", True),
        "write_automatic_subtitles": download_cfg.get("write_automatic_subtitles", True),
        "cookies_from_browser": download_cfg.get("cookies_from_browser"),
        "cookie_file": download_cfg.get("cookie_file"),
        "allow_remote_components": download_cfg.get("allow_remote_components", True)
    }
    registry_ids = load_download_registry_ids(download_cfg.get("download_registry_file"))
    if registry_ids:
        print(f"Download registry loaded: {len(registry_ids)} IDs")

    _ensure_dir(config["Dataset_dir"])
 
    json_dir = os.path.join(mms_data_dir, f"MMSData{domain}", "asset", "json", "*.json")
    #print(json_dir)
    #print(type(json_dir))
    all_json_files = glob.glob(json_dir)
    print(all_json_files)
    print(f"Total metadata files found: {len(all_json_files)}")

    download_json_files = []
    if not download_cfg.get("force_download", False):
        local_downloaded = set(os.listdir(config["Dataset_dir"]))
        for j_file in all_json_files:
            vid_id = os.path.splitext(os.path.basename(j_file))[0]
            if vid_id in registry_ids:
                continue
            if not is_downloaded_ok(vid_id, config["Dataset_dir"]) and not check_video(vid_id, config["check_downloaded_video_url"]):
                download_json_files.append(j_file)
    else:
        download_json_files = all_json_files

    max_items = download_cfg.get("max_items")
    if max_items is not None:
        download_json_files = download_json_files[:max(0, int(max_items))]

    print(f"Videos ready for crawling: {len(download_json_files)}")
    TOTAL_VIDEOS = len(download_json_files)

    chunk_size = 20
    chunks = [
        download_json_files[i:i+chunk_size]
        for i in range(0, len(download_json_files), chunk_size)
    ]

    num_worker = int(download_cfg.get("num_worker", min(os.cpu_count() * 2, 8)))
    num_worker = max(1, num_worker)
    print(f"Using {num_worker} processes...")

    worker_func = partial(process_batch, config=config)

    if sys.platform.startswith("win"):
        with ThreadPoolExecutor(max_workers=num_worker) as ex:
            for _ in ex.map(worker_func, chunks):
                pass
    else:
        with Pool(num_worker) as p:
            for _ in p.imap_unordered(worker_func, chunks):
                pass

    print(f"Finish for: {domain}")
