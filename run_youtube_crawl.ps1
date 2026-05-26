param(
    [string]$Config = "config/youtube_crawl_local.json",
    [switch]$SearchOnly,
    [switch]$DownloadOnly
)

$ErrorActionPreference = "Stop"

$argsList = @("run_youtube_crawl.py", "--config", $Config)
if ($SearchOnly) {
    $argsList += "--search-only"
}
if ($DownloadOnly) {
    $argsList += "--download-only"
}

python @argsList
