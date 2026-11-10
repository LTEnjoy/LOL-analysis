# 03 下一步实现建议与测试计划

## 0. 最近进展（2026-11-06）：多维评分

12. ✅ `lcu_sync.py` 每人导出 13 项评分指标（经济/补刀/野怪/视野/真眼/排眼/伤害/承伤/减伤/治疗/控制/目标伤害/推塔伤害），单测覆盖透传、缺字段省略、负数与非法值截断。
13. ✅ 网站评分改为同局 10 人百分位：影响力 4（KDA 最高权重、参团、助攻、治疗、控制、伤害、推塔、目标）、发育 3、视野 2、目标 1；单局 = 50% 加权 + 50% 最强三项；**胜负不参与**；总评取各局平均，不做收缩。
14. ✅ 缺指标的手录/旧对局回退旧「胜率 + KDA」公式；排名、概览、分队、对局卡片统一用新评分。
15. ✅ 离线校准：调整前后打野/常规/辅助型均分差从 15~25 分降到约 4 分；分数与胜负相关系数 ≈ 0.34（旧公式 ≈ 0.8）。
16. ✅ 重新同步：27 场（新增 11-05~11-06 的 5 场），备份旧数据为 `data/lcu_sync_22_backup.json`。
17. ✅ 新增 `tests/rating_smoke.py`；`lcu_sync_mapping_test.py` 15 项、`merge_import_smoke.py`（合成 + 真实 27 场）、`auto_sync_smoke.py` 全部通过。

已知取舍：辅助型（低补刀高视野）单局仍略低于常规打法；样本仅 27 局，权重如需调整改 `RATING_DIMS` 与 `RATING_STAT_FIELDS` 对应逻辑即可。

## 0.1 上轮进展（2026-11-05）

已完成：

1. ✅ 实测确认最近 101 局**包含自定义**（51 条）。
2. ✅ 网站新增合并入口（现为「导入 JSON 文件」），按 `m_lcu_<gameId>` 去重、按名字匹配/创建玩家、不覆盖现有数据。
3. ✅ 新增 `scripts/lcu_sync.py`，自动发现客户端/回放/凭证，输出合并格式。
4. ✅ 端到端：实机导出 22 场 → 合并导入 → 二次导入全去重 → 刷新后仍在。
5. ✅ 修复 `teams[].win` 字符串（`"Win"/"Fail"`）误判，新增映射单测。
6. ✅ 新增 headless Chrome 合并测试（合成数据 + 真实 22 场）。
7. ✅ 新增 `scripts/lcu_server.py`（仅 127.0.0.1:8765）与网站「检测并同步客户端」按钮：自动检测客户端进程/登录状态，直接拉取全部 5v5 峡谷自定义对局并合并。
8. ✅ 实测自动同步：真实客户端约 10 秒返回 22 场；file:// 页面跨源请求、断网/未启动/未登录/服务报错提示均已覆盖。
9. ✅ 新增 `scripts/start_lcu_server.py` / `install_protocol.py`：本地桥未运行时，点击按钮可通过 `lolsync://` 自动拉起，无需手动开终端。
10. ✅ 修复地图模式误判：只接受 `mapId=11` + `gameMode=CLASSIC`；海克斯大乱斗（`mapId=12`/`KIWI`）与练习模式全部跳过。
11. ✅ 清理旧数据：从 26 场中移除 4 场海克斯大乱斗，`data/lcu_sync.json` 与快照更新为 22 场。

未做：

- 自动触发（对局结束后无需点按钮）。
- PUUID 支持（改名/同名仍按名字匹配）。
- EOG watcher。
- 真实文件选择按钮的 CDP 自动化（核心合并函数已测，文件选择回调未自动点击）。

---

## 1. 原优先级（已完成部分）

最高优先级：**把“LCU 抓取”接到网站上，但不破坏现有数据和单文件分享能力。**

