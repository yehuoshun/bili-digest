#!/usr/bin/env python3
"""bili_subtitle.py — 抓取 B站视频信息、字幕（或简介+热评兜底）。

用法:
  python3 bili_subtitle.py <BV号或完整URL> [--cid N] [--json OUT.json] [--txt OUT.txt]

输出:
  --json: 结构化 JSON（bvid/aid/cid/title/desc/owner/duration/字幕数组/评论数组）
  --txt:  字幕纯文本 `[mm:ss] 内容`（无字幕时写简介+热评）

特性:
  - 字幕接口走 wbi 签名（自动从 nav 取 img_key/sub_key）
  - cookie 从 ~/.openclaw/secrets/bilibili-cookies.txt 读取（含 SESSDATA 才有字幕）
  - 中文字幕优先（lan 以 zh 开头，含 ai-zh）；无中文取第一条
  - 无字幕时兜底: 简介 + 热门评论（sort=2 按热度）
"""
import argparse
import hashlib
import os
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
REFERER = "https://www.bilibili.com/"
COOKIE_FILE = Path(os.environ.get("BILI_COOKIE_FILE", str(Path.home() / ".openclaw/secrets/bilibili-cookies.txt")))

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
]


def load_cookie():
    if not COOKIE_FILE.exists():
        return ""
    return COOKIE_FILE.read_text().strip()


def http_get(url, cookie="", extra_headers=None, timeout=20):
    headers = {
        "User-Agent": UA,
        "Referer": REFERER,
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.bilibili.com",
    }
    if cookie:
        headers["Cookie"] = cookie
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def get_mixin_key(orig: str) -> str:
    return "".join(orig[i] for i in MIXIN_KEY_ENC_TAB)[:32]


def wbi_sign(params: dict, img_key: str, sub_key: str) -> dict:
    mixin_key = get_mixin_key(img_key + sub_key)
    params = dict(params)
    params["wts"] = int(time.time())
    query = urllib.parse.urlencode(sorted(params.items()))
    params["w_rid"] = hashlib.md5((query + mixin_key).encode()).hexdigest()
    return params


def parse_bvid(text: str) -> str:
    m = re.search(r"BV[0-9A-Za-z]{10}", text)
    if m:
        return m.group(0)
    raise SystemExit(f"没找到 BV 号: {text}")


def fetch_video_info(bvid: str, cookie: str) -> dict:
    url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
    data = json.loads(http_get(url, cookie))
    if data.get("code") != 0:
        raise SystemExit(f"view 接口失败: {data}")
    d = data["data"]
    return {
        "bvid": d["bvid"],
        "aid": d["aid"],
        "cid": d["cid"],
        "title": d["title"],
        "desc": d.get("desc", ""),
        "owner": d.get("owner", {}).get("name", ""),
        "duration": d.get("duration", 0),
        "pages": [{"cid": p["cid"], "part": p["part"]} for p in d.get("pages", [])],
    }


def get_wbi_keys(cookie: str):
    data = json.loads(http_get("https://api.bilibili.com/x/web-interface/nav", cookie))
    if data.get("code") != 0:
        raise SystemExit(f"nav 接口失败: {data}")
    img = data["data"]["wbi_img"]["img_url"]
    sub = data["data"]["wbi_img"]["sub_url"]
    return img.rsplit("/", 1)[-1].split(".")[0], sub.rsplit("/", 1)[-1].split(".")[0]


def fetch_subtitles(info: dict, cookie: str, img_key: str, sub_key: str, cid: int | None = None):
    params = wbi_sign({"aid": info["aid"], "cid": cid or info["cid"]}, img_key, sub_key)
    url = "https://api.bilibili.com/x/player/wbi/v2?" + urllib.parse.urlencode(params)
    data = json.loads(http_get(url, cookie))
    if data.get("code") != 0:
        return []
    subs = data.get("data", {}).get("subtitle", {}).get("subtitles") or []
    return subs


