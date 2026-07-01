#!/usr/bin/env python3
"""生成静态看板数据：site/data.js（window.IOSTREND_DATA）+ site/data.json。

渲染层只画不算：所有计算在 analyze.py 完成，这里只把结果序列化给前端。
index.html 读 data.js（本地双击 file:// 也能看，无 CORS 问题）。
用法：python3 build_site.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import analyze
from common import SITE_DIR, today_iso

COUNTRY_CN = {
    "us": "美国", "jp": "日本", "kr": "韩国", "gb": "英国", "de": "德国",
    "fr": "法国", "ca": "加拿大", "au": "澳大利亚", "br": "巴西",
    "id": "印尼", "tw": "中国台湾", "hk": "中国香港", "cn": "中国大陆",
}
FEED_CN = {"top-free": "免费榜", "top-paid": "付费榜"}
CAT_FEED_CN = {"topfree": "免费榜", "toppaid": "付费榜", "topgrossing": "畅销榜"}


def _json_default(o):
    import numpy as np
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        f = float(o)
        return None if math.isnan(f) else f
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def build_payload() -> dict:
    data = analyze.build_all()
    cfg = data["config"]
    return {
        "generated": today_iso(),
        "latest_date": data["latest_date"],
        "dates": data["dates"],
        "has_trend": data["has_trend"],
        "spark_window": analyze.SPARK_WINDOW,
        "focus_label": data["focus_label"],
        "markets": [{"cc": c, "name": COUNTRY_CN.get(c, c.upper())} for c in cfg["markets"]],
        "feeds": cfg["feeds"],
        "feed_names": FEED_CN,
        "charts": data["changes"],
        "history": data["history"],
        "focus": data["focus"],
        # M2 分品类深榜
        "category": data.get("category", {}),
        "cat_genres": data.get("cat_genres", []),
        "cat_feeds": data.get("cat_feeds", []),
        "cat_feed_names": CAT_FEED_CN,
        "cat_focus": data.get("cat_focus", ""),
        # M3 雷达
        "watchlist": data.get("watchlist", []),
        "watchlist_misses": data.get("watchlist_misses", []),
    }


def run() -> None:
    payload = build_payload()
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    js = json.dumps(payload, ensure_ascii=False, default=_json_default)
    (SITE_DIR / "data.json").write_text(js, encoding="utf-8")
    (SITE_DIR / "data.js").write_text(f"window.IOSTREND_DATA = {js};", encoding="utf-8")
    print(f"[看板] 数据已写入 {SITE_DIR}/data.js（{len(payload['charts'])} 个榜单，"
          f"{len(payload['dates'])} 天）")


if __name__ == "__main__":
    run()
