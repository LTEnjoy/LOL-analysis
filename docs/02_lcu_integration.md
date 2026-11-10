# 02 LCU 集成：认证、接口与抓取方案

## 1. 结论

- 官方 Riot API **不适合**本场景：国服不在覆盖范围，自定义对局对普通 key 返回 404。
- 本机国服客户端的 **LCU 接口可用**：能读当前账号、最近战绩、单局 10 人详情、英雄名称。
- 自定义对局详情可以通过 `gameId` 获取；难点是**发现 gameId**。
- 已验证 `.rofl` 回放文件名可以提供 gameId，并成功反查 3 场 5v5 内战。
- 尚未验证“最近 101 局列表是否包含自定义”；需要用下一场自定义实测。

## 2. 本机环境

| 项 | 值 |
|---|---|
| 系统 | Windows 10.0.19045 x64 |
| 客户端 | 腾讯国服，`D:\WeGameApps\英雄联盟（含经典模式）` |
| 主要进程 | `LeagueClient.exe`、`LeagueClientUx.exe`、`RiotClientServices.exe` |
| LCU 端口（2026-11-05 测试时） | `57372` |
| Python | 3.11.7，`D:\Soft\Coding\Conda\Conda\python.exe` |
| requests | 2.31.0 |
| 回放目录 | `C:\Users\Administrator\Documents\League of Legends\Replays` |
| 客户端日志 | `D:\WeGameApps\英雄联盟（含经典模式）\LeagueClient\*LeagueClientUx.log` |

端口是动态的，不要硬编码；`lcu_sync.py` 每次运行都会重新发现。客户端目录和回放目录也支持自动发现，可用 `--install` / `--replays` 覆盖。

## 3. LCU 认证

### 3.1 为什么不用进程命令行

常规方案是从 `LeagueClientUx.exe` 的命令行读取：

```text
--app-port=4694
--remoting-auth-token=<token>
```

但当前 shell 不是管理员，客户端可能是管理员权限运行，`Get-CimInstance Win32_Process` 读不到 CommandLine；`wmic` 在新 Windows 上也不可用。因此改用**客户端日志**。

### 3.2 从日志读取

最新日志文件名类似：

```text
D:\WeGameApps\英雄联盟\LeagueClient\2026-11-05T16-02-38_20520_12936_LeagueClientUx.log
```

日志里包含启动参数。用正则提取：

```python
tokens = re.findall(r'remoting-auth-token\s*[=:]\s*"?([A-Za-z0-9_\-]{8,})', text)
ports  = re.findall(r'app-port\s*[=:]\s*"?(\d+)', text)
```

测试时 token 长度 22；**不要打印、不要写入交接包、不要发到外部**。

### 3.3 选择正确的端口

日志里可能同时出现 Riot Client 的端口和 LCU 的端口。逐个候选端口请求：

```http
GET https://127.0.0.1:<port>/lol-summoner/v1/current-summoner
Authorization: Basic base64("riot:<token>")
```

- 返回 200 的端口就是 LCU。
- 测试时 `4694` 返回 200。
- `14906` 是 Riot Client，使用 Riot Client lockfile 的 token 对 LCU 返回 401 `CREDENTIALS_INVALID`。
- LCU 使用自签名证书，需要 `verify=False`；**只对 127.0.0.1 关闭校验**。

### 3.4 可复用的认证流程

1. 先尝试客户端目录下的 `lockfile`（`port:token` 格式，本机该文件为 0 字节，通常不可用）。
2. 再找到 `...\LeagueClient\*LeagueClientUx.log`，按 mtime 取最新几个。
3. 正则提取 token / port 候选。
4. 对每个组合请求 `current-summoner`。
5. 第一次 200 的组合即为可用 session。
6. 客户端重启后 token 会变，重新执行以上步骤。

`lcu_sync.py` 已实现以上流程；连接只发往 `127.0.0.1`。

## 4. 已验证接口

