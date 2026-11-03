"""transcripts/queue.txt に書かれた動画IDの字幕（YouTubeの自動字幕を含む）を取得し、
transcripts/<動画ID>.txt に読みやすいテキストとして保存する。

GitHub Actions（.github/workflows/fetch-captions.yml）から実行される。
攻略ページを書くための下書き素材であり、サイトには公開しない（index.html からは読まない）。
"""
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DIR = ROOT / "transcripts"
QUEUE = DIR / "queue.txt"
RAW = DIR / "raw"


def vtt_to_text(vtt):
    """VTTからタイムスタンプとタグを外し、自動字幕の重複行をまとめる。1分ごとに目印を入れる。"""
    out, last, next_mark, sec = [], None, 0, 0
    for line in vtt.splitlines():
        m = re.match(r"(\d+):(\d+):(\d+)\.\d+ -->", line)
        if m:
            sec = int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3])
            continue
        if not line.strip() or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")) or "-->" in line:
            continue
        text = re.sub(r"<[^>]+>", "", line).strip()
        if not text or text == last:
            continue
        if sec >= next_mark:
            out.append(f"\n[{sec // 60}:{sec % 60:02d}]")
            next_mark = (sec // 60 + 1) * 60
        out.append(text)
        last = text
    return "\n".join(out).strip() + "\n"


def fetch(video_id):
    RAW.mkdir(parents=True, exist_ok=True)
    cmd = [
        "yt-dlp", "--skip-download",
        "--write-subs", "--write-auto-subs",
        "--sub-langs", "ja,ja-orig,ja.*",
        "--sub-format", "vtt",
        "-o", str(RAW / "%(id)s.%(ext)s"),
        f"https://www.youtube.com/watch?v={video_id}",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    print(res.stdout[-2000:])
    print(res.stderr[-2000:], file=sys.stderr)
    files = sorted(RAW.glob(f"{video_id}*.vtt"), key=lambda p: ("orig" in p.name, len(p.name)))
    if not files:
        return False
    (DIR / f"{video_id}.txt").write_text(vtt_to_text(files[0].read_text(encoding="utf-8")), encoding="utf-8")
    return True


def main():
    if not QUEUE.exists():
        return
    ids = [l.split("#")[0].strip() for l in QUEUE.read_text(encoding="utf-8").splitlines()]
    ids = [i for i in ids if i]
    done, failed = [], []
    for vid in ids:
        if (DIR / f"{vid}.txt").exists():
            continue
        (done if fetch(vid) else failed).append(vid)
    print("取得:", done)
    print("失敗:", failed)


if __name__ == "__main__":
    main()