1. ✅ 用真实 5v5 自定义验证“最近 101 局列表是否包含自定义”。
2. ✅ 给网站加“合并导入”能力（按 gameId 去重，保留现有数据）。
3. ✅ 写 `lcu_sync.py`，输出待合并 JSON。
4. ✅ 端到端测试：导出 → 合并导入 → 排行榜更新。
5. ✅ 本地服务（方案 B）：按钮检测客户端并自动同步。

## 2. 第一步：验证自定义对局发现（✅ 已完成）

2026-11-05 实测账号 `致风平浪静的初恋`：

```bash
D:\Soft\Coding\Conda\Conda\python.exe scripts\lcu_sync.py --dry-run
```

结果：

- 最近 101 局里有 **51 条 `CUSTOM_GAME` 摘要**，列表确实包含自定义。
- 摘要人数不参与判断：脚本对所有候选统一拉详情。
- 最近 51 条候选中，最终 22 场有效 5v5 峡谷；非峡谷/非经典 10、非 5v5 19。
- 2026-11-05 修正：queue 3270 / `mapId=12` / `gameMode=KIWI` 是海克斯大乱斗，不是重开局；旧数据里的 4 场已移除。

列表窗口仍是最近 101 局；超过窗口的自定义只能靠 `.rofl`（会过期）或 EOG watcher。结论已同步到 `docs/02_lcu_integration.md` 第 10 节。

## 3. 第二步：网站“合并导入”（✅ 已完成）

实现位置：`website/lol_stats.html`

- 数据页按钮 `#btn-auto-sync`（自动同步）、`#btn-merge-json`（文件兜底）+ 隐藏文件框 `#merge-file` + 状态区 `#merge-status`。
- 核心函数 `mergeLcuGames(payload)`、`autoSyncClient()`、`syncApi()`、`showMergeOutcome()`。
- 文件回调 `mergeJsonFile(event)`。
- `buildExportHtml()` 会清空合并状态，导出快照不残留提示。

### 为什么不直接用现有导入

现有 `importJson` 是**替换**语义，会覆盖当前 localStorage 数据。LCU 同步需要追加/合并，所以新增独立功能，保留原导入行为。

### UI（已实现）

在“数据”页新增一个“从客户端同步”卡片：

- 主按钮：`检测并同步客户端`（`#btn-auto-sync`）
- 兜底按钮：`导入 JSON 文件`（`#btn-merge-json` + 隐藏 `#merge-file`）
- 状态提示：检测中、未启动、未登录、服务未运行、同步场次、新增玩家名单、跳过重复/无效（最多列 5 条原因）
- Toast 提示结果
- 页面底部提示本地服务命令 `python scripts/lcu_server.py`

### 数据格式

`lcu_sync.py` 输出：

```json
{
  "source": "lcu",
  "fetchedAt": "2026-11-05T08:00:00.000Z",
  "games": [
    {
      "gameId": 11155247950,
      "date": "2026-07-31",
      "winner": "red",
      "participants": [
        {
          "name": "素来喜望花似锦",
          "team": "red",
          "kills": 22,
          "deaths": 3,
          "assists": 6,
          "champion": "法外狂徒",
          "position": ""
        }
      ]
    }
  ]
}
```

### 合并规则（实际实现）

1. 输入接受 `{games: [...]}` 或裸数组；没有 `games` 数组时抛错。
2. 对局 ID：`m_lcu_<gameId>`，`gameId` 必须是 1~20 位数字。
3. 已存在相同 ID（现有数据或同一文件内）→ 计入重复并跳过。
4. 玩家匹配：名字 `trim` 后忽略大小写匹配现有玩家；找不到时**自动创建** `active: true` 玩家，状态区列出新增名字。
5. 每场必须 10 人、红 5 蓝 5、名字不重复、胜方有效（`winner` 或 5 个 `win` 标记一致），否则整场跳过并给出原因。
6. 字段归一化：`date` 必须 `YYYY-MM-DD`（否则从 `createdAt` 取，再否则今天）；`kills/deaths/assists` 截断为非负整数；`champion` 最长 20；`position` 只接受合法值，否则空。
7. 先构造完整结果；至少一场有效才一次性提交（追加 `players` / `matches`、`saveState()`）；失败/全无效不写状态。
8. 现有玩家和对局不改；不改变 `importJson` 的替换语义。

