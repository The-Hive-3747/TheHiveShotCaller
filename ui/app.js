// HiveShotTracker UI. Plain ES modules; API contract: docs/api.md
import { ReplayViewer } from './viewer3d.js';

const $ = (id) => document.getElementById(id);
const IN_TO_M = 0.0254;
// Fallback ONLY: mirrors hiveshot/calib_targets.reference_point_names(). The live list comes from
// GET /api/calib/points when the Calibration tab opens (see loadCalibPoints).
const FALLBACK_CALIB_NAMES = [
  'Red HIVE up-CELL opening, high-left corner',
  'Red HIVE up-CELL opening, high-right corner',
  'Red HIVE up-CELL opening, low-right corner',
  'Red HIVE up-CELL opening, low-left corner',
  'HIVE frame top corner (-X, +Y)',
  'HIVE frame top corner (+X, +Y)',
  'HIVE frame top corner (-X, -Y)',
  'HIVE frame top corner (+X, -Y)',
];
let calibPoints = FALLBACK_CALIB_NAMES.map((name) => ({ name, xyz: null }));

const state = { config: null, sessionId: null, shots: [], stats: null, status: null, geometry: null, viewer: null, sessions: [], shotFilter: 'all', tips: [], rtmpUrls: {}, demo: false, demoPending: null, demoPosted: false, demoSession: null, demoPoll: null };

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function toast(msg) {
  const t = $('toast'); t.textContent = msg; t.style.display = 'block';
  clearTimeout(toast._t); toast._t = setTimeout(() => { t.style.display = 'none'; }, 4000);
}
async function api(method, url, body) {
  const opt = { method, headers: {} };
  if (body !== undefined) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
  const r = await fetch(url, opt);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = JSON.stringify(await r.json()); } catch (e) { /* ignore */ }
    throw new Error(`${method} ${url}: ${r.status} ${msg}`);
  }
  const ct = r.headers.get('content-type') || '';
  return ct.includes('json') ? r.json() : r.text();
}
const fmt = (v, d = 1) => (v === null || v === undefined || Number.isNaN(v) ? '-' : Number(v).toFixed(d));
const fmtSig = (v, n = 4) => (v === null || v === undefined || !Number.isFinite(Number(v)) ? '-' : Number(Number(v).toPrecision(n)).toString());
async function guarded(fn) { try { await fn(); } catch (e) { toast(e.message); console.error(e); } }

// ---------- tabs ----------
function showTab(name) {
  document.querySelectorAll('#tabs button').forEach((b) => b.classList.toggle('active', b.dataset.tab === name));
  document.querySelectorAll('.tab').forEach((s) => s.classList.toggle('active', s.id === 'tab-' + name));
  if (state.viewer) state.viewer.setVisible(name === 'replay');
  if (name === 'setup') startSetup(); else stopSetup();
  if (name === 'calibration') loadCalibration();
  if (name === 'settings') renderSettings();
  if (name === 'shots') loadShots();
}
document.querySelectorAll('#tabs button').forEach((b) => b.addEventListener('click', () => showTab(b.dataset.tab)));

// ---------- websocket ----------
function connectWs() {
  const ws = new WebSocket('ws://127.0.0.1:8765/ws');
  const set = (ok, txt) => { const p = $('wsState'); p.textContent = 'ws: ' + txt; p.className = 'pill ' + (ok ? 'ok' : 'bad'); };
  ws.onopen = () => set(true, 'connected');
  ws.onclose = () => { set(false, 'reconnecting'); setTimeout(connectWs, 2000); };
  ws.onerror = () => { try { ws.close(); } catch (e) { /* ignore */ } };
  ws.onmessage = (ev) => {
    let m; try { m = JSON.parse(ev.data); } catch (e) { return; }
    if (m.type === 'status') { state.status = m; renderStatus(); }
    else if (m.type === 'stats') {
      if (!state.sessionId && m.stats && m.stats.session_id) setSession(m.stats.session_id, false);
      if (!m.stats || m.stats.session_id === state.sessionId) { state.stats = m.stats; renderStats(); }
    } else if (m.type === 'shot') {
      if (m.shot && (!m.shot.session_id || m.shot.session_id === state.sessionId)) {
        state.shots = [m.shot, ...state.shots.filter((s) => s.shot_id !== m.shot.shot_id)];
        renderShots();
      }
    } else if (m.type === 'shot_updated') {
      if (m.shot && (!m.shot.session_id || m.shot.session_id === state.sessionId)) {
        const i = state.shots.findIndex((s) => s.shot_id === m.shot.shot_id);
        if (i >= 0) state.shots[i] = Object.assign({}, state.shots[i], m.shot);
        else state.shots = [m.shot, ...state.shots];
        renderShots();
      }
      if (m.stats && (!m.stats.session_id || m.stats.session_id === state.sessionId)) { state.stats = m.stats; renderStats(); }
    } else if (m.type === 'tip') {
      if (m.tip) { state.tips = [...state.tips, m.tip]; renderTips(); }
      toast('Tip: ' + JSON.stringify(m.tip));
    }
  };
}

