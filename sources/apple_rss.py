"""Apple Marketing Tools RSS v2 采集器。

源：https://rss.marketingtools.apple.com/api/v2/{country}/apps/{feed}/{limit}/apps.json
- 官方、免鉴权、每日更新、完全合规（公开 RSS）。
- 仅支持 feed = top-free / top-paid（没有畅销榜 top-grossing）。
- limit 上限 100；返回的 results 不含品类（genres 为空），品类需另用 iTunes Lookup 富化。
"""
from __future__ import annotations

BASE = "https://rss.marketingtools.apple.com/api/v2/{country}/apps/{feed}/{limit}/apps.json"


def fetch_chart(session, country: str, feed: str, limit: int = 100):
    """抓单个 (国家, 榜单)。返回 (榜单日期 YYYY-MM-DD, [行...])。

    每行：rank, app_id, app_name, artist_name, url
    """
    from common import to_iso_date

    url = BASE.format(country=country, feed=feed, limit=limit)
    resp = session.get(url, timeout=20)
    resp.raise_for_status()
    feed_obj = resp.json()["feed"]
    chart_date = to_iso_date(feed_obj.get("updated"))

    rows = []
    for rank, item in enumerate(feed_obj.get("results", []), start=1):
        rows.append({
            "rank": rank,
            "app_id": str(item.get("id", "")),
            "app_name": item.get("name", ""),
            "artist_name": item.get("artistName", ""),
            "url": item.get("url", ""),
            "artwork": item.get("artworkUrl100", ""),     # 100x100 图标
            "release_date": item.get("releaseDate", ""),  # 原始上线日 YYYY-MM-DD
        })
    return chart_date, rows
