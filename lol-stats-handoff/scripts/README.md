# 脚本说明

## 环境（2026-11-05 实机）

- Windows 10.0.19045 + 国服英雄联盟客户端
- 客户端安装：`D:\WeGameApps\英雄联盟（含经典模式）`
- 回放目录：`C:\Users\Administrator\Documents\League of Legends\Replays`
- Python 3.11.7：`D:\Soft\Coding\Conda\Conda\python.exe`
- `requests` 2.31.0（见 `requirements.txt`）
- 客户端必须已启动并登录

安装依赖：

```bash
D:\Soft\Coding\Conda\Conda\python.exe -m pip install -r requirements.txt
```

## 路径处理

`lcu_sync.py` / `lcu_server.py` 会自动发现路径：

- 客户端：环境变量 `LOL_INSTALL` → `--install` → 常见路径 → 扫描 `D:\WeGameApps\*\LeagueClient\LeagueClientUx.exe`
- 回放：环境变量 `LOL_REPLAYS` → `--replays` → 当前用户 Documents / OneDrive Documents
- 凭证：先试客户端 `lockfile`，再解析最新 `*LeagueClientUx.log`（本机 lockfile 为空，实际走日志）

旧的 `lcu_extract_customs.py` / `lcu_fetch.py` / `lcu_verify.py` / `lcu_custom_check.py` 仍是原环境原型，硬编码了 `D:\tmp` 和 `C:\Users\LTEnj`，移动后需自行改常量；日常同步请用 `lcu_server.py` 或 `lcu_sync.py`。

## 脚本列表

### `lcu_server.py`（自动同步桥，新增）

- 只监听 `127.0.0.1:8765`，供网站按钮检测并同步客户端。
- 复用 `lcu_sync.collect_games()`，不重复实现 LCU 逻辑。
- 接口：
  - `GET /api/status`：检测 `LeagueClientUx.exe` + 登录会话，返回状态与召唤师名（不含 token/端口）。
  - `POST /api/sync`：需要 `X-LCU-Sync: 1`；同步返回 `{source, fetchedAt, summoner, count, games}`；并发时返回 409。
  - `GET /`：直接打开网站。
- CORS 仅允许 file://（`Origin: null`）和 localhost；不返回、不打印 token。

运行：

```bash
D:\Soft\Coding\Conda\Conda\python.exe lcu_server.py
# 可选：--port 8766、--open
```

打开 `http://127.0.0.1:8765/`，或直接打开 `website/lol_stats.html`（文件方式固定连 8765）。

### `start_lcu_server.py`（一键拉起本地桥）

- 由 `lolsync://` 协议调用，或用 `python start_lcu_server.py` 手动运行。
- 先检查 `127.0.0.1:8765` 是否已健康；已运行则直接退出，端口被别的程序占用则报错。
- 用同目录的 `pythonw.exe` 后台启动 `lcu_server.py`，轮询健康检查，不打印 token。

### `install_protocol.py`（注册 `lolsync://`，只需一次）

```bash
D:\Soft\Coding\Conda\Conda\python.exe scripts\install_protocol.py
```

- 在 HKCU `Software\Classes\lolsync` 注册 `URL:LoL Sync Bridge`，命令指向 `pythonw.exe start_lcu_server.py`。
- 不把 URL 参数传给 shell，避免命令注入。
- `--status` 查看、`--remove` 移除；仅支持 Windows。

### `lcu_sync.py`（离线导出）

- 自动发现客户端/回放/凭证。
- 最近 101 局筛 `CUSTOM_GAME`，`.rofl` 兜底。
- 拉详情只保留 `mapId=11` + `gameMode=CLASSIC` 的 5v5 峡谷对局；校验 10 人、红蓝各 5、胜方存在。
- 跳过海克斯大乱斗（`mapId=12`/`KIWI`）、练习模式、人数不足 10、无胜方、旧 404。
- 英雄 ID → 中文名；位置默认空。
- 正确归一化 `teams[].win` 的 `"Win"/"Fail"` 字符串。
- 输出合并导入格式，默认 `data/lcu_sync.json`；不含 PUUID/token。

运行：

```bash
D:\Soft\Coding\Conda\Conda\python.exe lcu_sync.py
```

参数：

```text
--output PATH        默认 <项目>/data/lcu_sync.json
--since YYYY-MM-DD   只输出该日期及之后
--no-rofl            不扫描回放
--dry-run            只打印，不写文件
--include-positions  导入客户端 lane/role（默认关闭）
--install PATH       客户端目录
--replays PATH       回放目录
```

