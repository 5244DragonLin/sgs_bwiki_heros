# sgs_bwiki_heros

基于 BeautifulSoup + requests，从 bilibili 三国杀 WIKI 爬取武将信息的 Python 工具。支持增量爬取、多版本技能台词解析、多参数组合筛选，输出 JSON 格式。

## 为什么需要这个工具？

- 三国杀武将数据分散在 WIKI 各页面，手动查阅效率极低
- 经典、界限突破、国战三种版本的技能和台词各不相同，需要分别收集
- 武将数量庞大（646），增量爬取、断点续爬等机制是刚需

**sgs_bwiki_heros 解决这些问题**：一个命令就能批量获取全部武将的结构化数据，支持按势力/武将包灵活筛选。

## ⭐亮点

- **增量爬取**：checkpoint 机制记录已爬武将和页面 hash，再次运行只爬新武将
- **多版本覆盖**：自动区分经典/界限突破/国战版本，分别提取技能和台词
- **限时玩法过滤**：自动跳过自走棋/限时地主/喵喵杀等非常驻玩法区块，只保留常驻武将数据
- **技能台词分离**：每条台词绑定所属技能，结构清晰
- **珠联璧合**：国战武将的专属配对关系完整保留
- **自动保存**：每 N 个武将自动写盘，中断不丢数据
- **JSON 输出**：完整结构化 JSON + 武将包映射文件
- **武将包映射**：自动生成 `pack_character_map.json`，按网站顺序列出所有武将包，包含大类和子包图标路径
- **多参数筛选**：按武将包、势力、数量、版本自由组合查询
- **经典形象原画爬取**：可选下载武将「经典形象」原画到 `output/artworks/{name}-经典形象.png`，并在数据中记录 `artwork` 相对路径（默认关闭）
- **仅查询模式**：爬完后的数据可离线筛选，无需重新请求网络

## 📸效果预览

### CLI 运行

```text
[*] 正在获取武将列表...
[+] 共发现 646 个武将
[+] 势力分布: {'魏': 20, '蜀': 21, '吴': 23, '群': 23, '神': 38}
[+] 武将包数量: 91
[*] 需要爬取: 646 个武将（已存在 0 个，限时武将 0 个，体验卡测试 0 个）
爬取武将: 100%|█████████████████████████████| 646/646 [11:14<00:00, ...]
[+] 爬取完成: 成功 587，跳过(已存在) 0，跳过(限时武将) 40，跳过(体验卡测试) 19，失败 0
[+] 原画下载(同步): 成功 587，跳过(已存在) 0，失败(无原画/下载失败) 0
==================================================
[*] 爬取完成，共 587 个武将
```

### 输出目录结构

```text
output/
├── characters.json              # 全部武将（JSON）
├── pack_character_map.json      # 武将包与武将的映射（含图标路径）
├── artworks/                    # 经典形象原画（开启 --crawl-artwork 时）
│   └── {name}-经典形象.png
└── artworks_checkpoint.json     # 原画下载进度断点
```

### JSON 示例（关羽·经典版本）

```json
{
  "name": "关羽",
  "gender": "男",
  "faction": "蜀",
  "hall_of_fame": "五虎上将",
  "pack": "标准-蜀汉虎将",
  "release_time": "开服",
  "alliances": ["刘备"],
  "versions": {
    "classic": {
      "skills": [
        {"name": "武圣", "description": "你可以将一张红色牌当【杀】使用或打出。"}
      ],
      "lines": {
        "武圣": ["关羽在此，尔等受死！/看尔乃插标卖首！"],
        "阵亡": ["什么？此地名叫麦城。"]
      }
    }
  }
}
```

## 🚀快速开始

### 1. 克隆项目

```bash
# Gitee 镜像（国内访问快）
git clone https://gitee.com/yhl5244/sgs_bwiki_heros

# GitHub 原仓库
git clone https://github.com/5244DragonLin/sgs_bwiki_heros

cd sgs_bwiki_heros
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 运行

```bash
# 爬取所有武将（约需 10-20 分钟）
python sgs_bwiki_heros.py

