import base64
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

INSTALL = Path(r"D:\WeGameApps\英雄联盟")
OUT = Path(r"D:\tmp\lcu_verify_result.txt")
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
                    return s, port, r.json()
    return None, None, None


s, port, me = find_session()
if not s:
    log("LCU auth failed")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    raise SystemExit(1)

puuid = me.get("puuid")
log(f"summoner={me.get('displayName') or me.get('gameName')} puuid_len={len(puuid)}")

all_games = []
for start in range(0, 500, 100):
    r = s.get(
        f"https://127.0.0.1:{port}/lol-match-history/v1/products/lol/{puuid}/matches"
        f"?begIndex={start}&endIndex={start + 100}",
        timeout=20,
        verify=False,
    )
    if r.status_code != 200:
        log(f"page {start}-{start+100} HTTP {r.status_code}")
        break
    data = r.json()
    g = data.get("games", data)
    if isinstance(g, dict):
        g = g.get("games", [])
    log(f"page {start}-{start+100} count={len(g)}")
    all_games.extend(g)
    if len(g) == 0:
        break

types = Counter((g.get("gameType"), g.get("queueId"), g.get("gameMode")) for g in all_games)
log(f"total={len(all_games)}")
for k, v in types.most_common():
    log(f"  type={k[0]} queue={k[1]} mode={k[2]} count={v}")

customs = [g for g in all_games if g.get("gameType") == "CUSTOM_GAME" or g.get("queueId") == 0]
log(f"customs={len(customs)}")
for g in customs[:10]:
    log(f"  custom id={g.get('gameId')} queue={g.get('queueId')} date={g.get('gameCreation')}")

if all_games:
    target = all_games[0]
    gid = target.get("gameId")
    r = s.get(f"https://127.0.0.1:{port}/lol-match-history/v1/games/{gid}", timeout=15, verify=False)
    log("")
    log(f"detail id={gid} HTTP {r.status_code}")
    if r.status_code == 200:
        d = r.json()
        ids = {x.get("participantId"): x.get("player", {}) for x in d.get("participantIdentities", [])}
        ps = d.get("participants", [])
        log(f"  type={d.get('gameType')} queue={d.get('queueId')} mode={d.get('gameMode')} players={len(ps)}")
        for p in ps:
            info = ids.get(p.get("participantId"), {})
            n = info.get("gameName") or info.get("summonerName") or info.get("riotIdGameName") or "?"
            st = p.get("stats", {})
            log(
                f"  team={p.get('teamId')} name={n} champ={p.get('championId')} "
                f"{st.get('kills')}/{st.get('deaths')}/{st.get('assists')} win={st.get('win')}"
            )

log("")
log("rofl files:")
rofl_roots = [
    Path(r"D:\WeGameApps\英雄联盟"),
    Path(r"C:\Users\LTEnj\Documents"),
    Path(r"C:\Users\LTEnj\AppData\Local\Riot Games"),
]
n = 0
for root in rofl_roots:
    if not root.exists():
        continue
    for p in root.rglob("*.rofl"):
        try:
            st = p.stat()
        except Exception:
            continue
        n += 1
        if n <= 20:
            log(f"  {datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M')} {st.st_size} {p}")
log(f"rofl_total={n}")

OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"written {OUT} ({len(lines)} lines)")
