# Lip-sync ASR data pipeline

## Objective

Tạo thêm nhiều dữ liệu thật phục vụ training cho bài toán Lip-sync ASR bên cạnh các dữ liệu đã có

## Description

Luồng chạy crawl list video từ youtube bằng list keywords đã có, sau đó xử lý face drop cho từng chunk video.

Luồng xử lý data thực hiện 3 giai đoạn chính:

- Đọc config JSON và chuẩn bị tập keywords

- Chạy pipeline search + download data

- Preprocess + face drop cho từng sample video trong dataset.

## 1. Chuẩn bị keywords, config

Đọc JSON config như bên dưới lấy các biến domain, save_dir, keywords rồi tạo folder `${save_dir}/MMSData${domain}/asset`, metadata của các video download sẽ được ghi vào ở đây. Code sẽ tự động tìm các channels, videos theo keywords đã cho. 

```bash run_pipeline.sh config/podcast.json```

```{
    "save_dir": "/data1/loinh/tts-crawl/",
    "domain": "Podcast",
    "keywords": ["Vietcetera", "Vietsuccess","VietNam Innovators Digest"],
    "status": {
        "search": true,
        "download": false,
        "segmentation": false,
        "transcription": false,
        "quality_measurement": false,
        "data_selection": false,
        "analysis": false
    },
    "search_config": {
        "video_limit": 2500,
        "channel_limit": 100
    },
    "download_config": {
        "min_segment": 1,
        "lang": ["vi"],
        "verbose": true,
        "num_worker": 2,
        "force_download": false,
        "check_downloaded_video_url": "http://127.0.0.1:8020"
    }
}
```

## 2.  Search and download

Script sẽ chạy tuần tự 

```
1. `bash S01_search.sh "$DOMAIN" "$KEYWORDS_FILE" "$VIDEO_LIMIT" "$CHANNEL_LIMIT" "$SAVE_DIR"`
2. `python S02_download.py "$CFG"`
```

- `S01_search.sh`: thu thập list video/channel theo từ khóa và giới hạn.

- `S02_download`: download data theo config

## 3. Check video

Với mỗi sample trong dataset, xác định nhanh sample nào cần bỏ qua và sample nào có video hợp lệ để chạy face drop

Luồng kiểm tra nhất quán:

- Check file đã xử lý trước đó: - Nếu filter_dir đã có *.avi -> log already processed, skipped += 1, continue.

- Check thư mục video: - Nếu thiếu video_dir -> log missing video dir, skipped += 1, continue.

- Check danh sách video candidate: - Quét trong video_dir các đuôi .mp4/.mkv/.webm/.mov. - Nếu rỗng -> log no video file, skipped += 1, continue.

- Chọn videofile theo ưu tiên: 
  - Video không phải fragment (\\.f[0-9]+\\.[^.]+$) và có audio stream.
  - Bất kỳ video nào có audio stream.