// ---------- session / top bar ----------
function setSession(id, reload = true) {
  state.sessionId = id;
  renderSessLabel();
  $('lnkCsv').href = id ? `/api/sessions/${encodeURIComponent(id)}/export.csv` : '#';
  renderSessionPicker();
  if (reload && id) { guarded(loadStats); loadShots(); guarded(loadTips); }
}
function renderSessLabel() {
  const st = state.status;
  const noActive = st && Object.prototype.hasOwnProperty.call(st, 'session_id') && st.session_id === null;
  $('sessLabel').textContent = state.sessionId ? 'session ' + state.sessionId : noActive ? 'no active session' : 'no session';
  $('sessLabel').title = noActive ? 'Shots will be stored as "unassigned" until a session is started' : '';
}
async function loadTips() {
  if (!state.sessionId) { state.tips = []; renderTips(); return; }
  state.tips = await api('GET', `/api/sessions/${encodeURIComponent(state.sessionId)}/tips`);
  renderTips();
}
function renderTips() {
  const rows = [...state.tips].sort((a, b) => (b.t ?? 0) - (a.t ?? 0));
  $('tipCount').textContent = `(${rows.length})`;
  const tb = $('tipTable').querySelector('tbody');
  tb.innerHTML = rows.map((t) => {
    const d = t.t != null ? new Date(t.t * 1000) : null;
    const when = d && !Number.isNaN(d.getTime()) && t.t > 1e8 ? d.toLocaleTimeString() : fmt(t.t, 2) + ' s';
    return `<tr><td>${esc(when)}</td><td>${esc(t.alliance)}</td><td>${esc(t.new_up_cell)}</td><td>${esc(t.caused_by_shot_id ?? '-')}</td></tr>`;
  }).join('') || '<tr><td colspan="4" class="muted">no tips</td></tr>';
}
function renderSessionPicker() {
  const sel = $('selSession');
  const list = [...state.sessions].sort((a, b) => (b.started_at ?? 0) - (a.started_at ?? 0));
  if (state.sessionId && !list.some((s) => s.session_id === state.sessionId)) list.unshift({ session_id: state.sessionId, name: '' });
  sel.innerHTML = list.length
    ? list.map((s) => `<option value="${esc(s.session_id)}">${esc(s.session_id)}${s.name ? ' - ' + esc(s.name) : ''}${s.ended_at ? '' : ' (running)'}${s.shots != null ? ' [' + esc(s.shots) + ']' : ''}</option>`).join('')
    : '<option value="">(none)</option>';
  sel.value = state.sessionId || '';
}
async function refreshSessions() {
  state.sessions = await api('GET', '/api/sessions');
  renderSessionPicker();
  return state.sessions;
}
async function loadSessions() {
  const list = await refreshSessions();
  if (!list.length) return;
  const running = list.filter((s) => !s.ended_at);
  const newest = (arr) => arr.reduce((a, b) => ((a.started_at ?? 0) >= (b.started_at ?? 0) ? a : b));
  const pick = newest(running.length ? running : list);
  setSession(pick.session_id);
}
$('selSession').onchange = (e) => {
  if (!e.target.value) return;
  state.shots = []; state.stats = null; renderStats(); renderShots();
  setSession(e.target.value);
};
async function loadStats() {
  if (!state.sessionId) return;
  state.stats = await api('GET', `/api/sessions/${encodeURIComponent(state.sessionId)}/stats`);
  renderStats();
}
async function loadShots() {
  if (!state.sessionId) { renderShots(); return; }
  await guarded(async () => {
    state.shots = await api('GET', `/api/sessions/${encodeURIComponent(state.sessionId)}/shots`);
    renderShots();
  });
}
// ---------- demo mode (docs/api.md "Demo mode") ----------
function applyDemoUi() {
  const demo = state.demo === true;
  $('demoBadge').style.display = demo ? '' : 'none';
  const pend = state.demoPending;
  $('btnDemo').disabled = !!pend;
  $('btnDemo').textContent = pend === 'stopping' ? 'Exiting demo...' : pend === 'starting' ? 'Starting demo...' : demo ? 'Exit demo' : 'Run demo';
  $('demoBanner').style.display = demo ? '' : 'none';
  const save = document.getElementById('btnSave');
  if (save) { save.disabled = demo; save.title = demo ? 'Demo config is not saved; exit demo first' : ''; }
}
async function reloadAfterModeChange() {
  state.config = await api('GET', '/api/config');
  renderCams(); renderCalibCams(); updateSessName();
  state.status = await api('GET', '/api/pipeline/status');
  renderStatus();
}
// The demo endpoints return 200 before the pipeline has finished switching, so the button stays disabled
// ("Starting demo..." / "Exiting demo...") until a status message reports the new state; only then is
// the config/session data reloaded. Status arrives over the WebSocket, with a 1 s poll as a fallback.
const DEMO_TIMEOUT_MS = 40000;
function demoSettled(st) {
  if (!state.demoPending || !state.demoPosted) return;
  if ((st.demo === true) !== (state.demoPending === 'starting')) return;   // stale status; keep waiting
  finishDemoTransition();
}
function clearDemoPending() {
  state.demoPending = null; state.demoPosted = false;
  clearInterval(state.demoPoll); state.demoPoll = null;
  applyDemoUi();
}
async function finishDemoTransition() {
  const starting = state.demoPending === 'starting';
  const sid = state.demoSession;
  clearDemoPending();   // before reloading, so the status refresh below cannot re-enter
  await guarded(async () => {
    if (starting) { state.shots = []; state.stats = null; renderStats(); renderShots(); }
    await reloadAfterModeChange();
    await refreshSessions();
    if (starting) {
      if (sid) setSession(sid);
      showTab('dashboard');
    } else {
      toast('Demo stopped; your saved configuration is restored');
    }
  });
}
function watchDemoTransition() {
  state.demoPosted = true;
  const t0 = Date.now();
  const tick = async () => {
    if (!state.demoPending) return;
    if (Date.now() - t0 > DEMO_TIMEOUT_MS) { clearDemoPending(); toast('Demo mode change timed out; check the pipeline status'); return; }
    try { state.status = await api('GET', '/api/pipeline/status'); renderStatus(); } catch (e) { console.error(e); }
  };
  clearInterval(state.demoPoll);
  state.demoPoll = setInterval(tick, 1000);
  tick();
}
$('btnDemo').onclick = async () => {
  if (state.demoPending) return;
  const starting = !state.demo;
  state.demoPending = starting ? 'starting' : 'stopping';
  state.demoPosted = false; state.demoSession = null;
  applyDemoUi();
  try {
    const r = await api('POST', starting ? '/api/demo/start' : '/api/demo/stop');
    state.demoSession = (r && r.session_id) || null;
    watchDemoTransition();
  } catch (e) {
    clearDemoPending();
    toast(e.message); console.error(e);
  }
};

// Client-side expansion of config.session_name_template ({date} = YYYY-MM-DD, {time} = HH:MM, local time).
const DEFAULT_NAME_TEMPLATE = 'Practice {date} {time}';
function expandNameTemplate(tpl, d = new Date()) {
  const p2 = (n) => String(n).padStart(2, '0');
  const date = `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}`;
  const time = `${p2(d.getHours())}:${p2(d.getMinutes())}`;
  return String(tpl || DEFAULT_NAME_TEMPLATE).replace(/\{date\}/g, date).replace(/\{time\}/g, time);
}
let autoSessName = '';
function updateSessName() {
  const input = $('sessName');
  const fresh = expandNameTemplate(state.config && state.config.session_name_template);
  // only replace what we put there ourselves; never overwrite something the user typed
  if (!input.value.trim() || input.value === autoSessName) input.value = fresh;
  autoSessName = fresh;
}
// Name for a new session: the user's text, or the template re-expanded at the moment of starting.
function sessionNameNow() {
  const v = $('sessName').value.trim();
  if (!v || v === autoSessName) return expandNameTemplate(state.config && state.config.session_name_template);
  return v;
}
$('btnStart').onclick = () => guarded(async () => {
  const r = await api('POST', '/api/sessions', { name: sessionNameNow() });
  state.shots = []; state.stats = null; renderStats(); renderShots();
  await refreshSessions();
  setSession(r.session_id);
});
$('btnEnd').onclick = () => guarded(async () => {
  if (!state.sessionId) return;
  await api('POST', `/api/sessions/${encodeURIComponent(state.sessionId)}/end`);
  toast('Session ended');
});
$('btnPipeStart').onclick = () => guarded(async () => { await api('POST', '/api/pipeline/start'); toast('Pipeline started'); });
$('btnPipeStop').onclick = () => guarded(async () => { await api('POST', '/api/pipeline/stop'); toast('Pipeline stopped'); });
$('btnHive').onclick = () => guarded(async () => {
  await api('POST', '/api/hive/state', { alliance: $('selAlliance').value, up_cell: $('selUpCell').value });
  toast('HIVE state set');
});