### 代码落点（实际）

- `extractMergeGames`、`mergeLcuGames`、`setMergeStatus`、`mergeJsonFile`：位于导入导出区。
- 事件绑定：`bindEvents()` 中绑定 `#btn-merge-json` / `#merge-file`。
- 导出：`buildExportHtml()` 清空 `#merge-status`。
- 现有 `importJson` 未改动。

### 兼容性

- `schemaVersion` 仍为 1，localStorage key 不变。
- 使用确定性 match id `m_lcu_<gameId>`，未新增字段。
- 如果后续加 PUUID，再升 `schemaVersion` 并写迁移逻辑。

## 4. 第三步：`lcu_sync.py`（✅ 已完成）

已实现：`scripts/lcu_sync.py`。与旧原型相比：

- 不再硬编码 `D:\tmp` / `C:\Users\LTEnj`；自动发现客户端目录、回放目录、Python 无需改常量。
- 先试 `lockfile`，再解析最新 `LeagueClientUx.log`。
- 输出默认 `data/lcu_sync.json`（项目内，便于直接导入）。
- 修复 `teams[].win` 为 `"Win"/"Fail"` 字符串的问题。
- 只保留 `mapId=11` + `gameMode=CLASSIC` 的峡谷对局；跳过海克斯大乱斗、练习模式、人数不足 10、无胜方和旧 404。
- 输出不含 PUUID（只保留召唤师名、KDA、英雄、队伍）。

### 实际流程

1. `find_install()` / `find_replay_root()` 自动定位；支持 `--install` / `--replays`。
2. `find_session()` 发现可用端口/凭证，打印账号与端口（不打印 token）。
3. 拉当前 summoner / puuid。
4. 拉最近 101 局，筛 `CUSTOM_GAME` / `queueId=3110`。
5. 扫描 `.rofl` 补充 gameId（默认开启，`--no-rofl` 关闭）。
6. 逐个拉 `/lol-match-history/v1/games/{gameId}`，校验 10 人、红蓝各 5、胜方存在。
7. 英雄 ID → 中文名；位置默认空，`--include-positions` 才映射 lane/role。
8. 按日期升序输出 `{source, fetchedAt, summoner, count, games}`。
9. 控制台打印统计和每场 10 人 KDA；失败单局不中断。

### 实际参数

```text
--output PATH        输出路径，默认 data/lcu_sync.json
--since YYYY-MM-DD   只输出该日期及之后
--no-rofl            不扫描回放文件
--dry-run            只打印，不写文件
--include-positions  导入客户端 lane/role（默认关闭）
--install PATH       指定客户端目录
--replays PATH       指定回放目录
```

（未实现 `--all`；默认就是输出所有发现的对局，靠 gameId 去重。）

### 去重

- 以 `gameId` 为唯一键。
- 输出前按 `createdAt` 倒序或正序排序。
- 已导入的 gameId 由网站端按 `m_lcu_<gameId>` 跳过；脚本端也可以读一个本地 `data\lcu_synced_ids.json` 做二次去重，但不是必须（尚未实现）。

### 错误处理

- 客户端没启动 / 没登录：提示“请先启动并登录国服客户端”。
- 日志找不到 token：提示检查客户端日志路径/权限。
- 端口认证失败：重新扫描端口；不要打印 token。
- 单局 404：跳过并记录，不中断整批。
- 不是 10 人 / 不是 5v5 / 非峡谷（KIWI、练习模式）：跳过并记录。

## 5. 第四步：自动化选项

### 选项 1：本地服务 + 按钮（✅ 当前采用）

```bash
D:\Soft\Coding\Conda\Conda\python.exe scripts/lcu_server.py
```

