"""YouTubeのRSSから最新の投稿を取得し、data/videos.json に保存する。

GitHub Actions（.github/workflows/update-videos.yml）から1時間ごとに実行される。
RSSは1本あたり直近15件までしか返さないため、取得した分は data/videos.json に蓄積していく。

出力の形:
  {"videos": [...メインチャンネル...], "sub": [...サブチャンネル...]}
各動画: id, title, published, short, kind("video"|"live"|"short"), views, excerpt
"""
import json
import re
import pathlib
import urllib.request
import xml.etree.ElementTree as ET

CHANNELS = {
    "videos": "UCI4sJGfpJaa15xWM8D78pAg",  # るるゲーム（メイン）
    "sub": "UCeI7tXU8GgywzL10AEMPzYQ",     # るるゲームアルファ（サブ）
}
BASE = "https://www.youtube.com/feeds/videos.xml"
OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "videos.json"
KEEP = 80  # チャンネルごとに保存しておく最大件数

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}


def feeds_for(channel_id):
    """ショートが多い日は通常のRSSが全部ショートになるため、種類ごとの再生リストからも取る"""
    uploads = channel_id[2:]
    return [
        ("all", f"{BASE}?channel_id={channel_id}"),
        ("video", f"{BASE}?playlist_id=UULF{uploads}"),  # 通常の動画
        ("live", f"{BASE}?playlist_id=UULV{uploads}"),   # 生配信のアーカイブ
        ("short", f"{BASE}?playlist_id=UUSH{uploads}"),  # ショート
    ]


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


SKIP_LINE = re.compile(r"^(\d{1,2}:\d{2}|https?://|#|【.*】$|▼|▶|■|・?チャンネル登録)")


def pick_excerpt(desc):
    """概要欄から、紹介文として読める最初の1行を選ぶ（タイムスタンプやURL、ハッシュタグの行は飛ばす）"""
    for line in desc.splitlines():
        line = line.strip()
        if len(line) >= 8 and not SKIP_LINE.match(line):
            return line[:120]
    return ""


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
            "excerpt": pick_excerpt(desc),
        })
    return videos


def collect(channel_id, old):
    fresh = []
    for kind, url in feeds_for(channel_id):
        try:
            got = parse(fetch_feed(url), kind)
            print(f"  {kind}: {len(got)}")
            fresh.extend(got)
        except Exception as e:  # 1つ失敗しても他は続ける（再生リストが無いチャンネルもある）
            print(f"  {kind}: failed ({e})")
    merged = {v["id"]: v for v in old}
    for v in fresh:  # 新しい情報で上書き。種類は「生配信」「ショート」の判定を優先
        prev = merged.get(v["id"])
        if prev and prev.get("kind") in ("live", "short") and v["kind"] == "video":
            v["kind"], v["short"] = prev["kind"], prev["short"]
        merged[v["id"]] = v
    return sorted(merged.values(), key=lambda v: v["published"], reverse=True)[:KEEP], len(fresh)


def main():
    data = {}
    if OUT.exists():
        try:
            data = json.loads(OUT.read_text(encoding="utf-8"))
        except ValueError:
            data = {}
    total = 0
    for key, channel_id in CHANNELS.items():
        print(key)
        data[key], n = collect(channel_id, data.get(key, []))
        total += n
    if not total:
        raise SystemExit("どのフィードも取得できませんでした")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
