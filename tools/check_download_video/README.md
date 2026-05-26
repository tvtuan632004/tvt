# Flask Video Download Tracking Service

This is a simple Flask web service for tracking downloaded videos. It allows you to check if a video exists in the download list and add information about newly downloaded videos.

## Getting Started

### Prerequisites

Make sure you have Python and pip installed on your machine.

```bash
pip install Flask
```

### Installation

1. Clone the repository.

```bash
git clone git@bitbucket.org:vinbdi-slp/tts-crawl.git
cd tts-crawl/tools/check_download_video
```

2. Run the Flask application.

```bash
python check_download_video_api.py -d video_data.json -p 8020
```

The service will be available at `http://localhost:8020`.

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
### 2. Add New Video

- **Endpoint:** `/add_video`
- **Method:** GET
- **Parameters:**
  - `video_id`: Video ID to track as downloaded video

- **Example:**

  ```bash
  curl http://localhost:8020/add_video?video_id=your_video_id
  ```

### 3. List Downloaded Videos

- **Endpoint:** `/list_downloaded_videos`
- **Method:** GET
- **Example:**

  ```bash
  curl http://localhost:8020/list_downloaded_videos
  ```
- **Response:**
  ```json
  {
    "video_id1": "Ip address of download machine",
    "video_id2": "Ip address of download machine",
    "video_id3": "Ip address of download machine"
  }
  ```
### 4. Get Downloaded Video Info

- **Endpoint:** `/get_info`
- **Method:** GET
- **Example:**

  ```bash
  curl http://localhost:8020/get_info?video_id=your_video_id
  ```
- **Response:**
  ```json
  {
    "your_video_id": "Ip address of download machine",
  }
  ```
## Data Storage

The service uses a JSON file (`downloaded_videos.json`) to store information about downloaded videos. Make sure to handle file permissions and backup the file as needed.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
```

Feel free to customize the content based on your specific project details.