// ---------- cameras ----------
function renderCams() {
  const srcs = (state.config && state.config.sources) || [];
  const box = $('camList');
  if (!srcs.length) { box.textContent = 'No sources configured (Settings tab).'; return; }
  box.innerHTML = srcs.map((s) => `<div class="cam"><img alt="${esc(s.cam_id)}" data-cam="${esc(s.cam_id)}" src="/api/preview/${encodeURIComponent(s.cam_id)}.mjpg">
    <div class="ov"><b>${esc(s.cam_id)}</b><span id="camov-${esc(s.cam_id)}">-</span></div></div>`).join('');
}
function renderStatus() {
  const st = state.status; if (!st) return;
  const p = $('pipeState');
  p.textContent = 'pipeline: ' + (st.running ? 'running' : 'stopped') + (st.detector_fps ? ` ${fmt(st.detector_fps)} fps` : '');
  p.className = 'pill ' + (st.running ? 'ok' : '');
  for (const [id, c] of Object.entries(st.cameras || {})) {
    const el = document.getElementById('camov-' + id);
    if (el) {
      const [word, cls] = c.ended ? ['ENDED', 'camst-ended'] : c.is_alive === false ? ['DOWN', 'camst-down'] : ['LIVE', 'camst-live'];
      const dropped = Number(c.dropped ?? 0) || 0;
      const dropHtml = `<span class="${dropped > 0 ? 'cam-dropped' : ''}">dropped ${esc(dropped)}</span>`;
      el.innerHTML = `${fmt(c.fps)} fps | ${dropHtml} | <span class="${cls}">${word}</span>${c.last_error ? ' | ' + esc(c.last_error) : ''}`;
    }
  }
  renderSessLabel();
  const warns = Array.isArray(st.warnings) ? st.warnings.filter((w) => w) : [];
  const banner = $('warnBanner');
  banner.style.display = warns.length ? '' : 'none';
  banner.innerHTML = warns.map((w) => `<div>${esc(w)}</div>`).join('');
  $('noCalib').style.display = st.calibration_loaded === false ? '' : 'none';
  state.demo = st.demo === true;
  applyDemoUi();
  demoSettled(st);
  const hiveSrc = st.hive_state_source === 'tags' ? 'tags' : 'manual';
  $('hiveSrc').textContent = hiveSrc === 'tags' ? 'auto (tags)' : 'HIVE: manual';
  $('hiveSrc').className = 'pill' + (hiveSrc === 'tags' ? ' ok' : '');
  for (const id of ['selAlliance', 'selUpCell', 'btnHive']) {
    $(id).disabled = hiveSrc === 'tags';
    $(id).title = hiveSrc === 'tags' ? 'HIVE state is being set automatically from the tags on the up CELL; manual control is disabled' : '';
  }
  if (st.rtmp && st.rtmp.urls) state.rtmpUrls = st.rtmp.urls;
  refreshRtmpHints();
  const mm = st.calibration_mismatch || {};
  const mmKeys = Object.keys(mm);
  const chip = $('calMismatch');
  chip.style.display = mmKeys.length ? '' : 'none';
  chip.title = mmKeys.map((k) => `${k}: ${mm[k]}`).join('\n');
  chip.textContent = mmKeys.length ? `calibration mismatch (${mmKeys.length})` : '';
  if (st.hive_state) {
    if (st.hive_state.alliance) $('selAlliance').value = st.hive_state.alliance;
    if (st.hive_state.up_cell) $('selUpCell').value = st.hive_state.up_cell;
  }
}

// ---------- dashboard ----------
function renderStats() {
  const s = state.stats || {};
  const tiles = [
    ['Shots', s.shots], ['Made', s.made], ['Bounce-out', s.bounce_out], ['Miss', s.miss],
    ['Make rate', s.make_rate == null ? '-' : (s.make_rate * 100).toFixed(1) + '%'],
    ['Tips', s.tips],
    ['Mean exit m/s', s.mean_exit_speed_ips == null ? '-' : fmt(s.mean_exit_speed_ips * IN_TO_M, 2)],
    ['Mean exit in/s', fmt(s.mean_exit_speed_ips, 0)],
    ['Mean launch angle', s.mean_launch_angle_deg == null ? '-' : fmt(s.mean_launch_angle_deg) + '°'],
  ];
  $('tiles').innerHTML = tiles.map(([k, v]) => `<div class="tile"><b>${esc(v ?? '-')}</b><span>${esc(k)}</span></div>`).join('');
  const bt = s.by_ball_type || {};
  const rows = Object.entries(bt);
  const cols = [...new Set(rows.flatMap(([, v]) => Object.keys(v)))];
  $('ballTable').innerHTML = rows.length
    ? `<tr><th>Ball</th>${cols.map((c) => `<th>${esc(c)}</th>`).join('')}</tr>` +
      rows.map(([k, v]) => `<tr><td>${esc(k)}</td>${cols.map((c) => `<td>${esc(v[c] ?? 0)}</td>`).join('')}</tr>`).join('')
    : '<tr><td class="muted">no data</td></tr>';
  drawHist(s.failure_order_hist || {}, s.bounce_out_order_hist || {});
}
function drawHist(fail, bounce) {
  const cv = $('histChart'); const g = cv.getContext('2d');
  const W = cv.width; const H = cv.height;
  g.clearRect(0, 0, W, H);
  const keys = ['1', '2', '3', '4', '5'];
  const lab = ['1', '2', '3', '4', '>4'];
  const f = keys.map((k) => Number(fail[k] ?? 0));
  const b = keys.map((k) => Number(bounce[k] ?? 0));
  const max = Math.max(1, ...f, ...b);
  const L = 36; const B = H - 30; const T = 14; const gw = (W - L - 10) / keys.length;
  g.fillStyle = '#8b96a6'; g.strokeStyle = '#2f3846'; g.font = '12px sans-serif'; g.textAlign = 'right';
  for (let i = 0; i <= 4; i++) {
    const y = B - ((B - T) * i) / 4;
    g.beginPath(); g.moveTo(L, y); g.lineTo(W - 6, y); g.stroke();
    g.fillText(String(Math.round((max * i) / 4)), L - 5, y + 4);
  }
  g.textAlign = 'center';
  keys.forEach((k, i) => {
    const x0 = L + i * gw + gw * 0.12; const bw = gw * 0.38;
    [[f[i], '#f85149', 0], [b[i], '#e3a008', 1]].forEach(([v, col, j]) => {
      const h = ((B - T) * v) / max;
      g.fillStyle = col; g.fillRect(x0 + j * bw, B - h, bw - 2, h);
      if (v) { g.fillStyle = '#e4e8ee'; g.fillText(String(v), x0 + j * bw + bw / 2, B - h - 3); }
    });
    g.fillStyle = '#8b96a6'; g.fillText('burst ' + lab[i], L + i * gw + gw / 2, H - 10);
  });
}

// ---------- shots ----------
function renderShots() {
  const all = [...state.shots].sort((a, b) => (b.t_launch ?? 0) - (a.t_launch ?? 0));
  const rows = state.shotFilter === 'all' ? all : all.filter((s) => s.result === state.shotFilter);
  $('shotCount').textContent = `${rows.length} of ${all.length} shots`;
  const tb = $('shotTable').querySelector('tbody');
  tb.innerHTML = rows.map((s) => {
    const t = s.t_launch != null ? new Date(s.t_launch * 1000) : null;
    const when = t && !Number.isNaN(t.getTime()) && s.t_launch > 1e8 ? t.toLocaleTimeString() : fmt(s.t_launch, 2) + ' s';
    const dn = Number(s.dropped_during_flight ?? 0) || 0;
    const warn = dn > 0 ? `<span class="dropped-warn" title="frames dropped during flight: ${esc(dn)}">&#9888; ${esc(dn)}</span>` : '';
    return `<tr class="r-${esc(s.result)}" data-id="${esc(s.shot_id)}"><td>${esc(s.shot_id)}</td><td>${esc(when)}</td>
      <td>burst ${esc(s.burst_id)} · #${esc(s.burst_index)}</td><td>${esc(s.ball_type)}</td><td class="res">${esc(s.result)}${warn}</td>
      <td>${fmt(s.exit_speed_mps, 2)}</td><td>${fmt(s.exit_speed_ips, 0)}</td><td>${fmt(s.launch_angle_deg)}°</td>
      <td>${fmt(s.launch_azimuth_deg)}°</td><td>${fmt(s.apex_z_in)}</td></tr>`;
  }).join('');
}
$('shotFilter').onchange = (e) => { state.shotFilter = e.target.value; renderShots(); };
$('shotTable').querySelector('tbody').addEventListener('click', (ev) => {
  const tr = ev.target.closest('tr'); if (tr) openReplay(tr.dataset.id);
});

