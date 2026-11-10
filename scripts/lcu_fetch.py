import base64
import json
import re
import time
from datetime import datetime
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

INSTALL = Path(r"D:\WeGameApps\英雄联盟")
OUT = Path(r"D:\tmp\lcu_fetch_result.txt")
lines = []


def log(msg=""):
    lines.append(str(msg))


def find_creds():
    logs = sorted(
        (INSTALL / "LeagueClient").glob("*LeagueClientUx.log"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in logs[:3]:
        text = path.read_text(encoding="utf-8", errors="replace")
        tokens = re.findall(r'remoting-auth-token\s*[=:]\s*"?([A-Za-z0-9_\-]{8,})', text)
        ports = re.findall(r'app-port\s*[=:]\s*"?(\d+)', text)
        for token in dict.fromkeys(tokens):
            for port in dict.fromkeys(ports):
                s = requests.Session()
                s.headers.update({
                    "Authorization": "Basic " + base64.b64encode(f"riot:{token}".encode()).decode(),
                    "Accept": "application/json",
                })
                try:
                    r = s.get(
                        f"https://127.0.0.1:{port}/lol-summoner/v1/current-summoner",
                        timeout=5,
                        verify=False,
                    )
                except Exception:
                    continue
                if r.status_code == 200:
                    return s, port, path, r.json()
    return None, None, None, None


def get_json(session, port, path):
    r = session.get(f"https://127.0.0.1:{port}{path}", timeout=15, verify=False)
    if r.status_code != 200:
        return None, r.status_code, r.text[:300]
    try:
        return r.json(), r.status_code, ""
    except Exception as e:
        return None, r.status_code, f"{type(e).__name__}: {e}"


def fmt_time(ms):
    try:
        return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "?"


session, port, log_path, me = find_creds()
if not session:
    log("未能通过 LCU 认证。")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    raise SystemExit(1)

name = me.get("displayName") or me.get("gameName") or me.get("summonerName") or "?"
puuid = me.get("puuid") or ""
log(f"LCU port={port}")
log(f"credential_source={log_path.name}")
log(f"summoner={name} level={me.get('summonerLevel')} puuid_len={len(puuid)}")
log("")

if not puuid:
    log("当前账号没有返回 puuid，无法查询战绩。")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    raise SystemExit(1)

data, code, err = get_json(
    session, port,
    f"/lol-match-history/v1/products/lol/{puuid}/matches?begIndex=0&endIndex=100",
)
log(f"match_list HTTP {code} {err}")
if data is None:
    OUT.write_text("\n".join(lines), encoding="utf-8")
    raise SystemExit(1)

games = data.get("games", data)
if isinstance(games, dict):
    log(f"games_container_keys={sorted(games.keys())}")
    games = games.get("games", [])
if not isinstance(games, list):
    games = []

log(f"games={len(games)}")
for g in games:
    parts = g.get("participants") or []
    log(
        f"  {fmt_time(g.get('gameCreation'))} id={g.get('gameId')} "
        f"queue={g.get('queueId')} type={g.get('gameType')} "
        f"mode={g.get('gameMode')} players={len(parts)} "
        f"duration={g.get('gameDuration')}s"
    )

customs = [
    g for g in games
    if (g.get("gameType") == "CUSTOM_GAME" or g.get("queueId") == 0)
    and g.get("gameMode") == "CLASSIC"
]
log("")
log(f"custom_games={len(customs)}")

for g in customs[:3]:
    game_id = g.get("gameId")
    detail, dcode, derr = get_json(session, port, f"/lol-match-history/v1/games/{game_id}")
    log("")
    log(f"detail id={game_id} HTTP {dcode} {derr}")
    if detail is None:
        continue
    identities = {
        x.get("participantId"): x.get("player", {})
        for x in detail.get("participantIdentities", [])
    }
    participants = detail.get("participants", [])
    log(
        f"  type={detail.get('gameType')} queue={detail.get('queueId')} "
        f"mode={detail.get('gameMode')} players={len(participants)}"
    )
    for p in participants:
        info = identities.get(p.get("participantId"), {})
        pname = info.get("gameName") or info.get("summonerName") or info.get("riotIdGameName") or "?"
        tag = info.get("tagLine") or info.get("riotIdTagline") or ""
        if tag:
            pname = f"{pname}#{tag}"
        st = p.get("stats", {})
        log(
            f"  team={p.get('teamId')} name={pname} "
            f"champ={p.get('championId')} "
            f"{st.get('kills')}/{st.get('deaths')}/{st.get('assists')} "
            f"win={st.get('win')} puuid_len={len(info.get('puuid') or '')}"
        )

OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"written {OUT} ({len(lines)} lines)")
