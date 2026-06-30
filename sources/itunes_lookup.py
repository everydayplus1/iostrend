"""iTunes Lookup API 富化器。

源：https://itunes.apple.com/lookup?id={逗号分隔 id}&country={cc}
- 官方、免鉴权、免费；批量按 id 查询（每批 ~180 个）。
- 提供 primaryGenreName / genreIds / genres / 评分 / 价格 / 开发者 / 版本日期。
- 品类与区无关；评分/价格按 country 本地化（默认用参考区 us）。
"""
from __future__ import annotations

LOOKUP = "https://itunes.apple.com/lookup"


def enrich(session, app_ids: list[str], country: str = "us") -> dict[str, dict]:
    """批量富化。返回 {app_id: 元数据 dict}。查不到的 id 自动跳过。"""
    from common import GAMES_GENRE_ID, PUZZLE_GENRE_ID, chunks, polite_sleep

    out: dict[str, dict] = {}
    unique_ids = sorted(set(str(a) for a in app_ids if a))
    for batch in chunks(unique_ids, 180):
        resp = session.get(
            LOOKUP,
            params={"id": ",".join(batch), "country": country, "entity": "software"},
            timeout=20,
        )
        resp.raise_for_status()
        for item in resp.json().get("results", []):
            aid = str(item.get("trackId", ""))
            if not aid:
                continue
            gids = [str(g) for g in item.get("genreIds", [])]
            out[aid] = {
                "primary_genre": item.get("primaryGenreName", ""),
                "genre_ids": "|".join(gids),
                "genres": "|".join(item.get("genres", [])),
                "is_game": int(GAMES_GENRE_ID in gids),
                "is_puzzle": int(PUZZLE_GENRE_ID in gids),
                "avg_rating": item.get("averageUserRating"),
                "rating_count": item.get("userRatingCount"),
                "price": item.get("price"),
                "formatted_price": item.get("formattedPrice", ""),
                "seller_name": item.get("sellerName", ""),
                "version_date": (item.get("currentVersionReleaseDate") or "")[:10],
                "release_date": (item.get("releaseDate") or "")[:10],  # 原始上线日（权威）
            }
        polite_sleep()
    return out