控制台统计：候选数、有效 5v5 峡谷、非自定义、非峡谷/非经典、非 5v5、无效、请求失败、被 since 过滤；每场打印 10 人 KDA。Windows 控制台若中文乱码，直接查看 UTF-8 的 JSON。

### 测试

```bash
D:\Soft\Coding\Conda\Conda\python.exe -m unittest tests.lcu_sync_mapping_test -v
D:\Soft\Coding\Conda\Conda\python.exe tests/merge_import_smoke.py
D:\Soft\Coding\Conda\Conda\python.exe tests/merge_import_smoke.py --sync-file data/lcu_sync.json
D:\Soft\Coding\Conda\Conda\python.exe tests/auto_sync_smoke.py
```

### `lcu_extract_customs.py`（旧原型）

- 从 `LeagueClientUx.log` 发现 LCU 凭证/端口。
- 读取当前账号和最近 101 局。
- 扫描 `.rofl` 文件名，提取 gameId。
- 对每个 gameId 拉详情，筛 `CUSTOM_GAME`、10 人、5v5。
- 用 `champion-summary.json` 映射英雄名称。
- 输出 `D:\tmp\lcu_custom_games.json` 和 `D:\tmp\lcu_custom_games_summary.txt`。

运行：

```bash
python lcu_extract_customs.py
```

### 旧探测脚本（历史，不建议日常运行）

以下脚本保留了原环境的硬编码（`D:\tmp`、`C:\Users\LTEnj`），当前机器上直接运行可能写不出去；仅作排错参考。

#### `lcu_fetch.py`

- 发现 LCU 凭证。
- 输出当时召唤师、最近 101 局列表、前 3 场自定义详情（如果有）。
- 原输出：`D:\tmp\lcu_fetch_result.txt`（对应 `data/` 里的历史快照）。

#### `lcu_verify.py`

- 验证分页、单局详情、回放文件扫描。
- 原输出：`D:\tmp\lcu_verify_result.txt`。
- 注意：分页参数无效，每次返回同一批 101 局；结果文件里的 505 是重复计数。

#### `lcu_custom_check.py`

- 测试按 puuid / current-summoner 的列表接口。
- 测试带 `gameType` 过滤（400）。
- 测试 `.rofl` gameId 详情。
- 原输出：`D:\tmp\lcu_custom_check_result.txt`。

### `research/lcu_probe.py`

- 早期探测脚本：尝试读 `LeagueClientUx.exe` 命令行和 lockfile。
- 当前 shell 非管理员时读不到命令行；`wmic` 也可能不存在。
- 保留作为排错参考，**不是**当前可用的认证入口。

### `research/lcu_auth_probe.py`

- 读取 Riot Client lockfile，测试 Riot Client token 对 LCU 端口是否有效。
- 结论：Riot Client token 对 LCU 无效（401）；LCU token 要从 `LeagueClientUx.log` 取。
- 不会打印 token 内容。

## 通用注意事项

- 所有请求只发往 `127.0.0.1`。
- LCU 是自签名证书，脚本使用 `verify=False`；不要把这个设置用于外部 URL。
- 不要打印、记录、提交 token；不要把 `LeagueClientUx.log` 复制进交接包。
- 客户端重启后 token/端口会变，重新运行脚本即可。
- 如果客户端未启动或未登录，`current-summoner` 会失败；先启动客户端。
- 脚本里的中文输出文件是 UTF-8；Windows 控制台可能显示乱码，直接看输出文件即可。

## 当前状态与可选后续

`lcu_server.py` + 网站按钮已通过真实联调，日常流程是：

```text
首次：install_protocol.py 注册 lolsync://
之后：启动客户端 → 网站数据页 → “检测并同步客户端”（本地桥会按需自动拉起）
```

本地桥会自动过滤海克斯大乱斗和练习模式，只同步 5v5 峡谷自定义对局。

换电脑/不想开服务时，仍可用：

```text
运行 lcu_sync.py → 网站数据页 → “导入 JSON 文件”
```

可选改进（尚未实现）：

- 本地 gameId 缓存：避免每次都请求 100 场详情（当前单次约 10 秒）。
- 自动触发：对局结束后由常驻服务自动同步，不点按钮。
- EOG watcher：需先验证自定义对局的 EOG 数据。
- PUUID 映射：当前按召唤师名匹配；改名或同名时会分成两个玩家。
- 打包 `.bat`：双击启动服务并打开网站。
