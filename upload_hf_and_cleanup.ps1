param(
    [string]$Config = "config/hf_upload_config.json",
    [string]$RepoId = "",
    [string]$LocalPath = "",
    [string]$PathInRepo = "",
    [string]$UploadMode = "",
    [switch]$Yes,
    [switch]$NoDelete
)

$ErrorActionPreference = "Stop"

$argsList = @("upload_hf_and_cleanup.py", "--config", $Config)

if ($RepoId) {
    $argsList += @("--repo-id", $RepoId)
}
if ($LocalPath) {
    $argsList += @("--local-path", $LocalPath)
}
if ($PathInRepo) {
    $argsList += @("--path-in-repo", $PathInRepo)
}
if ($UploadMode) {
    $argsList += @("--upload-mode", $UploadMode)
}
if ($Yes) {
    $argsList += "--yes"
}
if ($NoDelete) {
    $argsList += "--no-delete"
}

python @argsList
