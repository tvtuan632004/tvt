import time
import os
import json
import asyncio
import argparse
import tqdm
import urllib.parse
import re
import yt_dlp

parser = argparse.ArgumentParser()
parser.add_argument('--keyword', type=str, help="path to keywords file", required=True)
parser.add_argument('--search', type=str, help="type of search", choices=['channel', 'video'], required=True)
parser.add_argument('--output', type=str, help="path to save video info", required=True)
parser.add_argument('--mark', type=str, help="folder to contain crawled channel-id, video-id", required=True)
parser.add_argument('--limit', type=int, help="limit results per search", default=2000)
parser.add_argument('--lang', type=str, help="language", default='vi')
parser.add_argument('--region', type=str, help="region", default='VN')
args = parser.parse_args()

mark_videos = {}
mark_channels = {}

FLAT_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'extract_flat': True,
}

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

def is_youtube_url(value):
    value = value.lower()
    return value.startswith(("https://www.youtube.com/", "https://youtube.com/", "http://www.youtube.com/", "http://youtube.com/"))

async def fetch_yt_data(url, opts):
    loop = asyncio.get_event_loop()
    def fetch():
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    return await loop.run_in_executor(None, fetch)

async def dump_info(entry, fallback_channel_info=None):
    vid_id = entry.get('id')
    if not vid_id or vid_id in mark_videos: return
    if not VIDEO_ID_RE.match(vid_id): return
    mark_videos[vid_id] = 1

    try:
        c_name = entry.get('uploader') or entry.get('channel') or (fallback_channel_info.get('name') if fallback_channel_info else "")
        c_id = entry.get('uploader_id') or entry.get('channel_id') or (fallback_channel_info.get('id') if fallback_channel_info else "")
        c_url = entry.get('uploader_url') or entry.get('channel_url') or (fallback_channel_info.get('url') if fallback_channel_info else "")

        item = {
            'duration': entry.get('duration'),
            'link': f"https://www.youtube.com/watch?v={vid_id}",
            'id': vid_id,
            'title': entry.get('title'),
            'channel_name': c_name,
            'channel_id': c_id,
            'channel_link': c_url,
            'subtitle': {
                'requested_lang': args.lang,
                # 'has_manual': None,  
                # 'has_auto': None,    
                # 'has_subtitles': None
            }
        }

        output_path = os.path.join(args.output, f"{vid_id}.json")
        with open(output_path, 'w', encoding='utf-8') as fout:
            json.dump(item, fout, ensure_ascii=False, indent=4)
            
    except Exception as e:
        print(f"Error dumping info for {vid_id}: {e}")

async def channel_search(keyword):
    """Tìm kiếm ra Channel -> Quét toàn bộ video trong Channel đó"""
    if is_youtube_url(keyword):
        await process_channel({
            'id': keyword,
            'name': keyword.rstrip('/').split('/')[-1],
            'url': keyword
        })
        return

    encoded = urllib.parse.quote(keyword)
    search_url = f"https://www.youtube.com/results?search_query={encoded}&sp=EgIQAg%253D%253D"
    
    opts = FLAT_OPTS.copy()
    opts['playlist_items'] = f"1-{args.limit}"

    print(f"Searching Channels for: '{keyword}'...")
    results = await fetch_yt_data(search_url, opts)

    if not results or not results.get('entries'):
        return

    for entry in results['entries']:
        if not entry: continue
        channel_info = {
            'id': entry.get('id'),
            'name': entry.get('title'),
            'url': entry.get('url') or f"https://www.youtube.com/channel/{entry.get('id')}"
        }
        await process_channel(channel_info)

async def process_channel(channel_info):
    channel_id = channel_info.get('id')
    channel_url = channel_info.get('url')
    channel_name = channel_info.get('name', channel_id)

    if not channel_id or channel_id in mark_channels: return

    print(f"\nProcessing Channel: {channel_name} ({channel_url})")
    try:
        opts = FLAT_OPTS.copy()
        opts['playlist_items'] = f"1-{args.limit}"
        channel_data = await fetch_yt_data(channel_url, opts)
        
        if channel_data and 'entries' in channel_data:
            entries = [e for e in channel_data['entries'] if e and e.get('id')]
            for entry in tqdm.tqdm(entries, desc=f"Videos in {channel_name[:15]}"):
                await dump_info(entry, fallback_channel_info=channel_info)
            mark_channels[channel_id] = 1
    except Exception as e:
        print(f"Error processing channel {channel_url}: {e}")

async def video_search(keyword):
    search_url = f"ytsearch{args.limit}:{keyword}"
    
    print(f"Searching Videos for: '{keyword}'...")
    results = await fetch_yt_data(search_url, FLAT_OPTS)

    if not results or not results.get('entries'):
        return

    for entry in tqdm.tqdm(results['entries'], desc=f"Saving Videos for '{keyword}'"):
        if not entry: continue
        
        channel_info = {
            'id': entry.get('channel_id'),
            'name': entry.get('channel'),
            'url': entry.get('channel_url')
        }
        await dump_info(entry, fallback_channel_info=channel_info)

async def crawl():
    os.makedirs(args.output, exist_ok=True)
    os.makedirs(args.mark, exist_ok=True)

    channel_path = os.path.join(args.mark, 'channels.txt')
    video_path = os.path.join(args.mark, 'videos.txt')

    if os.path.exists(channel_path):
        with open(channel_path, 'r') as f:
            for line in f: mark_channels[line.strip()] = 1
    if os.path.exists(video_path):
        with open(video_path, 'r') as f:
            for line in f: mark_videos[line.strip()] = 1

    list_keywords = []
    with open(args.keyword, 'r', encoding='utf-8') as f:
        list_keywords = [line.strip() for line in f if line.strip()]

    for keyword in list_keywords:
        if args.search == 'channel':
            await channel_search(keyword)
        else:
            await video_search(keyword)

    with open(channel_path, 'w') as f:
        for cid in mark_channels: f.write(f"{cid}\n")
    with open(video_path, 'w') as f:
        for vid in mark_videos: f.write(f"{vid}\n")

if __name__ == "__main__":
    start_time = time.time()
    asyncio.run(crawl())
    print(f"\nTotal time: {time.time() - start_time:.2f} seconds")