def pick_subtitle(subs: list) -> dict | None:
    if not subs:
        return None
    for s in subs:
        if s.get("lan", "").startswith("zh"):
            return s
    return subs[0]


def download_subtitle(sub: dict, cookie: str) -> list:
    url = sub["subtitle_url"]
    if url.startswith("//"):
        url = "https:" + url
    data = json.loads(http_get(url, cookie, extra_headers={"Accept": "*/*"}))
    return [{"from": b["from"], "to": b["to"], "content": b["content"]} for b in data.get("body", [])]


def fetch_comments(aid: int, cookie: str, ps: int = 10) -> list:
    url = f"https://api.bilibili.com/x/v2/reply?type=1&oid={aid}&sort=2&ps={ps}&nested=0"
    try:
        data = json.loads(http_get(url, cookie))
    except Exception as e:
        return [{"error": str(e)}]
    if data.get("code") != 0:
        return [{"error": f"code={data.get('code')} {data.get('message','')}"}]
    out = []
    for r in data.get("data", {}).get("replies") or []:
        out.append({
            "user": r["member"]["uname"],
            "like": r.get("like", 0),
            "content": r["content"]["message"],
        })
    return out


def fmt_ts(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 60:02d}:{sec % 60:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="BV号或完整 B站视频 URL")
    ap.add_argument("--cid", type=int, default=None, help="分P cid（默认第一P）")
    ap.add_argument("--json", default=None, help="JSON 输出路径")
    ap.add_argument("--txt", default=None, help="字幕文本输出路径")
    args = ap.parse_args()

    bvid = parse_bvid(args.input)
    cookie = load_cookie()
    info = fetch_video_info(bvid, cookie)
    if args.cid and any(p["cid"] == args.cid for p in info["pages"]):
        info["cid"] = args.cid

    img_key, sub_key = get_wbi_keys(cookie)
    subs = fetch_subtitles(info, cookie, img_key, sub_key)
    chosen = pick_subtitle(subs)

    result = {
        **info,
        "subtitle_lang": chosen.get("lan_doc", "") if chosen else None,
        "has_subtitle": bool(chosen),
        "subtitles": [],
        "comments": [],
    }

    if chosen:
        result["subtitles"] = download_subtitle(chosen, cookie)
    else:
        result["comments"] = fetch_comments(info["aid"], cookie)

    if args.json:
        Path(args.json).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.txt:
        lines = [f"标题: {info['title']}", f"UP: {info['owner']}", ""]
        if result["subtitles"]:
            lines.append(f"字幕语言: {result['subtitle_lang']}")
            lines.append("")
            lines += [f"[{fmt_ts(b['from'])}] {b['content']}" for b in result["subtitles"]]
        else:
            lines.append("（无字幕，以下为简介+热门评论）")
            lines.append("")
            lines.append("【简介】")
            lines.append(info["desc"] or "（无简介）")
            lines.append("")
            lines.append("【热门评论】")
            for c in result["comments"][:10]:
                if "error" in c:
                    lines.append(f"（评论获取失败: {c['error']}）")
                    break
                lines.append(f"@{c['user']} (+{c['like']}): {c['content']}")
        Path(args.txt).write_text("\n".join(lines), encoding="utf-8")

    # 标准输出：摘要
    print(f"bvid={info['bvid']} title={info['title']}")
    print(f"aid={info['aid']} cid={info['cid']} duration={info['duration']}s UP={info['owner']}")
    if len(info["pages"]) > 1:
        print(f"分P {len(info['pages'])} 个: " + " | ".join(f"{p['part']}(cid={p['cid']})" for p in info["pages"]))
    if chosen:
        print(f"字幕: {result['subtitle_lang']} {len(result['subtitles'])} 条")
    else:
        print(f"无字幕 → 兜底 简介+热评 {len(result['comments'])} 条")


if __name__ == "__main__":
    main()
