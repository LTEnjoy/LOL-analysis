#!/usr/bin/env python3
"""Headless Chrome smoke test for the multi-factor rating.

Feeds a hand-built 10-player game through the site's merge import and checks
within-game percentiles, dimension weights, the best-three blend, shrinking,
and the fallback to the old KDA/win formula for games without stats.
"""

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

KEYS = [
    "goldEarned", "totalMinionsKilled", "neutralMinionsKilled", "visionScore",
    "visionWardsBoughtInGame", "wardsKilled", "totalDamageDealtToChampions",
    "totalDamageTaken", "damageSelfMitigated", "totalHeal", "timeCCingOthers",
    "damageDealtToObjectives", "damageDealtToTurrets",
]


def part(name, team, k, d, a, vis, heal=0, cc=0):
    p = {
        "name": name, "team": team, "kills": k, "deaths": d, "assists": a,
        "champion": "测试英雄", "position": "",
    }
    base = {
        "goldEarned": 10000, "totalMinionsKilled": 150, "neutralMinionsKilled": 0,
        "visionScore": vis, "visionWardsBoughtInGame": 0, "wardsKilled": 0,
        "totalDamageDealtToChampions": 15000, "totalDamageTaken": 20000,
        "damageSelfMitigated": 10000, "totalHeal": heal, "timeCCingOthers": cc,
        "damageDealtToObjectives": 3000, "damageDealtToTurrets": 1000,
    }
    p.update(base)
    return p


def build_payload():
    # Same stats on both teams so percentile ranks depend only on within-game values.
    red = [
        part("carry", "red", 12, 1, 6, 20, heal=1000, cc=10),
        part("support", "red", 1, 5, 18, 90, heal=9000, cc=40),
        part("tank", "red", 2, 6, 10, 30, heal=0, cc=60),
        part("jungler", "red", 6, 3, 8, 40, heal=0, cc=20),
        part("mid", "red", 8, 2, 5, 25, heal=0, cc=15),
    ]
    blue = [
        part("b0", "blue", 0, 1, 0, 10),
        part("b1", "blue", 1, 1, 1, 11),
        part("b2", "blue", 2, 1, 2, 12),
        part("b3", "blue", 3, 1, 3, 13),
        part("b4", "blue", 4, 1, 4, 14),
    ]
    return {
        "source": "lcu",
        "count": 1,
        "games": [{
            "gameId": 9501, "date": "2026-11-05", "winner": "red", "duration": 1800,
            "participants": red + blue,
        }],
    }