# 爬取并下载武将「经典形象」原画（可选，默认关闭）
python sgs_bwiki_heros.py --crawl-artwork

# 爬取蜀势力武将，限制 10 个，每 5 个自动保存
python sgs_bwiki_heros.py --faction 蜀 --limit 10 --auto-save 5

# 从已有数据中筛选（不重新爬取）
python sgs_bwiki_heros.py --query --faction 魏 --limit 5
```

### 4. 配置文件（可选）

复制示例配置并按需修改，命令行参数优先级更高：

```bash
cp config.example.yaml config.yaml
# 编辑 config.yaml 修改请求间隔、输出目录等
python sgs_bwiki_heros.py
```

`config.example.yaml` 中可配置项：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `request.base_url` | Bwiki 基础地址 | `wiki.biligame.com/sgs` |
| `request.delay` | 基础请求间隔（秒） | `1.0` |
| `request.delay_jitter` | 随机抖动上限（秒），实际间隔 = delay + random.uniform(0, delay_jitter) | `2.0` |
| `request.max_retries` | 最大重试次数 | `5` |
| `request.timeout` | 请求超时时间（秒） | `30` |
| `output.dir` | 输出目录 | `output/` |
| `output.save_every_n` | 每 N 个武将自动保存 | `20` |
| `filters.pack` | 武将包筛选 | 空（全部） |
| `filters.faction` | 势力筛选 | 空（全部） |
| `filters.limit` | 数量限制（0=不限制） | `0` |
| `crawl_artwork` | 是否爬取武将经典形象原画（下载到 `output/artworks/`） | `false` |

## ⌨️CLI 模式

```
python sgs_bwiki_heros.py [-o OUTPUT] [--pack PACK] [--faction FACTION]
                      [--limit LIMIT] [--auto-save N] [--no-skip] [--query]
                      [--crawl-artwork] [--export-pack-map] [--version VER]
                      [--delay SEC] [--delay-jitter SEC] [--max-retries N]
                      [--timeout SEC]
```

### 筛选选项

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--pack PACK` | 按武将包筛选（如：标准-蜀汉虎将） | 全部 |
| `--faction FACTION` | 按势力筛选（魏/蜀/吴/群/神） | 全部 |
| `--limit N` | 限制爬取或查询数量 | 全部 |
| `--version VER` | 按武将版本筛选（classic/breakthrough/national_war） | 全部 |

### 爬取控制

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-o, --output DIR` | 输出目录 | `./output/` |
| `--auto-save N` | 每 N 个武将自动保存一次 | 20 |
| `--no-skip` | 不跳过已爬取的武将（强制重新爬取） | 跳过 |
| `--no-resume` | 不从检查点恢复 | 恢复 |
| `--crawl-artwork` | 爬取武将「经典形象」原画并下载到 `output/artworks/`（也可在 config.yaml 设 `crawl_artwork: true`） | 关闭 |
| `--export-pack-map` | 导出武将包映射到 `output/pack_character_map.json` | 关闭 |

### 网络参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--delay SEC` | 基础请求间隔（秒） | `1.0` |
| `--delay-jitter SEC` | 随机抖动上限（秒），实际间隔 = delay + random.uniform(0, jitter) | `2.0` |
| `--max-retries N` | 单个页面最大重试次数 | `5` |
| `--timeout SEC` | 请求超时时间（秒） | `30` |

### 查询模式

| 参数 | 说明 |
|------|------|
| `--query` | 仅查询已有数据，不重新发起网络请求 |

## 📂项目结构