// ---------- replay ----------
async function ensureViewer() {
  if (state.viewer) return state.viewer;
  state.viewer = new ReplayViewer($('viewport'));
  state.viewer.onProgress = (p, playing) => {
    $('scrub').value = Math.round(p * 1000);
    $('btnPlay').textContent = playing ? 'Pause' : 'Play';
  };
  state.viewer.setRobot(state.config && state.config.robot);
  state.viewer.setFollow($('chkFollow').checked);
  try { state.geometry = await api('GET', '/api/field/geometry'); state.viewer.setField(state.geometry); }
  catch (e) { toast('field geometry: ' + e.message); }
  return state.viewer;
}
async function openReplay(shotId) {
  showTab('replay');
  await guarded(async () => {
    const v = await ensureViewer();
    v.setVisible(true);
    const shot = await api('GET', `/api/shots/${encodeURIComponent(shotId)}`);
    v.setRobot(state.config && state.config.robot);
    v.showShot(shot);
    $('noTrack').style.display = (shot.track && shot.track.length) ? 'none' : 'block';
    const sp = shot.exit_speed_mps ?? (shot.exit_speed_ips != null ? shot.exit_speed_ips * IN_TO_M : null);
    const par = shot.parabola;
    // equation comes from the API (ShotSummary.equation); fall back to the list row if the detail lacks it
    const listed = state.shots.find((s) => s.shot_id === shot.shot_id);
    const equation = shot.equation || (listed && listed.equation) || '';
    $('replayInfo').className = 'card';
    $('replayInfo').innerHTML = `<div><b>Shot ${esc(shot.shot_id)}</b> (${esc(shot.ball_type)})</div>
      <div>Result: <span class="badge res-${esc(shot.result)}">${esc(shot.result)}</span></div>
      <div>Exit speed: ${fmt(sp, 2)} m/s (${fmt(shot.exit_speed_ips, 0)} in/s)</div>
      <div>Launch angle: ${fmt(shot.launch_angle_deg)}° &nbsp; azimuth ${fmt(shot.launch_azimuth_deg)}°</div>
      <div>Apex: ${fmt(shot.apex_z_in)} in</div>
      <div>Burst ${esc(shot.burst_id)} #${esc(shot.burst_index)}</div>
      <div class="eq">${esc(equation)}</div>
      ${par ? `<div class="muted">fit RMSE ${fmt(par.rmse_in, 2)} in</div>` : ''}
      ${shot.drag ? `<div class="muted">drag fit RMSE ${fmt(shot.drag.rmse_in, 2)} in, k (1/in) = ${esc(fmtSig(shot.drag.k_per_in, 4))}</div>` : ''}
      <div class="muted">Solid yellow: measured track. Dashed cyan: fitted parabola.</div>
      ${shot.clip_url ? `<div><a href="${esc(shot.clip_url)}" target="_blank" rel="noopener" class="muted">clip</a></div>` : ''}`;
  });
}
$('btnPlay').onclick = () => state.viewer && state.viewer.toggle();
$('scrub').oninput = (e) => { if (state.viewer) { state.viewer.pause(); state.viewer.setProgress(e.target.value / 1000); } };
$('chkFollow').onchange = (e) => state.viewer && state.viewer.setFollow(e.target.checked);
$('speed').onchange = (e) => state.viewer && state.viewer.setSpeed(parseFloat(e.target.value));

