# 内战战绩网站 + LCU 自动抓取 — 交接包

- 生成日期：2026-11-05；最近更新：2026-11-06（多维评分：KDA/助攻/治疗/控制/伤害/补刀/经济/视野/目标）
- 当前目录：`D:\PycharmProjects\lol_stats_handoff`
- 说明：本机环境与此前交接环境不同：客户端在 `D:\WeGameApps\英雄联盟（含经典模式）`，Windows 用户为 `Administrator`，回放目录在 `C:\Users\Administrator\Documents\...`。新脚本已改为自动发现路径，旧脚本仍按原环境硬编码。
- 主要交付物：`website\lol_stats.html`（单文件网站）、`scripts\lcu_server.py`（本地同步桥）、`scripts\lcu_sync.py`（离线导出）、`data\lcu_sync.json`（最近 27 场实机数据）
- 已验证能力：通过本机国服客户端 LCU 接口读取最近 101 局，提取 27 场有效 5v5 峡谷内战；网站按钮可自动检测客户端并同步，也可按 gameId 合并导入 JSON，不覆盖已有数据；评分在同局 10 人内按多维指标做百分位，KDA 权重最高，不含胜负。

---

## 1. 项目目标

用户和朋友们经常打 5v5 英雄联盟内战，需要一个网站：

1. 记录每个人的击杀 / 死亡 / 助攻，计算 KDA。
2. 实时添加新对局，自动更新排行榜。
3. 根据水平自动分队，尽量让两边实力接近。
4. 记录胜负，并支持英雄、位置。
5. 只有一个 HTML 文件，别人打开就能看；纯前端，无后端、无构建步骤。
6. 数据保存在本机浏览器；分享时导出“带数据 HTML”快照。
7. 用户希望尽量不手动录入，研究能否通过 API 直接抓战绩。

历史约束（原机器）：**所有文件不要放在 `C:\Users\LTEnj` 下，统一放 `D:\tmp`。**当前机器已不适用：脚本只写项目 `data\` 或 `--output` 指定路径，不写用户主目录。

---

## 2. 当前状态

| 模块 | 状态 | 说明 |
|---|---|---|
| 单文件网站 | 已完成并测试 | 排行榜、录入、编辑/删除、自动分队、玩家管理、导入/导出；新增「检测并同步客户端」与「导入 JSON 文件」 |
| 官方 Riot API 方案 | 已排除 | 国服不在覆盖范围；自定义对局对普通 key 返回 404 |
| LCU 本地接口 | 已验证（2026-11-05 实机） | 能读当前账号、最近 101 局、单局 10 人详情、英雄名称 |
| 自定义对局发现 | **已解决** | 最近 101 局**包含自定义**（本次 51 条）；`.rofl` 仍作为兜底 |
| 历史数据回填 | 已生成 | `data\lcu_sync.json`：27 场有效 5v5 峡谷，日期 2026-08-13 ~ 2026-11-06，13 名玩家，含评分指标 |
| 自动同步到网站 | **已完成** | 网站按钮 → 本地桥 `scripts\lcu_server.py` → 自动检测客户端、拉取全部 5v5 峡谷自定义对局并合并；JSON 文件导入保留为兜底 |
| 多维评分 | **已完成（2026-11-06）** | 每局 10 人内做百分位，KDA 权重最高，兼顾助攻/治疗/控制/伤害/补刀/经济/视野/目标；不含胜负 |

2026-11-06 新增：

- `scripts/lcu_sync.py` 每人多导出 13 个指标（经济、补刀、野怪、视野、真眼、排眼、伤害、承伤、减伤、治疗、控制、目标伤害、推塔伤害），符号为 LCU 原始字段名。
- 网站评分改为多维：影响力（KDA 权重最高）4 : 发育 3 : 视野 2 : 目标 1，单局 = 50% 加权平均 + 50% 最强三项；胜负不参与；总评直接取各局平均，不做收缩。
- 旧数据/手录对局没有指标时自动回退到原「胜率 + KDA」公式，新旧数据可混用。
- 排名、概览「最高评分」、自动分队均使用新评分；对局卡片显示每人单局评分。
- 新增测试：`tests\rating_smoke.py`（评分逻辑、平均、回退、渲染）。

上一轮（2026-11-05）新增：

- `scripts/lcu_sync.py`：自动发现客户端/回放/凭证，导出合并导入格式。
- `scripts/lcu_server.py`：只监听 `127.0.0.1:8765` 的本地桥，提供 `/api/status` 与 `/api/sync`，并可直接访问网站。
- 网站「数据」页新增「检测并同步客户端」：客户端未启动/未登录时给出明确提示；启动后自动拉取全部 5v5 峡谷自定义对局并合并。
- `scripts/start_lcu_server.py` + `scripts/install_protocol.py`：未启动本地桥时，点击同步按钮可通过 `lolsync://` 自动拉起服务；协议只需注册一次。
- 修复地图模式误判：只接受 `mapId=11` + `gameMode=CLASSIC`；海克斯大乱斗（`mapId=12` / `KIWI`）、练习模式、人数不足 10 的对局全部跳过。已从数据中移除 4 场海克斯大乱斗。
- 网站仍保留「导入 JSON 文件」作为兜底：按 `m_lcu_<gameId>` 去重，按召唤师名匹配/创建玩家，只追加、不覆盖。
- 修复真实 bug：LCU `teams[].win` 返回字符串 `"Win"/"Fail"`，按布尔判断会把 `"Fail"` 也当胜利。
- 新增测试：`tests\lcu_sync_mapping_test.py`（映射单测）、`tests\merge_import_smoke.py`（合并测试）、`tests\auto_sync_smoke.py`（自动同步交互测试）。

