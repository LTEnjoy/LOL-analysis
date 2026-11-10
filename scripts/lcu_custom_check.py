import base64
import re
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

INSTALL = Path(r"D:\WeGameApps\英雄联盟")
OUT = Path(r"D:\tmp\lcu_custom_check_result.txt")
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


def get(path):
    try:
        r = s.get(f"https://127.0.0.1:{port}{path}", timeout=20, verify=False)
        return r
    except Exception as e:
        log(f"GET {path} -> {type(e).__name__}: {e}")
        return None


def summarize_list(label, path):
    r = get(path)
    if r is None:
        return
    log("")
    log(f"[{label}] HTTP {r.status_code} {path}")
    if r.status_code != 200:
        log(f"  body={r.text[:200]}")
        return
    data = r.json()
    games = data.get("games", data)
    if isinstance(games, dict):
        games = games.get("games", [])
    if not isinstance(games, list):
        log(f"  unexpected keys={sorted(data.keys())}")
        return
    seen = {}
    for g in games:
        seen[g.get("gameId")] = g
    log(f"  returned={len(games)} unique={len(seen)}")
    counts = {}
    for g in seen.values():
        k = (g.get("gameType"), g.get("queueId"), g.get("gameMode"))
        counts[k] = counts.get(k, 0) + 1
    for k, v in sorted(counts.items(), key=lambda x: -x[1]):
        log(f"  type={k[0]} queue={k[1]} mode={k[2]} count={v}")
    customs = [g for g in seen.values() if g.get("gameType") == "CUSTOM_GAME" or g.get("queueId") == 0]
    log(f"  customs={len(customs)}")
    for g in customs[:10]:
        log(f"    id={g.get('gameId')} queue={g.get('queueId')} date={g.get('gameCreation')}")


summarize_list(
    "by-puuid",
    f"/lol-match-history/v1/products/lol/{puuid}/matches?begIndex=0&endIndex=100",
)
summarize_list(
    "current-summoner",
    "/lol-match-history/v1/products/lol/current-summoner/matches?begIndex=0&endIndex=20",
)
summarize_list(
    "filter-custom",
    f"/lol-match-history/v1/products/lol/{puuid}/matches?begIndex=0&endIndex=20&gameType=CUSTOM_GAME",
)

for gid in ["10641059881", "HN1-10641059881", "11431077066"]:
    r = get(f"/lol-match-history/v1/games/{gid}")
    log("")
    log(f"[detail] id={gid} HTTP {getattr(r, 'status_code', None)}")
    if r is None or r.status_code != 200:
        if r is not None:
            log(f"  body={r.text[:200]}")
        continue
    d = r.json()
    ids = {x.get("participantId"): x.get("player", {}) for x in d.get("participantIdentities", [])}
    ps = d.get("participants", [])
    log(f"  type={d.get('gameType')} queue={d.get('queueId')} mode={d.get('gameMode')} players={len(ps)}")
    for p in ps:
        info = ids.get(p.get("participantId"), {})
        n = info.get("gameName") or info.get("summonerName") or info.get("riotIdGameName") or "?"
        st = p.get("stats", {})
        log(f"  team={p.get('teamId')} name={n} champ={p.get('championId')} {st.get('kills')}/{st.get('deaths')}/{st.get('assists')} win={st.get('win')}")

OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"written {OUT} ({len(lines)} lines)")
