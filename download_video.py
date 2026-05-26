import os
import csv
import time
import random
import subprocess
from yt_dlp import YoutubeDL

def get_countries():
    """Lấy danh sách các quốc gia từ NordVPN."""
    try:
        result = subprocess.run(["nordvpn", "countries"], stdout=subprocess.PIPE, text=True, check=True)
        countries_raw = result.stdout.strip().split("\n")
        countries = []
        for line in countries_raw:
            # Loại bỏ các dòng trống và xử lý chuỗi để tách từng quốc gia
            countries.extend(line.split())
        return [country.strip() for country in countries if country.strip()]
    except Exception as e:
        print(f"LỖI: Không lấy được danh sách quốc gia - {e}")
        return []

def switch_vpn(enable_switch=True):
    """Đổi server VPN dựa trên quốc gia ngẫu nhiên nếu enable_switch = True."""
    if not enable_switch:
        print("INFO: VPN switching is disabled.")
        return

    print("INFO: Switching VPN...")
    try:
        subprocess.run(["nordvpn", "disconnect"], check=True)
        time.sleep(2)
        print("INFO: Connecting to the best server...")
        subprocess.run(["nordvpn", "connect"], check=True)
        print("INFO: VPN switched successfully.")
    except subprocess.CalledProcessError as e:
        print(f"LỖI: Không thể đổi VPN - {e}")
    except Exception as e:
        print(f"LỖI: Có lỗi xảy ra - {e}")

def download_channel(channel_url, output_folder, info_csv, enable_switch=False):
    """Tải video từ một kênh YouTube."""
    ydl_opts = {
        'outtmpl': f'{output_folder}/%(id)s.%(ext)s',  # Đặt tên file theo video ID
        'format': 'bestvideo[height<=720][protocol!=http_dash_segments]+bestaudio[protocol!=http_dash_segments]/best[height<=720][protocol!=http_dash_segments]',  # Chỉ tải video <=720p và không dùng DASH
        'merge_output_format': 'mp4',  # Định dạng hợp nhất video/audio
        'progress_hooks': [lambda d: download_video(d, info_csv, enable_switch)], 
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
        'retries': 5,  # Thử lại tối đa 5 lần nếu gặp lỗi
        'socket_timeout': 30,  # Tăng thời gian chờ kết nối
    }

    # Tạo thư mục và file nếu chưa tồn tại
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    if not os.path.exists(info_csv):
        with open(info_csv, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["Title", "ID", "URL", "Duration (seconds)"])

    # Tải video
    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([channel_url])
    except Exception as e:
        print(f"ERROR: Download failed - {e}. Switching VPN and retrying...")
        switch_vpn(enable_switch)
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([channel_url])

def calculate_duration(duration, duration_file):
    """Cập nhật tổng thời gian video vào file txt."""
    try:
        # Đọc tổng thời gian hiện tại từ file
        if os.path.exists(duration_file):
            with open(duration_file, 'r') as f:
                total_duration = int(f.read().strip() or 0)
        else:
            total_duration = 0

        # Cộng thêm thời lượng mới
        total_duration += duration

        # Ghi tổng thời gian mới vào file
        with open(duration_file, 'w') as f:
            f.write(str(total_duration))

        return total_duration
    except Exception as e:
        print(f"LỖI: Không thể cập nhật tổng thời gian - {e}")
        return None
    
def download_video(d, info_csv, enable_switch=False):
    """Xử lý từng video tải xuống."""
    global last_id, download_count, video_limit
    duration_file = "total_duration.txt"
    
    if d['status'] == 'finished':
        video_id = d['info_dict'].get('id', 'N/A')

        if video_id != last_id:
            last_id = video_id
            download_count += 1
            video_info = {
                'title': d['info_dict'].get('title', 'N/A'),
                'id': video_id,
                'url': d['info_dict'].get('webpage_url', 'N/A'),
                'duration': d['info_dict'].get('duration', 'N/A'),
            }
            save_info(video_info, info_csv)
            print(f"INFO: Video saved - {video_info}")
            
            # Cập nhật tổng thời gian vào file txt
            calculate_duration(video_info['duration'], duration_file)

            # Tạm dừng sau khi tải mỗi video
            sleep_time = random.randint(5, 10)
            time.sleep(sleep_time)

            # Dừng nếu đạt giới hạn video
            if video_limit is not None and download_count >= video_limit:
                print(f"INFO: Đã tải đủ {video_limit} video. Dừng chương trình.")
                raise SystemExit()

            # Đổi VPN nếu đạt ngưỡng
            if download_count % vpn_threshold == 0:
                switch_vpn(enable_switch)
        else:
            print(f"INFO: Duplicate file skipped - {d['filename']}")

def save_info(video_info, info_csv):
    """Lưu thông tin video vào file CSV."""
    with open(info_csv, 'a', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([
            video_info['title'], 
            video_info['id'], 
            video_info['url'], 
            video_info['duration']
        ])