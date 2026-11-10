#!/usr/bin/env python3
"""Headless Chrome smoke test for the website's auto-sync button.

Mocks fetch(), exercises the running / not-running / offline / error paths,
and checks that successful syncs merge games into localStorage-backed state.
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


def participant(name, team, kills=1, deaths=1, assists=1):
    return {
        "name": name,
        "team": team,
        "kills": kills,
        "deaths": deaths,
        "assists": assists,
        "champion": "测试英雄",
        "position": "",
    }


def build_payload():
    names = [f"玩家{i}" for i in range(10)]
    parts = [participant(n, "red" if i < 5 else "blue") for i, n in enumerate(names)]
    return {
        "source": "lcu",
        "fetchedAt": "2026-11-05T20:00:00+08:00",
        "summoner": "测试账号",
        "count": 2,
        "games": [
            {"gameId": 9101, "date": "2026-11-04", "winner": "red", "participants": parts},
            {"gameId": 9102, "date": "2026-11-05", "winner": "blue", "participants": parts},
        ],
    }


HARNESS = r"""
<script>
(async function () {
  const failures = [];
  const check = (cond, msg) => { if (!cond) failures.push(msg); };
  const eq = (got, want, msg) => check(got === want, msg + ' (got ' + JSON.stringify(got) + ', want ' + JSON.stringify(want) + ')');

  const calls = [];
  let mode = 'ok';
  let bridgeStarted = true;
  let launchCalls = 0;
  let autoStart = false;
  const response = (obj, status) => ({
    ok: status >= 200 && status < 300,
    status: status,
    json: async () => obj,
  });

  window.__launchBridge = () => {
    launchCalls += 1;
    if (autoStart) setTimeout(() => { bridgeStarted = true; }, 100);
  };

  window.fetch = async function (url, options) {
    calls.push({ url: String(url), options: options || {} });
    const path = String(url);
    if (mode === 'offline' && !bridgeStarted && !path.endsWith('/api/health')) {
      throw new TypeError('Failed to fetch');
    }
    if (path.endsWith('/api/health')) {
      if (mode === 'offline' && !bridgeStarted) throw new TypeError('Failed to fetch');
      return response({ ok: true }, 200);
    }
    if (path.endsWith('/api/status')) {
      if (mode === 'no-client') {
        return response({ ok: true, clientRunning: false, loggedIn: false, summoner: '', message: '未检测到英雄联盟客户端' }, 200);
      }
      if (mode === 'not-logged-in') {
        return response({ ok: true, clientRunning: true, loggedIn: false, summoner: '', message: '客户端已启动，但未登录' }, 200);
      }
      return response({ ok: true, clientRunning: true, loggedIn: true, summoner: '测试账号', message: '已连接' }, 200);
    }
    if (path.endsWith('/api/sync')) {
      if (mode === 'http-error') {
        return response({ ok: false, code: 'auth-failed', message: 'LCU 认证失败' }, 503);
      }
      if (mode === 'empty') {
        return response({ ok: true, source: 'lcu', games: [] }, 200);
      }
      return response(PAYLOAD, 200);
    }
    return response({ ok: false, message: 'unexpected' }, 404);
  };

  const statusText = () => document.getElementById('merge-status').textContent;
  const button = document.getElementById('btn-auto-sync');
  const startButton = document.getElementById('btn-start-bridge');
  const waitUntil = async (cond, ms) => {
    const deadline = Date.now() + ms;
    while (Date.now() < deadline) {
      if (cond()) return true;
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    return cond();
  };
  check(!!button, 'auto sync button exists');
  check(!!startButton && startButton.hidden, 'start bridge button starts hidden');

  await new Promise(resolve => setTimeout(resolve, 250));
  bridgeKnownOnline = null;
  setStartBridgeVisible(false);

  state = emptyState();
  saveState();
  await autoSyncClient();
  eq(state.matches.length, 2, 'sync merges two games');
  eq(state.players.length, 10, 'sync creates ten players');
  eq(calls.length, 2, 'sync calls status then sync');
  check(calls[0].url.endsWith('/api/status'), 'first request is status');
  check(calls[1].url.endsWith('/api/sync'), 'second request is sync');
  eq(calls[1].options.method, 'POST', 'sync uses POST');
  eq(calls[1].options.headers['X-LCU-Sync'], '1', 'sync sends header');
  check(statusText().includes('同步完成'), 'status reports completion: ' + statusText());
  check(statusText().includes('新增 2 场对局'), 'status reports two games');
  check(statusText().includes('测试账号'), 'status shows summoner');
  eq(button.disabled, false, 'button re-enabled after success');

  calls.length = 0;
  await autoSyncClient();
  eq(state.matches.length, 2, 'second sync does not duplicate');
  check(statusText().includes('跳过 2 场已存在'), 'second sync reports duplicates: ' + statusText());

  state = emptyState();
  saveState();
  mode = 'no-client';
  calls.length = 0;
  await autoSyncClient();
  eq(calls.length, 1, 'no-client stops after status');
  eq(state.matches.length, 0, 'no-client merges nothing');
  check(statusText().includes('未检测到'), 'no-client status message: ' + statusText());
  eq(button.disabled, false, 'button re-enabled after no-client');

  mode = 'not-logged-in';
  await autoSyncClient();
  check(statusText().includes('未登录'), 'not-logged-in status message: ' + statusText());
  eq(state.matches.length, 0, 'not-logged-in merges nothing');

  mode = 'offline';
  bridgeStarted = false;
  autoStart = true;
  launchCalls = 0;
  window.__lcuBridgeWaitMs = 5000;
  state = emptyState();
  saveState();
  await autoSyncClient();
  eq(launchCalls, 1, 'auto-start launches protocol once');
  eq(state.matches.length, 2, 'auto-start then syncs');
  check(statusText().includes('同步完成'), 'auto-start success status: ' + statusText());
  eq(button.disabled, false, 'button re-enabled after auto-start');

  mode = 'offline';
  bridgeStarted = false;
  autoStart = false;
  launchCalls = 0;
  window.__lcuBridgeWaitMs = 1200;
  state = emptyState();
  saveState();
  await autoSyncClient();
  eq(launchCalls, 1, 'failed auto-start still tries protocol');
  eq(state.matches.length, 0, 'failed auto-start merges nothing');
  check(statusText().includes('install_protocol'), 'failed auto-start names installer: ' + statusText());
  check(startButton.hidden === false, 'start button shown after failed auto-start');
  eq(bridgeKnownOnline, false, 'bridge marked offline after failed auto-start');

  mode = 'offline';
  bridgeStarted = false;
  autoStart = true;
  launchCalls = 0;
  window.__lcuBridgeWaitMs = 5000;
  state = emptyState();
  saveState();
  button.click();
  eq(launchCalls, 1, 'auto-sync click launches protocol synchronously when bridge known offline');
  await waitUntil(() => state.matches.length === 2 && !button.disabled, 6000);
  eq(state.matches.length, 2, 'auto-sync click then syncs after launch');
  eq(bridgeKnownOnline, true, 'bridge marked online after launched sync');
  check(startButton.hidden === true, 'start button hidden after launched sync');

  mode = 'offline';
  bridgeStarted = false;
  autoStart = true;
  launchCalls = 0;
  bridgeKnownOnline = false;
  window.__lcuBridgeWaitMs = 5000;
  state = emptyState();
  saveState();
  startButton.click();
  eq(launchCalls, 1, 'start button launches protocol once');
  await waitUntil(() => state.matches.length === 2 && !button.disabled, 6000);
  eq(state.matches.length, 2, 'start button then syncs');
  check(startButton.hidden === true, 'start button hidden after successful start');

  mode = 'ok';
  bridgeStarted = true;
  window.__lcuBridgeWaitMs = 15000;
  mode = 'http-error';
  state = emptyState();
  saveState();
  await autoSyncClient();
  check(statusText().includes('认证失败'), 'server error message shown: ' + statusText());
  eq(state.matches.length, 0, 'server error merges nothing');

  mode = 'empty';
  await autoSyncClient();
  check(statusText().includes('没有可用的 5v5 峡谷自定义对局'), 'empty sync message: ' + statusText());
  eq(state.matches.length, 0, 'empty sync merges nothing');
  eq(button.disabled, false, 'button re-enabled after empty sync');

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
    chrome = find_chrome()
    if not chrome:
        print("Chrome not found; set CHROME env var.")
        return 2

    html = SITE.read_text(encoding="utf-8")
    seed_tag = '<script type="application/json" id="seed-data">null</script>'
    if seed_tag not in html:
        print("Could not find seed-data tag in site.")
        return 2
    html = html.replace(seed_tag, seed_tag + COLLECTOR, 1)

    payload = json.dumps(build_payload(), ensure_ascii=False).replace("</", "<\\/")
    html = html.replace(
        "</body>",
        "<script>const PAYLOAD = " + payload + ";</script>" + HARNESS + "</body>",
        1,
    )

    work = Path(tempfile.mkdtemp(prefix="lol_autosync_test_"))
    page = work / "auto_sync_test.html"
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
        "--virtual-time-budget=10000",
        "--dump-dom",
        page.as_uri(),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    match = re.search(r'<pre id="test-result">(.*?)</pre>', proc.stdout or "", re.S)
    if not match:
        print("Test harness did not produce a result.")
        print("--- stdout tail ---\n" + (proc.stdout or "")[-2000:])
        print("--- stderr tail ---\n" + (proc.stderr or "")[-2000:])
        return 1

    result = json.loads(unescape(match.group(1)))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