- 首次运行一次 `scripts/install_protocol.py` 注册 `lolsync://`；之后按钮可自动拉起 `start_lcu_server.py`。
- 打开 `http://127.0.0.1:8765/`，或直接打开 `website/lol_stats.html`。
- 网站「数据」→「检测并同步客户端」。
- 本地桥未运行时先尝试自动拉起；若浏览器拦截，页面显示「启动本地服务」按钮。
- 服务检测 `LeagueClientUx.exe` 进程和登录会话；未启动/未登录会直接提示。
- 检测通过后执行一次全量采集（最近 101 局 + `.rofl` 兜底），返回合并格式。
- 只绑 localhost；CORS 仅 file:// / localhost；`/api/sync` 要求 `X-LCU-Sync: 1`；不输出 token。
- 实测：真实客户端下 22 场约 10 秒；file:// 页面直接请求通过。

优点：一键、可常驻、无需生成/选择文件。  
缺点：多一个本地进程；目前仍需用户点按钮。

### 选项 2：离线导出（兜底，保留）

```bash
D:\Soft\Coding\Conda\Conda\python.exe scripts/lcu_sync.py
```

然后网站「数据」→「导入 JSON 文件」→ 选择 `data/lcu_sync.json`。适合不想开服务或需要备份时。

### 选项 3：自动触发（未做）

- 常驻服务监听 LCU 阶段，对局结束后自动同步。
- 需要处理客户端重启、重复触发、网页未打开时的缓存/通知。
- EOG watcher 仍需先验证自定义对局的数据可用性。

### 选项 4：文件监听（未做）

- 监听 `.rofl` 目录或 `lcu_sync.json` 变化，自动生成合并文件。
- 仍需用户点导入，或者配合本地服务。

## 6. 测试计划

### 端到端（2026-11-05 已执行）

实测：当前客户端导出 **22 场**（13 名玩家，仅 5v5 峡谷），headless Chrome 合并结果：

- ✅ 22 场全部新增，0 跳过；
- ✅ 二次导入 `added=0`、`duplicates=22`；
- ✅ 刷新/重新 `loadState()` 后 22 场仍在；
- ✅ 所有对局 10 人、玩家引用可解析、统计可计算；
- ✅ 导出 HTML 种子含合并数据，合并状态已清空；
- ✅ 导出 JSON 保留全部对局。

自动同步（2026-11-05 已执行）：

- ✅ 本地桥 `/api/status`：真实客户端返回 `clientRunning=true`、`loggedIn=true`；
- ✅ 本地桥 `/api/sync`：约 10 秒返回 22 场/13 名玩家，结构校验通过；
- ✅ file:// 页面直接请求本地桥：`status=true,true`、`sync=true,22`（CORS 实测通过）；
- ✅ headless Chrome mock 测试：成功、重复、未启动、未登录、断网、自动拉起、拉起失败恢复、服务报错、0 场；
- ✅ 同步后按钮恢复可点，排行榜/统计随 `saveState()` 刷新。

测试命令：

```bash
python -m unittest tests.lcu_sync_mapping_test.py -v
python tests/merge_import_smoke.py
python tests/merge_import_smoke.py --sync-file data/lcu_sync.json
python tests/auto_sync_smoke.py
```

未自动化：真实文件选择框点击/`DOM.setFileInputFiles`；核心 `mergeLcuGames()`、自动同步与文件回调逻辑已分别覆盖。

### 原始测试计划（保留备查）

1. 启动并登录国服客户端。
2. 打一场 5v5 自定义（10 名真实玩家）。
3. 运行 `lcu_sync.py`。
4. 确认输出 JSON 包含该局，10 人、5v5、KDA/英雄/胜负正确。
5. 网站“数据”页点“合并导入”。
6. 确认：
   - 新对局出现在历史里。
   - 排行榜场次/KDA/胜率/评分更新。
   - 已有对局和玩家没有被覆盖。
   - 刷新页面后数据仍在。
   - 再次导入同一文件不会重复。
