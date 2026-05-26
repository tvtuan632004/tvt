# Shared Video Download Registry Service

This Flask service prevents multiple crawl workers from downloading the same YouTube video ID.
It stores records for uploaded, reserved, downloaded, and failed videos in a JSON file.

## Getting Started

### Prerequisites

Make sure you have Python and pip installed on your machine.

```powershell
python -m pip install -r requirements-download.txt
```

### Team Usage

Run this on one shared machine that everyone can reach on the LAN:

```powershell
.\run_download_registry.ps1 -Data outputs/shared_download_registry.json -Seed config/downloaded_videos_registry.json -Port 8020
```

Then every crawler should point `check_downloaded_video_url` to that machine:

```json
"check_downloaded_video_url": "http://<shared-machine-ip>:8020"
```

The seed file is only read to preload known Hugging Face uploads. New reservations/downloads are written to `outputs/shared_download_registry.json`, not back into the seed file.

For a local single-machine run, `run_youtube_crawl.py` starts this service automatically on `127.0.0.1`.

## API Endpoints

### 1. Check if Video Exists

- **Endpoint:** `/check_video`
- **Method:** GET
- **Parameters:**
  - `video_id`: Video ID to check
- **Example:**

  ```bash
  curl http://localhost:8020/check_video?video_id=your_video_id
  ```
- **Response:**
  ```json
  {
    "exists": true
  }
  ```

### 2. Reserve Video Before Download

- **Endpoint:** `/reserve_video`
- **Method:** POST
- **Body:**
  ```json
  {
    "video_id": "your_video_id",
    "metadata": {}
  }
  ```
- **Response:**
  ```json
  {
    "reserved": true,
    "exists": false
  }
  ```

If another worker already reserved or downloaded the ID, `reserved` is `false` and the crawler should skip it.

### 3. Complete Video After Download

- **Endpoint:** `/complete_video`
- **Method:** POST
- **Body:**
  ```json
  {
    "video_id": "your_video_id",
    "metadata": {
      "title": "...",
      "link": "..."
    }
  }
  ```

### 4. Mark Failed Video

- **Endpoint:** `/fail_video`
- **Method:** POST
- **Body:**
  ```json
  {
    "video_id": "your_video_id",
    "error": "download failed"
  }
  ```

Reserved-but-failed IDs are released so another worker can retry later.

### 5. Add New Video Legacy Endpoint

- **Endpoint:** `/add_video`
- **Method:** GET
- **Parameters:**
  - `video_id`: Video ID to track as downloaded video

- **Example:**

  ```bash
  curl http://localhost:8020/add_video?video_id=your_video_id
  ```

### 6. List Downloaded Videos

- **Endpoint:** `/list_downloaded_videos`
- **Method:** GET
- **Example:**

  ```bash
  curl http://localhost:8020/list_downloaded_videos
  ```
- **Response:**
  ```json
  {
    "video_id1": {
      "status": "downloaded",
      "metadata": {}
    }
  }
  ```

### 7. Get Downloaded Video Info

- **Endpoint:** `/get_info`
- **Method:** GET
- **Example:**

  ```bash
  curl http://localhost:8020/get_info?video_id=your_video_id
  ```
- **Response:**
  ```json
  {
    "your_video_id": {
      "status": "downloaded",
      "metadata": {}
    }
  }
  ```
## Data Storage

The service uses a JSON file to store records. Put that JSON file somewhere durable and shared/backed up if the team depends on it.
