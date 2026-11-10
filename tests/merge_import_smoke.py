#!/usr/bin/env python3
"""Headless Chrome smoke test for the website's LCU merge import.

Injects a synchronous harness after the site's own script, runs Chrome with
--dump-dom, and checks the JSON result printed by the harness.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from html import unescape
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SITE = BASE / "website" / "lol_stats.html"

CHROME_CANDIDATES = [
    os.environ.get("CHROME"),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

LONG_CHAMPION = "超长英雄名称测试ABCDEFGHIJKLMN"


def seed_participant(name, team, kills=0, deaths=0, assists=0, champion="", position=""):
    return {
        "name": name,
        "team": team,
        "kills": kills,
        "deaths": deaths,
        "assists": assists,
        "champion": champion,
        "position": position,
    }


def build_payload():
    red = [
        seed_participant("seed0", "red", "12", 2, 5, LONG_CHAMPION, "打野"),
        seed_participant("seed1", "red", 3, 4, 5, "英雄A", "乱写"),
        seed_participant("seed2", "red", 1, 0, 9, "英雄B", "辅助"),
        seed_participant("seed3", "red", -3, "x", 2, "英雄C", "上单"),
        seed_participant("seed4", "red", 7, 1, 4, "英雄D", "中单"),
    ]
    blue = [
        seed_participant(" New0 ", "blue", 2, 2, 2, "新英雄0", ""),
        seed_participant("new1", "blue", 2, 2, 2, "新英雄1", ""),
        seed_participant("New2", "blue", 2, 2, 2, "新英雄2", ""),
        seed_participant("New3", "blue", 2, 2, 2, "新英雄3", ""),
        seed_participant("New4", "blue", 2, 2, 2, "新英雄4", ""),
    ]
    game_a = {
        "gameId": 9001,
        "date": "2026-11-04",
        "createdAt": "2026-11-04T20:00:00",
        "winner": "red",
        "participants": red + blue,
    }
    game_b = {
        "gameId": 9002,
        "createdAt": "2026-11-03T21:30:00",
        "winner": "blue",
        "participants": [
            seed_participant("SEED0", "red", 1, 1, 1),
            seed_participant("seed1", "red", 1, 1, 1),
            seed_participant("seed2", "red", 1, 1, 1),
            seed_participant("seed3", "red", 1, 1, 1),
            seed_participant("seed4", "red", 1, 1, 1),
            seed_participant("New0", "blue", 1, 1, 1),
            seed_participant("New1", "blue", 1, 1, 1),
            seed_participant("New2", "blue", 1, 1, 1),
            seed_participant("New3", "blue", 1, 1, 1),
            seed_participant("New4", "blue", 1, 1, 1),
        ],
    }
    invalid = {
        "gameId": 9004,
        "date": "2026-11-05",
        "winner": "red",
        "participants": game_a["participants"][:9],
    }
    return {
        "source": "lcu",
        "fetchedAt": "2026-11-05T12:00:00",
        "games": [game_a, json.loads(json.dumps(game_a)), invalid, game_b],
    }


HARNESS = r"""
<script>
(function () {
  const failures = [];
  const check = (cond, msg) => { if (!cond) failures.push(msg); };
  const eq = (got, want, msg) => check(got === want, msg + ' (got ' + JSON.stringify(got) + ', want ' + JSON.stringify(want) + ')');

  state = emptyState();
  const seeded = [];
  for (let i = 0; i < 10; i++) {
    seeded.push({ id: 'p_seed_' + i, name: 'Seed' + i, active: true, createdAt: '2026-01-01T00:00:00.000Z' });
  }
  state.players = seeded;
  state.matches = [{
    id: 'm_manual_1',
    date: '2026-01-02',
    createdAt: '2026-01-02T12:00:00.000Z',
    winner: 'red',
    note: '手动',
    participants: seeded.map((p, i) => ({
      playerId: p.id,
      team: i < 5 ? 'red' : 'blue',
      kills: 1, deaths: 1, assists: 1, champion: '', position: ''
    }))
  }];
  saveState();

  const baseMatches = state.matches.length;
  const basePlayers = state.players.length;

  const r1 = mergeLcuGames(PAYLOAD);
  eq(r1.added, 2, 'first merge adds 2 games');
  eq(r1.duplicates, 1, 'first merge counts duplicate game');
  eq(r1.skipped.length, 1, 'first merge skips invalid game');
  eq(r1.newPlayers.length, 5, 'first merge creates 5 players');
  eq(state.matches.length, baseMatches + 2, 'first merge appends matches');
  eq(state.players.length, basePlayers + 5, 'first merge appends players');

  check(state.matches.some(m => m.id === 'm_lcu_9001'), 'game 9001 added');
  check(state.matches.some(m => m.id === 'm_lcu_9002'), 'game 9002 added');
  check(!state.matches.some(m => m.id === 'm_lcu_9004'), 'invalid game not added');

  const m1 = state.matches.find(m => m.id === 'm_lcu_9001');
  eq(m1.winner, 'red', 'game 9001 winner');
  eq(m1.date, '2026-11-04', 'game 9001 date kept');
  eq(m1.participants.length, 10, 'game 9001 has 10 participants');
  eq(m1.participants.filter(p => p.team === 'red').length, 5, 'game 9001 has 5 red');
  eq(m1.participants.filter(p => p.team === 'blue').length, 5, 'game 9001 has 5 blue');

  const matched = m1.participants.filter(p => seeded.some(s => s.id === p.playerId)).length;
  eq(matched, 5, 'case-insensitive name matching reuses seeded players');
  const created = state.players.filter(p => !seeded.some(s => s.id === p.id));
  eq(created.length, 5, 'created players count');
  check(created.every(p => p.name === p.name.trim() && p.name.length > 0), 'new names trimmed');
  check(created.every(p => p.active === true), 'new players are active');

  const seed0Part = m1.participants.find(p => p.playerId === 'p_seed_0');
  eq(seed0Part.kills, 12, 'numeric string kills parsed');
  eq(seed0Part.champion.length, 20, 'champion capped at 20 chars');
  eq(seed0Part.position, '打野', 'valid position kept');
  eq(m1.participants.find(p => p.playerId === 'p_seed_1').position, '', 'invalid position cleared');
  eq(m1.participants.find(p => p.playerId === 'p_seed_2').position, '辅助', 'second valid position kept');

  const seed3Part = m1.participants.find(p => p.playerId === 'p_seed_3');
  eq(seed3Part.kills, 0, 'negative kills clamped to 0');
  eq(seed3Part.deaths, 0, 'non-numeric deaths clamped to 0');

  const m2 = state.matches.find(m => m.id === 'm_lcu_9002');
  eq(m2.date, '2026-11-03', 'date falls back to createdAt');
  eq(m2.winner, 'blue', 'game 9002 winner');

  const manual = state.matches.find(m => m.id === 'm_manual_1');
  eq(manual.participants.length, 10, 'manual match intact');
  eq(manual.note, '手动', 'manual note intact');

  const r2 = mergeLcuGames(PAYLOAD);
  eq(r2.added, 0, 'second merge adds 0');
  eq(r2.duplicates, 3, 'second merge counts all duplicates');
  eq(state.matches.length, baseMatches + 2, 'second merge does not append');

  const rawArray = [{
    gameId: 9003,
    date: '2026-11-05',
    winner: 'red',
    participants: m1.participants.map(p => ({
      name: state.players.find(x => x.id === p.playerId).name,
      team: p.team,
      kills: 5, deaths: 2, assists: 3, champion: '测试', position: ''
    }))
  }];
  const r3 = mergeLcuGames(rawArray);
  eq(r3.added, 1, 'raw array payload accepted');
  eq(r3.newPlayers.length, 0, 'raw array reuses existing players');

  let threw = false;
  try { mergeLcuGames({ hello: 1 }); } catch (err) { threw = true; }
  check(threw, 'payload without games throws');

  const expectedMatches = state.matches.length;
  const expectedPlayers = state.players.length;
  state = emptyState();
  loadState();
  eq(state.matches.length, expectedMatches, 'reload keeps matches');
  eq(state.players.length, expectedPlayers, 'reload keeps players');

  const seed0 = calcPlayerStats().find(s => s.player.id === 'p_seed_0');
  check(seed0 && seed0.games === 4, 'stats include manual + 3 merged games');

  setMergeStatus('<strong>合并完成：</strong>测试');
  const exportHtml = buildExportHtml();
  const exportDoc = new DOMParser().parseFromString(exportHtml, 'text/html');
  const exportedStatus = exportDoc.getElementById('merge-status');
  check(exportedStatus && exportedStatus.textContent === '' && exportedStatus.hidden, 'export HTML clears merge status');
  const exportSeed = JSON.parse(exportDoc.getElementById('seed-data').textContent);
  check(exportSeed.matches.some(m => m.id === 'm_lcu_9001'), 'export HTML seed contains merged data');
  const exportJson = JSON.parse(buildExportJson());
  eq(exportJson.data.matches.length, expectedMatches, 'export JSON keeps all matches');

  if (window.REAL_PAYLOAD) {
    state = emptyState();
    saveState();
    const total = window.REAL_PAYLOAD.games.length;
    const rr1 = mergeLcuGames(window.REAL_PAYLOAD);
    eq(rr1.added, total, 'real sync: all games added');
    eq(rr1.duplicates, 0, 'real sync: no duplicates');
    eq(rr1.skipped.length, 0, 'real sync: nothing skipped');
    eq(state.matches.length, total, 'real sync: match count');
    check(state.matches.every(m => m.participants.length === 10), 'real sync: all games have 10 participants');
    check(new Set(state.matches.map(m => m.id)).size === total, 'real sync: match ids unique');
    check(state.matches.every(m => m.participants.every(p => state.players.some(x => x.id === p.playerId))),
      'real sync: player refs resolve');
    check(state.players.length >= 10, 'real sync: players created');
    const rr2 = mergeLcuGames(window.REAL_PAYLOAD);
    eq(rr2.added, 0, 'real sync: second run adds 0');
    eq(rr2.duplicates, total, 'real sync: second run all duplicates');
    eq(state.matches.length, total, 'real sync: second run no append');
    state = emptyState();
    loadState();
    eq(state.matches.length, total, 'real sync: reload keeps matches');
    check(calcPlayerStats().some(s => s.games > 0), 'real sync: stats computed');
  }

  check(!window.__pageErrors || window.__pageErrors.length === 0,
    'no page errors: ' + JSON.stringify(window.__pageErrors || []));

  const result = {
    ok: failures.length === 0,
    failures: failures,
    summary: { matches: state.matches.length, players: state.players.length },
  };
  const pre = document.createElement('pre');
  pre.id = 'test-result';
  pre.textContent = JSON.stringify(result);
  document.body.appendChild(pre);
  document.title = result.ok ? 'PASS' : 'FAIL';
})();
</script>
"""

COLLECTOR = r"""
<script>window.__pageErrors = []; window.addEventListener('error', function (e) { window.__pageErrors.push(String(e.message || e.error)); });</script>
"""


def find_chrome():
    for candidate in CHROME_CANDIDATES:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sync-file", type=Path, help="also merge a real lcu_sync.py output file")
    args = parser.parse_args()

    chrome = find_chrome()
    if not chrome:
        print("Chrome not found; set CHROME env var.")
        return 2

    real_payload = "null"
    if args.sync_file:
        raw = json.loads(args.sync_file.read_text(encoding="utf-8"))
        games = raw.get("games") if isinstance(raw, dict) else raw
        if not isinstance(games, list) or not games:
            print(f"{args.sync_file} has no games")
            return 2
        sync_payload = raw if isinstance(raw, dict) else {"games": games}
        real_payload = json.dumps(sync_payload, ensure_ascii=False).replace("</", "<\\/")

    html = SITE.read_text(encoding="utf-8")
    seed_tag = '<script type="application/json" id="seed-data">null</script>'
    if seed_tag not in html:
        print("Could not find seed-data tag in site.")
        return 2
    html = html.replace(seed_tag, seed_tag + COLLECTOR, 1)

    synthetic = json.dumps(build_payload(), ensure_ascii=False).replace("</", "<\\/")
    html = html.replace(
        "</body>",
        "<script>const PAYLOAD = " + synthetic + ";"
        + "window.REAL_PAYLOAD = " + real_payload + ";</script>" + HARNESS + "</body>",
        1,
    )

    work = Path(tempfile.mkdtemp(prefix="lol_merge_test_"))
    page = work / "merge_test.html"
    profile = work / "chrome-profile"
    page.write_text(html, encoding="utf-8")

    cmd = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={profile}",
        "--virtual-time-budget=5000",
        "--dump-dom",
        page.as_uri(),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    match = re.search(r'<pre id="test-result">(.*?)</pre>', proc.stdout or "", re.S)
    if not match:
        print("Test harness did not produce a result.")
        tail = (proc.stdout or "")[-2000:]
        err = (proc.stderr or "")[-2000:]
        print("--- stdout tail ---\n" + tail)
        print("--- stderr tail ---\n" + err)
        return 1

    result = json.loads(unescape(match.group(1)))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
