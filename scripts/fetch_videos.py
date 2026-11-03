"""YouTubeのRSSから最新の投稿を取得し、data/videos.json に保存する。

GitHub Actions から1時間ごとに実行される。
RSSには直近15件までしか含まれないため、過去の分は data/videos.json に蓄積していく。
"""
import json
import pathlib
import urllib.request
import xml.etree.ElementTree as ET

CHANNEL_ID = "UCI4sJGfpJaa15xWM8D78pAg"
BASE = "https://www.youtube.com/feeds/videos.xml"
UPLOADS = CHANNEL_ID[2:]
# ショートが多い日は通常のRSSが全部ショートになるため、種類ごとの再生リストからも取る
FEEDS = [
    ("all", f"{BASE}?channel_id={CHANNEL_ID}"),
    ("video", f"{BASE}?playlist_id=UULF{UPLOADS}"),  # 通常の動画
    ("live", f"{BASE}?playlist_id=UULV{UPLOADS}"),   # 生配信のアーカイブ
    ("short", f"{BASE}?playlist_id=UUSH{UPLOADS}"),  # ショート
]
OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "videos.json"
KEEP = 80  # 保存しておく最大件数

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}


def fetch_feed(url):
    req = urllib.request.Request(url, headers={"User-Agent": "rurugame-site-updater"})
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read()


def clean_title(title):
    """末尾のハッシュタグ（#にゃんこ大戦争 #shorts など）を外す"""
    words = title.split()
    while words and words[-1].startswith("#"):
        words.pop()
    return " ".join(words) or title


def parse(xml_bytes, kind="all"):
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
        is_short = kind == "short" or "/shorts/" in href
        videos.append({
            "id": vid,
            "title": clean_title(entry.findtext("atom:title", default="", namespaces=NS)),
            "published": entry.findtext("atom:published", default="", namespaces=NS),
            "short": is_short,
            "kind": "short" if is_short else ("live" if kind == "live" else "video"),
            "views": views,
            "excerpt": desc.strip().split("\n")[0][:120],
        })
    return videos


def main():
    fresh = []
    for kind, url in FEEDS:
        try:
            got = parse(fetch_feed(url), kind)
            print(f"{kind}: {len(got)}")
            fresh.extend(got)
        except Exception as e:  # 1つ失敗しても他は続ける
            print(f"{kind}: failed ({e})")
    if not fresh:
        raise SystemExit("どのフィードも取得できませんでした")
    old = []
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8")).get("videos", [])
        except (ValueError, AttributeError):
            old = []
    merged = {v["id"]: v for v in old}
    for v in fresh:  # 新しい情報で上書き。種類は「生配信」「ショート」の判定を優先
        prev = merged.get(v["id"])
        if prev and prev.get("kind") in ("live", "short") and v["kind"] == "video":
            v["kind"], v["short"] = prev["kind"], prev["short"]
        merged[v["id"]] = v
    videos = sorted(merged.values(), key=lambda v: v["published"], reverse=True)[:KEEP]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"videos": videos}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(fresh)} fetched, {len(videos)} stored")


if __name__ == "__main__":
    main()
