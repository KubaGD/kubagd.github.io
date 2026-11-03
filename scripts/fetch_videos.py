"""YouTubeのRSSから最新の投稿を取得し、data/videos.json に保存する。

GitHub Actions から1時間ごとに実行される。
RSSには直近15件までしか含まれないため、過去の分は data/videos.json に蓄積していく。
"""
import json
import pathlib
import urllib.request
import xml.etree.ElementTree as ET

CHANNEL_ID = "UCI4sJGfpJaa15xWM8D78pAg"
FEED_URL = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "videos.json"
KEEP = 60  # 保存しておく最大件数

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}


def fetch_feed():
    req = urllib.request.Request(FEED_URL, headers={"User-Agent": "rurugame-site-updater"})
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read()


def parse(xml_bytes):
    root = ET.fromstring(xml_bytes)
    videos = []
    for entry in root.findall("atom:entry", NS):
        vid = entry.findtext("yt:videoId", default="", namespaces=NS)
        link = entry.find("atom:link", NS)
        href = link.get("href", "") if link is not None else ""
        group = entry.find("media:group", NS)
        desc = ""
        views = None
        if group is not None:
            desc = group.findtext("media:description", default="", namespaces=NS) or ""
            stats = group.find("media:community/media:statistics", NS)
            if stats is not None and stats.get("views", "").isdigit():
                views = int(stats.get("views"))
        videos.append({
            "id": vid,
            "title": entry.findtext("atom:title", default="", namespaces=NS),
            "published": entry.findtext("atom:published", default="", namespaces=NS),
            "short": "/shorts/" in href,
            "views": views,
            "excerpt": desc.strip().split("\n")[0][:120],
        })
    return videos


def main():
    fresh = parse(fetch_feed())
    old = []
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8")).get("videos", [])
        except (ValueError, AttributeError):
            old = []
    merged = {v["id"]: v for v in old}
    merged.update({v["id"]: v for v in fresh})  # 新しい情報で上書き
    videos = sorted(merged.values(), key=lambda v: v["published"], reverse=True)[:KEEP]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"videos": videos}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(fresh)} fetched, {len(videos)} stored")


if __name__ == "__main__":
    main()