| 接口 | 结果 | 说明 |
|---|---|---|
| `GET /lol-summoner/v1/current-summoner` | 200 | `displayName`、`summonerLevel`、`puuid`、`accountId` |
| `GET /lol-match-history/v1/products/lol/{puuid}/matches?begIndex=0&endIndex=100` | 200 | 返回 101 局；分页参数无效 |
| `GET /lol-match-history/v1/games/{gameId}` | 200 | 单局完整详情，含 10 人 |
| `GET /lol-game-data/assets/v1/champion-summary.json` | 200 | 258 个英雄，本地化名称 |
| `GET /lol-gameflow/v1/gameflow-phase` | 200 | 当前客户端阶段 |
| `GET /lol-gameflow/v1/session` | 404 | 无对局时返回 `No gameflow session exists.` |
| `GET /lol-end-of-game/v1/eog-stats-block` | 404 | 无结算时返回 `No end of game stats available.` |
| `GET /lol-match-history/v1/products/lol/current-summoner/matches` | 200 | 与按 puuid 查询相同；仍只返回 101 局 |
| `GET /lol-match-history/v1/friend-matchlists/{accountId}` | 404 | 国服客户端没有该路由 |
| `GET /lol-match-history/v1/recently-played` | 404 | 无此路由 |
| `GET /lol-replays/v1/rofls` | 404 | 无此路由 |
| `GET /lol-end-of-game/v1/game-id` | 404 | 无此路由 |
| `GET /lol-pre-end-of-game/v1/current-game-id` | 404 | 无此路由 |
| `GET /swagger/v3/openapi.json` | 401 | 无法用来枚举接口 |
| `GET /swagger/v1|v2/openapi.json` | 404 | 无此路由 |

### 战绩列表的限制

- 无论 `begIndex/endIndex` 怎么传，始终返回最近 **101 局**；`0-1`、`100-200` 结果完全一样。
- 不支持 `gameType` 参数：400 `Unknown argument 'gameType'`。
- 不支持 `gameBeginDate/gameEndDate`：400 `Unknown argument 'gameBeginDate'`。
- 测试时最近 101 局覆盖 2026-10-11 到 2026-11-01，全部是：
  - `MATCHED_GAME` / queue 440 / CLASSIC
  - `MATCHED_GAME` / queue 420 / CLASSIC
  - `MATCHED_GAME` / queue 2400 / KIWI
- 没有 `CUSTOM_GAME`。

### 自定义对局详情

`GET /lol-match-history/v1/games/{gameId}` 对自定义对局返回 200，关键字段：

- `gameType = "CUSTOM_GAME"`
- `queueId = 3110`（峡谷还有 3130/3100）
- `mapId = 11` + `gameMode = "CLASSIC"` = 召唤师峡谷；`mapId = 12` + `gameMode = "KIWI"` = 海克斯大乱斗（queue 3270）；练习模式是 `gameMode = "PRACTICETOOL"`
- `participants` 10 人
- `participantIdentities` 里有 `player.summonerName` / `gameName` / `puuid`
- `participants[].stats` 里有 `kills/deaths/assists/win`
- `participants[].timeline` 里有 `lane/role`（位置不可靠）

## 5. 如何发现自定义对局

### 方案 1：最近 101 局列表（已实测，可用）

过滤 `gameType == "CUSTOM_GAME"` 或 `queueId == 3110`。

- 优点：最简单，不需要回放。
- 限制：只覆盖最近 101 局；超过就看不到。
- **2026-11-05 实测**：当前账号 `致风平浪静的初恋` 的最近 101 局中有 **51 条自定义对局摘要**，说明列表会包含自定义。详情仍需逐局调用 `/lol-match-history/v1/games/{gameId}`。
- 该 101 局窗口同时混合了匹配、峡谷自定义、海克斯大乱斗和练习模式，不能只依赖列表摘要做筛选；仍需详情校验 `mapId=11` + `gameMode=CLASSIC`、10 人、红蓝各 5、胜方。

### 方案 2：`.rofl` 回放文件（已验证）

回放文件名格式：

```text
HN1-11155247950.rofl
```

提取数字 gameId，然后：

```http
GET /lol-match-history/v1/games/11155247950
```

测试结果：

- 88 个回放
- 3 场 5v5 自定义
- 78 场非自定义
- 1 场不是 10 人
- 6 个 gameId 已 404（太旧）

