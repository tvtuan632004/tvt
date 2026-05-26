import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from huggingface_hub import HfApi, create_repo


ROOT = Path(__file__).resolve().parent
DEFAULT_ALLOWED_DELETE_ROOT = ROOT / "outputs" / "youtube_crawl"


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_path(value):
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def require_token(cli_token):
    token = cli_token or os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    if not token:
        raise RuntimeError(
            "Missing Hugging Face token. Set HF_TOKEN first, for example: "
            "$env:HF_TOKEN='hf_...'"
        )
    return token


def is_within(path, parent):
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def delete_local_path(path, allowed_root, yes):
    path = path.resolve()
    allowed_root = allowed_root.resolve()

    if not is_within(path, allowed_root):
        raise RuntimeError(f"Refusing to delete outside allowed root: {allowed_root}")
    if not path.exists():
        print(f"[CLEANUP] Already gone: {path}")
        return
    if not yes:
        raise RuntimeError(
            "Upload succeeded, but local cleanup was not confirmed. "
            "Re-run with --yes to delete local data after upload."
        )

    print(f"[CLEANUP] Deleting local data: {path}")
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def upload_one_folder(api, repo_id, repo_type, folder_path, path_in_repo, commit_message):
    print(f"[HF] Upload folder: {folder_path} -> {path_in_repo or '.'}")
    return api.upload_folder(
        repo_id=repo_id,
        repo_type=repo_type,
        folder_path=str(folder_path),
        path_in_repo=path_in_repo,
        commit_message=commit_message,
    )


def upload_by_video(api, repo_id, repo_type, local_path, path_in_repo, commit_message):
    asset_dir = local_path / "asset"
    data_dir = local_path / "data"

    if asset_dir.exists():
        upload_one_folder(
            api,
            repo_id,
            repo_type,
            asset_dir,
            f"{path_in_repo}/asset" if path_in_repo else "asset",
            f"{commit_message}: asset metadata",
        )

    if not data_dir.exists():
        print(f"[HF] No data directory found: {data_dir}")
        return

    video_dirs = sorted(p for p in data_dir.iterdir() if p.is_dir())
    total = len(video_dirs)
    for idx, video_dir in enumerate(video_dirs, start=1):
        size = sum(p.stat().st_size for p in video_dir.rglob("*") if p.is_file())
        print(f"[HF] Video {idx}/{total}: {video_dir.name} ({size / (1024 ** 3):.2f} GB)")
        upload_one_folder(
            api,
            repo_id,
            repo_type,
            video_dir,
            f"{path_in_repo}/data/{video_dir.name}" if path_in_repo else f"data/{video_dir.name}",
            f"{commit_message}: {video_dir.name}",
        )


def main():
    parser = argparse.ArgumentParser(
        description="Upload a local crawl dataset to Hugging Face, then optionally delete it."
    )
    parser.add_argument("--config", default="config/hf_upload_config.json")
    parser.add_argument("--repo-id", help="Override repo_id, e.g. username/dataset-name")
    parser.add_argument("--local-path", help="Override local_path")
    parser.add_argument("--path-in-repo", help="Override path_in_repo")
    parser.add_argument("--upload-mode", choices=["folder", "by_video"], help="Override upload mode.")
    parser.add_argument("--token", help="Hugging Face token. Prefer HF_TOKEN env var.")
    parser.add_argument("--yes", action="store_true", help="Confirm deletion after successful upload.")
    parser.add_argument("--no-delete", action="store_true", help="Upload only; keep local files.")
    args = parser.parse_args()

    config_path = resolve_path(args.config)
    cfg = load_config(config_path)

    repo_id = args.repo_id or cfg["repo_id"]
    repo_type = cfg.get("repo_type", "dataset")
    local_path = resolve_path(args.local_path or cfg["local_path"])
    path_in_repo = args.path_in_repo if args.path_in_repo is not None else cfg.get("path_in_repo")
    upload_mode = args.upload_mode or cfg.get("upload_mode", "folder")
    commit_message = cfg.get("commit_message", "Upload dataset")
    delete_after_upload = bool(cfg.get("delete_after_upload", False)) and not args.no_delete
    token = require_token(args.token)

    if "YOUR_HF_USERNAME" in repo_id:
        raise RuntimeError("Please set a real repo_id in config/hf_upload_config.json.")
    if not local_path.exists():
        raise FileNotFoundError(f"Local path does not exist: {local_path}")

    print(f"[HF] Repo: {repo_id} ({repo_type})")
    print(f"[HF] Local path: {local_path}")
    print(f"[HF] Path in repo: {path_in_repo or '.'}")

    create_repo(repo_id=repo_id, repo_type=repo_type, token=token, exist_ok=True)

    api = HfApi(token=token)
    if upload_mode == "by_video":
        upload_by_video(api, repo_id, repo_type, local_path, path_in_repo, commit_message)
    else:
        upload_one_folder(api, repo_id, repo_type, local_path, path_in_repo, commit_message)

    print("[HF] Upload completed successfully.")

    if delete_after_upload:
        delete_local_path(local_path, DEFAULT_ALLOWED_DELETE_ROOT, args.yes)
        print("[DONE] Uploaded and cleaned local data.")
    else:
        print("[DONE] Uploaded. Local data kept.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)
