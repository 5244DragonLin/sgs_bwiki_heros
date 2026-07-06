# sgs_bwiki_heros

基于 BeautifulSoup + requests，从 bilibili 三国杀 WIKI 爬取武将信息的 Python 工具。支持增量爬取、多版本技能台词解析、多参数组合筛选，输出 JSON 格式。

## 为什么需要这个工具？

- 三国杀武将数据分散在 WIKI 各页面，手动查阅效率极低
- 经典、界限突破、国战三种版本的技能和台词各不相同，需要分别收集
- 武将数量庞大（667+），增量爬取、断点续爬等机制是刚需

**sgs_bwiki_heros 解决这些问题**：一个命令就能批量获取全部武将的结构化数据，支持按势力/武将包灵活筛选。

## ⭐亮点

- **增量爬取**：checkpoint 机制记录已爬武将和页面 hash，再次运行只爬新武将
- **多版本覆盖**：自动区分经典/界限突破/国战版本，分别提取技能和台词
- **技能台词分离**：每条台词绑定所属技能，结构清晰
- **珠联璧合**：国战武将的专属配对关系完整保留
- **自动保存**：每 N 个武将自动写盘，中断不丢数据
- **JSON 输出**：完整结构化 JSON + 武将包映射文件
- **武将包映射**：自动生成 `pack_character_map.json`，按网站顺序列出所有武将包，包含大类和子包图标路径
- **多参数筛选**：按武将包、势力、数量、版本自由组合查询
- **仅查询模式**：爬完后的数据可离线筛选，无需重新请求网络

## 📸效果预览

### CLI 运行

```text
[*] 正在获取武将列表...
[+] 共发现 666 个武将
[+] 势力分布: {'魏': 20, '蜀': 22, '吴': 20, '群': 25, '神': 38}
[+] 武将包数量: 91

[1/1] 正在爬取: SP关羽...
  [OK] SP关羽 - 势力:魏 包:荟萃-千里单骑 版本:['classic']
[+] 检查点已保存 (1 个武将)
[+] JSON 已保存: output/characters.json (1 个武将)
```

### 输出目录结构

```text
output/
├── characters.json          # 全部武将（JSON）
├── pack_character_map.json  # 武将包与武将的映射（含图标路径）
└── checkpoint.json          # 爬取进度断点
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
| `request.delay` | 请求间隔（秒） | `2.0` |
| `request.max_retries` | 最大重试次数 | `5` |
| `output.dir` | 输出目录 | `output/` |
| `output.save_every_n` | 每 N 个武将自动保存 | `20` |
| `filters.pack` | 武将包筛选 | 空（全部） |
| `filters.faction` | 势力筛选 | 空（全部） |
| `filters.limit` | 数量限制（0=不限制） | `0` |

## ⌨️CLI 模式

```
python sgs_bwiki_heros.py [-o OUTPUT] [--pack PACK] [--faction FACTION]
                      [--limit LIMIT] [--auto-save N] [--no-skip] [--query]
                      [--version VER]
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
├── output/               # 爬取结果
│   ├── characters.json
│   └── pack_character_map.json  # 武将包与武将的映射（含图标路径）
```

## 配置说明

爬虫内置的默认参数（也可通过 `config.example.yaml` 统一管理，详见上方"### 4. 配置文件"）：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| 请求间隔 | 2.0s | 每次 HTTP 请求后的等待时间（含随机抖动） |
| 最大重试 | 5 次 | 单个页面请求失败后的重试次数（567 频率限制最多等 25s） |
| 自动保存 | 每 20 个 | 每爬取 N 个武将自动写入磁盘 |
| 输出目录 | `output/` | 结果文件和 checkpoint 存放目录 |

## ❓️FAQ

**爬取过程中被频率限制了怎么办？**

脚本内置 2.0s 请求间隔和 5 次自动重试。如果仍被限制，可增大 `REQUEST_DELAY` 变量（脚本顶部）。

**中断后如何继续？**

直接重跑同样的命令。`checkpoint.json` 会记录已爬取的武将及其页面 hash，增量模式下自动跳过。


**爬取后还想重新筛选怎么办？**

用 `--query` 模式：`python sgs_bwiki_heros.py --query --faction 魏`。不需要重新请求网络。

## 🤝贡献

欢迎提 Issue 和 PR！

### 已知问题 / 待改进点

- [ ] 自走棋模式技能暂未爬取（作为单独版本处理）

贡献流程：Fork → 创建分支 → 提交代码 → 发起 Pull Request。

## 📋更新日志

### v1.0

- 首次发布

## ⚠️免责声明

本工具仅供学习交流使用，数据来源为 bilibili 三国杀 WIKI 公开页面。使用者应遵守目标网站的 robots.txt 及相关使用条款。因使用本工具产生的一切后果由使用者自行承担。

## 📃许可证

本项目采用 MIT 许可证。详见 [LICENSE](./LICENSE) 文件。


