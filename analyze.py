"""趋势分析层。

把 apple_rank.csv（榜单时间序列）与 app_meta.csv（品类/评分/价格）合并，
产出结构化结果，供 report.py 与 build_site.py 共用（只算一次，渲染层只画不算）。

核心维度：
- 当日榜单 + 日环比名次变化（升/降/新进/掉出）
- 游戏 / 解谜品类筛选
- 各市场榜单的品类数量历史（趋势线）
- 解谜游戏跨市场专题（直接服务 arrowdoodle）
"""
from __future__ import annotations

import math

import pandas as pd

from common import CATEGORY_CSV, META_CSV, RANK_CSV, genre_cn, load_config

SPARK_WINDOW = 7  # 「最近趋势」回看天数

_META_COLS = [
    "app_id", "country", "primary_genre", "genre_ids", "genres",
    "is_game", "is_puzzle", "avg_rating", "rating_count",
    "price", "formatted_price", "seller_name", "version_date", "release_date",
]
_RANK_COLS = ["rank", "app_id", "app_name", "artist_name", "url", "artwork",
              "release_date", "date", "country", "feed"]
_CAT_COLS = ["date", "country", "feed", "genre_id", "genre_name", "rank",
             "app_id", "app_name", "artist_name", "url", "artwork"]
# 总榜 release_date 来自 apple_rank（marketing RSS）；meta 也有 release_date（lookup），
# 合并总榜时排除 meta 的 release_date 以免列名冲突；分品类则用 meta 的 release_date。
_META_MERGE_EXCLUDE = {"release_date"}


def _read_csv_safe(path, cols):
    """读 CSV；文件不存在或为空时返回带列名的空表（防首次运行/富化全失败时崩溃）。"""
    if not path.exists():
        return pd.DataFrame(columns=cols)
    try:
        return pd.read_csv(path, dtype={"app_id": str})
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=cols)


def _clean(v):
    """NaN -> None，便于 JSON / 表格渲染。"""
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    return v


def _load_meta_latest():
    """每个 (app_id,country) 的最新元数据；缺失/空时返回带列名空表。"""
    meta = _read_csv_safe(META_CSV, _META_COLS)
    if meta.empty:
        return pd.DataFrame(columns=_META_COLS)
    return (meta.sort_values("date")
                .drop_duplicates(["app_id", "country"], keep="last"))


def load_merged():
    """返回 (rank_df, merged_df)。merged 用每个 (app_id,country) 的最新元数据。

    对缺失/空 CSV 与缺失 meta 容错（不崩溃），让上层 build_all 优雅短路。
    """
    rank = _read_csv_safe(RANK_CSV, _RANK_COLS)
    if rank.empty:
        return rank, rank.copy()

    meta_latest = _load_meta_latest()
    merge_cols = [c for c in _META_COLS if c in meta_latest.columns
                  and c not in _META_MERGE_EXCLUDE]
    merged = rank.merge(meta_latest[merge_cols], on=["app_id", "country"], how="left")
    for col in ("is_game", "is_puzzle"):
        if col not in merged.columns:
            merged[col] = 0
        merged[col] = merged[col].fillna(0).astype(int)
    return rank, merged


def all_dates(merged) -> list[str]:
    return sorted(merged["date"].unique().tolist())


def _row_dict(row, delta, status, spark=None):
    return {
        "rank": int(row["rank"]),
        "app_id": str(row["app_id"]),
        "name": row["app_name"],
        "artist": row["artist_name"],
        "url": row.get("url", ""),
        "icon": _clean(row.get("artwork")) or "",
        "release_date": (_clean(row.get("release_date")) or "")[:10],
        "primary_genre": _clean(row.get("primary_genre")),
        "primary_genre_cn": genre_cn(_clean(row.get("primary_genre"))),
        "is_game": int(row.get("is_game", 0)),
        "is_puzzle": int(row.get("is_puzzle", 0)),
        "rating": _clean(row.get("avg_rating")),
        "rating_count": _clean(row.get("rating_count")),
        "price": _clean(row.get("formatted_price")),
        "seller": _clean(row.get("seller_name")),
        "version_date": _clean(row.get("version_date")),
        "delta": delta,        # 名次变化：正=上升，负=下降，None=新进/无对比
        "status": status,      # new / up / down / same / flat
        "spark": spark or [],  # 近 N 天名次序列（缺席的天为 None），供 sparkline
    }


