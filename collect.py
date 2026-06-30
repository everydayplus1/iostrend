#!/usr/bin/env python3
"""采集编排主入口。

流程：
  1. 按 config 遍历 (市场 × 榜单) 抓 Apple 官方榜单 → apple_rank.csv
  2. 汇总当日全部去重 app_id，用 iTunes Lookup 富化品类/评分/价格 → app_meta.csv
单源失败只记日志、不中断（resilience first）。CSV 幂等追加，自动累积历史。

用法：python3 collect.py
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (CATEGORY_CSV, META_CSV, RANK_CSV, load_config, make_session,
                    polite_sleep, today_iso, upsert_csv)
from sources import apple_genre_rss, apple_rss, itunes_lookup


def run() -> None:
    cfg = load_config()
    session = make_session()
    markets = cfg["markets"]
    feeds = cfg["feeds"]
    limit = int(cfg.get("limit", 100))

    rank_rows: list[dict] = []
    market_ids: dict[str, set] = defaultdict(set)   # 按市场分组的 app_id
    market_date: dict[str, str] = {}                # 各市场真实榜单日期

    # ---- 1. 抓榜 ----
    for country in markets:
        for feed in feeds:
            try:
                cdate, rows = apple_rss.fetch_chart(session, country, feed, limit)
                market_date[country] = cdate
                for r in rows:
                    r.update({"date": cdate, "country": country, "feed": feed})
                    market_ids[country].add(r["app_id"])
                rank_rows.extend(rows)
                print(f"[榜单] {country}/{feed}: {len(rows)} 条 ({cdate})")
                polite_sleep()
            except Exception as e:  # noqa: BLE001
                print(f"[警告] 抓榜失败 {country}/{feed}: {e}", file=sys.stderr)

    if rank_rows:
        total = upsert_csv(RANK_CSV, rank_rows, key_cols=["date", "country", "feed", "rank"])
        print(f"[写入] {RANK_CSV.name}: 本次 {len(rank_rows)} 行，累计 {total} 行")

    # ---- 1b. 抓分品类深榜（M2，旧版 genre RSS，可插拔补充源）----
    cat_rows: list[dict] = []
    cc = cfg.get("category_charts", {})
    if cc.get("enabled"):
        cat_feeds = cc.get("feeds", [])
        cat_limit = int(cc.get("limit", 50))
        genres = cc.get("genres", {})  # {显示名: genreId}
        for country in markets:
            for feed in cat_feeds:
                for gname, gid in genres.items():
                    try:
                        cdate, rows = apple_genre_rss.fetch_genre_chart(
                            session, country, feed, str(gid), cat_limit)
                        for r in rows:
                            r.update({"date": cdate, "country": country, "feed": feed,
                                      "genre_id": str(gid), "genre_name": gname})
                            market_ids[country].add(r["app_id"])  # 一并富化评分/上线日
                        cat_rows.extend(rows)
                        polite_sleep(0.6, 0.4)
                    except Exception as e:  # noqa: BLE001
                        print(f"[警告] 分品类抓取失败 {country}/{feed}/{gname}: {e}",
                              file=sys.stderr)
            print(f"[分品类] {country}: 累计 {sum(1 for r in cat_rows if r['country']==country)} 行")
        if cat_rows:
            total = upsert_csv(CATEGORY_CSV, cat_rows,
                               key_cols=["date", "country", "feed", "genre_id", "rank"])
            print(f"[写入] {CATEGORY_CSV.name}: 本次 {len(cat_rows)} 行，累计 {total} 行")

    # ---- 2. 富化元数据（按各 app 所在市场分别查，品类/评分/价格本地化准确）----
    meta_rows: list[dict] = []
    for country, ids in market_ids.items():
        try:
            meta = itunes_lookup.enrich(session, list(ids), country=country)
            cdate = market_date.get(country, today_iso())  # 用该市场真实日期，非全局
            for aid, m in meta.items():
                meta_rows.append({"app_id": aid, "country": country, "date": cdate, **m})
            games = sum(m["is_game"] for m in meta.values())
            puzzles = sum(m["is_puzzle"] for m in meta.values())
            print(f"[富化] {country}: {len(meta)}/{len(ids)} 个 app（游戏 {games} / 解谜 {puzzles}）")
        except Exception as e:  # noqa: BLE001
            print(f"[警告] 富化失败 {country}: {e}", file=sys.stderr)

    if meta_rows:
        total = upsert_csv(META_CSV, meta_rows, key_cols=["app_id", "country", "date"])
        print(f"[写入] {META_CSV.name}: 本次 {len(meta_rows)} 行，累计 {total} 行")


if __name__ == "__main__":
    run()