优点：不依赖 101 局窗口；缺点：客户端必须开启回放保存，且旧回放可能过期。

### 方案 3：对局结束统计 / 实时接口（备选）

- `/lol-end-of-game/v1/eog-stats-block` 在结算阶段可能返回数据；测试时不在结算阶段，返回 404。
- 可以轮询 `/lol-gameflow/v1/gameflow-phase`，在 `WaitingForStats` / `EndOfGame` 时抓取。
- 游戏中还可以尝试 Live Client Data API：`https://127.0.0.1:2999/liveclientdata/allgamedata`（本次未验证）。
- 优点：不依赖 101 局窗口和回放；缺点：必须在游戏结束时运行 watcher，时机要求高。

### 推荐组合

1. 每局结束后先查最近 101 局列表，发现 `CUSTOM_GAME` 就拉详情。
2. 列表没有时，扫描 `.rofl` 新文件。
3. 如果用户经常关闭回放保存，再考虑 EOG watcher 或本地服务常驻。

## 6. 数据映射

| LCU 字段 | 网站字段 | 规则 |
|---|---|---|
| `gameId` | `id` / 去重键 | 建议 `m_lcu_<gameId>` |
| `gameCreation` | `date` | 毫秒时间戳 → 本地 `YYYY-MM-DD` |
| `gameCreation` | `createdAt` | 毫秒时间戳 → ISO |
| `teams[].win` 或 `stats.win` | `winner` | team 100 胜 → `blue`；team 200 胜 → `red`；**注意 `teams[].win` 是 `"Win"/"Fail"` 字符串** |
| `teamId` | `team` | 100 → `blue`；200 → `red` |
| `stats.kills/deaths/assists` | 同名 | 非负整数 |
| `championId` | `champion` | 用 `champion-summary.json` 的 `id → name` |
| `timeline.lane/role` | `position` | 不建议直接用，见下 |
| `player.summonerName` | 玩家匹配 | 先按名字精确匹配 |
| `player.puuid` | 可选账号标识 | 名字会变，PUUID 稳定；网站当前没有该字段 |

### 胜负字段（重要）

`teams[]` 里的 `win` 是字符串 `"Win"` / `"Fail"`，而 `participants[].stats.win` 是布尔值。如果把 `teams[].win` 直接当布尔判断，`"Fail"` 也会被当成真，导致所有对局都判给 team 100（蓝队）。本轮曾出现“27 场全蓝胜”，修复后为 9 红 / 13 蓝（已过滤 4 场海克斯大乱斗）。`lcu_sync.py` 的 `team_won()` 已归一化字符串，并有 `tests/lcu_sync_mapping_test.py` 覆盖。

另外，重开局可能 10 人齐全、5v5、`duration` 很短但两队都没有胜方；这类对局应跳过，不要造假胜负。此前文档把 116 秒的 queue 3270 对局写成“重开局”是误判：它是 `mapId=12` / `KIWI` 的海克斯大乱斗，已按非峡谷过滤。

### 地图与模式（重要）

仅靠 `gameType == CUSTOM_GAME` 不够：海克斯大乱斗也是自定义、也是 5v5，会混进统计。区分方式：

| 模式 | mapId | gameMode | 常见 queueId |
|---|---|---|---|
| 召唤师峡谷自定义 | 11 | `CLASSIC` | 3110 / 3130 / 3100 |
| 海克斯大乱斗 | 12 | `KIWI` | 3270 |
| 练习模式 | 11 | `PRACTICETOOL` | 3140 |

`lcu_sync.map_game()` 现在只接受 `mapId=11` + `gameMode=CLASSIC`，且必须 10 人、红蓝各 5；其余整场跳过。

### 位置字段

`timeline.lane/role` 在自定义对局里不可靠。测试中同一队出现多个“打野”。建议：

- 默认把 `position` 留空，让玩家在网站里自己选；
- 或加一个“使用客户端位置”开关，并明确提示可能不准。

### 英雄名称

`champion-summary.json` 返回本地化名称（国服是中文），字段：

```json
{ "id": 121, "name": "虚空掠夺者", "alias": "Khazix" }
```