7. 导出带数据 HTML，在全新浏览器 profile 打开，确认数据完整。
8. 多标签页同时打开，确认 `storage` 同步。

### 边界情况

- 自定义对局不足 10 人 / 不是 5v5：应跳过并提示。
- 海克斯大乱斗（`mapId=12`/`KIWI`）/ 练习模式：不是峡谷，应跳过。
- 玩家名字包含特殊字符 / 前后空格：匹配前 trim。
- 同名玩家：当前无法区分；记录为已知限制。
- 玩家改名：PUUID 方案未实现；按名字会创建新玩家。
- 客户端重启：token/端口变化后脚本仍能重新发现。
- 回放保存关闭：列表仍应能发现最近自定义；否则需要 EOG watcher。
- 最近 101 局超过窗口：旧对局只能靠 `.rofl` 或 EOG。
- 导入文件损坏 / 字段缺失：不能破坏现有数据。
- localStorage 不可用：提示用户导出备份。
- 本地桥未启动 / 端口被占用：网站提示运行命令；服务启动失败时提示换端口。
- 客户端已启动未登录：状态接口返回 `loggedIn=false`，网站不发送同步请求。

### UI 测试

当前用 headless Chrome 注入测试脚本（不需要 Node/CDP）：

- `tests/merge_import_smoke.py`：合并规则、去重、持久化、导出。
- `tests/auto_sync_smoke.py`：mock `fetch` 覆盖自动同步全部提示路径。
- 本地桥真实接口用 Python `urllib` 直接调用；file:// 跨源用 headless Chrome 实测。
- 仍未自动化：真实文件选择框（可用 CDP `DOM.setFileInputFiles`）、桌面/移动端截图回归。

## 7. 已做决策与仍待确认

已做决策（本轮）：

1. 未知玩家：**自动创建**，并在状态区列出新增名单（不弹窗）。
2. 3 场旧历史：未自动导入；如需回填，可用「合并导入」选择 `data/lcu_custom_games.json`（数组格式已支持），但旧 gameId 可能已 404。
3. 位置字段：**默认留空**；需要时用 `--include-positions`。
4. 同步方式：**本地桥 + 按钮触发**（方案 B 已实现）；保留离线导出作为兜底。
5. 本地桥：只绑 `127.0.0.1`；CORS 白名单 + `X-LCU-Sync` 头；不引入随机 token，避免网页无法自动携带。
6. 改名/同名：仍按名字匹配；PUUID 未实现，属于已知限制。
7. 回放：默认扫描，`--no-rofl` 可关闭；回放过期问题已记录。
8. 撤销：未实现；合并只追加，可逐场删除。
9. 来源标记：未加字段（保持 schema 不变），历史里不显示“自动导入”。

仍待用户确认：

- 是否要做“对局结束自动触发”（服务常驻 + 阶段监听）。
- 是否值得为改名/同名加 PUUID（需要迁移）。
- 是否需要一键 `.bat` 或开机自启。
- 是否需要“撤销上次同步”。

## 8. 完成标准

- ✅ 不手动填 KDA，能从 LCU 导入 5v5 峡谷自定义（实测 22 场）。
- ✅ 点击网站按钮即可检测客户端并同步，本地桥未运行时可通过 `lolsync://` 自动拉起。
- ✅ 客户端未启动/未登录/自动拉起失败时，给出明确提示且不改数据。
- ✅ 海克斯大乱斗、练习模式、人数不足 10 的对局不会被导入。
- ✅ 导入不覆盖现有数据，按 gameId 去重。
- ✅ 排行榜、KDA、胜率、评分正确更新（测试断言覆盖）。
- ✅ 刷新/导出后数据正确。
- ✅ 不泄露 token；脚本不写用户主目录；本地桥只监听 127.0.0.1。
- ✅ 网站仍是单文件、纯前端、无外部依赖；本地桥为可选进程。
- ⏳ 真实文件选择框的 CDP 自动化（可选）。
