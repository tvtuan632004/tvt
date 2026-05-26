# Tài liệu chi tiết luồng chạy `run_pipeline.sh`

Tài liệu này mô tả chính xác thứ tự thực thi và các nhánh xử lý của script [`run_pipeline.sh`](/data1/loinh/tts-crawl/run_pipeline.sh).

## 1) Mục tiêu tổng quát

Script `run_pipeline.sh` thực hiện 3 giai đoạn chính:

1. Đọc config JSON và chuẩn bị `keywords.txt`.
2. Chạy pipeline tìm kiếm + tải dữ liệu (`S01_search.sh` và `S02_download.py`).
3. Tiền xử lý lip movement cho từng sample video trong dataset.

## 2) Cơ chế an toàn đầu script

Script bật:

- `set -e`: thoát ngay khi có lệnh lỗi (trừ các tình huống được bọc xử lý thủ công).
- `set -u`: lỗi khi dùng biến chưa khai báo.
- `set -o pipefail`: pipeline trả về lỗi nếu bất kỳ command nào lỗi.

Điều này giúp fail-fast, tránh chạy tiếp với trạng thái không nhất quán.

## 3) Input và biến nền

- `CFG=${1:-config/test.json}`:
  - Nếu có tham số thứ nhất khi chạy script: dùng làm đường dẫn config.
  - Nếu không có: mặc định `config/test.json`.
- `ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"`:
  - Lấy thư mục gốc chứa `run_pipeline.sh`.
  - Dùng để `cd` chính xác vào `av_preprocess` ở bước cuối.

Ví dụ gọi:

```bash
bash run_pipeline.sh config/podcast.json
```

## 4) Giai đoạn chuẩn bị `keywords.txt`

### 4.1 Python block đầu tiên

Script chạy một Python inline để:

1. Đọc JSON config.
2. Lấy:
   - `domain`
   - `save_dir`
   - `keywords` (mặc định `[]` nếu thiếu key)
3. Tạo thư mục:
   - `${save_dir}/MMSData${domain}/asset`
4. Ghi file:
   - `${asset_folder}/keywords.txt`

Luật ghi:

- Nếu `keywords` là list:
  - duyệt từng phần tử, ép `str`, `strip`, bỏ dòng rỗng.
- Nếu `keywords` không phải list:
  - ép thành một chuỗi duy nhất, `strip`, ghi nếu không rỗng.

Kết thúc block này, script `print` ra đường dẫn `keywords.txt`.

### 4.2 Trích xuất lại config sang biến shell

Script gọi thêm các Python inline riêng để lấy:

- `DOMAIN` từ `data["domain"]`
- `SAVE_DIR` từ `data["save_dir"]`
- `VIDEO_LIMIT` từ `data["search_config"]["video_limit"]`
- `CHANNEL_LIMIT` từ `data["search_config"]["channel_limit"]`
- `KEYWORDS_FILE` từ `${save_dir}/MMSData${domain}/asset/keywords.txt`

Lưu ý:

- Nếu thiếu key bắt buộc trong JSON (`domain`, `save_dir`, `search_config.video_limit`, `search_config.channel_limit`) thì Python sẽ lỗi và script dừng do `set -e`.

### 4.3 Log thông số đầu vào

Script in:

- `[PIPE] Domain: ...`
- `[PIPE] Keywords file: ...`
- `[PIPE] video_limit=... channel_limit=...`

Mục đích là giúp trace chính xác tham số runtime.

## 5) Giai đoạn search và download

Script chạy tuần tự:

1. `bash S01_search.sh "$DOMAIN" "$KEYWORDS_FILE" "$VIDEO_LIMIT" "$CHANNEL_LIMIT" "$SAVE_DIR"`
2. `python S02_download.py "$CFG"`

Ý nghĩa:

- `S01_search.sh`: thu thập danh sách video/channel theo từ khóa và giới hạn.
- `S02_download.py`: tải dữ liệu theo config.

Do `set -e`, nếu một trong hai bước lỗi non-zero, toàn bộ pipeline dừng.

## 6) Xác định dataset và điều kiện thoát sớm

- `DATASET_DIR="$SAVE_DIR/MMSData$DOMAIN/data"`

Nếu thư mục này chưa tồn tại:

- In: `[PIPE] Skip lip preprocess (dataset dir not found: ...)`
- `exit 0` (thoát thành công, coi như không có dữ liệu để xử lý tiếp).

Nếu tồn tại:

- Bắt đầu lip preprocess và khởi tạo bộ đếm:
  - `processed=0`
  - `skipped=0`
  - `failed=0`

## 7) Check video (hợp nhất kiểm tra + chọn đầu vào)

Mục tiêu:

- Với mỗi `sample_dir` trong `DATASET_DIR`, xác định nhanh sample nào cần bỏ qua và sample nào có `videofile` hợp lệ để chạy lip preprocess.

Bối cảnh và biến dùng trong mỗi sample:

- Vòng lặp: `for sample_dir in "$DATASET_DIR"/*; do`
- Chỉ xử lý khi `sample_dir` là thư mục.
- Biến chính:
  - `ref=$(basename "$sample_dir")`
  - `video_dir="$sample_dir/video"`
  - `lip_dir="$sample_dir/lip_movement"`
  - `filter_dir="$lip_dir/pyfilter/$ref"`
- Hàm kiểm tra audio:
  - `has_audio_stream "$vf"` dùng `ffprobe` để xác nhận file có stream `a:0` kiểu `audio`.

Luồng kiểm tra nhất quán (theo đúng thứ tự script):

1. Check đã xử lý trước đó:
   - Nếu `filter_dir` đã có `*.avi` -> log `already processed`, `skipped += 1`, `continue`.
2. Check thư mục video:
   - Nếu thiếu `video_dir` -> log `missing video dir`, `skipped += 1`, `continue`.
3. Check danh sách video candidate:
   - Quét trong `video_dir` các đuôi `.mp4/.mkv/.webm/.mov`.
   - Nếu rỗng -> log `no video file`, `skipped += 1`, `continue`.
4. Chọn `videofile` theo ưu tiên:
   - Ưu tiên A: video **không** phải fragment (`\.f[0-9]+\.[^.]+$`) và có audio stream.
   - Ưu tiên B (fallback): bất kỳ video nào có audio stream.
5. Nếu chưa chọn được video có audio, thử nhánh cứu bằng `raw_audio`:
   - Tìm `raw_audio/*.wav`.
   - Nếu có WAV:
     - Chọn `base_video` (ưu tiên non-fragment, nếu không có lấy file đầu tiên).
     - Mux thành `"$video_dir/${ref}.with_audio.mp4"` bằng ffmpeg.
     - Bắt buộc check lại `has_audio_stream` trên file muxed.
     - Nếu đạt, gán file muxed làm `videofile`.
   - Nếu không có WAV hoặc mux lỗi/không có audio -> `skipped += 1`, `continue`.

Kết quả cuối của mục Check video:

- `PASS`: sample có `videofile` hợp lệ (có audio stream) -> chuyển sang mục 11 để chạy `av_preprocess`.
- `SKIP`: sample không đạt bất kỳ điều kiện bắt buộc nào ở trên.

Ý nghĩa thiết kế:

- Gom toàn bộ quyết định đầu vào vào một điểm (`check video`) để giảm lỗi dữ liệu trước khi chạy model.
- Phân biệt rõ:
  - `skipped`: lỗi/chưa đủ dữ liệu đầu vào.
  - `failed`: đã có đầu vào hợp lệ nhưng lỗi khi chạy pipeline model ở mục 11.

## 11) Chạy chuỗi xử lý lip movement

Khi đã có `videofile`:

1. Log: `[LIP] Processing <ref> -> <videofile>`
2. `mkdir -p "$lip_dir"`
3. Chạy 4 bước trong subshell, sau khi `cd "$ROOT_DIR/av_preprocess"`:
   - `python run_face_detector.py --videofile ... --reference ... --data_dir ...`
   - `python run_talking_detector.py --videofile ... --reference ... --data_dir ...`
   - `python run_syncnet.py --videofile ... --reference ... --data_dir ...`
   - `python run_filter_videos.py --reference ... --data_dir ...`

Nếu cả block thành công:

- `processed += 1`

Nếu block lỗi ở bất kỳ bước nào:

- Log: `[LIP] Failed <ref>`
- `failed += 1`

Lý do script không dừng hẳn ở đây:

- Khối lệnh được đặt trong `if ( ... ); then ... else ... fi`, nên lỗi được bắt theo từng sample, cho phép xử lý sample tiếp theo.

## 12) Kết thúc pipeline

Sau khi duyệt xong:

- `shopt -u nullglob`
- In tổng kết:
  - `[PIPE] Lip preprocess done: processed=<n> skipped=<n> failed=<n>`

## 13) Điều kiện tiên quyết để chạy ổn định

Để script chạy trọn vẹn, môi trường cần có:

1. Python và các package cho:
   - `S02_download.py`
   - toàn bộ scripts trong `av_preprocess/`
2. `ffprobe` và `ffmpeg` trong `PATH`.
3. Config JSON đúng schema tối thiểu:
   - `domain`
   - `save_dir`
   - `search_config.video_limit`
   - `search_config.channel_limit`
   - `keywords` (không bắt buộc, có thể thiếu)

## 14) Sơ đồ luồng ngắn gọn

