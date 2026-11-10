import base64
import json
import re
from datetime import datetime
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

INSTALL = Path(r"D:\WeGameApps\英雄联盟")
REPLAY_ROOT = Path(r"C:\Users\LTEnj\Documents\League of Legends\Replays")
OUT_JSON = Path(r"D:\tmp\lcu_custom_games.json")
OUT_TXT = Path(r"D:\tmp\lcu_custom_games_summary.txt")

LANE_MAP = {
    ("TOP", "SOLO"): "上单",
    ("JUNGLE", "NONE"): "打野",
    ("MIDDLE", "SOLO"): "中单",
    ("BOTTOM", "DUO_CARRY"): "ADC",
    ("BOTTOM", "DUO_SUPPORT"): "辅助",
}
lines = []


def log(msg=""):
    lines.append(str(msg))


def find_session():
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
                    r = s.get(f"https://127.0.0.1:{port}/lol-summoner/v1/current-summoner", timeout=5, verify=False)
                except Exception:
                    continue
                if r.status_code == 200:
                    return s, port
    return None, None


def get_json(s, port, path):
    try:
        r = s.get(f"https://127.0.0.1:{port}{path}", timeout=20, verify=False)
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}"
    try:
        return r.json(), ""
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


s, port = find_session()
if not s:
    log("LCU auth failed")
    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")
    raise SystemExit(1)

champs_raw, err = get_json(s, port, "/lol-game-data/assets/v1/champion-summary.json")
champ_names = {}
if isinstance(champs_raw, list):
    champ_names = {c.get("id"): c.get("name") for c in champs_raw if isinstance(c, dict)}
log(f"LCU port={port} champion_names={len(champ_names)}")

rofl_ids = []
for p in REPLAY_ROOT.glob("*.rofl"):
    m = re.search(r"(\d{6,})", p.stem)
    if m:
        rofl_ids.append(m.group(1))
rofl_ids = list(dict.fromkeys(rofl_ids))
log(f"replays={len(rofl_ids)}")

recent_ids = []
me, _ = get_json(s, port, "/lol-summoner/v1/current-summoner")
puuid = (me or {}).get("puuid")
if puuid:
    data, _ = get_json(
        s, port,
        f"/lol-match-history/v1/products/lol/{puuid}/matches?begIndex=0&endIndex=100",
    )
    games = (data or {}).get("games", data or {})
    if isinstance(games, dict):
        games = games.get("games", [])
    for g in games or []:
        if g.get("gameType") == "CUSTOM_GAME":
            recent_ids.append(str(g.get("gameId")))
log(f"recent_custom_ids={len(set(recent_ids))}")

all_ids = list(dict.fromkeys(recent_ids + rofl_ids))
log(f"candidate_ids={len(all_ids)}")

customs = []
failed = []
non_custom = 0
not_5v5 = 0
for i, gid in enumerate(all_ids, 1):
    detail, err = get_json(s, port, f"/lol-match-history/v1/games/{gid}")
    if detail is None:
        failed.append((gid, err))
        continue
    if detail.get("gameType") != "CUSTOM_GAME":
        non_custom += 1
        continue
    ps = detail.get("participants") or []
    blue = [p for p in ps if p.get("teamId") == 100]
    red = [p for p in ps if p.get("teamId") == 200]
    if len(ps) != 10 or len(blue) != 5 or len(red) != 5:
        not_5v5 += 1
        continue

    identities = {
        x.get("participantId"): x.get("player", {})
        for x in detail.get("participantIdentities", [])
    }
    blue_won = any((p.get("stats") or {}).get("win") for p in blue)
    winner = "blue" if blue_won else "red"
    created = detail.get("gameCreation") or 0
    try:
        dt = datetime.fromtimestamp(created / 1000)
    except Exception:
        dt = None
    participants = []
    for p in ps:
        info = identities.get(p.get("participantId"), {})
        name = info.get("gameName") or info.get("summonerName") or info.get("riotIdGameName") or ""
        if not name:
            continue
        st = p.get("stats") or {}
        tl = p.get("timeline") or {}
        position = LANE_MAP.get((tl.get("lane"), tl.get("role")), "")
        participants.append({
            "name": name,
            "puuid": info.get("puuid", ""),
            "team": "blue" if p.get("teamId") == 100 else "red",
            "kills": st.get("kills", 0),
            "deaths": st.get("deaths", 0),
            "assists": st.get("assists", 0),
            "champion": champ_names.get(p.get("championId"), str(p.get("championId") or "")),
            "position": position,
            "win": bool(st.get("win")),
        })
    if len(participants) != 10:
        not_5v5 += 1
        continue
    customs.append({
        "gameId": int(gid),
        "date": dt.strftime("%Y-%m-%d") if dt else "",
        "createdAt": dt.isoformat() if dt else "",
        "queueId": detail.get("queueId"),
        "winner": winner,
        "duration": detail.get("gameDuration"),
        "participants": participants,
    })

customs.sort(key=lambda g: (g["createdAt"], g["gameId"]), reverse=True)
OUT_JSON.write_text(json.dumps(customs, ensure_ascii=False, indent=2), encoding="utf-8")

log("")
log(f"custom_5v5={len(customs)} non_custom={non_custom} not_5v5={not_5v5} failed={len(failed)}")
for gid, err in failed[:10]:
    log(f"  failed id={gid} {err}")
for g in customs:
    blue = [p for p in g["participants"] if p["team"] == "blue"]
    red = [p for p in g["participants"] if p["team"] == "red"]
    log("")
    log(f"{g['date']} id={g['gameId']} winner={g['winner']} duration={g['duration']}s")
    for p in blue + red:
        log(
            f"  {p['team']:<4} {p['name']} {p['champion']} "
            f"{p['kills']}/{p['deaths']}/{p['assists']} {p['position']} win={p['win']}"
        )

OUT_TXT.write_text("\n".join(lines), encoding="utf-8")
print(f"written {OUT_JSON} and {OUT_TXT}: customs={len(customs)}")