def _compute_changes(sub) -> dict:
    """对单个榜单的跨日子表算：当日行(含日环比/sparkline) + 掉出榜。通用于总榜与分品类。"""
    dates = sorted(sub["date"].unique().tolist())
    if not dates:
        return {"date": None, "prev_date": None, "rows": [], "droppers": []}
    cur_date = dates[-1]
    prev_date = dates[-2] if len(dates) >= 2 else None

    cur = sub[sub["date"] == cur_date].sort_values("rank")
    prev_rank: dict[str, int] = {}
    if prev_date:
        prev = sub[sub["date"] == prev_date]
        prev_rank = dict(zip(prev["app_id"].astype(str), prev["rank"]))

    recent_dates = dates[-SPARK_WINDOW:]
    rank_by_date = {
        d: dict(zip(sub[sub["date"] == d]["app_id"].astype(str),
                    sub[sub["date"] == d]["rank"]))
        for d in recent_dates
    }

    rows = []
    for _, row in cur.iterrows():
        aid = str(row["app_id"])
        pr = prev_rank.get(aid)
        if not prev_date:
            delta, status = None, "flat"
        elif pr is None:
            delta, status = None, "new"
        else:
            delta = int(pr - row["rank"])  # 名次数字变小=上升
            status = "up" if delta > 0 else ("down" if delta < 0 else "same")
        spark = [int(rank_by_date[d][aid]) if aid in rank_by_date[d] else None
                 for d in recent_dates]
        rows.append(_row_dict(row, delta, status, spark))

    droppers = []
    if prev_date:
        cur_ids = set(cur["app_id"].astype(str))
        prev = sub[sub["date"] == prev_date].sort_values("rank")
        for _, row in prev.iterrows():
            if str(row["app_id"]) not in cur_ids:
                droppers.append({"app_id": str(row["app_id"]),
                                 "name": row["app_name"],
                                 "prev_rank": int(row["rank"])})

    return {"date": cur_date, "prev_date": prev_date, "rows": rows, "droppers": droppers}


def chart_changes(merged, country: str, feed: str) -> dict:
    """单个 (国家,总榜) 的当日榜单 + 日环比变化。"""
    sub = merged[(merged["country"] == country) & (merged["feed"] == feed)]
    out = _compute_changes(sub)
    out.update(country=country, feed=feed)
    return out


def load_category_merged():
    """分品类深榜 join 最新元数据（评分/上线日/品类）。空时返回带列名空表。"""
    cat = _read_csv_safe(CATEGORY_CSV, _CAT_COLS)
    if cat.empty:
        return cat
    cat["genre_id"] = cat["genre_id"].astype(str)
    meta_latest = _load_meta_latest()
    meta_cols = [c for c in ["app_id", "country", "avg_rating", "rating_count",
                             "formatted_price", "release_date", "primary_genre",
                             "is_game", "is_puzzle"] if c in meta_latest.columns]
    merged = cat.merge(meta_latest[meta_cols], on=["app_id", "country"], how="left")
    for col in ("is_game", "is_puzzle"):
        if col not in merged.columns:
            merged[col] = 0
        merged[col] = merged[col].fillna(0).astype(int)
    return merged