```text
sgs_bwiki_heros/
├── sgs_bwiki_heros.py    # 主爬虫脚本
├── requirements.txt      # Python 依赖
├── config.example.yaml   # 示例配置文件（可选，复制为 config.yaml 使用）
├── LICENSE               # MIT 许可证
├── README.md             # 本文件
├── tests/                # 单元测试与 fixtures
│   ├── verify_skill_fix.py
│   ├── verify_timed_mode_skip.py
│   ├── verify_skip_log.py
│   └── verify_artwork_crawl.py
└── output/               # 爬取结果（git 忽略）
    ├── characters.json
    ├── pack_character_map.json  # 武将包与武将的映射（含图标路径）
    ├── artworks/                # 经典形象原画（开启 --crawl-artwork 时）
    ├── artworks_checkpoint.json # 原画下载进度断点
    └── checkpoint.json          # 爬取进度断点
```

## 配置说明

爬虫内置的默认参数（也可通过 `config.example.yaml` 统一管理，详见上方"### 4. 配置文件"）：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| 请求间隔 | 1.0s + 随机抖动 0~2.0s | 每次 HTTP 请求后的等待时间（delay + random.uniform(0, delay_jitter)） |
| 最大重试 | 5 次 | 单个页面请求失败后的重试次数（567 频率限制指数退避等待） |
| 请求超时 | 30s | 单次 HTTP 请求超时时间 |
| 自动保存 | 每 20 个 | 每爬取 N 个武将自动写入磁盘 |
| 输出目录 | `output/` | 结果文件和 checkpoint 存放目录 |

## ❓️FAQ

**爬取过程中被频率限制了怎么办？**

脚本内置 1.0s 基础间隔 + 0~2.0s 随机抖动，以及 5 次自动重试（567 频率限制时指数退避等待）。如仍被限制，可在 `config.yaml` 调大 `request.delay` / `request.delay_jitter`，或用 `--delay` / `--delay-jitter` 命令行参数临时调整。

**中断后如何继续？**

直接重跑同样的命令。`checkpoint.json` 会记录已爬取的武将及其页面 hash，增量模式下自动跳过。


**爬取后还想重新筛选怎么办？**

用 `--query` 模式：`python sgs_bwiki_heros.py --query --faction 魏`。不需要重新请求网络。

## 📝已知问题 / 待改进点（可选）

- [x] 限时玩法（自走棋 / 限时地主 / 喵喵杀）已显式跳过：非常驻玩法区块整体不入库，常驻武将数据集不再被污染
- [ ] SP太史慈「击虚」孤立 section 配对问题：该技能位于自走棋之后的孤立区块，被版本配对逻辑丢弃，需补充 fixture 加固
- [x] 经典形象原画爬取（`--crawl-artwork`）已验证通过：分阶段下载稳定，反爬污染已修复，进度条空列表不再显示
- [x] 体验卡测试武将自动过滤：爬取和输出阶段均将「体验卡测试」标记的武将排除，数据集中不再包含未正式上线武将

## 🤝贡献

欢迎提 Issue 和 PR！

贡献流程：Fork → 创建分支 → 提交代码 → 发起 Pull Request。

## 📋更新日志

### v0.3

