"""Build the bundled game catalog from Steam Store search snapshots.

The script uses only Python's standard library. It can either fetch the first
pages of Steam's top-sellers search or consume JSON snapshots saved earlier.
"""

from __future__ import annotations

import argparse
import glob
import html
import json
import re
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any


SOURCE_URL = "https://store.steampowered.com/search/results/"
EXCLUDE = re.compile(
    r"\b(soundtrack|original score|\bost\b|artbook|season pass|currency|"
    r"dedicated server|playtest|benchmark tool|wallpaper|avatar pack|demo|\bdlc\b|"
    r"starter pack|premier pack|content pack|currency pack|coin pack|credit pack|"
    r"points pack|season bundle|expansion pass|upgrade pack)\b",
    re.IGNORECASE,
)
LIGHT_TAGS = {492, 597, 1664, 3871, 3964, 4136, 4191}
HEAVY_TAGS = {1695, 21978, 4175, 1100689}


def fetch_pages(page_count: int, page_size: int) -> list[dict[str, Any]]:
    pages = []
    for page in range(page_count):
        query = urllib.parse.urlencode(
            {
                "query": "",
                "start": page * page_size,
                "count": page_size,
                "dynamic_data": "",
                "sort_by": "_ASC",
                "filter": "topsellers",
                "category1": 998,
                "infinite": 1,
            }
        )
        request = urllib.request.Request(f"{SOURCE_URL}?{query}", headers={"User-Agent": "SYSTEM-PERF catalog builder"})
        with urllib.request.urlopen(request, timeout=30) as response:
            pages.append(json.load(response))
    return pages


def load_pages(pattern: str) -> list[dict[str, Any]]:
    pages = []
    for path in sorted(glob.glob(pattern), key=_snapshot_start):
        pages.append(json.loads(Path(path).read_text(encoding="utf-8")))
    return pages


def _snapshot_start(path: str) -> int:
    match = re.search(r"(\d+)(?=\.json$)", path)
    return int(match.group(1)) if match else 0


def parse_release(raw: str) -> date | None:
    value = " ".join(html.unescape(raw).split())
    for pattern in ("%d %b, %Y", "%b %Y", "%Y"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    return None


def requirement_tier(year: int, tags: set[int]) -> str:
    if year <= 2012:
        index = 0
    elif year <= 2016:
        index = 1
    elif year <= 2019:
        index = 2
    else:
        index = 3
    if tags & LIGHT_TAGS and index >= 2:
        index -= 1
    if tags & HEAVY_TAGS and year >= 2020:
        index += 1
    return ("light", "standard", "modern", "demanding", "extreme")[min(index, 4)]


def parse_pages(pages: list[dict[str, Any]], snapshot: date) -> list[dict[str, Any]]:
    games: dict[int, dict[str, Any]] = {}
    for page in pages:
        markup = page.get("results_html", "")
        for block in re.findall(r"<a\s+href=.*?</a>", markup, flags=re.DOTALL | re.IGNORECASE):
            if "search_result_row" not in block:
                continue
            app_match = re.search(r'data-ds-appid="(\d+)"', block)
            title_match = re.search(r'<span class="title">(.*?)</span>', block, flags=re.DOTALL)
            release_match = re.search(r'<div class="search_released responsive_secondrow">(.*?)</div>', block, flags=re.DOTALL)
            tags_match = re.search(r'data-ds-tagids="\[([^]]*)\]"', block)
            if not app_match or not title_match or not release_match or not tags_match:
                continue
            name = " ".join(html.unescape(re.sub(r"<[^>]+>", "", title_match.group(1))).split())
            if not name or EXCLUDE.search(name):
                continue
            released = parse_release(release_match.group(1))
            if released is None or released > snapshot:
                continue
            tags = {int(value) for value in re.findall(r"\d+", tags_match.group(1))}
            if len(tags) < 2:
                continue
            platforms = []
            if 'platform_img win' in block:
                platforms.append("windows")
            if 'platform_img mac' in block:
                platforms.append("macos")
            if 'platform_img linux' in block:
                platforms.append("linux")
            if not platforms:
                continue
            app_id = int(app_match.group(1))
            games[app_id] = {
                "id": app_id,
                "name": name,
                "year": released.year,
                "tier": requirement_tier(released.year, tags),
                "platforms": platforms,
            }
    ordered = list(games.values())
    for rank, game in enumerate(ordered, 1):
        game["rank"] = rank
    return ordered


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-glob", help="Read previously downloaded Steam result JSON pages")
    parser.add_argument("--pages", type=int, default=16)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--snapshot-date", default=date.today().isoformat())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    snapshot = date.fromisoformat(args.snapshot_date)
    pages = load_pages(args.input_glob) if args.input_glob else fetch_pages(args.pages, args.page_size)
    games = parse_pages(pages, snapshot)
    payload = {
        "schema_version": "1.0.0",
        "source": {
            "name": "Steam Store top sellers",
            "url": SOURCE_URL,
            "snapshot_date": snapshot.isoformat(),
            "selection": f"Games-only top-sellers snapshot from {len(pages)} pages; ranking is retained only for display order.",
        },
        "tiers": {
            "light": {"gpu_min": 5, "gpu_rec": 15, "vram_min": 1, "vram_rec": 2, "ram_min": 4, "ram_rec": 8, "cpu_min": 20, "cpu_rec": 35},
            "standard": {"gpu_min": 15, "gpu_rec": 30, "vram_min": 2, "vram_rec": 4, "ram_min": 8, "ram_rec": 16, "cpu_min": 30, "cpu_rec": 45},
            "modern": {"gpu_min": 25, "gpu_rec": 45, "vram_min": 3, "vram_rec": 6, "ram_min": 8, "ram_rec": 16, "cpu_min": 35, "cpu_rec": 50},
            "demanding": {"gpu_min": 35, "gpu_rec": 60, "vram_min": 4, "vram_rec": 8, "ram_min": 16, "ram_rec": 32, "cpu_min": 45, "cpu_rec": 65},
            "extreme": {"gpu_min": 50, "gpu_rec": 75, "vram_min": 6, "vram_rec": 12, "ram_min": 16, "ram_rec": 32, "cpu_min": 55, "cpu_rec": 75},
        },
        "games": sorted(games, key=lambda item: item["name"].casefold()),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Wrote {len(games)} games to {args.output}")
    if len(games) < 1000:
        raise SystemExit("Catalog contains fewer than 1,000 games; fetch more pages or relax filters.")


if __name__ == "__main__":
    main()