// ---------- calibration ----------
const calibClicks = {};   // cam_id -> [{u,v,name}]
function renderCalibCams() {
  const srcs = (state.config && state.config.sources) || [];
  const root = $('calibCams');
  if (!srcs.length) { root.innerHTML = '<div class="card muted">No sources configured.</div>'; return; }
  root.innerHTML = srcs.map((s) => {
    const id = s.cam_id;
    return `<div class="card calibcam" data-cam="${esc(id)}">
      <div><h3>${esc(id)}</h3>
        <div class="imgwrap"><img alt="${esc(id)}" src="/api/preview/${encodeURIComponent(id)}.jpg?t=${Date.now()}"></div>
        <div style="margin-top:6px">
          <button data-act="refresh">Refresh image</button>
          <button data-act="undo">Undo point</button>
          <button data-act="clear">Clear</button>
          <button data-act="solve">Solve extrinsics</button>
          <button data-act="istart">Start intrinsics</button>
          <button data-act="istop">Stop intrinsics</button>
        </div>
        <div class="result muted" style="margin-top:6px"></div></div>
      <div><b>Click in order:</b><ol class="pts"></ol></div></div>`;
  }).join('');
  srcs.forEach((s) => paintCalib(s.cam_id));
}
function calibEl(id) { return document.querySelector(`.calibcam[data-cam="${CSS.escape(id)}"]`); }
function paintCalib(id) {
  const el = calibEl(id); if (!el) return;
  const pts = calibClicks[id] || [];
  el.querySelector('ol.pts').innerHTML = calibPoints.map((cp, i) => {
    const n = cp.name;
    const cls = i < pts.length ? 'done' : i === pts.length ? 'next' : '';
    const xyz = Array.isArray(cp.xyz) ? ` <span class="muted">[${cp.xyz.map((v) => fmt(v, 1)).join(', ')}] in</span>` : '';
    return `<li class="${cls}">${esc(n)}${xyz}${i < pts.length ? ` (${Math.round(pts[i].u)}, ${Math.round(pts[i].v)})` : ''}</li>`;
  }).join('');
  const wrap = el.querySelector('.imgwrap');
  wrap.querySelectorAll('.dot').forEach((d) => d.remove());
  const img = wrap.querySelector('img');
  const sx = img.clientWidth / (img.naturalWidth || 1);
  pts.forEach((p, i) => {
    const d = document.createElement('div'); d.className = 'dot'; d.textContent = String(i + 1);
    d.style.left = p.u * sx + 'px'; d.style.top = p.v * sx + 'px'; wrap.appendChild(d);
  });
}
$('calibCams').addEventListener('click', (ev) => {
  const el = ev.target.closest('.calibcam'); if (!el) return;
  const id = el.dataset.cam;
  calibClicks[id] = calibClicks[id] || [];
  const out = el.querySelector('.result');
  if (ev.target.tagName === 'IMG') {
    if (calibClicks[id].length >= calibPoints.length) { toast(`All ${calibPoints.length} points set; undo or clear to change`); return; }
    const img = ev.target; const r = img.getBoundingClientRect();
    const k = img.naturalWidth / r.width;   // click in native image pixels
    calibClicks[id].push({ u: (ev.clientX - r.left) * k, v: (ev.clientY - r.top) * k, name: calibPoints[calibClicks[id].length].name });
    paintCalib(id);
    return;
  }
  const act = ev.target.dataset && ev.target.dataset.act; if (!act) return;
  guarded(async () => {
    if (act === 'refresh') { el.querySelector('img').src = `/api/preview/${encodeURIComponent(id)}.jpg?t=${Date.now()}`; }
    else if (act === 'undo') { calibClicks[id].pop(); paintCalib(id); }
    else if (act === 'clear') { calibClicks[id] = []; paintCalib(id); out.textContent = ''; }
    else if (act === 'solve') {
      if (calibClicks[id].length !== calibPoints.length) { toast(`Need ${calibPoints.length} points (have ${calibClicks[id].length})`); return; }
      const r = await api('POST', `/api/calib/extrinsics/${encodeURIComponent(id)}`, { points: calibClicks[id] });
      out.innerHTML = `RMSE <b>${fmt(r.rmse_in, 3)} in</b><br>` +
        (r.per_point || []).map((p) => `${esc(p.name)}: ${fmt(p.err_px, 2)} px`).join('<br>');
      loadCalibration();
    } else if (act === 'istart') {
      await api('POST', `/api/calib/intrinsics/${encodeURIComponent(id)}/start`); out.textContent = 'Recording intrinsics frames...';
    } else if (act === 'istop') {
      const r = await api('POST', `/api/calib/intrinsics/${encodeURIComponent(id)}/stop`);
      out.textContent = `Intrinsics: reprojection RMSE ${fmt(r.reprojection_rmse_px, 3)} px, ${r.frames_used} frames`;
      loadCalibration();
    }
  });
});
// Cross-check: POST /api/calib/crosscheck -> rows [{name, xyz_measured, xyz_expected, error_in}] + max_error_in.
// Accepts either a bare array or an object holding the array under points/rows/results.
const CROSSCHECK_OK_IN = 1.0;
const fmtXyz = (a) => (Array.isArray(a) ? '[' + a.map((v) => fmt(v, 1)).join(', ') + ']' : '-');
function renderCrosscheck(r) {
  const rows = Array.isArray(r) ? r : (r && (r.points || r.rows || r.results)) || [];
  let max = r && !Array.isArray(r) ? r.max_error_in : null;
  if (max == null) max = rows.reduce((m, p) => Math.max(m, Number(p.error_in) || 0), 0);
  const cls = (e) => (e != null && Number(e) < CROSSCHECK_OK_IN ? 'xc-ok' : 'xc-bad');
  $('crosscheckOut').innerHTML = rows.length
    ? `<div>Max error <b class="${cls(max)}">${fmt(max, 2)} in</b> (green = under ${CROSSCHECK_OK_IN} in)</div>
      <table class="data"><thead><tr><th>Point</th><th>Measured (in)</th><th>Expected (in)</th><th>Error in</th></tr></thead><tbody>${
  rows.map((p) => `<tr><td>${esc(p.name)}</td><td>${esc(fmtXyz(p.xyz_measured))}</td><td>${esc(fmtXyz(p.xyz_expected))}</td><td class="${cls(p.error_in)}">${fmt(p.error_in, 2)}</td></tr>`).join('')
}</tbody></table>`
    : '<div class="muted">No cross-check points returned.</div>';
}
$('btnCrosscheck').onclick = () => guarded(async () => {
  $('crosscheckOut').textContent = 'Running cross-check...';
  try { renderCrosscheck(await api('POST', '/api/calib/crosscheck')); }
  catch (e) { $('crosscheckOut').textContent = ''; throw e; }
});
async function loadCalibPoints() {
  const warn = $('calibWarn');
  let list = null;
  try {
    const r = await api('GET', '/api/calib/points');
    if (Array.isArray(r) && r.length && r.every((p) => p && typeof p.name === 'string')) list = r;
  } catch (e) { console.error(e); }
  if (list) {
    warn.style.display = 'none'; warn.textContent = '';
  } else {
    list = FALLBACK_CALIB_NAMES.map((name) => ({ name, xyz: null }));
    warn.textContent = 'Could not load reference points from the server; showing built-in names that may be out of date. Check docs/calibration.md before clicking.';
    warn.style.display = '';
  }
  const changed = list.length !== calibPoints.length || list.some((p, i) => p.name !== calibPoints[i].name);
  calibPoints = list;
  if (changed) { for (const k of Object.keys(calibClicks)) calibClicks[k] = []; }
  (((state.config && state.config.sources) || [])).forEach((s) => paintCalib(s.cam_id));
}
async function loadCalibration() {
  await loadCalibPoints();
  await guarded(async () => {
    const c = await api('GET', '/api/calib');
    const summ = {};
    for (const [k, v] of Object.entries(c || {})) {
      summ[k] = v && typeof v === 'object' && !Array.isArray(v) ? Object.keys(v) : v;
    }
    $('calibJson').textContent = 'Top-level summary:\n' + JSON.stringify(summ, null, 1) + '\n\nFull:\n' + JSON.stringify(c, null, 1);
  });
}