网站此前 QA 已做过：10 名玩家、录入对局、KDA 排名、编辑、自动分队、点击换人、导出 HTML 在新浏览器打开、刷新持久化、桌面/移动端截图检查。测试数据在临时 Chrome profile 中，已清理；**当前 `lol_stats.html` 的 seed 是 `null`**（新数据请用 merge 导入，不要改 seed）。

---

## 3. 目录结构

```text
D:\PycharmProjects\lol_stats_handoff\
├─ README.md                         # 先读这个
├─ docs\
│  ├─ 01_product.md                  # 产品需求、功能、数据模型、公式、测试情况
│  ├─ 02_lcu_integration.md          # LCU 认证、接口、抓取方案、限制、安全
│  └─ 03_next_steps.md               # 本轮进展、后续建议、测试计划、待确认问题
├─ website\
│  ├─ lol_stats.html                 # 单文件网站（含自动同步 + 合并导入 + 多维评分）
│  ├─ lol_stats_snapshot_20261106.html # 已内嵌 27 场数据（含多维评分）的可查看快照
│  └─ lol_stats_snapshot_20261105.html # 旧快照（22 场，旧版评分逻辑）
├─ scripts\
│  ├─ README.md                      # 脚本路径/运行说明
│  ├─ requirements.txt
│  ├─ lcu_server.py                  # ★ 新增：本地同步桥（127.0.0.1:8765）
│  ├─ lcu_sync.py                    # LCU -> 合并导入 JSON（自动发现路径）
│  ├─ lcu_extract_customs.py         # 旧原型：回放 gameId + LCU -> 对局数组
│  ├─ lcu_fetch.py                   # 旧原型：当前账号 + 最近战绩列表
│  ├─ lcu_verify.py                  # 旧原型：分页验证、单局详情、回放扫描
│  ├─ lcu_custom_check.py            # 旧原型：备选列表接口 + 自定义详情验证
│  └─ research\
│     ├─ lcu_probe.py                # 早期探测（读进程命令行，非管理员会失败）
│     └─ lcu_auth_probe.py           # 端口/token 探测（Riot Client token 对 LCU 无效）
├─ tests\
│  ├─ lcu_sync_mapping_test.py       # 胜负/5v5/位置映射单测
│  ├─ merge_import_smoke.py          # headless Chrome 合并导入测试
│  └─ auto_sync_smoke.py             # headless Chrome 自动同步交互测试
└─ data\
   ├─ README.md                      # 数据文件说明
   ├─ lcu_sync.json                  # ★ 新增：22 场 5v5 峡谷内战，合并导入格式（无 PUUID/token）
   ├─ lcu_custom_games.json          # 旧样例：3 场 5v5 内战，含 PUUID
   ├─ lcu_custom_games_summary.txt   # 旧样例可读摘要
   ├─ lcu_fetch_result.txt           # 旧环境最近 101 局列表（历史快照）
   ├─ lcu_verify_result.txt          # 旧环境详情/分页/回放扫描结果
   ├─ lcu_custom_check_result.txt    # 旧环境自定义详情 + 备选接口结果
   ├─ lcu_list_probe_result.txt      # 旧环境分页/日期过滤/好友列表探测
   ├─ lcu_eog_result.txt             # 旧环境对局结束/回放接口探测
   └─ lcu_swagger_result.txt         # 旧环境 Swagger 探测（不可用）
```

