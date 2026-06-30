# iostrend · iOS 海外榜单热度雷达

每日采集 Apple App Store 海外榜单，分析热度趋势，生成报告与交互看板，**指导自家 app 开发**（解谜游戏 [arrowdoodle](../liuchengxiang/arrowdoodle) 为重点参照）。

姐妹项目：[trendradar](../wxmini/trendradar)（小程序热度分析）——同一套「公开合规源 → CSV → 报告 → 看板」范式。

---

## 数据源与诚实边界（务必先读）

| 源 | 用途 | 合规性 |
|----|------|--------|
| **Apple Marketing Tools RSS v2** | 总榜排名（`top-free` / `top-paid`，各国，每日更新，上限 100） | 官方公开、免鉴权、完全合规 |
| **iTunes genre RSS（旧版，M2）** | **分品类深榜**（解谜/游戏/文字 × 免费/付费/**畅销**，各国） | Apple 公开 legacy 接口，仍可用但未来可能变动 |
| **iTunes Lookup API** | 按 app id 富化品类 / 评分 / 价格 / 开发者 / 上线日期 | 官方公开、免鉴权 |

**边界（写死在每份报告与看板抬头）：**
1. 免费官方源**只有总榜**，**没有畅销榜（grossing）、也没有细分品类深榜**——下载/收入估算与品类深榜需付费 API（Sensor Tower / AppTweak 等）。
2. 「游戏 / 解谜」是从总榜里按品类 **筛出**的，不是 App Store 品类榜。小众品类（如解谜）在总榜 Top 100 里常常很少出现，**覆盖深度有限**——这是当前 v1 的已知局限（见 Roadmap）。
3. 评分 / 价格按各市场本地化口径；品类全球一致。
4. 趋势需连续多日累积才有意义。

---

## 安装

```bash
cd iostrend
pip install -r requirements.txt   # requests / PyYAML / pandas / matplotlib
```

## 用法

```bash
python3 collect.py      # 采集榜单+富化 → data/apple_rank.csv, data/app_meta.csv（幂等累积）
python3 report.py       # 生成 reports/YYYY-MM-DD.md（+ 趋势 PNG，需≥2天）
python3 build_site.py   # 生成 site/data.js（看板数据）
```

看看板：

```bash
cd site && python3 -m http.server 8765   # 浏览器开 http://localhost:8765
```
（看板用 `<script src=data.js>` 加载数据，本地双击 `site/index.html` 也能看。趋势折线需联网加载 Chart.js。）

## 配置

只改 `config/targets.yaml`，无需动代码：

```yaml
markets: [us, jp, kr, gb, de]   # 国家码，自由增删（fr ca au br id tw hk …）
feeds: [top-free, top-paid]     # 免费官方源仅这两类
limit: 100                      # 官方上限
watch_genres: {game: "6014", puzzle: "7012", word: "7019"}
focus_genre_id: "7012"          # 看板/报告的「专题」聚焦品类
focus_label: "解谜游戏"
```

---

## 每日自动化

**推荐：GitHub Actions（云端跑，解决笔记本睡眠/关机无法定时的问题）**
`.github/workflows/daily.yml` 已配好：每天定时采集 → 提交回累积数据 → 部署看板到 GitHub Pages。
推到 GitHub 后，在仓库 **Settings → Pages → Source 选 GitHub Actions** 即可。

**本地替代：cron**
```cron
0 17 * * *  cd /Users/lcx/iostrend && /usr/bin/python3 collect.py && python3 report.py && python3 build_site.py
```

---

## 架构

```
iostrend/
├── collect.py          采集编排（抓榜 → 富化 → 幂等写 CSV）
├── analyze.py          趋势分析（名次升降/新进/掉榜/品类聚合/专题）—— 只算
├── report.py           Markdown 报告 + 趋势 PNG
├── build_site.py       看板数据序列化（site/data.js）
├── common.py           路径/HTTP会话/限速/CSV幂等/品类常量
├── config/targets.yaml 市场×榜单×品类配置
├── sources/
│   ├── apple_rss.py    Apple Marketing Tools RSS v2 采集
│   └── itunes_lookup.py iTunes Lookup 富化
├── data/*.csv          累积历史（进版本库）
├── reports/*.md        每日报告（进版本库）
└── site/index.html     交互看板（渲染层只画不算）
```

设计原则（沿用 trendradar）：渲染层只画不算、CSV 幂等累积、单源失败不中断、诚实边界写死在报告。

---

## Roadmap

- **M1（已完成）** 官方免费源全链路：5 市场 × 免费/付费榜，每日采集 + 报告 + 交互看板 + CI。
- **M2（已完成）** 分品类深榜：旧版 genre RSS（可插拔补充源）拿到解谜/游戏/文字 × 免费/付费/**畅销**榜；看板分品类区 + 上线时长列 + 年龄过滤，补足解谜赛道纵深。
- **M3** 量级信号：接入下载/收入估算（Sensor Tower / AppTweak），补齐畅销榜维度。
- **M4** 自家 app 雷达：把 arrowdoodle 自身排名/竞品对比做成看板专页，趋势告警。
