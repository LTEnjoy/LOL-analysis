#!/usr/bin/env python3
"""Export recent 5v5 Summoner's Rift custom games in merge-import format.

Only talks to 127.0.0.1. Never prints the LCU auth token.
Output can be merged into the website via 「合并导入 LCU 对局」.
"""

import argparse
import base64
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import requests
import urllib3

# LCU uses a self-signed cert; TLS verification is disabled only for 127.0.0.1 URLs below.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = BASE / "data" / "lcu_sync.json"
CUSTOM_QUEUE_ID = 3110
SUMMONERS_RIFT_MAP_ID = 11
CLASSIC_GAME_MODE = "CLASSIC"
CLIENT_NOT_RUNNING_MESSAGE = "未检测到英雄联盟客户端。请先启动并登录客户端，再重试。"

RATING_STAT_FIELDS = (
    "goldEarned",
    "totalMinionsKilled",
    "neutralMinionsKilled",
    "visionScore",
    "visionWardsBoughtInGame",
    "wardsKilled",
    "totalDamageDealtToChampions",
    "totalDamageTaken",
    "damageSelfMitigated",
    "totalHeal",
    "timeCCingOthers",
    "damageDealtToObjectives",
    "damageDealtToTurrets",
)

LANE_MAP = {
    ("TOP", "SOLO"): "上单",
    ("JUNGLE", "NONE"): "打野",
    ("MIDDLE", "SOLO"): "中单",
    ("BOTTOM", "DUO_CARRY"): "ADC",
    ("BOTTOM", "DUO_SUPPORT"): "辅助",
}

INSTALL_CANDIDATES = [
    Path(r"D:\WeGameApps\英雄联盟（含经典模式）"),
    Path(r"D:\WeGameApps\英雄联盟"),
    Path(r"C:\Riot Games\League of Legends"),
    Path(r"C:\Program Files\Riot Games\League of Legends"),
]


def safe_print(*args):
    try:
        print(*args)
    except UnicodeEncodeError:
        print(*(str(a).encode("utf-8", "replace").decode("utf-8", "replace") for a in args))


def find_install(explicit):
    if explicit:
        return Path(explicit)
    env = os.environ.get("LOL_INSTALL")
    if env:
        return Path(env)
    for path in INSTALL_CANDIDATES:
        if (path / "LeagueClient").is_dir():
            return path
    for root in (Path(r"D:\WeGameApps"), Path(r"C:\Riot Games")):
        if not root.is_dir():
            continue
        for exe in root.glob("*/LeagueClient/LeagueClientUx.exe"):
            return exe.parents[1]
    return None


def find_replay_root(explicit):
    if explicit:
        return Path(explicit)
    env = os.environ.get("LOL_REPLAYS")
    if env:
        return Path(env)
    home = Path.home()
    for path in (
        home / "Documents" / "League of Legends" / "Replays",
        home / "OneDrive" / "Documents" / "League of Legends" / "Replays",
    ):
        if path.is_dir():
            return path
    return None


def make_session(port, token):
    session = requests.Session()
    session.headers.update({
        "Authorization": "Basic " + base64.b64encode(f"riot:{token}".encode()).decode(),
        "Accept": "application/json",
    })
    return session


def session_from_lockfile(install):
    for candidate in (install / "lockfile", install / "LeagueClient" / "lockfile"):
        try:
            text = candidate.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        parts = text.split(":")
        if len(parts) < 5:
            continue
        port, password = parts[2], parts[3]
        if not port.isdigit() or not password:
            continue
        session = make_session(port, password)
        try:
            r = session.get(
                f"https://127.0.0.1:{port}/lol-summoner/v1/current-summoner",
                timeout=(3, 8),
                verify=False,
            )
        except requests.RequestException:
            continue
        if r.status_code == 200:
            return session, int(port), candidate.name
    return None