---

## 4. 快速开始

### 网站

直接用浏览器打开：

```text
D:\PycharmProjects\lol_stats_handoff\website\lol_stats.html
```

- 数据保存在浏览器 `localStorage`，key 为 `lol-custom-stats-v1`。
- “数据”页可以导出 JSON、导入 JSON、**检测并同步客户端**、**导入 JSON 文件（合并）**、导出带数据 HTML、清空数据。
- 导入 JSON 会**替换**当前数据；自动同步/合并导入只按 gameId 追新，不覆盖。
- 导出 HTML 会生成一个内嵌数据的新文件，适合发群里。
- 同一浏览器多个标签页会通过 `storage` 事件自动同步。
- 想直接看当前 27 场数据：打开 `website\lol_stats_snapshot_20261106.html`。

**交接前请确认**：如果当前浏览器里已经录入了真实战绩，请先在网站“数据”页导出 JSON（或带数据 HTML），放到 `data\` 下。否则交接包里只有 3 场 LCU 样例数据，网站 seed 为空，下一个 agent 打开看到的是空站点。

### 自动同步（推荐）

前提：国服客户端已启动并登录。首次使用只需注册一次 `lolsync://` 协议：

```bash
D:\Soft\Coding\Conda\Conda\python.exe D:\PycharmProjects\lol_stats_handoff\scripts\install_protocol.py
```

然后直接打开 `website\lol_stats.html`，进入「数据」页 →「检测并同步客户端」：

1. 本地桥未启动：按钮会尝试通过 `lolsync://` 自动拉起（浏览器若询问是否打开“LoL Sync”，选择允许）；也可以点旁边的「启动本地服务」。
2. 未启动客户端：提示先启动并登录，不会改数据。
3. 客户端已启动但未登录：提示确认登录。
4. 检测成功：自动拉取全部可用的 5v5 峡谷自定义对局，按 gameId 合并并刷新页面。
5. 海克斯大乱斗（`mapId=12` / `gameMode=KIWI`）、练习模式、人数不足 10 的对局会被跳过。

也可以手动常驻启动本地桥（可选）：

```bash
D:\Soft\Coding\Conda\Conda\python.exe D:\PycharmProjects\lol_stats_handoff\scripts\lcu_server.py
```

用 `http://127.0.0.1:8765/` 打开时，数据存在该地址的 localStorage，与 `file://` 打开的是两套；建议固定用一种方式。

### 离线导出 / 文件导入（兜底）

```bash
D:\Soft\Coding\Conda\Conda\python.exe D:\PycharmProjects\lol_stats_handoff\scripts\lcu_sync.py
```

默认输出 `data\lcu_sync.json`。然后：

1. 打开网站 →「数据」页 →「导入 JSON 文件」；
2. 选择 `data\lcu_sync.json`；
3. 页面会显示新增多少场、新增哪些玩家、跳过多少场。

离线导出也可用于备份，或在不启动本地桥时使用。本机 Python：`D:\Soft\Coding\Conda\Conda\python.exe`（3.11.7，已装 requests 2.31.0）。

