"""旧版 iTunes genre RSS 采集器 —— 分品类深榜（M2 可插拔补充源）。

源：https://itunes.apple.com/{cc}/rss/{feed}applications/limit={N}/genre={GID}/json
- feed ∈ topfree / toppaid / topgrossing（**含畅销榜**，新版 marketing tools 源没有）。
- 能拿到「游戏 > 解谜」这类细分品类榜，补足总榜的覆盖盲区。
- ⚠️ 这是 Apple 的 legacy 接口（免鉴权、公开、目前仍可用），未来可能变动；
  故设计成可插拔补充源，坏了不影响主源（marketing tools 总榜）。
"""
from __future__ import annotations

BASE = ("https://itunes.apple.com/{cc}/rss/{feed}applications"
        "/limit={limit}/genre={gid}/json")


def fetch_genre_chart(session, country: str, feed: str, gid: str, limit: int = 50):
    """抓单个 (国家, 榜单类型, 品类)。返回 (榜单日期 YYYY-MM-DD, [行...])。

    每行：rank, app_id, app_name, artist_name, url, artwork
    """
    from common import to_iso_date

    url = BASE.format(cc=country, feed=feed, limit=limit, gid=gid)
    resp = session.get(url, timeout=20)
    resp.raise_for_status()
    feed_obj = resp.json().get("feed", {})
    chart_date = to_iso_date(feed_obj.get("updated", {}).get("label"))

    entries = feed_obj.get("entry", [])
    if isinstance(entries, dict):   # 仅 1 条时 Apple 返回 dict 而非 list
        entries = [entries]

    rows = []
    for rank, e in enumerate(entries, start=1):
        try:
            imgs = e.get("im:image", [])
            rows.append({
                "rank": rank,
                "app_id": str(e["id"]["attributes"]["im:id"]),
                "app_name": e["im:name"]["label"],
                "artist_name": e.get("im:artist", {}).get("label", ""),
                "url": e["id"]["label"],
                "artwork": imgs[-1]["label"] if imgs else "",
            })
        except (KeyError, TypeError, IndexError):
            continue
    return chart_date, rows
