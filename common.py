"""共享工具：路径常量、HTTP 会话、礼貌限速、CSV 幂等追加、配置与品类常量。

设计原则（沿用姐妹项目 trendradar）：
- 所有 IO 路径集中常量化；
- 采集礼貌限速 + 自动重试，避免规律请求被风控；
- CSV 幂等追加（同 key 覆盖、保留历史），天然累积时间序列。
"""
from __future__ import annotations

import random
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
import yaml
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------------------------------------------------------------- 路径常量
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"
CONFIG_DIR = ROOT / "config"
SITE_DIR = ROOT / "site"

RANK_CSV = DATA_DIR / "apple_rank.csv"      # 榜单快照（每日累积）
META_CSV = DATA_DIR / "app_meta.csv"        # app 元数据（品类/评分/价格）

# ---------------------------------------------------------------- 品类常量
GAMES_GENRE_ID = "6014"
PUZZLE_GENRE_ID = "7012"
WORD_GENRE_ID = "7019"

# 游戏子品类 genreId -> 中文名
GAME_SUBGENRES = {
    "7001": "动作", "7002": "冒险", "7003": "休闲", "7004": "棋盘",
    "7005": "卡牌", "7006": "博彩", "7009": "家庭", "7011": "音乐",
    "7012": "解谜", "7013": "竞速", "7014": "角色扮演", "7015": "模拟",
    "7016": "体育", "7017": "策略", "7018": "问答", "7019": "文字",
}

# App Store 品类英文名 -> 中文（顶级品类 + 常见游戏子类兜底）
GENRE_CN = {
    "Games": "游戏", "Business": "商务", "Education": "教育", "Entertainment": "娱乐",
    "Finance": "财务", "Food & Drink": "美食佳饮", "Health & Fitness": "健康健美",
    "Lifestyle": "生活", "Medical": "医疗", "Music": "音乐", "Navigation": "导航",
    "News": "新闻", "Photo & Video": "摄影与录像", "Productivity": "效率",
    "Reference": "参考", "Shopping": "购物", "Social Networking": "社交",
    "Sports": "体育", "Travel": "旅游", "Utilities": "工具", "Weather": "天气",
    "Books": "图书", "Book": "图书", "Magazines & Newspapers": "报刊杂志",
    "Graphics & Design": "图形设计", "Newsstand": "报刊杂志",
    "Developer Tools": "开发者工具", "Stickers": "贴纸", "Kids": "儿童",
    # 游戏子类（以防 primaryGenreName 偶尔返回子类）
    "Puzzle": "解谜", "Word": "文字", "Casual": "休闲", "Action": "动作",
    "Adventure": "冒险", "Board": "棋盘", "Card": "卡牌", "Casino": "博彩",
    "Family": "家庭", "Racing": "竞速", "Role Playing": "角色扮演",
    "Simulation": "模拟", "Strategy": "策略", "Trivia": "问答",
}


def genre_cn(name: str | None) -> str:
    """英文品类名转中文；未知保留原文，空值返回破折号。"""
    if not name:
        return "—"
    return GENRE_CN.get(name, name)


# ---------------------------------------------------------------- HTTP
def make_session() -> requests.Session:
    """带自动重试的会话；只对 429/5xx 重试，404 不重试（无数据是预期）。"""
    s = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.8,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers.update({"User-Agent": "iostrend/1.0 (personal app-trend radar)"})
    return s


def polite_sleep(base: float = 1.0, jitter: float = 0.6) -> None:
    """礼貌限速：固定基数 + 随机抖动，避免规律请求。"""
    time.sleep(base + random.random() * jitter)


# ---------------------------------------------------------------- 时间
def today_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def to_iso_date(s: str | None) -> str:
    """把 Apple 的 RFC1123 / ISO 时间转成 YYYY-MM-DD，失败则回退今天。"""
    if not s:
        return today_iso()
    # 兼容 RFC1123 数字时区(+0000)、字面 GMT、ISO。
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT",
                "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:  # 字面 GMT / 无时区 → 按 UTC
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # 所有格式都不匹配：仅当前 10 字符确为 YYYY-MM-DD 才采用，否则回退今天，
    # 避免把垃圾串（如 "Mon, 30 Ju"）写进日期主键。
    cand = s[:10]
    if len(cand) == 10 and cand[4] == "-" and cand[7] == "-" and cand[:4].isdigit():
        return cand
    return today_iso()


# ---------------------------------------------------------------- 配置
def load_config() -> dict:
    with open(CONFIG_DIR / "targets.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------- CSV 幂等
def upsert_csv(path: Path, rows: list[dict], key_cols: list[str]) -> int:
    """幂等追加：同 key 用新行覆盖旧行，保留其余历史。返回写入后总行数。"""
    new_df = pd.DataFrame(rows)
    if new_df.empty:
        return 0
    for k in key_cols:
        new_df[k] = new_df[k].astype(str)
    if path.exists():
        old = pd.read_csv(path, dtype={k: str for k in key_cols})
        combined = pd.concat([old, new_df], ignore_index=True)
        combined = combined.drop_duplicates(subset=key_cols, keep="last")
    else:
        combined = new_df
    path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(path, index=False)
    return len(combined)


def chunks(seq: list, n: int):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]