def category_chart(cat_merged, country: str, feed: str, gid: str) -> dict:
    """单个 (国家,榜单类型,品类) 的分品类深榜 + 日环比变化。"""
    sub = cat_merged[(cat_merged["country"] == country)
                     & (cat_merged["feed"] == feed)
                     & (cat_merged["genre_id"].astype(str) == str(gid))]
    out = _compute_changes(sub)
    out.update(country=country, feed=feed, genre_id=str(gid))
    return out


def genre_history(merged) -> dict[str, list[dict]]:
    """各 (国家|榜单) 的游戏/解谜数量按日历史，用于趋势线。"""
    g = (merged.groupby(["country", "feed", "date"])
               .agg(games=("is_game", "sum"), puzzle=("is_puzzle", "sum"))
               .reset_index())
    out: dict[str, list[dict]] = {}
    for (country, feed), grp in g.groupby(["country", "feed"]):
        key = f"{country}|{feed}"
        out[key] = [{"date": r["date"], "games": int(r["games"]),
                     "puzzle": int(r["puzzle"])}
                    for _, r in grp.sort_values("date").iterrows()]
    return out


def focus_spotlight(changes_by_key: dict, focus_attr: str = "is_puzzle") -> list[dict]:
    """聚焦品类（默认解谜）的跨市场专题：同一 app 聚合它在各市场/榜单的名次。"""
    apps: dict[str, dict] = {}
    for key, ch in changes_by_key.items():
        country, feed = key.split("|")
        for r in ch["rows"]:
            if not r.get(focus_attr):
                continue
            entry = apps.setdefault(r["app_id"], {
                "name": r["name"], "artist": r["artist"],
                "rating": r["rating"], "price": r["price"],
                "version_date": r["version_date"], "appearances": [],
            })
            entry["appearances"].append({
                "country": country, "feed": feed,
                "rank": r["rank"], "delta": r["delta"], "status": r["status"],
            })
    # 按出现市场数 → 最佳名次排序
    result = list(apps.values())
    result.sort(key=lambda a: (-len(a["appearances"]),
                               min(x["rank"] for x in a["appearances"])))
    return result


def build_all() -> dict:
    """一站式产出所有分析结果。"""
    cfg = load_config()
    _, merged = load_merged()
    dates = all_dates(merged)

    if not dates:  # 无任何数据：优雅短路，由 report/build_site 的 latest_date 判空处理
        return {"config": cfg, "dates": [], "latest_date": None, "has_trend": False,
                "changes": {}, "history": {}, "focus": [],
                "focus_label": cfg.get("focus_label", "解谜游戏"),
                "category": {}, "cat_genres": [], "cat_feeds": [], "cat_focus": ""}

    changes_by_key: dict[str, dict] = {}
    for country in cfg["markets"]:
        for feed in cfg["feeds"]:
            changes_by_key[f"{country}|{feed}"] = chart_changes(merged, country, feed)

    # 分品类深榜（M2）
    category: dict[str, dict] = {}
    cc = cfg.get("category_charts", {})
    cat_genres = cc.get("genres", {}) if cc.get("enabled") else {}
    cat_feeds = cc.get("feeds", []) if cc.get("enabled") else []
    if cat_genres:
        cat_merged = load_category_merged()
        if not cat_merged.empty:
            for country in cfg["markets"]:
                for feed in cat_feeds:
                    for gname, gid in cat_genres.items():
                        category[f"{country}|{feed}|{gid}"] = category_chart(
                            cat_merged, country, feed, str(gid))

    return {
        "config": cfg,
        "dates": dates,
        "latest_date": dates[-1] if dates else None,
        "has_trend": len(dates) >= 2,
        "changes": changes_by_key,
        "history": genre_history(merged),
        "focus": focus_spotlight(changes_by_key, "is_puzzle"),
        "focus_label": cfg.get("focus_label", "解谜游戏"),
        "category": category,
        "cat_genres": [{"name": n, "gid": str(g)} for n, g in cat_genres.items()],
        "cat_feeds": cat_feeds,
        "cat_focus": cc.get("focus", ""),
    }
