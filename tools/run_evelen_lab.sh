#!/usr/bin/env bash
set -euo pipefail
ELEVEN_AUTHORIZATION='Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6IjJiMzZhYjQxYTczOTJlMTRlNjM1ZmRlM2M2YWYwOWZlYmFhM2YyZDYiLCJ0eXAiOiJKV1QifQ.eyJuYW1lIjoiSG_DoG5nIEzhu6NpIiwicGljdHVyZSI6Imh0dHBzOi8vbGgzLmdvb2dsZXVzZXJjb250ZW50LmNvbS9hL0FDZzhvY0x5MTN0ZkVTRlhVcU80bG9YMFA5M0M4ODgxZ2t5ZTZOTXp3MldKbFhKMjBNYXkyQT1zOTYtYyIsIndvcmtzcGFjZV9pZCI6IjhmYTUzNGI5YzZlZTQzNmE5MTczMDk5MDc4OGIyNWE1Iiwid29ya3NwYWNlX3VzZXJfaWQiOiJ1c2VyXzE5MDFrcXJid3ZzZWZmZHRyajZ3dnc2bnZzbnEiLCJpc3MiOiJodHRwczovL3NlY3VyZXRva2VuLmdvb2dsZS5jb20veGktbGFicyIsImF1ZCI6InhpLWxhYnMiLCJhdXRoX3RpbWUiOjE3Nzc5NjcxMTUsInVzZXJfaWQiOiJDV2tXTXlXWHFjaHV2Q3cyOXh1R1RVcGlaRGYxIiwic3ViIjoiQ1drV015V1hxY2h1dkN3Mjl4dUdUVXBpWkRmMSIsImlhdCI6MTc3Nzk2NzExNSwiZXhwIjoxNzc3OTcwNzE1LCJlbWFpbCI6ImhvYW5nbG9pMjAwMUBnbWFpbC5jb20iLCJlbWFpbF92ZXJpZmllZCI6dHJ1ZSwiZmlyZWJhc2UiOnsiaWRlbnRpdGllcyI6eyJnb29nbGUuY29tIjpbIjEwMDY3Mjk4MTkxNjA2MTgxNDg0MSJdLCJlbWFpbCI6WyJob2FuZ2xvaTIwMDFAZ21haWwuY29tIl19LCJzaWduX2luX3Byb3ZpZGVyIjoiZ29vZ2xlLmNvbSJ9fQ.GFTesUPza97-LJjMavJWS_YmBYGwCatjGIL2AvQ-yz7bgRll2JQN8sQXiB3Ti8UUtNuRxI2ql5viuWp54VfROZj8zGwP1cxfQFxIwutRgh2NrEwIxidZ3rpgf8grhF-f_0LqBScIqIWAH7BdlCrGuksiK1O4hQOGpSNBSQ8S2ARnYNYQiATToy0eakcwRIa9mS_ByYBCJnQYECR7oFNR-oyUjJxV8e7OBPB5wXNUmJt0z5prGO680hsO1ZbyPFY3_TjeC64hpDAAYvGZwhuJEkFtoNCXiyIjsR7rJG2XxbyMzlry1G4-qAvAQYCCoMG1pWw3OvLaOpz6secHHsv1oA'
#ELEVEN_COOKIE=''

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python "$SCRIPT_DIR/crawl_elevenlabs_voices.py" \
  --language vi \
  --page-size 30 \
  --output-json "$SCRIPT_DIR/elevenlabs_voices_vi.json" \
  --output-csv "$SCRIPT_DIR/elevenlabs_voices_vi.csv" \
  ${ELEVEN_AUTHORIZATION:+--authorization "$ELEVEN_AUTHORIZATION"} \
  ${ELEVEN_COOKIE:+--cookie "$ELEVEN_COOKIE"} \
  ${ELEVEN_XI_API_KEY:+--xi-api-key "$ELEVEN_XI_API_KEY"}

python "$SCRIPT_DIR/download_elevenlabs_previews.py" \
  --input-csv "$SCRIPT_DIR/elevenlabs_voices_vi.csv" \
  --output-dir "$SCRIPT_DIR/elevenlabs_previews_vi" \
  --metadata-csv "$SCRIPT_DIR/elevenlabs_previews_vi/metadata.csv" \
  --metadata-jsonl "$SCRIPT_DIR/elevenlabs_previews_vi/metadata.jsonl" \
  --skip-existing