def session_from_logs(install):
    logs = sorted(
        (install / "LeagueClient").glob("*LeagueClientUx.log"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in logs[:5]:
        text = path.read_text(encoding="utf-8", errors="replace")
        tokens = re.findall(r'remoting-auth-token\s*[=:]\s*"?([A-Za-z0-9_\-]{8,})', text)
        ports = re.findall(r'app-port\s*[=:]\s*"?(\d+)', text)
        for token in dict.fromkeys(tokens):
            for port in dict.fromkeys(ports):
                session = make_session(port, token)
                try:
                    r = session.get(
                        f"https://127.0.0.1:{port}/lol-summoner/v1/current-summoner",
                        timeout=(3, 8),
                        verify=False,
                    )
                except requests.RequestException:
                    continue
                if r.status_code == 200:
                    return session, int(port), path.name
    return None


def find_session(install):
    return session_from_lockfile(install) or session_from_logs(install)


def client_process_running():
    """Detect LeagueClientUx.exe without needing LCU credentials."""
    if os.name != "nt":
        return False
    try:
        completed = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq LeagueClientUx.exe", "/NH"],
            capture_output=True,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return b"leagueclientux.exe" in (completed.stdout or b"").lower()


def get_json(session, port, path, timeout=20):
    try:
        r = session.get(f"https://127.0.0.1:{port}{path}", timeout=timeout, verify=False)
    except requests.RequestException as e:
        return None, f"{type(e).__name__}: {e}"
    if r.status_code != 200:
        body = r.text.strip().replace("\n", " ")[:120]
        return None, f"HTTP {r.status_code}" + (f": {body}" if body else "")
    try:
        return r.json(), ""
    except ValueError as e:
        return None, f"{type(e).__name__}: {e}"


def extract_games(payload):
    games = payload.get("games", payload) if isinstance(payload, dict) else payload
    if isinstance(games, dict):
        games = games.get("games", [])
    return games if isinstance(games, list) else []


def is_custom_summary(game):
    return game.get("gameType") == "CUSTOM_GAME" or game.get("queueId") == CUSTOM_QUEUE_ID


def to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def team_won(value):
    # LCU returns "Win"/"Fail" strings here, while participant stats use booleans.
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("win", "true", "1", "yes")
    return bool(value)


def map_game(detail, champ_names, include_positions):
    """Return (game, error). game is None when the match is not a usable 5v5 custom."""
    if detail.get("gameType") != "CUSTOM_GAME" and detail.get("queueId") != CUSTOM_QUEUE_ID:
        return None, "not-custom"
    if detail.get("mapId") != SUMMONERS_RIFT_MAP_ID or detail.get("gameMode") != CLASSIC_GAME_MODE:
        return None, "not-summoners-rift"

    participants_raw = detail.get("participants") or []
    blue = [p for p in participants_raw if p.get("teamId") == 100]
    red = [p for p in participants_raw if p.get("teamId") == 200]
    if len(participants_raw) != 10 or len(blue) != 5 or len(red) != 5:
        return None, "not-5v5"

    identities = {
        x.get("participantId"): x.get("player", {})
        for x in detail.get("participantIdentities") or []
    }

    participants = []
    seen_names = set()
    for p in participants_raw:
        info = identities.get(p.get("participantId"), {})
        name = (info.get("gameName") or info.get("summonerName") or info.get("riotIdGameName") or "").strip()
        if not name:
            return None, "missing-name"
        key = name.casefold()
        if key in seen_names:
            return None, "duplicate-name"
        seen_names.add(key)
        stats = p.get("stats") or {}
        timeline = p.get("timeline") or {}
        position = LANE_MAP.get((timeline.get("lane"), timeline.get("role")), "") if include_positions else ""
        entry = {
            "name": name,
            "team": "blue" if p.get("teamId") == 100 else "red",
            "kills": max(0, to_int(stats.get("kills"))),
            "deaths": max(0, to_int(stats.get("deaths"))),
            "assists": max(0, to_int(stats.get("assists"))),
            "champion": str(champ_names.get(p.get("championId"), p.get("championId") or ""))[:20],
            "position": position,
        }
        for key in RATING_STAT_FIELDS:
            if key in stats:
                entry[key] = max(0, to_int(stats.get(key)))
        participants.append(entry)

    winner = ""
    for team in detail.get("teams") or []:
        if team_won(team.get("win")):
            winner = "blue" if team.get("teamId") == 100 else "red"
            break
    if not winner:
        blue_won = any((p.get("stats") or {}).get("win") for p in blue)
        red_won = any((p.get("stats") or {}).get("win") for p in red)
        if blue_won and not red_won:
            winner = "blue"
        elif red_won and not blue_won:
            winner = "red"
    if not winner:
        return None, "missing-winner"

    created = to_int(detail.get("gameCreation"))
    try:
        dt = datetime.fromtimestamp(created / 1000)
    except (OverflowError, OSError, ValueError):
        dt = None

    return {
        "gameId": to_int(detail.get("gameId")),
        "date": dt.strftime("%Y-%m-%d") if dt else "",
        "createdAt": dt.isoformat(timespec="seconds") if dt else "",
        "queueId": detail.get("queueId"),
        "winner": winner,
        "duration": max(0, to_int(detail.get("gameDuration"))),
        "participants": participants,
    }, ""


def collect_game_ids(session, port, puuid, replay_root, use_rofl, logger=safe_print):
    log = logger or (lambda *args: None)
    ids = []
    data, err = get_json(
        session, port,
        f"/lol-match-history/v1/products/lol/{puuid}/matches?begIndex=0&endIndex=100",
    )
    recent_custom = 0
    if data is None:
        log(f"[warn] 战绩列表获取失败：{err}")
    else:
        for game in extract_games(data):
            if is_custom_summary(game):
                ids.append(str(game.get("gameId")))
                recent_custom += 1
    log(f"[info] 最近 101 局中的自定义对局：{recent_custom}")

    rofl_count = 0
    if use_rofl and replay_root and replay_root.is_dir():
        rofl_paths = sorted(
            replay_root.glob("*.rofl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for path in rofl_paths:
            match = re.search(r"(\d{6,})", path.stem)
            if match:
                ids.append(match.group(1))
                rofl_count += 1
        log(f"[info] 回放目录：{replay_root}（{rofl_count} 个回放）")
    elif use_rofl:
        log("[warn] 未找到回放目录，跳过 .rofl 扫描（可用 --replays 指定）")

    return list(dict.fromkeys(ids))


def collect_games(install=None, replays=None, since=None, use_rofl=True,
                  include_positions=False, logger=safe_print):
    """Collect usable 5v5 custom games.

    Returns a dict with ok/code/message/payload so both the CLI and the local
    server can share the same LCU logic. No token or PUUID is included.
    """
    log = logger or (lambda *args: None)
    empty = {"payload": None, "counts": {}, "failures": []}

    install_path = find_install(install)
    if not install_path or not (install_path / "LeagueClient").is_dir():
        return {
            "ok": False,
            "code": "install-not-found",
            "message": "未找到英雄联盟客户端目录。请先启动客户端，或用 --install 指定安装目录。",
            **empty,
        }

    found = find_session(install_path)
    if not found:
        return {
            "ok": False,
            "code": "auth-failed",
            "message": "LCU 认证失败。请确认客户端已启动并登录；若刚重启过，请稍后再试。",
            **empty,
        }
    session, port, source = found

    me, err = get_json(session, port, "/lol-summoner/v1/current-summoner")
    if me is None:
        return {
            "ok": False,
            "code": "summoner-failed",
            "message": f"无法读取当前账号：{err}",
            **empty,
        }
    puuid = me.get("puuid") or ""
    summoner = me.get("displayName") or me.get("gameName") or me.get("summonerName") or "?"
    log(f"[info] 账号：{summoner}（端口 {port}，凭证来源 {source}）")
    if not puuid:
        return {
            "ok": False,
            "code": "no-puuid",
            "message": "当前账号没有返回 puuid，无法查询战绩。",
            **empty,
        }

    champ_raw, champ_err = get_json(session, port, "/lol-game-data/assets/v1/champion-summary.json")
    champ_names = {}
    if isinstance(champ_raw, list):
        champ_names = {c.get("id"): c.get("name") for c in champ_raw if isinstance(c, dict)}
    else:
        log(f"[warn] 英雄名称映射获取失败，将输出英雄 ID：{champ_err}")

    replay_root = find_replay_root(replays)
    candidate_ids = collect_game_ids(session, port, puuid, replay_root, use_rofl, logger=log)
    log(f"[info] 候选对局：{len(candidate_ids)} 个")

    games = []
    counts = {
        "not_custom": 0,
        "not_summoners_rift": 0,
        "not_5v5": 0,
        "invalid": 0,
        "failed": 0,
        "since": 0,
    }
    failures = []

    for game_id in candidate_ids:
        detail, detail_err = get_json(session, port, f"/lol-match-history/v1/games/{game_id}")
        if detail is None:
            counts["failed"] += 1
            failures.append((game_id, detail_err))
            continue
        game, reason = map_game(detail, champ_names, include_positions)
        if game is None:
            if reason in ("not-custom", "not-summoners-rift", "not-5v5"):
                counts[reason.replace("-", "_")] += 1
            else:
                counts["invalid"] += 1
                failures.append((game_id, reason))
            continue
        if since and game["date"] and game["date"] < since:
            counts["since"] += 1
            continue
        games.append(game)

    games.sort(key=lambda g: (g["date"], g["createdAt"], g["gameId"]))

    log("")
    log(
        f"[result] 5v5 峡谷自定义：{len(games)} 场 · 非自定义 {counts['not_custom']} · "
        f"非峡谷/非经典模式 {counts['not_summoners_rift']} · 非 5v5 {counts['not_5v5']} · "
        f"无效 {counts['invalid']} · 请求失败 {counts['failed']} · 被 --since 过滤 {counts['since']}"
    )
    for game_id, reason in failures[:10]:
        log(f"  [skip] id={game_id} {reason}")

    payload = {
        "source": "lcu",
        "fetchedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "summoner": summoner,
        "count": len(games),
        "games": games,
    }
    return {
        "ok": True,
        "code": "ok",
        "message": f"已同步 {len(games)} 场 5v5 峡谷自定义对局",
        "payload": payload,
        "counts": counts,
        "failures": failures,
        "summoner": summoner,
    }


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="从本机 LCU 导出 5v5 峡谷自定义对局，供网站「合并导入」使用。",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help=f"输出 JSON 路径（默认 {DEFAULT_OUTPUT}）")
    parser.add_argument("--since", metavar="YYYY-MM-DD", help="只输出该日期及之后的对局")
    parser.add_argument("--no-rofl", action="store_true", help="不扫描 .rofl 回放文件")
    parser.add_argument("--dry-run", action="store_true", help="只打印结果，不写文件")
    parser.add_argument("--include-positions", action="store_true", help="导入客户端 lane/role 位置（可能不准）")
    parser.add_argument("--install", type=Path, help="英雄联盟客户端安装目录")
    parser.add_argument("--replays", type=Path, help="回放目录")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    since = None
    if args.since:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.since):
            safe_print("--since 需要 YYYY-MM-DD 格式")
            return 2
        since = args.since

    result = collect_games(
        install=args.install,
        replays=args.replays,
        since=since,
        use_rofl=not args.no_rofl,
        include_positions=args.include_positions,
    )
    if not result["ok"]:
        safe_print(result["message"])
        if result["code"] == "auth-failed":
            install = find_install(args.install)
            if install:
                safe_print(f"客户端目录：{install}")
        return 1

    payload = result["payload"]
    games = payload["games"]
    for game in games:
        safe_print("")
        safe_print(f"{game['date']} id={game['gameId']} winner={game['winner']} duration={game['duration']}s")
        for p in game["participants"]:
            safe_print(
                f"  {p['team']:<4} {p['name']} {p['champion']} "
                f"{p['kills']}/{p['deaths']}/{p['assists']}"
                + (f" {p['position']}" if p["position"] else "")
            )

    if args.dry_run:
        safe_print("")
        safe_print("[dry-run] 未写入文件")
        return 0

    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        safe_print(f"写入失败：{e}")
        return 1

    safe_print("")
    safe_print(f"[done] 已写入 {args.output}（{len(games)} 场）")
    safe_print("下一步：打开网站「数据」页 →「合并导入 LCU 对局」→ 选择该文件，或使用本地服务自动同步。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