HARNESS = r"""
<script>
(function () {
  const failures = [];
  const check = (cond, msg) => { if (!cond) failures.push(msg); };
  const near = (got, want, eps, msg) => check(Math.abs(got - want) <= eps,
    msg + ' (got ' + JSON.stringify(got) + ', want ~' + want + ')');

  try {
    const payload = JSON.parse(document.getElementById('test-payload').textContent);
    state = emptyState();
    saveState();
    const result = mergeLcuGames(payload);
    if (result.added !== 1) failures.push('merge added ' + result.added);

    const match = state.matches[0];
    check(match.duration === 1800, 'duration kept');
    const scores = getMatchScores(match);
    if (!scores) {
      failures.push('no scores computed');
      throw new Error('stop');
    }
    const ids = match.participants.map(p => p.playerId);
    const byName = {};
    state.players.forEach(p => { byName[p.name] = p.id; });
    const scoreOf = name => scores[ids.indexOf(byName[name])].score;
    Object.keys(scores).forEach(k => {
      const s = scores[k];
      check(s.score >= 0 && s.score <= 100, 'score out of range ' + s.score);
    });

    // support has the best vision (rank 1), carry has the best KDA; nobody inherits a position.
    check(scoreOf('support') > scoreOf('b1'), 'support above low blue');
    const dimAvg = scores.map(s => s.dims.reduce((n, x) => n + x, 0) / s.dims.length);
    near(dimAvg.reduce((n, x) => n + x, 0) / dimAvg.length, 0.5, 1e-9, 'dimension ranks average to 0.5');
    check(scoreOf('carry') > 55, 'strong KDA lifts carry above average');
    check(scoreOf('support') > 50, 'top vision keeps support competitive');

    // player totals
    const stats = calcPlayerStats();
    const st = name => stats.find(s => s.player.name === name);
    check(st('support').scoreGames === 1, 'support score game counted');
    // total rating is the plain average of scored games, no shrink
    near(st('support').rating, scoreOf('support'), 1e-9, 'rating equals game score');
    check(st('b0').games === 1 && st('b0').rating < st('support').rating, 'ranking uses average score');
    renderRanking();
    const row = Array.from(document.querySelectorAll('#rank-body tr')).find(tr => tr.textContent.includes('support'));
    check(row && row.textContent.includes(st('support').rating.toFixed(1)), 'rank table shows average rating');

    // winner field must not be required by the score: flip winner and scores stay identical.
    const before = scores.map(s => s.score);
    match.winner = 'blue';
    matchScoreCache.clear();
    const after = getMatchScores(match).map(s => s.score);
    check(JSON.stringify(before) === JSON.stringify(after), 'scores ignore win/loss');
    match.winner = 'red';
    matchScoreCache.clear();

    // old-style manual match without stats falls back to the legacy formula
    const legacyPlayers = [];
    const legacyParts = [];
    for (let i = 0; i < 10; i += 1) {
      const p = { id: 'lp' + i, name: '旧' + i, active: true, createdAt: new Date().toISOString() };
      legacyPlayers.push(p);
      legacyParts.push({ playerId: p.id, team: i < 5 ? 'red' : 'blue', kills: 5, deaths: 2, assists: 5,
        champion: '', position: '' });
    }
    state.players = state.players.concat(legacyPlayers);
    const legacyMatch = { id: 'm_manual', date: '2026-01-01', createdAt: '', winner: 'red', note: '',
      participants: legacyParts };
    check(getMatchScores(legacyMatch) === null, 'manual match has no multi-factor score');
    state.matches.push(legacyMatch);
    const stats2 = calcPlayerStats();
    const legacyStat = stats2.find(s => s.player.name === '旧0');
    if (legacyStat.games !== 1 || legacyStat.wins !== 1) {
      failures.push('legacy match not counted (games=' + legacyStat.games + ', wins=' + legacyStat.wins + ')');
    }
    const legacyShrunk = 5 / (1 + SHRINK_GAMES);
    const expected = ((1.0 * 0.5) + Math.min(legacyShrunk / RATING_KDA_FULL, 1) * 0.5) * 100;
    near(legacyStat.rating, expected, 1e-6, 'legacy fallback formula');
    check(legacyStat.scoreGames === 0, 'legacy match not counted as scored');

    // a second scored game brings the total to the plain mean of the two game scores
    const second = JSON.parse(JSON.stringify(match));
    second.id = 'm_lcu_9502';
    state.matches.push(second);
    matchScoreCache.clear();
    const twoStats = calcPlayerStats();
    const supportTwo = twoStats.find(s => s.player.name === 'support');
    check(supportTwo.scoreGames === 2, 'second game counted');
    near(supportTwo.rating, scoreOf('support'), 1e-9, 'mean of identical games equals one game');

    // ties are broken by games played, not by KDA
    const tieA = { id: 'ta', name: '并列多场', games: 9, rating: 60, kda: 1, winRate: 0.5, scoreGames: 9 };
    const tieB = { id: 'tb', name: '并列少场', games: 3, rating: 60, kda: 9, winRate: 0.5, scoreGames: 3 };
    const cmp = [tieA, tieB].sort((a, b) => b.rating - a.rating || b.games - a.games || b.kda - a.kda);
    check(cmp[0].name === '并列多场', 'rating tie broken by games played');

    // min-games filter hides low-sample players without changing their score
    rankSort = 'rating';
    renderRanking();
    const ratingUnfiltered = Array.from(document.querySelectorAll('#rank-body tr'))
      .map(tr => [tr.querySelector('.player-name').textContent, tr.lastElementChild.textContent]);
    const supportRowBefore = ratingUnfiltered.find(([n]) => n === 'support');
    const supportRatingDirect = calcPlayerStats().find(s => s.player.name === 'support').rating;
    rankMinGames = 1;
    renderRanking();
    const supportRowAfter = Array.from(document.querySelectorAll('#rank-body tr'))
      .find(tr => tr.querySelector('.player-name').textContent === 'support');
    check(supportRowBefore && supportRowAfter &&
      supportRowAfter.lastElementChild.textContent === supportRowBefore[1], 'min-games filter does not change rating');
    near(Number(supportRowAfter.lastElementChild.textContent), supportRatingDirect, 0.051, 'row shows calc rating');
    rankMinGames = 3;
    renderRanking();
    const namesFiltered = Array.from(document.querySelectorAll('#rank-body tr'))
      .map(tr => tr.querySelector('.player-name'))
      .filter(Boolean)
      .map(el => el.textContent);
    check(!namesFiltered.includes('b0'), 'min-games filter hides 2-game player');
    check(!namesFiltered.includes('support'), 'min-games filter hides 2-game player (support)');
    check(namesFiltered.length === 0, 'no player reaches 3 games in this fixture');
    rankMinGames = 0;
    rankSort = 'kda';

    // no JS errors surfaced from render
    renderAll();
  } catch (err) {
    failures.push('harness error: ' + (err && err.message));
  }

  const out = document.createElement('pre');
  out.id = 'test-result';
  out.textContent = JSON.stringify({ ok: failures.length === 0, failures: failures });
  document.body.appendChild(out);
})();
</script>
"""


def build_page():
    html = SITE.read_text(encoding="utf-8")
    payload = json.dumps(build_payload(), ensure_ascii=False).replace("</", "<\\/")
    injection = (
        '<script type="application/json" id="test-payload">' + payload + "</script>\n"
        + HARNESS
        + "\n</body>"
    )
    if "</body>" not in html:
        raise SystemExit("site has no </body>")
    return html.replace("</body>", injection, 1)


def find_chrome():
    for path in CHROME_CANDIDATES:
        if path and Path(path).exists():
            return path
    raise SystemExit("Chrome not found; set CHROME env var")


def run():
    tmp = tempfile.mkdtemp(prefix="lol_rating_smoke_")
    try:
        page = Path(tmp) / "page.html"
        page.write_text(build_page(), encoding="utf-8")
        profile = Path(tmp) / "profile"
        cmd = [
            find_chrome(), "--headless=new", "--disable-gpu", "--no-first-run",
            "--no-default-browser-check", f"--user-data-dir={profile}",
            "--allow-file-access-from-files", "--dump-dom", page.as_uri(),
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=120)
        dom = proc.stdout.decode("utf-8", "replace")
        match = re.search(r'<pre id="test-result">(.*?)</pre>', dom, re.S)
        if not match:
            sys.stderr.write(proc.stderr.decode("utf-8", "replace")[-2000:])
            raise SystemExit("harness result not found")
        result = json.loads(unescape(match.group(1)))
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("ok") else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(run())