常用参数：

```bash
# 只看结果不写文件
python scripts\lcu_sync.py --dry-run
# 只导出某天之后
python scripts\lcu_sync.py --since 2026-10-01
# 不扫回放
python scripts\lcu_sync.py --no-rofl
# 导入客户端位置（可能不准，默认关闭）
python scripts\lcu_sync.py --include-positions
```

旧的 `lcu_extract_customs.py` / `lcu_fetch.py` 等仍是原环境原型，里面硬编码了 `D:\tmp`、`C:\Users\LTEnj`；日常同步请用 `lcu_sync.py`，详见 `scripts\README.md`。

---

## 5. LCU 验证结果

### 能拿到（2026-11-05 实机）

- 当前账号：`致风平浪静的初恋`
- 最近 101 局：**包含 51 条自定义对局摘要**（此前文档的判断“没有自定义”已被推翻）
- 单局详情：`GET /lol-match-history/v1/games/{gameId}` 返回 10 人完整数据
- 自定义对局：`gameType=CUSTOM_GAME`，峡谷常见 `queueId=3110/3130/3100`、`mapId=11`、`gameMode=CLASSIC`；queue 3270 是海克斯大乱斗（`mapId=12`、`gameMode=KIWI`），不是重开局，已过滤
- 英雄名称：`GET /lol-game-data/assets/v1/champion-summary.json`

### 本轮提取结果

`data\lcu_sync.json`（无 PUUID、无 token）：

| 项 | 值 |
|---|---|
| 有效 5v5 峡谷 | 27 场（仅 `mapId=11` + `gameMode=CLASSIC`） |
| 日期范围 | 2026-08-13 ~ 2026-11-06 |
| 玩家 | 13 名（按召唤师名去重） |
| 胜负 | 红 12 / 蓝 15 |
| 其它候选 | 最近 51 条候选中：非峡谷/非经典 10、非 5v5 19（人数不足或红蓝不均）；旧回放 404 另计 |

2026-11-06 起同步输出每人 13 个评分指标（经济、补刀、视野、伤害、承伤、治疗、控制、目标），网站据此计算多维评分；旧的 22 场版本备份在 `data\lcu_sync_22_backup.json`。

旧的 3 场样例仍在 `data\lcu_custom_games.json`（2026-07-31 / 02-08 / 01-30，含 PUUID），对应 gameId 现在可能已经 404；网站合并导入同时接受这种“数组”格式，需要回填时可手动导入。

### 关键限制

1. 战绩列表只返回最近 **101 局**，`begIndex/endIndex` 无效，也没有日期过滤参数；超过 101 局仍需 `.rofl` 兜底。
2. `.rofl` 会过期：本次 59 个回放里 46 个 gameId 已 404；回放保存关闭时无法兜底。
3. 自定义对局的位置字段（lane/role）不可靠，可能出现多个“打野”；`lcu_sync.py` 默认不导入位置。
4. **胜负字段坑**：`teams[].win` 是字符串 `"Win"/"Fail"`，不是布尔；按布尔判断会把 `"Fail"` 当成胜利。`lcu_sync.py` 已做字符串归一化，并有单测。
5. 客户端必须运行；token 在客户端重启后会变化；token 存在客户端日志里，属于敏感信息。
6. LCU 是未公开接口，国服客户端版本更新后可能变化。

### 官方 API 为什么不行

- 国服由腾讯运营，Riot 官方 API 的 routing 没有中国大陆。
- 即使在国际服，Match-V5 对自定义对局返回 404。
- 自定义房间战绩只对开通 RSO 的客户端开放，普通开发 key / 生产 key 都不行。

---

## 6. 下一步建议

**方案 A：合并导入（已完成）**

1. ✅ `lcu_sync.py`：读取 LCU → 最近 101 局 + `.rofl` 兜底 → 拉详情 → 校验 10 人/5v5 → 输出 `{source, fetchedAt, games: [...]}`。
2. ✅ 网站“数据”页支持合并导入：按 `m_lcu_<gameId>` 去重，按召唤师名匹配/创建玩家，**不替换现有 localStorage 数据**。
3. ✅ 已验证：最近 101 局包含自定义；列表就是可靠的发现方式，`.rofl` 只作兜底。