// ---------- settings ----------
let devices = [];
function inp(path, val, type = 'number', cls = '') {
  const v = type === 'json' ? JSON.stringify(val ?? null) : (val ?? '');
  return `<input data-path="${esc(path)}" data-type="${type}" type="${type === 'json' ? 'text' : type}" step="any" class="${cls}" value="${esc(v)}">`;
}
function field(label, html) { return `<span class="f">${esc(label)}${html}</span>`; }
async function renderSettings() {
  const form = $('settingsForm');
  if (!state.config) { form.textContent = 'config not loaded'; return; }
  try { devices = await api('GET', '/api/devices'); } catch (e) { devices = []; }
  const c = state.config; const r = c.robot || {}; const d = c.detector || {};
  const kinds = ['file', 'device', 'rtmp', 'url'];
  const devOpts = devices.map((x) => `<option value="${esc(x.index)}">device ${esc(x.index)} (${esc(x.width)}x${esc(x.height)} @${esc(x.fps)})</option>`).join('');
  form.innerHTML = `
  <fieldset><legend>Sources</legend><div id="srcs">${(c.sources || []).map((s, i) => srcRow(s, i, kinds)).join('')}</div>
    <button type="button" id="addSrc">Add source</button>
    ${profileNames().length ? `<span class="muted"> Profile: </span><select id="profilePick">${profileNames().map((n) => `<option>${esc(n)}</option>`).join('')}</select>
    <button type="button" id="applyProfile">Apply profile to all sources</button>` : ''}
    <span class="muted"> Device picker: </span><select id="devPick"><option value="">detected devices</option>${devOpts}</select>
    <span class="muted">(choose, then click a device-kind row's "use" button)</span></fieldset>
  <fieldset><legend>Match</legend>
    ${field('alliance', `<select data-path="alliance" data-type="text">${['red', 'blue'].map((a) => `<option ${a === c.alliance ? 'selected' : ''}>${a}</option>`).join('')}</select>`)}
    ${field('hive_up_cell', `<select data-path="hive_up_cell" data-type="text">${['audience', 'far'].map((a) => `<option ${a === c.hive_up_cell ? 'selected' : ''}>${a}</option>`).join('')}</select>`)}
    ${field('calibration_path', inp('calibration_path', c.calibration_path, 'text', 'wide'))}
    ${field('preview_fps', inp('preview_fps', c.preview_fps))}
    ${field('burst_gap_s', inp('burst_gap_s', c.burst_gap_s))}
    ${field('settle_time_s', inp('settle_time_s', c.settle_time_s))}</fieldset>
  <fieldset><legend>Robot (in)</legend>
    ${['length', 'width', 'height', 'launch_exit_height'].map((k) => field(k, inp('robot.' + k, r[k]))).join('')}</fieldset>
  <fieldset><legend>Detector</legend>
    ${['min_radius_px', 'max_radius_px', 'motion_thresh'].map((k) => field(k, inp('detector.' + k, d[k]))).join('')}
    ${field('pollen_hsv [[lo],[hi]]', inp('detector.pollen_hsv', d.pollen_hsv, 'json', 'wide'))}
    ${field('nectar_hsv [[lo],[hi]]', inp('detector.nectar_hsv', d.nectar_hsv, 'json', 'wide'))}</fieldset>
  <button type="submit" id="btnSave">Save config</button>`;
  refreshRtmpHints();
  applyDemoUi();
}
function srcRow(s, i, kinds) {
  return `<div class="srcrow" data-i="${i}">
    ${field('cam_id', `<input data-s="cam_id" value="${esc(s.cam_id)}" size="8">`)}
    ${field('kind', `<select data-s="kind">${kinds.map((k) => `<option ${k === s.kind ? 'selected' : ''}>${k}</option>`).join('')}</select>`)}
    ${field('target', `<input data-s="target" class="wide" value="${esc(s.target)}">`)}
    <span class="rtmphint muted"></span>
    ${field('width', `<input data-s="width" type="number" value="${esc(s.width)}">`)}
    ${field('height', `<input data-s="height" type="number" value="${esc(s.height)}">`)}
    ${field('fps_hint', `<input data-s="fps_hint" type="number" value="${esc(s.fps_hint)}">`)}
    ${field('realtime', `<input data-s="realtime" type="checkbox" ${s.realtime ? 'checked' : ''}>`)}
    ${field('loop', `<input data-s="loop" type="checkbox" ${s.loop ? 'checked' : ''}>`)}
    <button type="button" data-act="usedev">use picked device</button>
    <button type="button" data-act="rmsrc">remove</button></div>`;
}
// Profiles come from config.profiles ({name: {source fields...}}); applying one overrides those fields on
// every source but never changes its identity (cam_id / kind / target).
const PROFILE_KEEP = new Set(['cam_id', 'kind', 'target']);
function profileNames() { return Object.keys((state.config && state.config.profiles) || {}); }
function applyProfileToSource(src, profile) {
  const out = { ...src };
  for (const [k, v] of Object.entries(profile || {})) {
    if (!PROFILE_KEEP.has(k) && (v === null || typeof v !== 'object')) out[k] = v;
  }
  return out;
}
// For rtmp sources, show the full publish URL (from status.rtmp.urls) next to the target field.
function refreshRtmpHints() {
  document.querySelectorAll('#srcs .srcrow').forEach((row) => {
    const hint = row.querySelector('.rtmphint'); if (!hint) return;
    const kind = row.querySelector('[data-s=kind]').value;
    if (kind !== 'rtmp') { hint.innerHTML = ''; return; }
    const cam = row.querySelector('[data-s=cam_id]').value;
    const url = (state.rtmpUrls || {})[cam];
    hint.innerHTML = `<br>Publish URL: ${url ? `<code class="rtmpurl">${esc(url)}</code>` : '<i>(save config to see the URL)</i>'}
      <br>Enter the stream name, e.g. cam0; publish from GoPro Quik or ffmpeg to this URL.`;
  });
}
function readSources() {
  const base = (state.config.sources || []);
  return [...document.querySelectorAll('#srcs .srcrow')].map((row, i) => {
    const o = { ...(base[Number(row.dataset.i)] || base[i] || {}) };
    row.querySelectorAll('[data-s]').forEach((el) => {
      const k = el.dataset.s;
      if (el.type === 'checkbox') o[k] = el.checked;
      else if (el.type === 'number') o[k] = el.value === '' ? null : Number(el.value);
      else o[k] = el.value;
    });
    return o;
  });
}
function setPath(obj, path, val) {
  const parts = path.split('.'); let o = obj;
  for (let i = 0; i < parts.length - 1; i++) { o[parts[i]] = o[parts[i]] || {}; o = o[parts[i]]; }
  o[parts[parts.length - 1]] = val;
}
$('settingsForm').addEventListener('click', (ev) => {
  const t = ev.target;
  if (t.id === 'addSrc') {
    state.config.sources = readSources();
    state.config.sources.push({ cam_id: 'cam' + state.config.sources.length, kind: 'device', target: '0', width: 1920, height: 1080, fps_hint: 60, backend: 'auto', loop: true, realtime: true });
    renderSettings();
  } else if (t.id === 'applyProfile') {
    const pname = $('profilePick').value;
    const prof = state.config.profiles && state.config.profiles[pname];
    if (!prof) { toast('Pick a profile first'); return; }
    state.config.sources = readSources().map((s) => applyProfileToSource(s, prof));
    renderSettings();
    toast(`Profile "${pname}" applied to sources; click Save config to keep it`);
  } else if (t.dataset.act === 'rmsrc') {
    state.config.sources = readSources(); state.config.sources.splice(Number(t.closest('.srcrow').dataset.i), 1); renderSettings();
  } else if (t.dataset.act === 'usedev') {
    const idx = $('devPick').value; if (idx === '') { toast('Pick a device first'); return; }
    const d = devices.find((x) => String(x.index) === idx); const row = t.closest('.srcrow');
    row.querySelector('[data-s=kind]').value = 'device'; row.querySelector('[data-s=target]').value = idx;
    if (d) { row.querySelector('[data-s=width]').value = d.width; row.querySelector('[data-s=height]').value = d.height; }
  }
});
$('settingsForm').addEventListener('input', (ev) => { if (ev.target.dataset && ev.target.dataset.s) refreshRtmpHints(); });
$('settingsForm').addEventListener('change', (ev) => { if (ev.target.dataset && ev.target.dataset.s) refreshRtmpHints(); });
$('settingsForm').addEventListener('submit', (ev) => {
  ev.preventDefault();
  guarded(async () => {
    const merged = JSON.parse(JSON.stringify(state.config));
    merged.sources = readSources();
    for (const el of $('settingsForm').querySelectorAll('[data-path]')) {
      let v = el.value; const ty = el.dataset.type;
      if (ty === 'number') v = v === '' ? null : Number(v);
      else if (ty === 'json') { try { v = JSON.parse(v); } catch (e) { throw new Error(`${el.dataset.path}: invalid JSON`); } }
      setPath(merged, el.dataset.path, v);
    }
    state.config = await api('PUT', '/api/config', merged);
    renderCams(); renderCalibCams(); updateSessName();
    if (state.viewer) state.viewer.setRobot(state.config.robot);
    toast('Config saved');
  });
});

// ---------- setup wizard ----------
// Contract: docs/api.md "Setup, auto-calibration and tuning". Steps: Cameras -> Tags -> Colors -> Done.
const FALLBACK_PROFILE = { width: 1920, height: 1080, fps_hint: 90 };
const FALLBACK_TAG_NAMES = [
  'frame top corner (-X,+Y)', 'frame top corner (+X,+Y)', 'frame top corner (-X,-Y)', 'frame top corner (+X,-Y)',
];
const setup = { status: null, step: 'cameras', statusTimer: null, previewTimer: null, previews: [], assigned: false };