```text
Load config -> write keywords.txt
    -> S01_search.sh
    -> S02_download.py
    -> check DATASET_DIR exists?
        -> no: exit 0
        -> yes: loop samples
            -> already processed? skip
            -> find video files
            -> pick video with audio
                -> if none: try raw_audio mux
                -> if still none: skip
            -> run face/talking/syncnet/filter
                -> success: processed++
                -> fail: failed++
Done -> print processed/skipped/failed
```

## 15) Bổ sung chi tiết riêng cho phần lip movement

### 15.1) Decision tree đầy đủ cho mỗi sample

Với mỗi `sample_dir`, pipeline đi theo cây quyết định:

1. `already processed?`
   - Có `lip_movement/pyfilter/<ref>/*.avi` -> `skip` ngay.
2. `video dir tồn tại?`
   - Không có `video/` -> `skip`.
3. `có video candidate?`
   - Không tìm thấy `.mp4/.mkv/.webm/.mov` -> `skip`.
4. `tìm được video có audio stream?`
   - Có -> dùng luôn.
   - Không -> chuyển sang nhánh mux từ `raw_audio`.
5. `mux thành công + output có audio stream?`
   - Có -> dùng file muxed.
   - Không -> `skip`.
6. Chạy chuỗi 4 bước `av_preprocess`.
   - tất cả pass -> `processed++`
   - bất kỳ bước fail -> `failed++`

Phân biệt trạng thái:

- `skip`: sample không đạt điều kiện đầu vào.
- `failed`: sample đạt điều kiện nhưng lỗi khi chạy preprocess.

### 15.2) Vì sao bắt buộc có audio stream

Dù mục tiêu là lip movement, pipeline downstream (đặc biệt bước sync) cần cặp audio-video hợp lệ.
Vì vậy script chỉ cho qua khi video có `a:0`.
Nếu video gốc thiếu audio, script thử ghép `raw_audio/*.wav`; không cứu được thì bỏ sample để tránh dữ liệu nhiễu.

### 15.3) Giải thích kỹ nhánh mux fallback bằng `ffmpeg`

Lệnh mux:

```bash
ffmpeg -y -i "$base_video" -i "${audio_files[0]}" \
  -map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -shortest "$muxed_video" -loglevel error
```

Ý nghĩa:

- `-map 0:v:0`: lấy video track đầu tiên từ file video.
- `-map 1:a:0`: lấy audio track đầu tiên từ WAV.
- `-c:v copy`: giữ nguyên stream video, không encode lại.
- `-c:a aac`: encode audio sang AAC để tương thích mp4.
- `-shortest`: output dừng ở track ngắn hơn để tránh kéo dài lệch.
- `-loglevel error`: chỉ in lỗi.

Sau mux, script kiểm tra lại bằng `ffprobe` (`has_audio_stream`) thay vì tin tưởng output tuyệt đối.

### 15.4) Ý nghĩa thực thi 4 bước trong `av_preprocess`

Thứ tự chạy là bắt buộc:

1. `run_face_detector.py`
   - tạo tín hiệu/metadata khuôn mặt theo frame.
2. `run_talking_detector.py`
   - đánh dấu đoạn có hoạt động nói/chuyển động mouth liên quan.
3. `run_syncnet.py`
   - chấm độ đồng bộ audio-lip trên đoạn candidate.
4. `run_filter_videos.py`
   - lọc, xuất kết quả cuối cùng vào nhánh `pyfilter/<ref>`.

Artifact dùng để nhận diện “đã xử lý xong” ở lần chạy sau:

- `lip_movement/pyfilter/<ref>/*.avi`

### 15.5) Cách đọc log để khoanh lỗi nhanh

Nhánh input:

- `[LIP] Skip <ref> (no video with audio stream and no raw_audio wav)`:
  - không có video-audio và cũng không có WAV để cứu.
- `[LIP] <ref>: muxing external audio into video`:
  - đang đi vào nhánh fallback.
- `[LIP] Skip <ref> (cannot mux raw_audio into video)`:
  - ffmpeg fail (file lỗi, codec/container không hợp lệ, hoặc input hỏng).
- `[LIP] Skip <ref> (muxed video still has no audio stream)`:
  - output mux không đạt tiêu chí `a:0`.

Nhánh preprocess:

- `[LIP] Processing <ref> -> <videofile>`:
  - sample đã qua gate input.
- `[LIP] Failed <ref>`:
  - ít nhất 1/4 script trả non-zero.

Khi gặp `Failed`, chạy lại thủ công từng lệnh trong `av_preprocess` theo đúng thứ tự để xác định bước hỏng.

### 15.6) Vì sao dùng `if ( ... )` thay vì chạy thẳng

Nếu chạy thẳng dưới `set -e`, lỗi ở 1 sample sẽ làm dừng toàn bộ pipeline.
Cách viết hiện tại bắt lỗi theo từng sample, giúp:

- xử lý được nhiều sample trong 1 lần chạy,
- có thống kê cuối cùng `processed/skipped/failed`,
- dễ quyết định re-run chỉ các sample lỗi.

## 16) av_preprocess: từng bước dùng model gì

Phần này map trực tiếp 4 lệnh trong `run_pipeline.sh` sang model/checkpoint thực tế trong code `av_preprocess`.

### 16.1) `run_face_detector.py`

Model dùng:

- Face detector: `S3FD` (class `faceDetector.S3FD`).
- Weight file: `model-bin/sfd_face.pth`.
- Điểm load weight nằm trong `av_preprocess/faceDetector/s3fd/__init__.py`:
  - `PATH_WEIGHT = 'model-bin/sfd_face.pth'`
  - `state_dict = torch.load(PATH, map_location=self.device)`

Pipeline nội bộ bước này:

1. Normalize video về `25 fps` + tách frames + tách audio wav 16k.
2. Chạy S3FD detect face theo batch (`detect_faces_batch`) với `conf_th=0.9` và `facedet_scale` mặc định `0.25`.
3. Track mặt theo IOU (`iouThres=0.5`) và điều kiện `min_track`, `min_face_size`.
4. Crop từng face-track thành các clip `pycrop/<ref>/xxxxx.avi` + audio tương ứng `xxxxx.wav`.

Đầu ra quan trọng cho bước sau:

- `pycrop/<ref>/*.avi`, `pycrop/<ref>/*.wav`
- `pywork/<ref>/tracks.pckl`

### 16.2) `run_talking_detector.py`

Model dùng:

- Active Speaker Detection model (ASD), class `talkingDetector.ASD`.
- Checkpoint mặc định: `model-bin/finetuning_TalkSet.model` (arg `--initial_model`).
- Load tại:
  - `ASD_MODEL = ASD()`
  - `ASD_MODEL.loadParameters(opt.initial_model)`

Pipeline nội bộ bước này:

1. Đọc từng clip face từ `pycrop`.
2. Audio feature: MFCC (`python_speech_features.mfcc`, 16kHz).
3. Visual feature: grayscale crop vùng mặt 112x112 từ frame 224x224.
4. Chạy mạng ASD audio-visual để sinh score theo thời gian.
5. Hậu xử lý score để tách các đoạn “đang nói” (`s >= 0`, có smoothing).
6. Trim các đoạn nói đủ dài (`> 0.5s`) sang `pycrop_talking/<ref>/*.avi`.

Đầu ra quan trọng:

- `pywork/<ref>/scores.pckl`
- `pywork/<ref>/talking_tracks.pckl`
- `pycrop_talking/<ref>/*.avi`

### 16.3) `run_syncnet.py`

Model dùng:

- SyncNet model: `SyncNetInstance` (`syncDetector.SyncNetInstance`).
- Checkpoint mặc định: `model-bin/syncnet_v2.model` (arg `--initial_model`).
- Load tại:
  - `s = SyncNetInstance()`
  - `s.loadParameters(opt.initial_model)`

Pipeline nội bộ bước này:

1. Lấy từng clip talking face từ `pycrop_talking/<ref>/*.avi`.
2. Với mỗi clip, chạy `s.evaluate(...)` để lấy:
   - `offset`: lệch đồng bộ audio-lip,
   - `conf`: độ tin cậy,
   - `dist`: khoảng cách embedding.
3. Ghi toàn bộ kết quả vào `pywork/<ref>/activesd.pckl`.

Lưu ý:

- Trong code hiện tại, bước này không loại clip ngay; chỉ chấm điểm và lưu kết quả.

### 16.4) `run_filter_videos.py`

Model dùng:

- Không dùng model mới.
- Đây là bước rule-based filter dựa trên output SyncNet (`activesd.pckl`).

Điều kiện giữ clip:

- `offset` khác `None`
- `conf` khác `None`
- `abs(offset) < 10`
- `conf > 3`

Clip đạt điều kiện sẽ được copy từ `pycrop_talking/<ref>/` sang:

- `pyfilter/<ref>/`

Đây cũng là artifact mà `run_pipeline.sh` dùng để xác định sample đã xử lý xong (`pyfilter/<ref>/*.avi`).

### 16.5) Tổng hợp nhanh model theo 4 bước

1. `run_face_detector.py` -> `S3FD` + `model-bin/sfd_face.pth`
2. `run_talking_detector.py` -> `ASD` + `model-bin/finetuning_TalkSet.model`
3. `run_syncnet.py` -> `SyncNet` + `model-bin/syncnet_v2.model`
4. `run_filter_videos.py` -> không model, chỉ rule filter theo `offset/conf`
