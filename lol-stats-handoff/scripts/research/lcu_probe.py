import base64
import json
import re
import subprocess
import sys
from datetime import datetime

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def run_ps(script):
    p = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        capture_output=True,
    )
    return (p.stdout or b"").decode("utf-8", "replace")


def get_cmdline():
    ps = (
        "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
        "$p=Get-CimInstance Win32_Process -Filter \"name='LeagueClientUx.exe'\" "
        "| Select-Object -First 1; if($p){$p.CommandLine}"
    )
    text = run_ps(ps).strip()
    if "--remoting-auth-token" in text:
        return text, "cim"
    p = subprocess.run(
        ["wmic", "process", "where", "name='LeagueClientUx.exe'", "get", "CommandLine", "/value"],
        capture_output=True,
    )
    text = (p.stdout or b"").decode("utf-8", "replace").strip()
    if "--remoting-auth-token" in text:
        return text, "wmic"
    return text, "none"


def parse_auth(text):
    port = re.search(r"--app-port(?:=|\s+)\"?(\d+)", text)
    token = re.search(r"--remoting-auth-token(?:=|\s+)\"?([A-Za-z0-9_\-]+)", text)
    if port and token:
        return port.group(1), token.group(1)
    return None, None


def read_lockfiles():
    candidates = [
        r"D:\WeGameApps\英雄联盟\LeagueClient\lockfile",
        r"D:\WeGameApps\英雄联盟\Riot Client Data\User Data\Config\lockfile",
        r"C:\Users\LTEnj\AppData\Local\Riot Games\Riot Client\Config\lockfile",
    ]
    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                parts = f.read().strip().split(":")
            if len(parts) >= 5:
                print(f"[lockfile] {path} -> name={parts[0]} port={parts[2]} token_len={len(parts[3])}")
                if "League" in parts[0]:
                    return parts[2], parts[3]
        except Exception as e:
            print(f"[lockfile] {path} 读取失败: {type(e).__name__}")
    # 旧文件可能为空，忽略


cmdline, source = get_cmdline()
print(f"[auth] source={source} cmdline_len={len(cmdline)}")
port, token = parse_auth(cmdline)
if not port:
    port, token = read_lockfiles()
if not port:
    print("[auth] 未找到 LCU 端口/token。客户端可能未登录，或需要管理员权限读取进程命令行。")
    sys.exit(1)
print(f"[auth] port={port} token_len={len(token)}")

base = f"https://127.0.0.1:{port}"
s = requests.Session()
s.headers.update({
    "Authorization": "Basic " + base64.b64encode(f"riot:{token}".encode()).decode(),
    "Accept": "application/json",
})


def get(path):
    try:
        r = s.get(base + path, timeout=10, verify=False)
        return r.status_code, r.text
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


code, body = get("/lol-summoner/v1/current-summoner")
print(f"[summoner] HTTP {code}")
if code != 200:
    code2, body2 = get("/lol-login/v1/session")
    print(f"[login] HTTP {code2} body={body2[:300]}")
    sys.exit(1)

me = json.loads(body)
name = me.get("displayName") or me.get("gameName") or me.get("summonerName")
puuid = me.get("puuid", "")
print(f"[summoner] name={name} level={me.get('summonerLevel')} puuid_len={len(puuid)}")

code, body = get(f"/lol-match-history/v1/products/lol/{puuid}/matches?begIndex=0&endIndex=20")
print(f"[matches] HTTP {code}")
if code != 200:
    print(body[:500])
    sys.exit(1)

data = json.loads(body)
games = data.get("games", data)
if isinstance(games, dict):
    games = games.get("games", [])
print(f"[matches] count={len(games)}")

for g in games:
    ts = g.get("gameCreation")
    when = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M") if ts else "?"
    parts = g.get("participants") or []
    print(
        f"  gameId={g.get('gameId')} {when} queue={g.get('queueId')} "
        f"type={g.get('gameType')} mode={g.get('gameMode')} players={len(parts)}"
    )

customs = [g for g in games if g.get("gameType") == "CUSTOM_GAME" or g.get("queueId") == 0]
print(f"[custom] count={len(customs)}")
if not customs:
    print("最近 20 局里没有自定义对局。")
    sys.exit(0)

latest = customs[0]
code, body = get(f"/lol-match-history/v1/games/{latest.get('gameId')}")
print(f"[detail] gameId={latest.get('gameId')} HTTP {code}")
if code != 200:
    print(body[:500])
    sys.exit(1)

game = json.loads(body)
identities = {x.get("participantId"): x.get("player", {}) for x in game.get("participantIdentities", [])}
print(f"[detail] gameType={game.get('gameType')} queue={game.get('queueId')} duration={game.get('gameDuration')}s")
for p in game.get("participants", []):
    info = identities.get(p.get("participantId"), {})
    pname = (
        info.get("gameName")
        or info.get("summonerName")
        or info.get("riotIdGameName")
        or "?"
    )
    stats = p.get("stats", {})
    print(
        f"  team={p.get('teamId')} name={pname} champ={p.get('championId')} "
        f"{stats.get('kills')}/{stats.get('deaths')}/{stats.get('assists')} "
        f"win={stats.get('win')} puuid_len={len(info.get('puuid') or '')}"
    )
