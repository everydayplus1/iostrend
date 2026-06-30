#!/usr/bin/env python3
"""报告生成：每日 Markdown（reports/YYYY-MM-DD.md）+ 趋势 PNG（≥2 天才出）。

诚实边界写死在报告抬头（沿用 trendradar 约定）。
用法：python3 report.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import analyze
from common import GAME_SUBGENRES, REPORTS_DIR

CLIMB_THRESHOLD = 10  # 上升 ≥ 多少名算「强势上升」

COUNTRY_CN = {
    "us": "美国", "jp": "日本", "kr": "韩国", "gb": "英国", "de": "德国",
    "fr": "法国", "ca": "加拿大", "au": "澳大利亚", "br": "巴西",
    "id": "印尼", "tw": "中国台湾", "hk": "中国香港", "cn": "中国大陆",
}
FEED_CN = {"top-free": "免费榜", "top-paid": "付费榜"}


def _cc(c: str) -> str:
    return f"{COUNTRY_CN.get(c, c.upper())} {c.upper()}"


def _arrow(delta):
    if delta is None:
        return "🆕"
    if delta > 0:
        return f"▲{delta}"
    if delta < 0:
        return f"▼{abs(delta)}"
    return "—"


def _rating(r):
    return f"{r:.2f}" if isinstance(r, (int, float)) else "—"


def _age(rel, base):
    """已上线时长（X年X个月）。"""
    if not rel or len(rel) < 7 or not base:
        return "—"
    try:
        months = (int(base[:4]) - int(rel[:4])) * 12 + (int(base[5:7]) - int(rel[5:7]))
        months = max(0, months)
        y, m = divmod(months, 12)
        return f"{y}年{m}个月" if (y and m) else (f"{y}年" if y else (f"{m}个月" if m else "新上线"))
    except (ValueError, TypeError):
        return "—"


def _md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def _disclaimer() -> str:
    return (
        "> **诚实边界（数据口径，务必先读）**\n"
        "> 1. 总榜 = Apple 官方 Marketing Tools（每日更新，top-free / top-paid）。\n"
        "> 2. 分品类深榜 = 旧版 iTunes genre RSS（Apple 公开 **legacy** 接口，含**畅销榜**，仍可用但未来可能变动）。\n"
        "> 3. 品类 / 评分 / 上线日由 iTunes Lookup 富化，按各市场本地化。\n"
        "> 4. 趋势需连续多日累积才有意义。\n"
    )


def build_md(data: dict) -> str:
    L = [f"# iOS 海外榜单热度雷达 · {data['latest_date']}", "", _disclaimer(), ""]
    cfg = data["config"]
    changes = data["changes"]

    # ---- 各市场名次异动 ----
    for country in cfg["markets"]:
        L.append(f"## {_cc(country)}")
        any_section = False
        for feed in cfg["feeds"]:
            ch = changes.get(f"{country}|{feed}")
            if not ch or not ch["rows"]:
                continue
            climbers = [r for r in ch["rows"]
                        if r["delta"] is not None and r["delta"] >= CLIMB_THRESHOLD]
            newcomers = [r for r in ch["rows"] if r["status"] == "new"]
            droppers = ch["droppers"]

            if ch["prev_date"] is None:
                # 首日：无对比，给 Top10 快照
                L.append(f"\n### {FEED_CN.get(feed, feed)} · 今日 Top 10（首日快照，暂无环比）")
                top = ch["rows"][:10]
                L.append(_md_table(
                    ["#", "App", "开发者", "品类"],
                    [[r["rank"], r["name"], r["artist"], r["primary_genre_cn"]] for r in top]))
                any_section = True
                continue

            if climbers:
                L.append(f"\n### {FEED_CN.get(feed, feed)} · 🚀 强势上升（≥{CLIMB_THRESHOLD} 名）")
                L.append(_md_table(
                    ["变化", "现#", "App", "品类", "评分"],
                    [[_arrow(r["delta"]), r["rank"], r["name"],
                      r["primary_genre_cn"], _rating(r["rating"])]
                     for r in sorted(climbers, key=lambda x: -x["delta"])[:10]]))
                any_section = True
            if newcomers:
                L.append(f"\n### {FEED_CN.get(feed, feed)} · 🆕 新进榜")
                L.append(_md_table(
                    ["现#", "App", "开发者", "品类"],
                    [[r["rank"], r["name"], r["artist"], r["primary_genre_cn"]]
                     for r in newcomers[:15]]))
                any_section = True
            if droppers:
                L.append(f"\n### {FEED_CN.get(feed, feed)} · 📉 掉出榜")
                L.append(_md_table(
                    ["原#", "App"],
                    [[d["prev_rank"], d["name"]] for d in droppers[:15]]))
                any_section = True
        if not any_section:
            L.append("\n_（暂无数据）_")
        L.append("")

    # ---- M2 分品类深榜：聚焦品类（解谜）各市场免费榜 Top 8 ----
    cat = data.get("category", {})
    gid = next((g["gid"] for g in data.get("cat_genres", []) if g["name"] == data.get("cat_focus")), None)
    feed0 = (data.get("cat_feeds") or ["topfree"])[0]
    base = data["latest_date"]
    L.append(f"## 🧩 {data.get('cat_focus', '解谜')}深榜（各市场免费榜 Top 8 · 服务 arrowdoodle）")
    L.append("> 旧版 genre RSS 细分品类；「已上线」短=新机会。")
    if not cat or not gid:
        L.append("\n_（分品类数据未启用或暂无）_")
    else:
        for country in cfg["markets"]:
            ch = cat.get(f"{country}|{feed0}|{gid}")
            if not ch or not ch["rows"]:
                continue
            L.append(f"\n### {_cc(country)}")
            L.append(_md_table(
                ["#", "App", "开发者", "已上线", "评分"],
                [[r["rank"], r["name"], r["artist"], _age(r["release_date"], base), _rating(r["rating"])]
                 for r in ch["rows"][:8]]))
    L.append("")

    # ---- 游戏品类总览 ----
    L.append("## 🎮 游戏品类分布（各总榜中游戏数量）")
    hist = data["history"]
    rows = []
    for country in cfg["markets"]:
        for feed in cfg["feeds"]:
            h = hist.get(f"{country}|{feed}")
            if h:
                last = h[-1]
                rows.append([_cc(country), FEED_CN.get(feed, feed),
                             last["games"], last["puzzle"]])
    L.append("\n" + _md_table(["市场", "榜单", "游戏数", "解谜数"], rows))
    L.append("")

    return "\n".join(L)


def build_trend_png(data: dict, path: Path) -> bool:
    """画各市场免费榜中游戏数量随时间变化。≥2 天才有意义。"""
    if not data["has_trend"]:
        return False
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    hist = data["history"]
    cfg = data["config"]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    plotted = False
    for country in cfg["markets"]:
        h = hist.get(f"{country}|top-free")
        if h and len(h) >= 2:
            ax.plot([x["date"] for x in h], [x["games"] for x in h],
                    marker="o", label=country.upper())
            plotted = True
    if not plotted:
        plt.close(fig)
        return False
    ax.set_title("Games in App Store top-free chart (overall) by market")
    ax.set_ylabel("# games in top-100")
    ax.set_xlabel("date")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return True


def run() -> None:
    data = analyze.build_all()
    if not data["latest_date"]:
        print("[报告] 无数据，先运行 collect.py")
        return
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    md_path = REPORTS_DIR / f"{data['latest_date']}.md"
    md_path.write_text(build_md(data), encoding="utf-8")
    print(f"[报告] {md_path}")

    png_path = REPORTS_DIR / f"{data['latest_date']}_trend.png"
    if build_trend_png(data, png_path):
        print(f"[趋势图] {png_path}")
    else:
        print("[趋势图] 数据不足 2 天，跳过")


if __name__ == "__main__":
    run()