- Nếu chưa chọn được video có audio, thử nhánh cứu bằng raw_audio:

    - Tìm raw_audio/*.wav.

    - Nếu có wav:

      - Chọn base_video (ưu tiên non-fragment, nếu không có lấy file đầu tiên).

      - Mux thành "$video_dir/${ref}.with_audio.mp4" bằng ffmpeg.

      - Bắt buộc check lại has_audio_stream trên file muxed.

      - Nếu oke, gán file muxed làm videofile.

  - Nếu không có WAV hoặc mux lỗi/không có audio -> skipped += 1, continue.

Kết quả hợp lệ:

- PASS: sample có videofile hợp lệ (có audio stream) -> chuyển sang chạy av_preprocess(face drop).

- SKIP: sample không đạt bất kỳ điều kiện bắt buộc nào ở trên.

## 4. AV process (face drop)

Bước dùng chạy để process av từ videofile đã lọc ở trên gồm 4 bước chính

### Face detector

- Face detector: S3FD (class faceDetector.S3FD). 
- Weight file: model-bin/sfd_face.pth.

```python run_face_detector.py --videofile ... --reference ... --data_dir ...```

1. Normalize video về 25 fps + tách frames + tách audio wav 16k. 
2. Chạy S3FD detect face theo batch (detect_faces_batch) với conf_th=0.9 và facedet_scale mặc định 0.25. 
3. Track mặt theo IOU (iouThres=0.5) và điều kiện min_track, min_face_size. 
4. Crop từng face-track thành các clip pycrop/<ref>/xxxxx.avi + audio tương ứng xxxxx.wav.

### Talking detector

- Active Speaker Detection model (ASD), class talkingDetector.ASD. 
- Checkpoint: model-bin/finetuning_TalkSet.model.

```python run_talking_detector.py --videofile ... --reference ... --data_dir ...```

1. Đọc từng clip face từ pycrop. 

2. Audio feature: MFCC (python_speech_features.mfcc, 16kHz)

3. Visual feature: grayscale crop vùng mặt 112x112 từ frame 224x224. 

4. Chạy mạng ASD audio-visual để sinh score theo thời gian. 

5. Hậu xử lý score để tách các đoạn “đang nói” (s >= 0, có smoothing). 6. Trim các đoạn nói đủ dài (> 0.5s) sang pycrop_talking/<ref>/*.avi.

### Syncnet

- SyncNet model: SyncNetInstance (syncDetector.SyncNetInstance). 

- Checkpoint: model-bin/syncnet_v2.model

```python run_syncnet.py --videofile ... --reference ... --data_dir ...```

1. Lấy từng clip talking face từ pycrop_talking/<ref>/*.avi. 

2. Với mỗi clip, chạy s.evaluate(...) để lấy: 

    a. offset: lệch đồng bộ audio-lip, 

    b. conf: độ tin cậy, 

    c. dist: khoảng cách embedding.

3. Ghi toàn bộ kết quả vào pywork/<ref>/activesd.pckl.

### Filter video

```python run_filter_videos.py --reference ... --data_dir ...```

- Đây là bước rule-based filter dựa trên output SyncNet (activesd.pckl). 
- Điều kiện giữ clip: 
  - `offset` khác `None`
  - `conf` khác `None`
  - `abs(offset) < 10` - `conf > 3`

Clip đạt điều kiện sẽ được copy từ pycrop_talking/<ref>/ sang pyfilter/<ref>/

## Future works

### Crawl pipeline

- Bổ sung VPN để crawl liên tục không bị ngắt giữa chừng.

- Thêm check codec, fps, duration, audio sample rate, SNR, clipping, silence ratio cho raw audio.

- Thêm cơ chế resume từ điểm cuối đề phòng khi luồng sập bất khả kháng.

### Face drop pipeline

- Face detector (S3FD): benchmark/thay bằng một số các model tốt hơn như RetinaFace/SCRFD/YOLO, tăng tracking ổn định hoặc fine-tune thêm data.

- Talking detector (ASD): research thêm kiến trúc mới hơn, train thêm hard negatives, calibrate score để threshold ổn định.

- Sync model (SyncNet v2): fine-tune theo dữ liệu tiếng Việt/nhiễu thực tế(nếu có), tối ưu threshold theo validation thay vì rule cứng.

- Ngoài ra luồng chạy drop face đang khá chậm, cần phân tích để đưa ra các hướng tối ưu tốc độ.

## Example channels 

Mê Phim Việt 

https://www.youtube.com/channel/UCltOANXKL8wMHaf6ffFDRow 

VFC Offical 

https://www.youtube.com/@VFCOFFICIAL 

SCTV14 Kênh phim Việt 

https://www.youtube.com/c/SCTV14K%C3%AAnhPhimVi%E1%BB%87tOfficial 

Phim giờ vàng VTV 

https://www.youtube.com/@PhimGioVangVTVChannel 

THVL Phim 

https://www.youtube.com/@THVLPhim 

HTV Phim Truyện 

https://www.youtube.com/@HTVPhimtruyen 

Kho phim VTV 

https://www.youtube.com/@khophimvtv 

Phim Việt nam VTV 

https://www.youtube.com/@PhimVietNamVTVOfficial1 

VTV Phim Việt Xưa 

https://www.youtube.com/@VTVPhimVietXua 