function plainError(e) {
  const m = String((e && e.message) || e);
  const j = m.indexOf('{');
  if (j >= 0) {
    try {
      const o = JSON.parse(m.slice(j));
      const d = o.detail ?? o.error ?? o.message;
      if (d) return typeof d === 'string' ? d : JSON.stringify(d);
    } catch (err) { /* not JSON */ }
  }
  return m;
}
function setupProfile() {
  if (!$('chkProfile').checked) return null;
  return (state.config && state.config.profiles && state.config.profiles.arducam_1080p90) || FALLBACK_PROFILE;
}
function showStep(name) {
  setup.step = name;
  document.querySelectorAll('#setupStepBtns button').forEach((b) => b.classList.toggle('active', b.dataset.step === name));
  document.querySelectorAll('.setupstep').forEach((s) => s.classList.toggle('active', s.dataset.step === name));
  if (name === 'tags') loadTagInfo();
  if (name === 'colors') renderColorCams();
  if (name === 'hivetags') renderLearnSummary();
  renderSetupStatus();
}
$('setupStepBtns').addEventListener('click', (ev) => { if (ev.target.dataset && ev.target.dataset.step) showStep(ev.target.dataset.step); });
function renderSetupStatus() {
  const st = setup.status; if (!st) return;
  const recs = Array.isArray(st.recommendations) ? st.recommendations : [];
  const html = recs.map((r) => `<div>${esc(r)}</div>`).join('');
  document.querySelectorAll('#tab-setup .hints').forEach((h) => { h.innerHTML = html; });
  if (!setup.previews.length) {
    const devs = st.cameras_detected || [];
    $('setupCamMsg').textContent = devs.length
      ? `Detected ${devs.length} camera(s): ` + devs.map((d) => `device ${d.index} (${d.width}x${d.height} @${d.fps})`).join(', ')
      : 'No cameras detected yet. Plug them in; this list refreshes by itself.';
  }
  if (setup.step === 'hivetags') renderLearnSummary();
  const seen = st.tags_seen || {};
  const ids = Object.keys(seen);
  $('tagsSeen').textContent = ids.length
    ? 'Tags currently visible: ' + ids.map((c) => `${c}: ${(seen[c] || []).length ? seen[c].join(', ') : 'none'}`).join(' | ')
    : 'No tag information yet (start the pipeline so the cameras are running).';
}
async function pollSetup() {
  try { setup.status = await api('GET', '/api/setup/status'); renderSetupStatus(); } catch (e) { console.error(e); }
}
function refreshSetupImages() {
  document.querySelectorAll('#tab-setup .thumb img').forEach((img) => {
    if (img.offsetParent === null || !img.dataset.cam) return;
    img.src = `/api/preview/${encodeURIComponent(img.dataset.cam)}.jpg?t=${Date.now()}`;
  });
}
function stopSetup() {
  clearInterval(setup.statusTimer); clearInterval(setup.previewTimer);
  setup.statusTimer = null; setup.previewTimer = null;
}
function startSetup() {
  stopSetup();
  pollSetup();
  setup.statusTimer = setInterval(pollSetup, 2000);
  setup.previewTimer = setInterval(refreshSetupImages, 1000);
}
async function applySources(sources) {
  try { await api('POST', '/api/pipeline/stop'); } catch (e) { /* was not running */ }
  const merged = JSON.parse(JSON.stringify(state.config));
  merged.sources = sources;
  state.config = await api('PUT', '/api/config', merged);
  await api('POST', '/api/pipeline/start');
  renderCams(); renderCalibCams();
}
function deviceSource(cam, d, profile) {
  return applyProfileToSource({ cam_id: cam, kind: 'device', target: String(d.index), width: d.width, height: d.height,
    fps_hint: d.fps, backend: 'auto', loop: false, realtime: true }, profile);
}
function renderCameraThumbs() {
  $('setupDevices').innerHTML = setup.previews.map((p) => `<div class="thumb">
    <img alt="${esc(p.label)}" data-cam="${esc(p.cam)}" src="/api/preview/${encodeURIComponent(p.cam)}.jpg?t=${Date.now()}">
    <div>${esc(p.label)}${p.role ? ` &rarr; <b>${esc(p.role)}</b>` : ''}</div>
    ${setup.assigned ? '' : `<button data-act="wall" data-index="${esc(p.dev.index)}">This is the -X wall camera</button>`}</div>`).join('');
}
$('btnDetectStart').onclick = () => guarded(async () => {
  await pollSetup();
  const devs = ((setup.status && setup.status.cameras_detected) || []).slice(0, 4);
  if (!devs.length) { $('setupCamMsg').textContent = 'No cameras detected. Plug them in and try again.'; return; }
  const prof = setupProfile();
  $('setupCamMsg').textContent = 'Starting temporary previews...';
  await applySources(devs.map((d) => deviceSource(`dev${d.index}`, d, prof)));
  setup.previews = devs.map((d) => ({ cam: `dev${d.index}`, dev: d, label: `device ${d.index} (${d.width}x${d.height})`, role: '' }));
  setup.assigned = false;
  renderCameraThumbs();
  $('setupCamMsg').textContent = 'Click the button under the picture from the camera on the minus-X wall.';
});
$('setupDevices').addEventListener('click', (ev) => {
  const b = ev.target.closest('button[data-act=wall]'); if (!b) return;
  guarded(async () => {
    const wall = setup.previews.find((p) => String(p.dev.index) === b.dataset.index);
    const other = setup.previews.find((p) => p !== wall);
    if (!wall) return;
    const prof = setupProfile();
    const sources = [deviceSource('cam0', wall.dev, prof)];
    if (other) sources.push(deviceSource('cam1', other.dev, prof));
    await applySources(sources);
    setup.previews = [{ ...wall, cam: 'cam0', role: 'cam0' }, ...(other ? [{ ...other, cam: 'cam1', role: 'cam1' }] : [])];
    setup.assigned = true;
    renderCameraThumbs();
    $('setupCamMsg').textContent = other
      ? 'Saved: the wall camera is cam0 and the other is cam1. Next: Tags.'
      : 'Saved: the only camera is cam0. Next: Tags.';
    pollSetup();
  });
});
// "kit" = the printed tag sheet, "hive" = the HIVE's own tags (no printer).
function tagSource() {
  const el = document.querySelector('#tagSource input[name=tagSource]:checked');
  return el ? el.value : 'kit';
}
$('tagSource').addEventListener('change', () => loadTagInfo());
async function loadTagInfo() {
  if (tagSource() === 'hive') {
    $('lnkTagsPdf').parentElement.style.display = 'none';
    $('tagsInfo').innerHTML = `<div>No tags to print: the cameras will use the tags that are part of the HIVE itself.
      Make sure both cameras can see the HIVE, then press Auto-calibrate. The printed tag sheet gives a more accurate result when you can print it.</div>`;
    return;
  }
  $('lnkTagsPdf').parentElement.style.display = '';
  let items = null;
  try {
    const t = await api('GET', '/api/calib/tags');
    if (Array.isArray(t) && t.length) items = t.map((x) => `${x.name} (tag id ${x.id}, ${fmt(x.size_in, 1)} in square)`);
  } catch (e) { console.error(e); }
  if (!items) items = FALLBACK_TAG_NAMES.map((n) => `${n} (tag names are printed under each tag)`);
  $('tagsInfo').innerHTML = `<div>Print the sheet, cut the tags out and tape one at each corner of the HIVE frame:</div>
    <ul>${items.map((n) => `<li>${esc(n)}</li>`).join('')}</ul>
    <div>Each camera must see at least 2 tags. Then press Auto-calibrate.</div>`;
}
function renderAutoCal(r) {
  const skip = new Set(['max_error_in', 'crosscheck', 'warnings']);
  let per = r && (r.cameras || r.results || r.per_camera || r.extrinsics);
  if (!per || typeof per !== 'object') {
    per = Object.fromEntries(Object.entries(r || {}).filter(([k, v]) => !skip.has(k) && v && typeof v === 'object'));
  }
  const entries = Array.isArray(per) ? per.map((x, i) => [x.cam_id ?? `camera ${i + 1}`, x]) : Object.entries(per);
  const rows = entries.map(([cam, v]) => {
    const err = v && (v.error || v.detail);
    if (err) return `<tr><td>${esc(cam)}</td><td class="xc-bad" colspan="3">${esc(typeof err === 'string' ? err : JSON.stringify(err))}</td></tr>`;
    const good = v && v.rmse_in != null && Number(v.rmse_in) < CROSSCHECK_OK_IN;
    return `<tr><td>${esc(cam)}</td><td class="${good ? 'xc-ok' : 'xc-bad'}">${fmt(v && v.rmse_in, 2)} in</td>
      <td>${fmt(v && v.reprojection_px, 2)} px</td><td>${esc(((v && v.tags_used) || []).join(', ') || '-')}</td></tr>`;
  }).join('');
  const max = r ? r.max_error_in : null;
  const warnList = r ? [].concat(r.warning ?? [], r.warnings ?? []).filter((w) => w) : [];
  const warnHtml = warnList.map((w) => `<div class="warnbox card">${esc(typeof w === 'string' ? w : JSON.stringify(w))}</div>`).join('');
  $('autoCalOut').innerHTML = `${warnHtml}<div>Max error <b class="${max != null && Number(max) < CROSSCHECK_OK_IN ? 'xc-ok' : 'xc-bad'}">${fmt(max, 2)} in</b>
    (green = under ${CROSSCHECK_OK_IN} in)</div>
    <table class="data"><thead><tr><th>Camera</th><th>Pose error</th><th>Reprojection</th><th>Tags used</th></tr></thead><tbody>${rows}</tbody></table>`;
}
$('btnAutoCal').onclick = async () => {
  $('autoCalOut').textContent = 'Calibrating...';
  try { renderAutoCal(await api('POST', '/api/calib/auto_all', { source: tagSource() })); pollSetup(); }
  catch (e) { $('autoCalOut').innerHTML = `<div class="xc-bad">${esc(plainError(e))}</div>`; }
};
// Learn HIVE tags: one POST per physical HIVE state (audience CELL up, then far CELL up).
setup.learned = { audience: false, far: false };
function renderLearnSummary() {
  const both = (setup.learned.audience && setup.learned.far)
    || [state.status, setup.status].some((s) => s && s.hive_state_source === 'tags');
  const todo = ['audience', 'far'].filter((k) => !setup.learned[k]);
  $('learnSummary').innerHTML = both
    ? '<div class="xc-ok">Both HIVE states are learned. From now on the HIVE state (and tips) are detected automatically from the tags; you do not need to set it by hand.</div>'
    : `<div class="muted">Learned: ${['audience', 'far'].filter((k) => setup.learned[k]).join(', ') || 'none yet'}. Still to do: ${todo.join(', ')}.</div>`;
}
function renderLearnResult(r, upCell) {
  const ids = (a) => (Array.isArray(a) && a.length ? a.join(', ') : 'none');
  const vis = r.visible_per_camera || {};
  const visTxt = Array.isArray(vis) ? vis.join(', ') : Object.entries(vis).map(([c, v]) => `${c}: ${Array.isArray(v) ? v.length : v}`).join(' | ');
  const missing = Array.isArray(r.missing_ids) ? r.missing_ids : [];
  $('learnOut').innerHTML = `<div><b>${esc(upCell)} CELL up</b> learned.</div>
    <table class="data"><tbody>
    <tr><td>Learned tag ids</td><td class="xc-ok">${esc(ids(r.learned_ids))}</td></tr>
    <tr><td>Missing tag ids</td><td class="${missing.length ? 'muted' : 'xc-ok'}">${esc(ids(missing))}</td></tr>
    <tr><td>Visible per camera</td><td>${esc(visTxt || '-')}</td></tr>
    ${r.up_cell_error_in != null ? `<tr><td>Up CELL tag check (manual vs seen)</td><td class="${Number(r.up_cell_error_in) < CROSSCHECK_OK_IN ? 'xc-ok' : 'xc-bad'}">${fmt(r.up_cell_error_in, 2)} in</td></tr>` : ''}
    <tr><td>Max residual</td><td class="${r.max_residual_in != null && Number(r.max_residual_in) < CROSSCHECK_OK_IN ? 'xc-ok' : 'xc-bad'}">${fmt(r.max_residual_in, 2)} in</td></tr>
    </tbody></table>`;
}
$('btnLearn').onclick = async () => {
  const upCell = $('learnState').value;
  const alliance = $('selAlliance').value || (state.config && state.config.alliance) || 'red';
  $('learnOut').textContent = 'Learning...';
  try {
    renderLearnResult(await api('POST', '/api/calib/hive_tags/learn', { state: { alliance, up_cell: upCell } }), upCell);
    setup.learned[upCell] = true;
    if (!setup.learned[upCell === 'audience' ? 'far' : 'audience']) $('learnState').value = upCell === 'audience' ? 'far' : 'audience';
    pollSetup();
  } catch (e) { $('learnOut').innerHTML = `<div class="xc-bad">${esc(plainError(e))}</div>`; }
  renderLearnSummary();
};
function renderColorCams() {
  const srcs = (state.config && state.config.sources) || [];
  $('colorCams').innerHTML = srcs.length ? srcs.map((s) => `<div class="thumb clickable">
    <img alt="${esc(s.cam_id)}" data-cam="${esc(s.cam_id)}" src="/api/preview/${encodeURIComponent(s.cam_id)}.jpg?t=${Date.now()}">
    <div>${esc(s.cam_id)}</div></div>`).join('') : '<div class="muted">No cameras configured yet (step 1).</div>';
}
$('colorCams').addEventListener('click', (ev) => {
  const img = ev.target; if (img.tagName !== 'IMG') return;
  guarded(async () => {
    const cam = img.dataset.cam; const r = img.getBoundingClientRect();
    const props = (((state.status || {}).cameras || {})[cam] || {}).props || {};
    // click position as a fraction of the picture, scaled to the full-resolution frame size
    const u = ((ev.clientX - r.left) / r.width) * (props.width || img.naturalWidth);
    const v = ((ev.clientY - r.top) / r.height) * (props.height || img.naturalHeight);
    const ball = $('colorBall').value;
    const res = await api('POST', '/api/detector/sample', { cam_id: cam, u, v, ball_type: ball });
    $('colorOut').textContent = `${ball} color range updated from ${cam} at (${Math.round(u)}, ${Math.round(v)}):\n` + JSON.stringify(res, null, 1);
    state.config = await api('GET', '/api/config');   // keep the local copy in sync so Settings does not save a stale range
  });
});
$('btnFinish').onclick = () => guarded(async () => {
  const st = await api('GET', '/api/pipeline/status');
  if (!st.running) await api('POST', '/api/pipeline/start');
  const r = await api('POST', '/api/sessions', { name: sessionNameNow() });
  state.shots = []; state.stats = null; renderStats(); renderShots();
  await refreshSessions();
  setSession(r.session_id);
  $('finishMsg').textContent = `Pipeline running; session ${r.session_id} started.`;
  showTab('dashboard');
});

// ---------- init ----------
async function init() {
  connectWs();
  renderStats(); renderShots();
  await guarded(async () => {
    state.config = await api('GET', '/api/config');
    if (state.config.alliance) $('selAlliance').value = state.config.alliance;
    if (state.config.hive_up_cell) $('selUpCell').value = state.config.hive_up_cell;
    renderCams(); renderCalibCams();
    updateSessName();
  });
  await guarded(loadSessions);
  await guarded(async () => { state.status = await api('GET', '/api/pipeline/status'); renderStatus(); });
  await guarded(async () => {
    const st = await api('GET', '/api/setup/status');
    if (state.demo) return;   // demo mode never opens the wizard
    if (st && (st.sources_configured === false || st.calibration_loaded === false)) showTab('setup');
  });
}
init();