直接用 `id → name`。当前文件里 258 个条目。

## 7. 已提取数据

### `data/lcu_sync.json`（2026-11-06，当前环境）

合并导入格式 `{source, fetchedAt, summoner, count, games}`：

- 27 场有效 5v5 峡谷自定义，日期 2026-08-13 ~ 2026-11-06
- 13 名玩家（按召唤师名去重）
- 红 12 胜 / 蓝 15 胜；queueId 3110 ×23、3130 ×2、3100 ×2
- 不含 PUUID、不含 token
- 参与者字段：`name/team/kills/deaths/assists/champion/position`；`position` 默认空
- 评分指标（原样透传，非负整数）：`goldEarned / totalMinionsKilled / neutralMinionsKilled / visionScore / visionWardsBoughtInGame / wardsKilled / totalDamageDealtToChampions / totalDamageTaken / damageSelfMitigated / totalHeal / timeCCingOthers / damageDealtToObjectives / damageDealtToTurrets`；字段清单见 `lcu_sync.RATING_STAT_FIELDS`

扫描统计（最近列表 51 条候选）：有效 22、非峡谷/非经典 10、非 5v5 19（人数不足或红蓝不均）；旧回放另有 404。2026-11-05 已从旧数据中移除 4 场海克斯大乱斗；2026-11-06 重新同步新增 5 场，旧版本备份为 `lcu_sync_22_backup.json`。

### `data/lcu_custom_games.json`（旧环境样例）

包含 3 场 5v5：

| 日期 | 胜方 | gameId | 备注 |
|---|---|---|---|
| 2026-07-31 | 红队 | 11155247950 | 时长 1961s |
| 2026-02-08 | 红队 | 10670583178 | 时长 1832s |
| 2026-01-30 | 蓝队 | 10641059881 | 时长 1951s |

样例（2026-07-31）：

- 红队 `素来喜望花似锦` 法外狂徒 22/3/6
- 红队 `Yooaena` 解脱者 6/5/13
- 蓝队 `初梦lostdream` 不落魔锋 6/3/9
- 蓝队 `我梦中的新娘` 封魔剑魂 5/8/3

这是**数组**格式；网站合并导入也接受数组，可用于回填旧数据。完整数据在 `data/lcu_custom_games.json`，可读摘要见 `data/lcu_custom_games_summary.txt`。这些 gameId 在当前客户端可能已 404。

## 8. 安全注意事项

- Token 只在 `127.0.0.1` 使用，绝不能打印、写入日志、提交到仓库或发到外部。
- `LeagueClientUx.log` 含 token，属于敏感文件；不要复制进交接包或分享。
- `verify=False` 只用于 LCU 自签名证书；不要对外部 HTTPS 关闭校验。
- `data/lcu_custom_games.json` 含 PUUID；分享前可删除 `puuid` 字段。
- LCU 是未公开接口，不要把它当成稳定 API；客户端更新后重新验证。
- `lcu_server.py` 只绑定 `127.0.0.1`；CORS 只放行 file://（Origin `null`）与 localhost；`/api/sync` 要求 `X-LCU-Sync: 1`；响应与日志都不含 token。

## 9. 建议的同步架构

### 方案 A：合并导入（已实现，2026-11-05）

```text
LCU (localhost)
   ↓ Python scripts/lcu_sync.py（自动发现路径/凭证）
data/lcu_sync.json
   ↓ 网站「数据」→「导入 JSON 文件（合并）」
localStorage（按 m_lcu_<gameId> 去重、按玩家名映射）
```

优点：

- 保持单文件网站可分享。
- 不需要常驻服务。
- 不会覆盖现有数据。
- 每局后运行一次脚本 + 点一次导入即可。

`lcu_sync.py` 实际流程：

