param(
    [string]$Data = "outputs/shared_download_registry.json",
    [string]$Seed = "config/downloaded_videos_registry.json",
    [int]$Port = 8020
)

$ErrorActionPreference = "Stop"

python tools/check_download_video/check_download_video_api.py `
    -d $Data `
    -p $Port `
    --seed $Seed