**方案 B：本地服务自动同步（已完成）**

1. ✅ `lcu_server.py` 只监听 `127.0.0.1:8765`，提供 `/api/status`、`/api/sync`，并直接托管网站。
2. ✅ 网站按钮先检测客户端进程/登录会话，再一次性拉取全部可用 5v5 峡谷自定义对局并合并。
3. ✅ 实测：真实客户端下约 10 秒拉回 22 场；从 `file://` 页面直接请求本地桥也已验证通过。
4. ✅ 安全：只绑 localhost；CORS 仅允许 `null`（file://）和 localhost 来源；同步 POST 需要 `X-LCU-Sync` 头；不返回、不打印 token。

日常流程：打完 → 启动 `lcu_server.py`（可常驻）→ 网站「数据」→「检测并同步客户端」。

> 升级 `lcu_sync.py` / `lcu_server.py` 后要**重启常驻的桥**，旧进程不会加载新代码。早期桥返回的对局没有评分字段，这些对局会按旧公式计分；重启后点一次同步即可按 gameId 自动补上指标，不需要清空数据。页面在收到无指标的数据时也会给出提示。

**后续可选**

- EOG watcher：对局结束阶段自动抓取，适合关闭回放保存的情况。
- PUUID 支持：解决改名/同名；需要升 `schemaVersion` 并写迁移。
- 一键 `.bat`：双击同时启动本地桥并打开网站。
- 开机自启/托盘：让本地桥常驻。
- 自动化测试补强：用 CDP `DOM.setFileInputFiles` 覆盖真实文件选择按钮。

方案 C（直接改 HTML 里的 seed）仍不推荐：新 seed 会覆盖浏览器 localStorage 里更新的数据，容易丢数据。

---

## 7. 安全与约束

- 本交接包**没有写入 LCU token**；`lcu_sync.py` / `lcu_server.py` 都不会打印/保存 token。凭证来源是 `D:\WeGameApps\英雄联盟（含经典模式）\LeagueClient\*LeagueClientUx.log`。
- 不要复制或分享 `*LeagueClientUx.log`，里面含认证 token。
- LCU 的 `verify=False` 只用于 `127.0.0.1` 的自签名证书；不要对外部 URL 关闭 TLS 校验。
- 本地桥只绑定 `127.0.0.1`，不监听局域网/公网；CORS 只放行 `null`（file://）和 localhost 来源；`/api/sync` 额外要求 `X-LCU-Sync: 1`。
- `data\lcu_sync.json` 不含 PUUID/token，但含 22 场真实召唤师名；分享前自行判断。
- `data\lcu_custom_games.json`（旧样例）含 PUUID；分享前可删除 `puuid` 字段，网站不需要它。
- 脚本只读回放目录、只写 `data\` 或 `--output` 指定路径，不写入用户主目录。旧的 `C:\Users\LTEnj` 约束已不适用。
- 网站保持单文件、纯前端、无外部依赖；本地桥是可选的外部进程，不改变网页本身的单文件属性。

---

## 8. 文档索引

- 产品功能、数据模型、公式、已做测试：`docs\01_product.md`
- LCU 认证、接口细节、抓取方案、限制：`docs\02_lcu_integration.md`
- 本轮进展、后续建议、测试计划、待确认问题：`docs\03_next_steps.md`
- 脚本运行与路径：`scripts\README.md`
- 数据字段：`data\README.md`
- 回归测试：
  - 映射单测：`python -m unittest tests/lcu_sync_mapping_test.py -v`
  - 合并冒烟（含真实同步文件）：`python tests/merge_import_smoke.py --sync-file data/lcu_sync.json`
  - 自动同步交互：`python tests/auto_sync_smoke.py`
  - 本地桥接口：启动 `scripts/lcu_server.py` 后访问 `/api/health`、`/api/status`