1. 自动发现客户端目录（环境变量/常见路径/`D:\WeGameApps` 扫描）、回放目录。
2. 先试 `lockfile`，再解析最新 `*LeagueClientUx.log` 的 token/port，请求 `current-summoner` 验证。
3. 取当前 summoner / puuid。
4. 取最近 101 局，筛 `CUSTOM_GAME` / `queueId=3110`。
5. 扫描 `.rofl` 补充 gameId（`--no-rofl` 可关闭），按 mtime 倒序。
6. 对每个新 gameId 拉详情，校验 10 人、红蓝各 5、胜方存在。
7. 取英雄名称映射；`--include-positions` 才写入位置。
8. 支持 `--since`、`--output`、`--dry-run`、`--install`、`--replays`。
9. 输出（默认 `data/lcu_sync.json`）：

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

网站“合并导入”实际行为：

- 按 `m_lcu_<gameId>` 去重，已存在则计入“跳过重复”，不会重复写入。
- 按 `name` 忽略大小写、trim 后匹配现有玩家；找不到时**自动创建**启用玩家，并在状态区列出新增名字。
- 校验每场 10 人、红蓝各 5、名字不重复、胜方有效；无效场次整场跳过并在状态区说明。
- 只追加玩家和对局；现有数据不动；全部校验完成后一次性 `saveState()`，失败不会半写入。
- 同时接受 `{games:[...]}` 和裸数组（旧 `lcu_custom_games.json` 格式）。
- 不修改现有 `importJson` 的“替换”语义。

### 方案 B：本地服务（已实现，2026-11-05，按钮触发）

```text
网页按钮
   ↓ GET  /api/status  检测 LeagueClientUx.exe 进程 + 登录会话
   ↓ POST /api/sync    （X-LCU-Sync: 1）
scripts/lcu_server.py（只监听 127.0.0.1:8765）
   ↓ 复用 lcu_sync.collect_games()
LCU (localhost)
   ↓ JSON 响应
网页按 m_lcu_<gameId> 合并到 localStorage
```

- `GET /api/status`：不返回 token/port；只返回 `clientRunning`、`loggedIn`、`summoner`、`message`。先查进程，未运行立即返回，避免无谓的日志解析。
- `POST /api/sync`：同步执行一次全量采集（最近 101 局 + `.rofl` 兜底），返回与 `lcu_sync.json` 相同的信封；同一时间只允许一个同步任务（409）。
- `GET /`：直接托管 `website/lol_stats.html`，此时网页与 API 同源，无需 CORS。
- 文件方式打开网页时，自动同步固定连接 `http://127.0.0.1:8765`；`lcu_server.py --port` 改端口只影响“用服务托管网站”的方式。
- CORS：仅允许无 Origin、`null`（file://）、`127.0.0.1` / `localhost` 来源；`POST /api/sync` 需要自定义头，附带预检。
- 实测：真实客户端下 `/api/status` 检测成功，`/api/sync` 约 **10 秒**返回 22 场（仅峡谷 5v5）；从 `file://` 页面直接请求也已通过。
- 不是轮询/定时器：目前仍由用户点按钮触发，避免网页后台持续请求 LCU。

### 方案 C：直接改 HTML seed（不推荐）

- 新 seed 的 `updatedAt` 会覆盖浏览器 localStorage 中更新的数据。
- 只适合生成快照，不适合日常同步。

## 10. 验证状态

1. ✅ 已确认：最近 101 局包含自定义（本次 51 条）。
2. ✅ 不依赖摘要人数：`lcu_sync.py` 对所有候选统一拉详情取 10 人。
3. ⏳ EOG stats 对自定义对局是否可用、时间窗口；本轮未验证。
4. ⚠️ `.rofl` 会过期：本次 59 个回放有 46 个 404；是否长期开启回放仍取决于用户设置。
5. ⏳ 客户端重启后的 token/端口重发现：逻辑已有，但本轮未做重启实测。
6. ⏳ 国服客户端更新后接口是否变化。
7. ✅ 非峡谷过滤：海克斯大乱斗（`mapId=12`/`KIWI`）、练习模式、人数不足 10 的对局全部跳过；此前 116 秒的 queue 3270 对局是海克斯大乱斗，不是重开局。
8. ✅ 本地桥：进程检测、登录检测、真实同步（22 场，约 10 秒）、file:// 跨源请求均已实测。
9. ⏳ 客户端未登录时的完整 UI 流程：已用 mock 测试覆盖提示文案；真实“已启动未登录”状态未专门构造。
