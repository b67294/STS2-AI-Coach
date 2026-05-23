from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "spire-codex"
RAW_BASE = "https://raw.githubusercontent.com/ptrlrd/spire-codex/main/data/{lang}/{name}.json"
ASSET_BASE = "https://spire-codex.com"
FILES = ("acts", "encounters", "monsters", "events")
USER_AGENT = "STS2-AI-Coach knowledge sync"


def fetch_json(url: str, timeout: float = 30.0) -> Any:
    req = request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_bytes(url: str, timeout: float = 30.0) -> bytes:
    req = request.Request(url, headers={"User-Agent": USER_AGENT})
    with request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def as_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in ("data", "items", "results"):
            nested = value.get(key)
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
    return []


def image_urls(items: list[dict[str, Any]]) -> list[str]:
    urls: list[str] = []
    for item in items:
        for key in ("image_url", "image", "sprite_url", "icon_url"):
            value = item.get(key)
            if not isinstance(value, str) or not value:
                continue
            if value.startswith("/"):
                value = f"{ASSET_BASE}{value}"
            if value.startswith(("http://", "https://")) and value not in urls:
                urls.append(value)
    return urls


def image_filename(url: str) -> str:
    path = urlparse(url).path
    name = path.rsplit("/", 1)[-1] or "image"
    if "." not in name:
        name = f"{name}.png"
    return name


def download_images(urls: list[str], data_dir: Path, limit: int | None) -> tuple[int, list[str]]:
    image_dir = data_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    downloaded = 0
    selected = urls if limit is None else urls[:limit]
    for url in selected:
        target = image_dir / image_filename(url)
        if target.exists() and target.stat().st_size > 0:
            continue
        try:
            target.write_bytes(fetch_bytes(url))
            downloaded += 1
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    return downloaded, errors


def sync(lang: str, data_dir: Path, image_limit: int | None) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    fetched: dict[str, Any] = {}
    source_urls: dict[str, str] = {}
    for name in FILES:
        url = RAW_BASE.format(lang=lang, name=name)
        print(f"fetch {name}: {url}")
        fetched[name] = fetch_json(url)
        source_urls[name] = url
        write_json(data_dir / f"{name}.json", fetched[name])

    monsters = as_items(fetched.get("monsters"))
    events = as_items(fetched.get("events"))
    image_source_urls = image_urls(monsters) + image_urls(events)
    downloaded, image_errors = download_images(image_source_urls, data_dir, image_limit)

    meta = {
        "source": "Spire Codex",
        "source_repository": "https://github.com/ptrlrd/spire-codex",
        "language": lang,
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "files": source_urls,
        "counts": {
            "acts": len(as_items(fetched.get("acts"))),
            "encounters": len(as_items(fetched.get("encounters"))),
            "monsters": len(monsters),
            "events": len(events),
            "image_urls": len(image_source_urls),
            "images_downloaded": downloaded,
            "image_errors": len(image_errors),
        },
        "image_errors": image_errors[:20],
    }
    write_json(data_dir / "meta.json", meta)
    print(f"done: {data_dir}")
    print(json.dumps(meta["counts"], ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync local Spire Codex data cache for STS2 Coach.")
    parser.add_argument("--lang", default="zhs", help="Spire Codex language code. Default: zhs")
    parser.add_argument("--data-dir", default=str(DATA_DIR), help="Output cache directory.")
    parser.add_argument("--image-limit", type=int, default=-1, help="Max images to download. Use -1 for all.")
    args = parser.parse_args()
    image_limit = None if args.image_limit < 0 else args.image_limit

    try:
        sync(args.lang, Path(args.data_dir), image_limit)
        return 0
    except (error.URLError, TimeoutError) as exc:
        print(f"network error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"sync failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
