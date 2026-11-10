#!/usr/bin/env python3
"""Headless Chrome smoke test for backfilling rating stats into imported games.

An older bridge imported games without the 13 rating fields, so they all fell
back to the legacy win-rate/KDA formula. Syncing again must fill those fields
by gameId without touching winners, players or hand-edited KDA.
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

STATS_KEYS = [
    "goldEarned", "totalMinionsKilled", "neutralMinionsKilled", "visionScore",
    "visionWardsBoughtInGame", "wardsKilled", "totalDamageDealtToChampions",
    "totalDamageTaken", "damageSelfMitigated", "totalHeal", "timeCCingOthers",
    "damageDealtToObjectives", "damageDealtToTurrets",
]


def participant(name, team, kills, index, with_stats):
    p = {
        "name": name, "team": team, "kills": kills, "deaths": 2, "assists": 4,
        "champion": "测试英雄", "position": "",
    }
    if with_stats:
        p.update({
            "goldEarned": 9000 + index * 500, "totalMinionsKilled": 100 + index * 10,
            "neutralMinionsKilled": index, "visionScore": 10 + index * 8,
            "visionWardsBoughtInGame": index, "wardsKilled": index % 3,
            "totalDamageDealtToChampions": 12000 + index * 900, "totalDamageTaken": 18000 + index * 400,
            "damageSelfMitigated": 8000 + index * 300, "totalHeal": index * 700,
            "timeCCingOthers": index * 6, "damageDealtToObjectives": 2500 + index * 200,
            "damageDealtToTurrets": 900 + index * 150,
        })
    return p


def build_payload(with_stats, games=2):
    names = [f"玩家{i}" for i in range(10)]
    out = []
    for n in range(games):
        parts = [participant(name, "red" if i < 5 else "blue", 3 + i, i, with_stats)
                 for i, name in enumerate(names)]
        out.append({"gameId": 9300 + n, "date": "2026-11-0%d" % (n + 1), "winner": "red",
                    "duration": 1800, "participants": parts})
    return {"source": "lcu", "count": len(out), "games": out}


HARNESS = r"""
<script>
(async function () {
  const failures = [];
  const check = (cond, msg) => { if (!cond) failures.push(msg); };
  const eq = (got, want, msg) => check(got === want, msg + ' (got ' + JSON.stringify(got) + ', want ' + JSON.stringify(want) + ')');
  const near = (got, want, eps, msg) => check(Math.abs(got - want) <= eps, msg + ' (got ' + got + ')');

  try {
    const oldPayload = JSON.parse(document.getElementById('legacy-payload').textContent);
    const newPayload = JSON.parse(document.getElementById('stats-payload').textContent);
    const legacy = JSON.parse(document.getElementById('legacy-only').textContent);
    state = emptyState();
    saveState();

    // 1. old bridge: games imported without rating fields -> legacy formula
    const first = mergeLcuGames(oldPayload);
    eq(first.added, 2, 'old payload imported');
    eq(first.legacyPayload, 2, 'old payload flagged as legacy');
    const st0 = calcPlayerStats().find(s => s.player.name === '玩家0');
    eq(st0.scoreGames, 0, 'legacy import has no scored games');

    // hand-edit a KDA value, backfill must keep it
    const editedMatch = state.matches.find(m => m.id === 'm_lcu_9300');
    const p0 = state.players.find(p => p.name === '玩家0');
    const editedPart = editedMatch.participants.find(pt => pt.playerId === p0.id);
    editedPart.kills = 17;

    // 2. new bridge: same gameIds but with stats -> backfill, nothing added
    const second = mergeLcuGames(newPayload);
    eq(second.added, 0, 'existing games are still duplicates');
    eq(second.legacyPayload, 0, 'new payload has stats');
    const filled = backfillRatingStats(newPayload);
    eq(filled.filled, 2, 'both games backfilled');
    eq(filled.partial, 0, 'no partial backfill');

    const stats = calcPlayerStats();
    const everyScored = stats.filter(s => s.games > 0).every(s => s.scoreGames === 2);
    check(everyScored, 'all players score both games with multi-factor rating');

    // 3. hand-edited KDA survives, winner/teams untouched, duration kept
    const after = state.matches.find(m => m.id === 'm_lcu_9300');
    const partAfter = after.participants.find(pt => pt.playerId === p0.id);
    eq(partAfter.kills, 17, 'hand-edited kills preserved');
    eq(after.winner, 'red', 'winner preserved');
    eq(after.duration, 1800, 'duration preserved');
    check(partAfter.goldEarned === 9000, 'stats written onto participant');
    eq(state.players.length, 10, 'no players created by backfill');

    // 4. other players still sit in their own team slot
    const p9 = state.players.find(p => p.name === '玩家9');
    const part9 = after.participants.find(pt => pt.playerId === p9.id);
    eq(part9.team, 'blue', 'team unchanged for later player');
    check(part9.goldEarned === 9000 + 9 * 500, 'stats matched by name, not index');

    // 5. idempotent: running again changes nothing
    const again = backfillRatingStats(newPayload);
    eq(again.filled, 0, 'second backfill is a no-op');

    // 6. a game that only exists in the payload is not invented by backfill
    const legacyResult = mergeLcuGames(legacy);
    eq(legacyResult.added, 1, 'legacy-only game imported');
    const beforeCount = state.matches.length;
    const nothing = backfillRatingStats(legacy);
    eq(nothing.filled, 0, 'payload without stats cannot backfill');
    eq(state.matches.length, beforeCount, 'backfill never adds matches');

    // 7. status line warns about legacy payloads and reports backfills
    const r = { added: 0, duplicates: 2, skipped: [], newPlayers: [], legacyPayload: 2, backfilled: 0, backfillPartial: 0 };
    showMergeOutcome(r, '同步完成');
    check(document.getElementById('merge-status').textContent.includes('旧公式'), 'legacy warning shown');
    const r2 = { added: 0, duplicates: 2, skipped: [], newPlayers: [], legacyPayload: 0, backfilled: 3, backfillPartial: 0 };
    showMergeOutcome(r2, '同步完成');
    check(document.getElementById('merge-status').textContent.includes('补上评分指标'), 'backfill count shown');

    // 8. scores now really come from the multi-factor path
    const scoredMatch = getMatchScores(after);
    check(Array.isArray(scoredMatch) && scoredMatch.length === 10, 'game 9300 now has multi-factor scores');
    const single = { legacyPayload: 0, backfilled: 0, backfillPartial: 0, added: 0, duplicates: 1, skipped: [], newPlayers: [] };
    showMergeOutcome(single, '同步完成');
    check(!document.getElementById('merge-status').textContent.includes('旧公式'), 'no stale legacy warning');

    renderAll();
  } catch (err) {
    failures.push('harness error: ' + (err && err.stack ? err.stack : err));
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
    legacy_only = build_payload(False, games=1)
    legacy_only["games"][0]["gameId"] = 9399
    payloads = {
        "legacy-payload": build_payload(False),
        "stats-payload": build_payload(True),
        "legacy-only": legacy_only,
    }
    blocks = []
    for pid, obj in payloads.items():
        blob = json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")
        blocks.append(f'<script type="application/json" id="{pid}">{blob}</script>')
    if "</body>" not in html:
        raise SystemExit("site has no </body>")
    return html.replace("</body>", "\n".join(blocks) + "\n" + HARNESS + "\n</body>", 1)


def find_chrome():
    for path in CHROME_CANDIDATES:
        if path and Path(path).exists():
            return path
    raise SystemExit("Chrome not found; set CHROME env var")


def run():
    tmp = tempfile.mkdtemp(prefix="lol_backfill_smoke_")
    try:
        page = Path(tmp) / "page.html"
        page.write_text(build_page(), encoding="utf-8")
        cmd = [
            find_chrome(), "--headless=new", "--disable-gpu", "--no-first-run",
            "--no-default-browser-check", f"--user-data-dir={Path(tmp) / 'profile'}",
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