- **新增：** 经典形象原画爬取——新增 `--crawl-artwork` 命令行参数与 `config.yaml` 的 `crawl_artwork` 开关（默认关闭）；按 `alt="{name}-经典形象.png"` 精确定位原画图并还原大图 URL，下载到 `output/artworks/{name}-经典形象.png`，在武将数据中记录 `artwork` 相对路径；下载失败不阻断武将入库。测试见 `tests/verify_artwork_crawl.py`
- **修复：** 原画下载反爬污染——全局 SESSION 在 600+ 请求后被标记，返回残缺 HTML 导致原画提取失败；新增 `fetch_page_fresh`（每次新建 Session，不继承 cookie）专供原画下载阶段兜底使用
- **修复：** 原画 URL 规范化 Bug——`_normalize_artwork_src` 解析 URL 后丢失 host，导致 `download_image` 收到相对路径而报 Invalid URL；改为保留完整 URL 格式
- **新增：** 体验卡测试武将自动过滤——爬取阶段检测「体验卡测试」标记并排除 19 个未正式上线武将；输出统计单独展示体验卡跳过数量
- **修复：** 技能 / 台词解析错误——WIKI 新版模板移除 `技能标签` CSS 类导致技能被当成台词丢弃；改为 row 级判定（用 `bikit-audio` 区分技能 / 台词），删除误把含 `/` 的技能描述判为台词的旧分支，新增 `row_container` 兜底。修复影响卫温诸葛直 / 孙霸 / 文钦等武将。测试见 `tests/verify_skill_fix.py`
- **修复：** 跳过限时玩法技能数据——`parse_character_page` 改用"最近前置 h2 配对"策略，对自走棋 / 限时地主 / 喵喵杀等非常驻玩法区块整体跳过；新增 `is_timed_mode_character` 谓词，按 `pack` 字段或武将名括号标记在抓取主循环过滤，避免限时玩法污染常驻武将数据集
- **优化：** 爬取进度输出细化——摘要行从单一「跳过(限时武将) N」拆分为「跳过(已存在)/跳过(限时武将)/跳过(体验卡测试)」三项
- **优化：** 原画下载统计顺序调整为「成功/跳过/失败」，无待处理项目时不再显示空进度条
- **优化：** 检查点数据（page_hashes）统一存入 `characters.json` 的 `meta` 字段，去除独立的 `checkpoint.json` 文件
- **优化：** 武将包映射 `pack_character_map.json` 改为 `--export-pack-map` 可选导出

### v0.2

- **新增：** 请求间隔随机抖动：实际间隔 = `request.delay` + `random.uniform(0, request.delay_jitter)`，默认 `1.0 + 0~2.0` 秒，打破机械节奏，降低被识别概率
- **新增：** 网络参数（delay / delay_jitter / max_retries / timeout）现可通过 `config.yaml` 或命令行参数配置；先前这些字段虽写在配置文件中但未被代码读取，本次一并修复
- **修复：** bwiki 频率限制（HTTP 567）被快速拦截的问题：补全请求头（Referer / Accept / Accept-Language 等），并改用 `requests.Session` 保持会话与 cookie，使请求更接近真实浏览器
- 同步更新 README 配置说明、CLI 参数表与 FAQ

### v0.1

- 首次发布：基于 BeautifulSoup + requests 从 bilibili 三国杀 WIKI 爬取武将结构化数据（技能 / 台词 / 版本 / 称号 / 定位等），支持增量爬取、多版本解析、多参数筛选，输出 JSON

## 🔗 关联项目

- **[sgs-skin-gallery](https://github.com/5244DragonLin/sgs-skin-gallery)** — 基于本项目武将/皮肤数据的可视化画廊，前端浏览与收藏
  - GitHub：https://github.com/5244DragonLin/sgs-skin-gallery
  - Gitee：https://gitee.com/yhl5244/sgs-skin-gallery

- **[sgs_bwiki_skins](https://github.com/5244DragonLin/sgs_bwiki_skins)** — 从 BWIKI 下载皮肤图片和元数据，本项目的皮肤图片数据源
  - GitHub：https://github.com/5244DragonLin/sgs_bwiki_skins
  - Gitee：https://gitee.com/yhl5244/sgs_bwiki_skins

## ☕捐赠

如果这个项目对你有帮助，可以请我喝杯咖啡~

| 支付宝 | 微信 |
|--------|------|
| ![支付宝](./assets/donate_alipay.jpg) | ![微信](./assets/donate_wechat.jpg) |

## ⚠️免责声明

本工具仅供学习交流使用，数据来源为 bilibili 三国杀 WIKI 公开页面。使用者应遵守目标网站的 robots.txt 及相关使用条款。因使用本工具产生的一切后果由使用者自行承担。

## 📃许可证

本项目采用 MIT 许可证。详见 [LICENSE](./LICENSE) 文件。
