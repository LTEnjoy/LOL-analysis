# 数据文件说明

当前使用的同步产物是 `lcu_sync.json`；其余 JSON/TXT 是早期探测留下的历史快照。

## `lcu_sync.json`（当前）

`scripts/lcu_sync.py` 的默认输出，也是网站「导入 JSON 文件（合并）」的输入。网站「检测并同步客户端」走本地桥时，返回的是同样的信封，不会写这个文件。

结构是**合并导入信封**（对象），不是网站状态：

```json
{
  "source": "lcu",
  "fetchedAt": "2026-11-05T17:09:30+08:00",
  "summoner": "致风平浪静的初恋",
  "count": 26,
  "games": [
    {
      "gameId": 8930358121,
      "date": "2026-08-13",
      "createdAt": "2026-08-13T22:39:29",
      "queueId": 3130,
      "winner": "red",
      "duration": 2225,
      "participants": [
        {
          "name": "素来喜望花似锦",
          "team": "red",
          "kills": 22,
          "deaths": 3,
          "assists": 6,
          "champion": "法外狂徒",
          "position": "",
          "goldEarned": 18342,
          "totalMinionsKilled": 214,
          "neutralMinionsKilled": 0,
          "visionScore": 36,
          "timeCCingOthers": 18
        }
      ]
    }
  ]
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| `source` | 固定为 `lcu` |
| `fetchedAt` | 生成时间（带时区） |
| `summoner` | 当前登录召唤师名，仅作参考 |
| `count` | `games` 数量 |
| `games[].gameId` | LCU 对局 ID，天然去重键 |
| `games[].date` | 本地日期 `YYYY-MM-DD` |
| `games[].createdAt` | 本地 ISO 时间 |
| `games[].queueId` | 客户端队列 ID；自定义不只 3110 |
| `games[].winner` | `blue` / `red`（已归一化） |
| `games[].duration` | 秒 |
| `games[].participants[].name` | 召唤师名，用于匹配网站玩家 |
| `games[].participants[].team` | `blue` / `red` |
| `games[].participants[].kills/deaths/assists` | KDA 原始数据 |
| `games[].participants[].champion` | 本地化英雄名 |
| `games[].participants[].position` | 默认空；仅 `--include-positions` 时填客户端 lane/role |
| `games[].participants[].goldEarned` 等 | 评分指标，原样透传并截断为非负整数：`goldEarned / totalMinionsKilled / neutralMinionsKilled / visionScore / visionWardsBoughtInGame / wardsKilled / totalDamageDealtToChampions / totalDamageTaken / damageSelfMitigated / totalHeal / timeCCingOthers / damageDealtToObjectives / damageDealtToTurrets` |

评分指标缺失时网站自动回退旧公式（胜率 + KDA），新旧数据可混用。

本机快照（2026-11-06 重新同步，已过滤非峡谷）：

- 27 场有效 5v5 峡谷自定义，日期 2026-08-13 至 2026-11-06。
- 13 名玩家；胜方红 12 / 蓝 15。
- queueId 分布：3110 ×23、3130 ×2、3100 ×2；全部为 `mapId=11` + `gameMode=CLASSIC`。
- 2026-11-05 修正：已移除 4 场海克斯大乱斗（queue 3270、`mapId=12`、`gameMode=KIWI`）。
- 2026-11-06：重新同步新增 5 场（11-05 ~ 11-06）并补齐评分指标；旧的 22 场版本备份为 `data/lcu_sync_22_backup.json`。
- 筛选条件：`gameType == CUSTOM_GAME` + `mapId=11` + `gameMode=CLASSIC` + 10 人 + 红蓝各 5；不能只看 queueId。
- 不含 PUUID、token。

网站合并导入规则：

- 对局 ID 用 `m_lcu_<gameId>` 与原数据去重，重复导入不会产生重复对局。
- 玩家按 `name`（去首尾空格、不区分大小写）匹配；找不到时自动创建。
- 只追加新对局，不覆盖现有 `players` / `matches`。
- 人数不是 10、红蓝不是 5/5、名称重复、缺少胜方的对局会被跳过。
- `lcu_sync.py` / 本地桥输出的文件已只含 5v5 峡谷；旧版裸数组若含海克斯大乱斗，导入前需自行清理。

重新生成：

```bash
D:\Soft\Coding\Conda\Conda\python.exe scripts/lcu_sync.py
```

## `lcu_custom_games.json`（历史样例）

早期从 LCU 抓到的 3 场 5v5 自定义对局，用于确认详情接口和字段。**不是**当前同步入口。

结构是**数组**：

```json
[
  {
    "gameId": 11155247950,
    "date": "2026-07-31",
    "createdAt": "2026-07-31T13:00:00",
    "queueId": 3110,
    "winner": "red",
    "duration": 1961,
    "participants": [
      {
        "name": "素来喜望花似锦",
        "puuid": "……",
        "team": "red",
        "kills": 22,
        "deaths": 3,
        "assists": 6,
        "champion": "法外狂徒",
        "position": "打野",
        "win": true
      }
    ]
  }
]
```

与 `lcu_sync.json` 的差异：

- 顶层是数组，没有 `source` / `fetchedAt` 信封。
- 每个参与者多 `puuid` 和 `win`；网站合并导入会忽略这两个字段。
- `position` 是本机推断值，存在多个“打野”等不准的情况；新脚本默认不输出。

数据内容：

| 日期 | 胜方 | gameId |
|---|---|---|
| 2026-07-31 | 红队 | 11155247950 |
| 2026-02-08 | 红队 | 10670583178 |
| 2026-01-30 | 蓝队 | 10641059881 |

文件含 PUUID；分享前可删除该字段。

## 历史探测结果

以下文件来自原机器/早期环境，仅用于回溯，不要当成当前账号的完整数据。

## `lcu_custom_games_summary.txt`

上面 3 场对局的可读摘要，按日期倒序，列出双方 10 人的英雄/KDA/位置/胜负。

## `lcu_fetch_result.txt`

- 当时召唤师：`素来喜望花似锦`，369 级。
- 最近 101 局列表。
- 当时全部是 `MATCHED_GAME`，没有自定义；后续换账号验证时列表已包含自定义。

## `lcu_verify_result.txt`

- 分页测试：`0-100`、`100-200`、`200-300`、`300-400`、`400-500` 都返回同一批 101 局；文件里的 `total=505` 是重复计数，不是 505 场不同对局。
- 单局详情示例：10 人完整数据。
- `.rofl` 文件列表（前 20 个）。
- 注意：文件里的日期来自当时客户端/文件，不要当成当前赛季数据。

## `lcu_custom_check_result.txt`

- 按 puuid / current-summoner 查询列表，结果都是 101 局。
- `gameType` 过滤返回 400。
- 用 `.rofl` 的 gameId 查详情：`10641059881` 为 `CUSTOM_GAME`、queue 3110、10 人。
- 验证了自定义详情接口可用。

## `lcu_list_probe_result.txt`

- 分页参数无效。
- 日期过滤参数不支持（`Unknown argument 'gameBeginDate'`）。
- 好友战绩接口 404。
- 结论：没有可靠的“按日期/队列列出自定义”的列表接口。

## `lcu_eog_result.txt`

- 无对局时 `/lol-gameflow/v1/session`、`/lol-end-of-game/v1/eog-stats-block` 返回 404。
- `/lol-gameflow/v1/gameflow-phase` 返回 200。
- 说明 EOG 数据只在结算阶段可用；本次未验证自定义对局。

## `lcu_swagger_result.txt`

- `/swagger/v3/openapi.json` 返回 401；v2/v1 返回 404。
- 不能靠 Swagger 枚举接口。

## 安全

- 这些数据文件**不包含 LCU token**。
- `lcu_sync.json` 不含 PUUID，可直接用于合并导入；仍包含召唤师名和对局 ID。
- `lcu_custom_games.json` 含 PUUID，分享前自行删除。
- 不要为了调试把 `LeagueClientUx.log` 放进这个目录。
