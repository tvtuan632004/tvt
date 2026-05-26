#!/bin/bash
set -euo pipefail

CFG=${1:-config/test.json}
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DOMAIN=$(python - "$CFG" <<'PY'
import json, sys
cfg = sys.argv[1]
with open(cfg, "r", encoding="utf-8") as f:
    data = json.load(f)
print(data["domain"])
PY
)

SAVE_DIR=$(python - "$CFG" <<'PY'
import json, sys
cfg = sys.argv[1]
with open(cfg, "r", encoding="utf-8") as f:
    data = json.load(f)
print(data["save_dir"])
PY
)

DATASET_DIR="$SAVE_DIR/MMSData$DOMAIN/data"
ASSET_DIR="$SAVE_DIR/MMSData$DOMAIN/asset"
STATE_FILE="$ASSET_DIR/lip_processed_ids.txt"

if [[ ! -d "$DATASET_DIR" ]]; then
  echo "[LIP] Skip (dataset dir not found: $DATASET_DIR)"
  exit 0
fi

mkdir -p "$ASSET_DIR"
touch "$STATE_FILE"

declare -A processed_ids=()
while IFS= read -r line; do
  id="$(echo "$line" | tr -d '\r' | xargs || true)"
  [[ -n "$id" ]] && processed_ids["$id"]=1
done < "$STATE_FILE"

echo "[LIP] Start lip movement preprocess: $DATASET_DIR"
echo "[LIP] Processed state file: $STATE_FILE"
processed=0
skipped=0
failed=0

has_audio_stream() {
  local vf="$1"
  ffprobe -v error -select_streams a:0 -show_entries stream=codec_type -of csv=p=0 "$vf" | grep -q '^audio$'
}

mark_processed() {
  local id="$1"
  if [[ -z "${processed_ids[$id]:-}" ]]; then
    echo "$id" >> "$STATE_FILE"
    processed_ids["$id"]=1
  fi
}

shopt -s nullglob
for sample_dir in "$DATASET_DIR"/*; do
  [[ -d "$sample_dir" ]] || continue

  ref="$(basename "$sample_dir")"
  video_dir="$sample_dir/video"
  lip_dir="$sample_dir/lip_movement"
  filter_dir="$lip_dir/pyfilter/$ref"

  if [[ -n "${processed_ids[$ref]:-}" ]]; then
    echo "[LIP] Skip $ref (already processed by state file)"
    skipped=$((skipped + 1))
    continue
  fi

  if [[ -d "$filter_dir" ]] && compgen -G "$filter_dir/*.avi" > /dev/null; then
    echo "[LIP] Skip $ref (already processed by output files)"
    mark_processed "$ref"
    skipped=$((skipped + 1))
    continue
  fi

  if [[ ! -d "$video_dir" ]]; then
    echo "[LIP] Skip $ref (missing video dir)"
    skipped=$((skipped + 1))
    continue
  fi

  mapfile -t video_files < <(find "$video_dir" -maxdepth 1 -type f \( -iname '*.mp4' -o -iname '*.mkv' -o -iname '*.webm' -o -iname '*.mov' \) | sort)
  if [[ "${#video_files[@]}" -eq 0 ]]; then
    echo "[LIP] Skip $ref (no video file)"
    skipped=$((skipped + 1))
    continue
  fi

  videofile=""
  for vf in "${video_files[@]}"; do
    bn="$(basename "$vf")"
    if [[ ! "$bn" =~ \.f[0-9]+\.[^.]+$ ]] && has_audio_stream "$vf"; then
      videofile="$vf"
      break
    fi
  done

  if [[ -z "$videofile" ]]; then
    for vf in "${video_files[@]}"; do
      if has_audio_stream "$vf"; then
        videofile="$vf"
        break
      fi
    done
  fi

  if [[ -z "$videofile" ]]; then
    raw_audio_dir="$sample_dir/raw_audio"
    mapfile -t audio_files < <(find "$raw_audio_dir" -maxdepth 1 -type f -iname '*.wav' | sort 2>/dev/null || true)

    if [[ "${#audio_files[@]}" -gt 0 ]]; then
      base_video=""
      for vf in "${video_files[@]}"; do
        bn="$(basename "$vf")"
        if [[ ! "$bn" =~ \.f[0-9]+\.[^.]+$ ]]; then
          base_video="$vf"
          break
        fi
      done
      [[ -z "$base_video" ]] && base_video="${video_files[0]}"

      muxed_video="$video_dir/${ref}.with_audio.mp4"
      if [[ ! -f "$muxed_video" ]]; then
        echo "[LIP] $ref: muxing external audio into video"
        if ! ffmpeg -y -i "$base_video" -i "${audio_files[0]}" -map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -shortest "$muxed_video" -loglevel error; then
          echo "[LIP] Skip $ref (cannot mux raw_audio into video)"
          skipped=$((skipped + 1))
          continue
        fi
      fi

      if has_audio_stream "$muxed_video"; then
        videofile="$muxed_video"
      else
        echo "[LIP] Skip $ref (muxed video still has no audio stream)"
        skipped=$((skipped + 1))
        continue
      fi
    else
      echo "[LIP] Skip $ref (no video with audio stream and no raw_audio wav)"
      skipped=$((skipped + 1))
      continue
    fi
  fi

  echo "[LIP] Processing $ref -> $videofile"
  mkdir -p "$lip_dir"

  if (
    cd "$ROOT_DIR/av_preprocess"
    python run_face_detector.py --videofile "$videofile" --reference "$ref" --data_dir "$lip_dir"
    python run_talking_detector.py --videofile "$videofile" --reference "$ref" --data_dir "$lip_dir"
    python run_syncnet.py --videofile "$videofile" --reference "$ref" --data_dir "$lip_dir"
    python run_filter_videos.py --reference "$ref" --data_dir "$lip_dir"
  ); then
    mark_processed "$ref"
    processed=$((processed + 1))
  else
    echo "[LIP] Failed $ref"
    failed=$((failed + 1))
  fi
done
shopt -u nullglob

echo "[LIP] Done: processed=$processed skipped=$skipped failed=$failed"
