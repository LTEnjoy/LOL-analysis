import base64
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

lock = Path(r"D:\WeGameApps\英雄联盟\Riot Client Data\User Data\Config\lockfile")
parts = lock.read_text(errors="replace").strip().split(":")
riot_port, riot_token = parts[2], parts[3]
print(f"[riot] port={riot_port} token_len={len(riot_token)}")

league_ports = ["4694", "30716", "40017", "56259"]


def clean(text):
    if not text:
        return ""
    return text.replace(riot_token, "***")[:160]


def probe(port, token=None, path="/lol-summoner/v1/current-summoner"):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Basic " + base64.b64encode(f"riot:{token}".encode()).decode()
    try:
        r = requests.get(
            f"https://127.0.0.1:{port}{path}",
            headers=headers,
            timeout=4,
            verify=False,
        )
        return r.status_code, r.headers.get("WWW-Authenticate", ""), clean(r.text)
    except Exception as e:
        return None, "", f"{type(e).__name__}: {e}"


print("\n[riot client] with its own token")
for path in ["/riotclient/ux-state", "/lol-summoner/v1/current-summoner"]:
    code, www, body = probe(riot_port, riot_token, path)
    print(f"  {path} -> {code} auth={www!r} body={body!r}")

print("\n[league ports] no auth")
for port in league_ports:
    code, www, body = probe(port)
    print(f"  {port} -> {code} auth={www!r} body={body!r}")

print("\n[league ports] with riot client token")
for port in league_ports:
    code, www, body = probe(port, riot_token)
    print(f"  {port} -> {code} auth={www!r} body={body!r}")
