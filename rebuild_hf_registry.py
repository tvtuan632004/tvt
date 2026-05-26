import argparse
import json
import re
from pathlib import Path

from huggingface_hub import list_repo_files


ROOT = Path(__file__).resolve().parent
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def resolve_path(path):
    path = Path(path)
    if not path.is_absolute():
        path = ROOT / path
    return path


def main():
    parser = argparse.ArgumentParser(description="Rebuild downloaded video registry from a Hugging Face dataset repo.")
    parser.add_argument("--repo-id", default="tuantv6304/Tuantv")
    parser.add_argument("--repo-type", default="dataset")
    parser.add_argument("--dataset-root", default="MMSDataMePhimVietTHVL")
    parser.add_argument("--output", default="config/downloaded_videos_registry.json")
    args = parser.parse_args()

    files = list_repo_files(args.repo_id, repo_type=args.repo_type)
    prefix = f"{args.dataset_root.rstrip('/')}/data/"
    video_ids = sorted({
        path[len(prefix):].split("/", 1)[0]
        for path in files
        if path.startswith(prefix) and "/" in path[len(prefix):]
    })
    video_ids = [video_id for video_id in video_ids if VIDEO_ID_RE.match(video_id)]

    registry = {
        video_id: f"huggingface://datasets/{args.repo_id}/{args.dataset_root}/data/{video_id}"
        for video_id in video_ids
    }

    output = resolve_path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=4)
        f.write("\n")

    print(f"Wrote {len(registry)} video IDs to {output}")


if __name__ == "__main__":
    main()
