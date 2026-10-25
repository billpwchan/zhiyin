const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const names = (arts) => (arts || []).map((a) => a.name).join(t('、'));
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const store = {
  get(k) { try { return JSON.parse(localStorage.getItem(`zhiyin.${k}`)); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(`zhiyin.${k}`, JSON.stringify(v)); } catch { /* private mode */ } },
  del(k) { try { localStorage.removeItem(`zhiyin.${k}`); } catch { /* private mode */ } },
};
// what this browser remembers about an account stays with that account
const acct = (k) => `${S?.me?.uid}.${k}`;

const I = {
  play: '<svg class="i-play" viewBox="0 0 24 24"><path d="M8 5.5v13l11-6.5z"/></svg>',
  pause: '<svg class="i-pause" viewBox="0 0 24 24"><rect x="6.5" y="5.5" width="3.8" height="13" rx="1"/><rect x="13.7" y="5.5" width="3.8" height="13" rx="1"/></svg>',
  prev: '<svg viewBox="0 0 24 24"><path d="M6.5 6.5v11"/><path d="M17.5 6.8v10.4L9.8 12z" fill="currentColor"/></svg>',
  next: '<svg viewBox="0 0 24 24"><path d="M17.5 6.5v11"/><path d="M6.5 6.8v10.4l7.7-5.2z" fill="currentColor"/></svg>',
  heart: '<svg viewBox="0 0 24 24"><path d="M12 19.5s-7.5-4.5-7.5-10A4.2 4.2 0 0 1 12 7a4.2 4.2 0 0 1 7.5 2.5c0 5.5-7.5 10-7.5 10z"/></svg>',
  x: '<svg viewBox="0 0 24 24"><path d="M7 7l10 10M17 7 7 17"/></svg>',
  branch: '<svg viewBox="0 0 24 24"><path d="M6 4v7a4 4 0 0 0 4 4h9"/><path d="m15 11 4 4-4 4"/></svg>',
  ext: '<svg viewBox="0 0 24 24"><path d="M14 5h5v5M19 5l-8 8M17 14v5H5V7h5"/></svg>',
  plus: '<svg viewBox="0 0 24 24"><path d="M12 6v12M6 12h12"/></svg>',
  refresh: '<svg viewBox="0 0 24 24"><path d="M19.5 11A7.5 7.5 0 1 0 17.3 16.3M19.5 5v6h-6"/></svg>',
  lyrics: '<svg viewBox="0 0 24 24"><path d="M4.5 6.5h15M4.5 11h10M4.5 15.5h12M4.5 20h6"/></svg>',
  pip: '<svg viewBox="0 0 24 24"><rect x="3.5" y="5" width="17" height="14" rx="2.5"/><rect x="12" y="11.5" width="6" height="4.5" rx="1" fill="currentColor" stroke="none"/></svg>',
  full: '<svg viewBox="0 0 24 24"><path d="M4.5 9V4.5H9M15 4.5h4.5V9M19.5 15v4.5H15M9 19.5H4.5V15"/></svg>',
  shrink: '<svg viewBox="0 0 24 24"><path d="M9 4.5V9H4.5M19.5 9H15V4.5M15 19.5V15h4.5M4.5 15H9v4.5"/></svg>',
  more: '<svg viewBox="0 0 24 24"><circle cx="6" cy="12" r="1.3" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.3" fill="currentColor" stroke="none"/><circle cx="18" cy="12" r="1.3" fill="currentColor" stroke="none"/></svg>',
  updown: '<svg viewBox="0 0 24 24"><path d="m8 9 4-4 4 4M8 15l4 4 4-4"/></svg>',
  check: '<svg viewBox="0 0 24 24"><path d="m5.5 12.5 4 4 9-9"/></svg>',
  gear: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 3.5v2.2M12 18.3v2.2M20.5 12h-2.2M5.7 12H3.5M18 6l-1.6 1.6M7.6 16.4 6 18M18 18l-1.6-1.6M7.6 7.6 6 6"/></svg>',
  out: '<svg viewBox="0 0 24 24"><path d="M14 5H6.5v14H14M10 12h10M17 8.5 20.5 12 17 15.5"/></svg>',
  keyb: '<svg viewBox="0 0 24 24"><rect x="3.5" y="6.5" width="17" height="11" rx="2"/><path d="M7 10h.01M10.5 10h.01M14 10h.01M17 10h.01M8 14h8"/></svg>',
  down: '<svg viewBox="0 0 24 24"><path d="m7 10 5 5 5-5"/></svg>',
  close: '<svg viewBox="0 0 24 24"><path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/></svg>',
  swap: '<svg viewBox="0 0 24 24"><path d="M7 8h12M15.5 4.5 19 8l-3.5 3.5M17 16H5M8.5 12.5 5 16l3.5 3.5"/></svg>',
};

let S = null;          // server state
let ST = [];           // stations, in display order
let Q = null;          // the queue being played: { key, st, tracks, reserve, i, played }
let view = 'listen';
let pendingAsk = null;
let WARM = null;       // radios from the newest likes, while a new listener's stations are being made
const queues = new Map();
const ready = () => !S.me || S.me.status === 'ready';
const fb = new Map();
const prefs = { lyr: store.get('lyr') ?? true, lyrNarrow: true, imm: false };

async function api(path, body) {
  // Say which account this page shows, so a tab left open after switching accounts can't write into the other one.
  const headers = S?.me?.uid ? { 'X-Zhiyin-Uid': S.me.uid } : {};
  const r = await fetch(path, body === undefined ? { headers } : { method: 'POST', headers: { ...headers, 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (r.status === 401) { location.href = '/login'; throw new Error(data.detail || t('需要重新登录')); }
  if (r.status === 409 && data.detail === 'account-changed') { location.reload(); throw new Error(t('这个浏览器已经换了账号')); }
  if (r.status === 409 && data.detail === 'busy') throw Object.assign(new Error(t('上一次还没做完，稍等一下')), { code: 'busy' });
  if (!r.ok) throw new Error(data.detail || r.statusText);
  return data;
}

/* ---------- covers ---------- */
const isGoogleArt = (u) => /googleusercontent|ggpht/.test(u || '');
const letterboxed = (u) => /\/(hq|sd)default/.test(u || '');
function cover(p, size) {
  if (p.thumb && isGoogleArt(p.thumb)) return p.thumb.replace(/=w\d+-h\d+/, `=w${size}-h${size}`).replace(/=s\d+/, `=s${size}`);
  if (size > 300) return `https://i.ytimg.com/vi/${p.vid}/maxresdefault.jpg`;
  return p.thumb || `https://i.ytimg.com/vi/${p.vid}/mqdefault.jpg`;
}
// 4:3 YouTube thumbnails carry black bars around 16:9 video; scale them out of the square crop.
const lb = (u) => (letterboxed(u) ? 'lb' : '');
// Covers go through the local cache: same origin (so the ambient colour can read pixels) and no hotlink limits.
const px = (u) => `/api/img?u=${encodeURIComponent(u)}`;
function imgTag(p, size) {
  const u = cover(p, size);
  return `<img loading="lazy" src="${px(u)}" class="${lb(u)}" alt="">`;
}

const spaced = (name) => (/[A-Za-z0-9.)]$/.test(name) ? `${name} ` : name);
const fmt = (s) => {
  if (!s && s !== 0) return '';
  s = Math.round(s);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = String(s % 60).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${x}` : `${m}:${x}`;
};
function when(ts) {
  const d = new Date(ts * 1000), now = new Date();
  const hm = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  const days = Math.round((new Date(now.toDateString()) - new Date(d.toDateString())) / 864e5);
  return days === 0 ? t('今天 {hm}', { hm }) : days === 1 ? t('昨天 {hm}', { hm }) : d.toLocaleDateString(LANG, { month: 'short', day: 'numeric' });
}
function reasonOf(p) {
  if (p.reason) return p.reason;
  if (p.near) return t('听感接近你收藏的〈{s}〉', { s: p.near });
  const v = p.via?.[0];
  return v ? t('和你喜欢的〈{s}〉一路', { s: v.split(' - ')[0] }) : '';
}

/* ---------- toast ---------- */
function toast(msg, actions = [], ms) {
  const t = $('#toast');
  t.innerHTML = `<span>${esc(msg)}</span>${actions.length ? `<div class="acts">${actions.map(([l], i) => `<button data-i="${i}">${esc(l)}</button>`).join('')}</div>` : ''}`;
  $$('button', t).forEach((b) => { b.onclick = () => { t.classList.remove('show'); actions[+b.dataset.i][1](); }; });
  t.classList.add('show');
  clearTimeout(t._h);
  t._h = setTimeout(() => t.classList.remove('show'), ms || (actions.length ? 6000 : 2800));
}

/* ---------- stations ---------- */
const artistLine = (picks) => [...new Set((picks || []).map((p) => p.artists?.[0]?.name).filter(Boolean))].slice(0, 3).join(t('、'));

function buildStations() {
  const ed = S.edition;
  const out = [];
  if (WARM?.tracks?.length) out.push({ key: 'warm', group: 'warm', name: WARM.name, sub: WARM.sub, when: WARM.seeds?.length ? t('从〈{s}〉等你最近的喜欢出发', { s: WARM.seeds[0] }) : '', tracks: WARM.tracks, reserve: [] });
  if (pendingAsk) out.push({ key: 'ask:pending', group: 'ask', name: pendingAsk, sub: t('正在找…'), tracks: [], pending: true });
  (S.asks || []).slice(0, 4).forEach((a) => out.push({
    key: `ask:${a.created}`, group: 'ask', name: a.intent, sub: artistLine(a.picks), when: t('你说：{q}', { q: a.q }), tracks: a.picks, reserve: [],
  }));
  for (const l of ed?.lanes || []) out.push({ key: l.key, group: 'lane', name: l.name, sub: artistLine(l.picks), when: l.when, tracks: l.picks, reserve: l.reserve || [] });
  if (ed?.focus?.picks?.length) out.push({ key: 'focus', group: 'lane', name: t('专注'), sub: t('一小时左右的长歌单'), when: ed.focus.when, tracks: ed.focus.picks, reserve: [] });
  ST = out;
}

function stHTML(s) {
  const imgs = s.tracks.slice(0, s.tracks.length >= 4 ? 4 : 1).map((p) => imgTag(p, 120)).join('');
  return `<button class="st ${s.pending ? 'pending' : ''}" data-st="${esc(s.key)}" ${Q?.key === s.key ? 'aria-current="true"' : ''} title="${esc(s.when || '')}">
    <span class="mosaic ${s.pending ? 'wait' : ''} ${s.tracks.length < 4 ? 'one' : ''}">${s.pending ? '' : imgs}</span>
    <span class="txt"><span class="nm">${esc(s.name)}</span><span class="sb">${esc(s.sub)}</span></span><span class="eqs"><i></i><i></i><i></i></span></button>`;
}

const STEPS = () => [t('读取你的喜欢'), t('了解你的口味'), t('挑第一批电台')];
function prepHTML() {
  const me = S.me;
  if (!me) return '';
  if (me.google?.error === 'revoked') return `<div class="prep"><b>${t('YouTube Music 的连接失效了')}</b><p>${t('喜欢暂时同步不过去。重新连接一下就好。')}</p><a class="tb" href="/auth/google/start">${t('重新连接')}</a></div>`;
  if (me.status === 'importing' || me.status === 'building') {
    const j = S.jobs?.setup, step = Math.max(1, j?.step || (me.status === 'building' ? 2 : 1));
    return `<div class="prep"><b>${t('正在准备你的电台 · {n}/3', { n: step })}</b><p>${esc(STEPS()[step - 1])}${t('。')}${step === 1 ? t('要几分钟，可以先听着，好了会告诉你。') : t('大约一刻钟，可以先听着，好了会告诉你。')}</p></div>`;
  }
  if (me.status === 'thin') return `<div class="prep"><b>${t('还不够认识你')}</b><p>${t('你在 YouTube 只点过 {n} 首歌的喜欢，至少要 20 首才分得出你的几种口味。先听「先听着」，喜欢的点 ♥，会同步回你的 YouTube Music。', { n: me.last_sync?.songs ?? 0 })}</p><button class="tb" data-k="setup">${t('攒够了，重新读取')}</button></div>`;
  if (me.status === 'error') return `<div class="prep"><b>${t('准备电台时出了问题')}</b><p>${esc((S.jobs?.setup?.error || '').slice(0, 80))}</p><button class="tb" data-k="setup">${t('再试一次')}</button></div>`;
  return '';
}

function renderStations() {
  const asks = ST.filter((s) => s.group === 'ask'), lanes = ST.filter((s) => s.group === 'lane'), warm = ST.filter((s) => s.group === 'warm');
  const busy = S.jobs?.refresh?.running;
  const label = busy ? t('正在挑新的一批…') : S.edition ? t('电台 · {when} 更新', { when: when(S.edition.created) }) : '';
  renderMe();
  if (!ready() || !lanes.length) {
    $('#stations').innerHTML = `${prepHTML()}${warm.length ? `<div class="st-h"><span>${t('先听着')}</span></div>` : ''}${warm.map(stHTML).join('')}${lanes.map(stHTML).join('')}`;
    return;
  }
  $('#stations').innerHTML = `${prepHTML()}
    ${asks.length ? `<div class="st-h"><span>${t('你点的')}</span></div>${asks.map(stHTML).join('')}` : ''}
    <div class="st-h"><span>${label}</span><button class="${busy ? 'busy' : ''}" data-k="refresh" title="${t('现在重新挑一批')}" ${busy ? 'disabled' : ''}>${I.refresh}</button></div>
    ${lanes.map(stHTML).join('')}
    ${warm.length ? `<div class="st-h"><span>${t('先听着')}</span></div>${warm.map(stHTML).join('')}` : ''}`;
}

function queueOf(st) {
  const id = `${S.edition?.id}|${st.key}`;
  let q = queues.get(id);
  if (!q) {
    q = { key: st.key, tracks: st.tracks.filter((p) => fb.get(p.vid) !== 'dislike'), reserve: [...(st.reserve || [])], i: 0, played: new Set() };
    queues.set(id, q);
  }
  q.st = st;
  return q;
}

function selectStation(key, play = true) {
  const st = ST.find((s) => s.key === key);
  if (!st || st.pending || !st.tracks.length) return;
  const same = Q?.key === key;
  Q = queueOf(st);
  store.set(acct('last'), key);
  if (view !== 'listen') { location.hash = ''; return loadTrack(play); }
  renderStations();
  renderQueue();
  if (!same || play) loadTrack(play);
}

// The first station of a visit fits the hour: something quiet late at night, something with a pulse by day.
function defaultStation() {
  const h = new Date().getHours();
  const want = h >= 22 || h < 5 ? 1.5 : h >= 19 ? 2.5 : h < 11 ? 2 : 3.5;
  const mid = (k) => { const e = S.lanes?.find((l) => l.key === k)?.energy; return e ? (e[0] + e[1]) / 2 : 3; };
  const lanes = ST.filter((x) => x.group === 'lane' && x.key !== 'focus' && x.tracks.length);
  return lanes.sort((a, b) => Math.abs(mid(a.key) - want) - Math.abs(mid(b.key) - want))[0] || ST.find((x) => x.group === 'warm');
}

/* ---------- playback ---------- */
const cur = () => Q?.tracks[Q.i];

function trackChanged() {
  const p = cur();
  if (!p) return;
  store.set(acct('pos'), { ed: S.edition?.id, key: Q.key, vid: p.vid });
  paintNow();
  ambient(p);
  Lyr.load(p);
  MS.meta(p);
  if (view === 'ear') { paintHub(); paintDisc(); }
}

function loadTrack(play) {
  const p = cur();
  if (!p) return;
  Player.load(p, play);
  trackChanged();
}

function logPlay(p, ev, pos = 0) {
  if (p) api('/api/play', { vid: p.vid, lane: Q?.key, ev, pos: Math.round(pos) }).catch(() => {});
}

async function next() {
  if (!Q) return;
  const p = cur();
  if (p) {
    Q.played.add(p.vid);
    const [t, d] = Player.time();
    // Leaving within the first half is the strongest "not now" signal a listener gives without saying anything.
    if (Player.playing && t < Math.min(30, d / 2)) { logPlay(p, 'skip', t); adapt('neg', p); }
  }
  if (Q.i >= Q.tracks.length - 1) await extend(true);
  if (Q.i < Q.tracks.length - 1) { Q.i++; loadTrack(true); }
}
function prev() {
  if (!Q) return;
  if (Player.time()[0] > 4 || Q.i === 0) return Player.seekTo(0);
  Q.i--;
  loadTrack(true);
}

async function extend(silent) {
  if (!Q) return;
  if (Q.reserve.length) {
    Q.tracks.push(...Q.reserve.splice(0, 4).filter((p) => fb.get(p.vid) !== 'dislike'));
    renderQueue();
    return;
  }
  const seed = cur() || Q.tracks[Q.tracks.length - 1];
  if (!seed) return;
  try {
    const r = await api(`/api/more?vid=${seed.vid}&exclude=${Q.tracks.map((p) => p.vid).join(',')}`);
    Q.tracks.push(...r.tracks.slice(0, 8));
    renderQueue();
    if (!r.tracks.length && !silent) toast(t('这条线暂时没有更多了'));
  } catch { if (!silent) toast(t('没取到更多的歌，稍后再试')); }
}

async function continueFrom(btn) {
  const p = cur();
  if (!p) return;
  btn && (btn.disabled = true);
  try {
    const r = await api(`/api/more?vid=${p.vid}&exclude=${Q.tracks.map((x) => x.vid).join(',')}`);
    const add = r.tracks.slice(0, 8);
    Q.tracks.splice(Q.i + 1, 0, ...add);
    renderQueue();
    toast(add.length ? t('接下来沿着〈{s}〉放 {n} 首', { s: p.title, n: add.length }) : t('这首的电台里没有新的了'));
  } catch { toast(t('没取到，稍后再试')); }
  btn && (btn.disabled = false);
}

/* ---------- listening session: the queue leans towards what you keep and away from what you skip ---------- */
const vecs = new Map();
function vec(p) {
  if (!p?.v) return null;
  let x = vecs.get(p.v);
  if (!x) {
    const b = atob(p.v);
    x = new Float32Array(b.length);
    let n = 0;
    for (let i = 0; i < b.length; i++) { const c = (b.charCodeAt(i) << 24) >> 24; x[i] = c; n += c * c; }
    n = Math.sqrt(n) || 1;
    for (let i = 0; i < x.length; i++) x[i] /= n;
    vecs.set(p.v, x);
  }
  return x;
}
const dot = (a, b) => { let s = 0; for (let i = 0; i < a.length; i++) s += a[i] * b[i]; return s; };
// Measured on the library: two random songs sit around 0.40, the top 10% of pairs above 0.66, and a song's
// nearest neighbour around 0.91. Only the top of that range counts as "sounds like".
const NEAR = 0.72;
const near = (x, refs) => (x && refs.length ? Math.max(...refs.map((r) => dot(x, r))) : 0);

function sessionOf(q) { return (q.sess ||= { pos: [], neg: [], steer: 0, fresh: false }); }

function adapt(event, p) {
  if (!Q) return;
  const s = sessionOf(Q), x = vec(p);
  if (event && x) (event === 'neg' ? s.neg : s.pos).push(x);
  const upcoming = Q.tracks.slice(Q.i + 1);
  if (!upcoming.length && !Q.reserve.length) return;
  const score = (c, k, inReserve) => {
    const v = vec(c);
    let sc = inReserve ? -0.45 - 0.02 * k : -0.04 * k;
    sc += 3 * Math.max(0, near(v, s.pos) - NEAR) - 4 * Math.max(0, near(v, s.neg) - NEAR);
    if (s.steer && typeof c.en === 'number') sc += 0.55 * s.steer * clamp(c.en, -2.5, 2.5);
    if (s.fresh) sc += c.familiar ? -0.5 : 0.35;
    return sc;
  };
  const pool = [...upcoming.map((c, k) => [c, score(c, k, false)]), ...Q.reserve.map((c, k) => [c, score(c, k, true)])];
  pool.sort((a, b) => b[1] - a[1]);
  const n = Math.max(upcoming.length, Math.min(6, pool.length));
  const keep = pool.slice(0, n).map((x) => x[0]);
  const before = upcoming.map((c) => c.vid).join();
  Q.tracks = [...Q.tracks.slice(0, Q.i + 1), ...keep];
  Q.reserve = pool.slice(n).map((x) => x[0]);
  if (keep.map((c) => c.vid).join() === before) return;
  renderQueue();
  Lyr.prefetch();
  if (event && p) s.note = event === 'neg' ? t('少放和〈{s}〉相近的', { s: p.title }) : t('多放和〈{s}〉相近的', { s: p.title });
  paintSteer();
}

function steer(k) {
  if (!Q) return;
  const s = sessionOf(Q);
  if (k === 'fresh') s.fresh = !s.fresh;
  else s.steer = s.steer === (k === 'up' ? 1 : -1) ? 0 : (k === 'up' ? 1 : -1);
  const before = Q.tracks.slice(Q.i + 1).map((c) => c.vid);
  adapt();
  // say what the switch did to the songs ahead, or that they already fit
  const after = Q.tracks.slice(Q.i + 1).map((c) => c.vid);
  const moved = after.filter((v, j) => before[j] !== v).length;
  const what = { calm: t('更安静'), up: t('更带劲'), fresh: t('多些新歌手') }[k];
  const on = k === 'fresh' ? s.fresh : s.steer === (k === 'up' ? 1 : -1);
  s.note = !on ? t('取消了「{what}」', { what }) : moved ? t('{what}：接下来换了 {n} 首', { what, n: moved }) : t('{what}：接下来的歌已经是这样了', { what });
  paintSteer();
}

function paintSteer() {
  const s = Q ? sessionOf(Q) : {};
  $$('[data-k="calm"]').forEach((b) => b.classList.toggle('on', s.steer === -1));
  $$('[data-k="up"]').forEach((b) => b.classList.toggle('on', s.steer === 1));
  $$('[data-k="fresh"]').forEach((b) => b.classList.toggle('on', !!s.fresh));
  const w = $('#qWhen'), n = $('#sNote');
  if (w && Q) w.textContent = Q.st.when || '';
  if (n) n.textContent = s.note || '';
}

/* ---------- player: two YouTube decks so one song can run into the next ---------- */
const XF = 3;   // seconds the outgoing and incoming songs overlap at a natural ending

const Player = {
  decks: [], a: 0, want: null, playing: false, logged: null, timer: null, fade: null, clock: { raw: -1, at: 0 },
  get on() { return this.decks[this.a]; },
  get ready() { return this.decks.length === 2 && this.decks.every((d) => d.ready); },
  init() {
    window.onYouTubeIframeAPIReady = () => {
      this.decks = ['ytA', 'ytB'].map((id, k) => {
        const d = { k, ready: false, vid: null, yt: null, duck: 0 };
        d.yt = new YT.Player(id, {
          width: '100%', height: '100%',
          playerVars: { autoplay: 0, controls: 0, disablekb: 1, fs: 0, iv_load_policy: 3, playsinline: 1, rel: 0, origin: location.origin },
          events: {
            onReady: () => {
              d.ready = true;
              if (this.ready && this.want) { const w = this.want; this.want = null; this.load(w.p, w.play); }
            },
            onStateChange: (e) => this.onState(d, e.data),
            onError: () => this.onError(d),
          },
        });
        return d;
      });
    };
    const s = document.createElement('script');
    s.src = 'https://www.youtube.com/iframe_api';
    document.head.append(s);
  },
  paintDecks() { $$('.yt-crop').forEach((el, k) => el.classList.toggle('on', k === this.a)); },
  start(d, vid, vol, play = true) {
    clearInterval(d.duck);
    d.vid = vid;
    d.yt.setVolume(vol);
    d.yt.unMute();
    play ? d.yt.loadVideoById(vid) : d.yt.cueVideoById(vid);
  },
  silence(d, ms) {
    const t0 = performance.now();
    clearInterval(d.duck);
    d.duck = setInterval(() => {
      const x = clamp((performance.now() - t0) / ms);
      d.yt.setVolume(Math.round(100 * (1 - x)));
      if (x >= 1) { clearInterval(d.duck); d.yt.pauseVideo(); }
    }, 30);
  },
  load(p, play) {
    $('#ytHost').classList.remove('live');
    if (!this.ready) { this.want = { p, play }; return; }
    this.endFade();
    const from = this.on;
    if (play && this.playing && from.vid !== p.vid) {
      // Start the new song on the other deck and let the old one fall away, so a skip never leaves silence.
      this.a = 1 - this.a;
      this.start(this.on, p.vid, 100);
      this.silence(from, 260);
    } else {
      this.start(from, p.vid, 100, play);
    }
    this.paintDecks();
  },
  crossfade() {
    const nx = Q?.tracks[Q.i + 1];
    if (!nx) return;
    const from = this.on, p = cur();
    Q.played.add(p.vid);
    logPlay(p, 'done', this.time()[0]);
    this.a = 1 - this.a;
    this.fade = { from, to: this.on, t0: 0, h: 0 };
    this.start(this.on, nx.vid, 0);
    this.paintDecks();
    Q.i++;
    $('#ytHost').classList.remove('live');
    trackChanged();
    adapt('pos', p);   // only after the incoming song is fixed, or the queue could move under it
  },
  runFade() {
    const f = this.fade;
    f.t0 = performance.now();
    f.h = setInterval(() => {
      const x = clamp((performance.now() - f.t0) / (XF * 1000));
      f.to.yt.setVolume(Math.round(100 * Math.sin((x * Math.PI) / 2)));
      f.from.yt.setVolume(Math.round(100 * Math.cos((x * Math.PI) / 2)));
      if (x >= 1) this.endFade();
    }, 40);
  },
  endFade() {
    const f = this.fade;
    if (!f) return;
    clearInterval(f.h);
    this.fade = null;
    f.to.yt.setVolume(100);
    f.from.yt.pauseVideo();
  },
  onError(d) {
    if (d !== this.on) return;
    this.endFade();
    toast(t('〈{s}〉不允许在网页里播放，已跳过', { s: cur()?.title || '' }));
    setTimeout(next, 400);
  },
  onState(d, s) {
    if (d !== this.on) return;  // the outgoing deck playing out its last bars
    if (this.fade && s === 1 && !this.fade.t0) this.runFade();
    this.playing = s === 1 || s === 3;
    document.body.classList.toggle('playing', this.playing);
    Pip.w?.document.body.classList.toggle('playing', this.playing);
    MS.state(this.playing);
    // YouTube draws its title bar and play bezel over the first seconds of playback; keep the cover up until they fade.
    clearTimeout(this.liveT);
    if (s === 1) { const vid = d.vid; this.liveT = setTimeout(() => { if (this.playing && this.on.vid === vid) $('#ytHost').classList.add('live'); }, 3500); }
    else $('#ytHost').classList.remove('live');
    clearInterval(this.timer);
    if (this.playing) this.timer = setInterval(tick, 250);
    tick();
    Lyr.run();
    const p = cur();
    if (s === 1 && p && this.logged !== p.vid) { this.logged = p.vid; logPlay(p, 'start'); Lyr.prefetch(); }
    if (s === 0) { logPlay(p, 'done', this.time()[1]); next(); }
  },
  toggle() {
    if (!cur()) return;
    MS.arm();
    if (!this.ready) { this.want = { p: cur(), play: true }; return; }
    this.endFade();
    this.playing ? this.on.yt.pauseVideo() : this.on.yt.playVideo();
  },
  play() { if (!this.playing) this.toggle(); },
  pause() { if (this.ready && this.playing) { this.endFade(); this.on.yt.pauseVideo(); } },
  seekTo(sec) { if (!this.ready) return; this.endFade(); this.on.yt.seekTo(Math.max(0, sec), true); this.clock.raw = -1; },
  seek(frac) { const d = this.time()[1]; if (d) this.seekTo(d * frac); },
  time() {
    const d = this.on;
    if (!this.ready || !d) return [0, cur()?.dur || 0];
    return [d.yt.getCurrentTime?.() || 0, d.yt.getDuration?.() || cur()?.dur || 0];
  },
  // YouTube reports the position in coarse steps; extrapolate between them so lyrics can move with the voice.
  now() {
    const [t] = this.time();
    const c = this.clock, n = performance.now();
    if (t !== c.raw) { c.raw = t; c.at = n; }
    return this.playing ? Math.min(c.raw + (n - c.at) / 1000, c.raw + 1) : c.raw;
  },
};

function tick() {
  const [t, d] = Player.time();
  const f = d ? Math.min(1, t / d) : 0;
  $$('.bar').forEach((b) => b.style.setProperty('--p', f));
  Pip.w && $$('.bar', Pip.w.document).forEach((b) => b.style.setProperty('--p', f));
  const c = $('#tCur'), e = $('#tDur');
  if (c) c.textContent = fmt(t);
  if (e) e.textContent = fmt(d);
  if (Player.playing && !Player.fade && d > 60 && d - t <= XF + 0.4 && Q?.tracks[Q.i + 1]) Player.crossfade();
  else if (Player.playing && d - t < 20 && Q && Q.i >= Q.tracks.length - 1 && !extend.busy) {
    extend.busy = true;
    extend(true).finally(() => { extend.busy = false; });
  }
  MS.position(t, d);
}

/* ---------- system media controls (keyboard media keys, Control Centre, Now Playing) ---------- */
// Chrome routes media keys to the top-most frame that is playing something. The music plays inside YouTube's
// iframe, so a silent loop in this page keeps the controls (and our song info) pointed at 知音.
const MS = {
  el: null,
  ok: 'mediaSession' in navigator,
  init() {
    if (!this.ok) return;
    const h = { play: () => Player.play(), pause: () => Player.pause(), previoustrack: prev, nexttrack: next,
      seekto: (e) => Player.seekTo(e.seekTime) };
    for (const [k, f] of Object.entries(h)) { try { navigator.mediaSession.setActionHandler(k, f); } catch { /* unsupported action */ } }
  },
  arm() {
    if (!this.ok || this.el) return;
    const rate = 8000, n = rate, buf = new ArrayBuffer(44 + n * 2), v = new DataView(buf);
    const w = (o, s) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
    w(0, 'RIFF'); v.setUint32(4, 36 + n * 2, true); w(8, 'WAVEfmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true);
    v.setUint16(22, 1, true); v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true);
    v.setUint16(34, 16, true); w(36, 'data'); v.setUint32(40, n * 2, true);
    this.el = new Audio(URL.createObjectURL(new Blob([buf], { type: 'audio/wav' })));
    this.el.loop = true;
    if (Player.playing) this.el.play().catch(() => {});
  },
  state(playing) {
    if (!this.ok) return;
    navigator.mediaSession.playbackState = playing ? 'playing' : 'paused';
    if (this.el) playing ? this.el.play().catch(() => {}) : this.el.pause();
  },
  meta(p) {
    if (!this.ok || !p) return;
    navigator.mediaSession.metadata = new MediaMetadata({
      title: p.title, artist: names(p.artists), album: p.album?.name || Q?.st?.name || t('知音'),
      artwork: [{ src: new URL(px(cover(p, 544).replace('maxresdefault', 'hqdefault')), location.href).href, sizes: '544x544' }],
    });
  },
  position(t, d) {
    if (!this.ok || !d || !navigator.mediaSession.setPositionState) return;
    try { navigator.mediaSession.setPositionState({ duration: d, position: Math.min(t, d), playbackRate: 1 }); } catch { /* bad values while loading */ }
  },
};

/* ---------- lyrics ---------- */
const Lyr = {
  cache: new Map(), vid: null, data: null, idx: -2, hold: 0, raf: 0, lastF: [],
  tr: store.get('tr') ?? true, ro: store.get('ro') ?? false,
  get delay() { return (store.get(acct('off')) || {})[this.vid] || 0; },
  set delay(v) { const o = store.get(acct('off')) || {}; o[this.vid] = Math.round(v * 100) / 100; if (!o[this.vid]) delete o[this.vid]; store.set(acct('off'), o); },
  fetch(p) {
    if (this.cache.has(p.vid)) return this.cache.get(p.vid);
    const q = new URLSearchParams({ vid: p.vid, t: p.title, a: (p.artists || []).map((a) => a.name).join('|'), al: p.album?.name || '', d: p.dur || 0 });
    const pr = api(`/api/lyrics?${q}`).catch(() => ({ found: false }));
    this.cache.set(p.vid, pr);
    return pr;
  },
  prefetch() { Q?.tracks.slice(Q.i + 1, Q.i + 3).forEach((p) => this.fetch(p)); },
  async load(p) {
    if (this.vid !== p.vid) { this.vid = p.vid; this.data = null; this.idx = -2; this.render(); }
    const d = await this.fetch(p);
    if (cur()?.vid !== p.vid) return;
    if (d.translating) {
      // A Japanese/Korean/English song with no translation anywhere is being translated in the background.
      clearTimeout(this.again);
      this.again = setTimeout(() => { if (cur()?.vid === p.vid) { this.cache.delete(p.vid); this.load(p); } }, 12000);
    }
    this.data = d.found ? this.prep(d) : null;
    this.idx = -2;
    this.render();
    layoutStage();
    paintCredits();
    this.run();
  },
  prep(d) {
    const lines = [];
    if (d.lines[0]?.t > 6) lines.push({ t: 0, x: '', gap: true });
    for (const l of d.lines) lines.push({ ...l, gap: !l.x });
    lines.forEach((l, i) => { l.end = lines[i + 1]?.t ?? (l.e || l.t + 6); });
    return { ...d, lines };
  },
  html() {
    const d = this.data;
    if (!d) return '';
    const by = [d.source && t('歌词来自{src}', { src: /^[A-Za-z]/.test(d.source) && LANG !== 'en' ? ` ${d.source}` : d.source }), d.tr_by === 'AI' && d.translated && t('翻译由 AI 生成')].filter(Boolean).join(' · ');
    return `<div class="ly-scroll"><div class="ly-in ${this.tr ? 'tr-on' : ''} ${this.ro ? 'ro-on' : ''}">${d.lines.map((l, i) => {
      if (l.gap) return `<p class="ll gap" data-i="${i}"><span class="dots"><i></i><i></i><i></i></span></p>`;
      const main = l.w ? l.w.map((w) => `<span class="wd">${esc(w[2])}</span>`).join('') : esc(l.x);
      return `<p class="ll ${l.w ? 'w' : ''}" data-i="${i}"><span class="lx">${main}</span>${l.tr ? `<span class="lt">${esc(l.tr)}</span>` : ''}${l.ro ? `<span class="lr">${esc(l.ro)}</span>` : ''}</p>`;
    }).join('')}</div></div>
    <div class="ly-foot"><span>${esc(by)}</span>
      ${d.lines.some((l) => l.tr) ? `<button class="lk ${this.tr ? 'on' : ''}" data-k="lytr" title="${t('翻译（T）')}">${t('译')}</button>` : ''}
      ${d.lines.some((l) => l.ro) ? `<button class="lk ${this.ro ? 'on' : ''}" data-k="lyro" title="${t('罗马音（R）')}">${t('音')}</button>` : ''}</div>`;
  },
  render() {
    for (const el of this.hosts()) {
      el.innerHTML = this.html();
      const sc = $('.ly-scroll', el);
      if (!sc) continue;
      const stop = () => { this.hold = performance.now() + 3500; };
      sc.addEventListener('wheel', stop, { passive: true });
      sc.addEventListener('touchmove', stop, { passive: true });
    }
    this.lastF = [];
    this.paintPip(true);
  },
  hosts() { return $$('.lyr'); },
  visible() { return !!this.data && (Pip.w || $$('.stage.lyr-on').length > 0); },
  run() {
    cancelAnimationFrame(this.raf);
    if (!this.visible()) return;
    const step = () => { this.sync(); if (Player.playing && this.visible()) this.raf = requestAnimationFrame(step); };
    step();
  },
  at(t) {
    const L = this.data.lines;
    let lo = 0, hi = L.length - 1, k = -1;
    while (lo <= hi) { const m = (lo + hi) >> 1; if (L[m].t <= t) { k = m; lo = m + 1; } else hi = m - 1; }
    return k;
  },
  sync(force) {
    if (!this.data) return;
    const t = Player.now() - this.delay + 0.1;
    const k = this.at(t), L = this.data.lines;
    if (k !== this.idx || force) {
      for (const host of this.hosts()) {
        $$('.ll.on', host).forEach((el) => el.classList.remove('on'));
        const el = $(`.ll[data-i="${k}"]`, host);
        el?.classList.add('on');
        this.follow(host, el);
      }
      this.idx = k;
      this.lastF = [];
      this.paintPip();
    }
    const l = L[k];
    if (!l) return;
    if (l.w) {
      for (const host of this.hosts()) {
        const spans = $$(`.ll[data-i="${k}"] .wd`, host);
        l.w.forEach((w, j) => {
          const f = clamp((t - w[0]) / Math.max(0.05, w[1]));
          const key = `${host.id}${j}`;
          if (this.lastF[key] !== f && spans[j]) { spans[j].style.setProperty('--f', f.toFixed(3)); this.lastF[key] = f; }
        });
      }
    } else if (l.gap) {
      const f = clamp((t - l.t) / Math.max(0.5, l.end - l.t - 0.6));
      for (const host of this.hosts()) $(`.ll[data-i="${k}"]`, host)?.style.setProperty('--f', f.toFixed(3));
    }
  },
  follow(host, el) {
    const sc = $('.ly-scroll', host);
    if (!sc || !el || performance.now() < this.hold) return;
    const top = el.offsetTop - sc.clientHeight * 0.36 + el.offsetHeight / 2;
    sc.scrollTo({ top, behavior: document.hidden ? 'auto' : 'smooth' });
  },
  paintPip(reset) {
    if (!Pip.w) return;
    const d = Pip.w.document, l = this.data?.lines[this.idx];
    const a = $('#pLine', d), b = $('#pTr', d);
    if (!a) return;
    if (reset || !l || l.gap) { a.textContent = this.data ? (l?.gap ? '♪' : '') : ''; b.textContent = ''; return; }
    a.textContent = l.x;
    b.textContent = this.tr ? l.tr || '' : '';
  },
  nudge(dt) {
    if (!this.data) return;
    this.delay += dt;
    const v = this.delay;
    toast(v === 0 ? t('歌词时间已复原') : t(v > 0 ? '歌词延后 {s} 秒' : '歌词提前 {s} 秒', { s: Math.abs(v).toFixed(2).replace(/0$/, '') }));
    this.sync(true);
  },
};

function paintCredits() {
  const el = $('#nCred');
  if (!el) return;
  const c = (Lyr.data?.credits || []).filter(([r]) => r === '作曲' || r === '作词' || r === '编曲').slice(0, 3);
  el.textContent = c.map(([r, n]) => `${t(r)} ${n}`).join(' · ');
}

/* ---------- stage layout: lyrics beside the cover when there is room ---------- */
const LYR_SIDE = 560;   // stage content width from which lyrics sit beside the cover; matches the container query in CSS
function stageWidth(st) {
  const cs = getComputedStyle(st);
  return st.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
}
function layoutStage() {
  const st = $('.stage');
  if (!st) return;
  const wide = stageWidth(st) >= LYR_SIDE || prefs.imm;
  const has = !!Lyr.data;
  const on = has && (prefs.imm || (wide ? prefs.lyr : prefs.lyrNarrow));
  st.classList.toggle('lyr-on', on);
  // a phone scrolls the page under the station strip and the tab bar: size the cover so play is on the first screen
  const fr = $('.frame', st), meta = $('.meta', st);
  if (PHONE.matches && fr && meta) {
    const room = innerHeight - $('#tabs').offsetHeight - (fr.getBoundingClientRect().top + scrollY) - meta.offsetHeight - 32;
    st.style.setProperty('--fit', `${Math.max(120, Math.round(room))}px`);
  } else st.style.removeProperty('--fit');
  $$('[data-k="lyrics"]').forEach((b) => { b.classList.toggle('on', on); b.toggleAttribute('aria-disabled', !has); b.title = has ? t('歌词（G）') : t('这首没有找到歌词'); });
  placeHost();
  if (on) { Lyr.sync(true); Lyr.run(); }
}
function toggleLyrics() {
  const st = $('.stage');
  if (!st || !Lyr.data) { if (st) toast(t('这首没有找到歌词')); return; }
  const wide = stageWidth(st) >= LYR_SIDE || prefs.imm;
  if (prefs.imm) return;
  if (wide) { prefs.lyr = !st.classList.contains('lyr-on'); store.set('lyr', prefs.lyr); } else prefs.lyrNarrow = !st.classList.contains('lyr-on');
  layoutStage();
}
const stageRO = new ResizeObserver(() => layoutStage());
const PHONE = matchMedia('(max-width: 899px)');

/* ---------- immersive: just the song, the cover and the words ---------- */
function immersive(on = !prefs.imm) {
  if (view !== 'listen' || !cur()) return;
  prefs.imm = on;
  document.body.classList.toggle('imm', on);
  $$('[data-k="imm"]').forEach((b) => { b.innerHTML = on ? I.shrink : I.full; b.title = on ? t('退出沉浸（F / Esc）') : t('沉浸（F）'); });
  paintBackdrop();
  requestAnimationFrame(() => { layoutStage(); placeHost(); });
}
let idleT = 0;
addEventListener('mousemove', () => {
  if (!prefs.imm) return;
  document.body.classList.remove('idle');
  clearTimeout(idleT);
  idleT = setTimeout(() => document.body.classList.add('idle'), 2600);
});

// The cover lights the room. Two layers crossfade so a new song washes in instead of cutting.
function paintBackdrop() {
  const p = cur(), el = $('#backdrop');
  if (!p || !el) return;
  const u = px(cover(p, 120).replace('maxresdefault', 'mqdefault'));
  if (el.dataset.u === u) return;
  el.dataset.u = u;
  if (el.children.length < 2) el.innerHTML = '<i></i><i></i>';
  const [a, b] = el.children, nx = a.classList.contains('on') ? b : a, old = nx === a ? b : a;
  const img = new Image();
  img.onload = () => {
    if (el.dataset.u !== u) return;
    nx.style.backgroundImage = `url("${u}")`;
    nx.classList.add('on');
    old.classList.remove('on');
  };
  img.src = u;
}

/* ---------- picture-in-picture mini player (stays on top of other apps) ---------- */
const Pip = {
  w: null,
  async toggle() {
    if (this.w) { this.w.close(); return; }
    if (!window.documentPictureInPicture) { toast(t('这个浏览器不支持小窗，用 Chrome 116 以上')); return; }
    if (!cur()) return;
    const w = await documentPictureInPicture.requestWindow({ width: 400, height: 176, preferInitialWindowPlacement: true });
    this.w = w;
    const d = w.document;
    for (const l of $$('link[rel=stylesheet]')) d.head.append(l.cloneNode());
    d.body.className = `pip ${Player.playing ? 'playing' : ''}`;
    d.body.style.setProperty('--amb', document.body.style.getPropertyValue('--amb'));
    d.body.innerHTML = `<div class="pp">
      <img id="pImg" alt="">
      <div class="pm"><div class="tt" id="pTitle"></div><div class="ar" id="pArtist"></div></div>
      <div class="pc">
        <button class="ib" data-k="prev" title="${t('上一首')}">${I.prev}</button>
        <button class="ib play" data-k="toggle" title="${t('播放 / 暂停')}">${I.play}${I.pause}</button>
        <button class="ib" data-k="next" title="${t('下一首')}">${I.next}</button>
        <button class="ib like" data-k="like" title="${t('喜欢')}">${I.heart}</button>
      </div>
      <div class="pl"><div id="pLine"></div><div id="pTr"></div></div>
      <div class="bar"><i></i></div>
    </div>`;
    d.addEventListener('click', (e) => { const b = e.target.closest('[data-k]'); if (b) act(b.dataset.k, b); });
    d.addEventListener('keydown', onKey);
    w.addEventListener('pagehide', () => { this.w = null; $$('[data-k="pip"]').forEach((b) => b.classList.remove('on')); });
    $$('[data-k="pip"]').forEach((b) => b.classList.add('on'));
    paintNow();
    Lyr.paintPip(true);
    Lyr.sync(true);
    Lyr.run();
  },
};

/* ---------- ambient colour from the cover ---------- */
const ambCache = new Map();
function colorOf(src) {
  return new Promise((res, rej) => {
    const img = new Image();
    img.onload = () => {
      const c = document.createElement('canvas');
      c.width = c.height = 32;
      const x = c.getContext('2d', { willReadFrequently: true });
      x.drawImage(img, 0, 0, 32, 32);
      const d = x.getImageData(0, 0, 32, 32).data;
      let r = 0, g = 0, b = 0, w = 0;
      for (let i = 0; i < d.length; i += 4) {
        const mx = Math.max(d[i], d[i + 1], d[i + 2]), mn = Math.min(d[i], d[i + 1], d[i + 2]);
        const l = (mx + mn) / 510, s = mx === mn ? 0 : (mx - mn) / (255 - Math.abs(mx + mn - 255));
        const wt = 0.03 + s * s * Math.max(0, 1 - Math.abs(l - 0.5) * 1.7);
        r += d[i] * wt; g += d[i + 1] * wt; b += d[i + 2] * wt; w += wt;
      }
      res(toHsl(r / w, g / w, b / w));
    };
    img.onerror = rej;
    img.src = src;
  });
}
function toHsl(r, g, b) {
  r /= 255; g /= 255; b /= 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2;
  let h = 0, s = 0;
  if (mx !== mn) {
    const d = mx - mn;
    s = l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn);
    h = mx === r ? (g - b) / d + (g < b ? 6 : 0) : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
    h *= 60;
  }
  return `hsl(${Math.round(h)} ${Math.round(Math.min(s, 0.5) * 100)}% ${Math.round(Math.min(0.56, Math.max(0.38, l)) * 100)}%)`;
}
async function ambient(p) {
  const u = cover(p, 120).replace('maxresdefault', 'mqdefault');
  let c = ambCache.get(u);
  if (!c) {
    try { c = await colorOf(px(u)); } catch { c = '#34343a'; }
    ambCache.set(u, c);
  }
  if (cur() !== p) return;
  document.body.style.setProperty('--amb', c);
  Pip.w?.document.body.style.setProperty('--amb', c);
}

/* ---------- now playing ---------- */
function paintNow() {
  const p = cur();
  if (!p) return;
  const big = cover(p, 1200);
  const img = $('#ytCover');
  if (img.dataset.src !== big) {
    img.dataset.src = big;
    img.className = `yt-cover ${lb(big)}`;
    const fallback = () => { if (big.includes('maxresdefault')) { img.onerror = null; img.src = px(big.replace('maxresdefault', 'hqdefault')); img.className = 'yt-cover lb'; } };
    // maxresdefault is missing for videos without an HD thumbnail
    img.onerror = fallback;
    img.onload = () => { if (img.naturalWidth <= 120) fallback(); };
    img.src = px(big);
  }
  const set = (id, v, doc = document) => { const el = $(id, doc); if (el) el.textContent = v; };
  set('#nTitle', p.title);
  set('#nArtist', names(p.artists));
  set('#nAlbum', [p.album?.name && p.album.name !== p.title ? p.album.name : '', p.year].filter(Boolean).join(' · '));
  set('#nWhy', reasonOf(p));
  set('#dTitle', p.title);
  set('#dArtist', names(p.artists));
  set('#mTitle', p.title);
  set('#mArtist', names(p.artists));
  paintCredits();
  const mi = $('#mImg');
  if (mi) mi.src = px(cover(p, 120));
  if (Pip.w) {
    const d = Pip.w.document;
    set('#pTitle', p.title, d);
    set('#pArtist', names(p.artists), d);
    const pi = $('#pImg', d);
    if (pi) pi.src = px(cover(p, 226));
  }
  const open = $('#nOpen');
  if (open) open.href = `https://music.youtube.com/watch?v=${p.vid}`;
  paintLikes();
  $$('.tr').forEach((r) => {
    const i = +r.dataset.i;
    r.classList.toggle('cur', i === Q.i);
    r.classList.toggle('done', i !== Q.i && Q.played.has(Q.tracks[i]?.vid));
  });
  keepCurrentRowVisible();
  document.title = `${p.title} · ${names(p.artists)}`;
  paintBackdrop();
  tick();
  placeHost();
}

// Scroll only the programme's own row; on phones the list is part of the page and must not drag the page along.
function keepCurrentRowVisible() {
  const list = $('#qList'), row = $('.tr.cur');
  if (!list || !row || list.scrollWidth <= list.clientWidth + 2) return;
  const a = list.getBoundingClientRect(), b = row.getBoundingClientRect();
  if (b.left < a.left + 24 || b.right > a.right - 48) list.scrollBy({ left: b.left - a.left - 36, behavior: document.hidden ? 'auto' : 'smooth' });
}

// One player, two homes: the stage while listening, the card in the rail (or above the tabs) everywhere else.
// When it changes home it flies there, so the song you hear never looks like it vanished and came back.
let hostAt = null;
function placeHost() {
  const host = $('#ytHost');
  const docked = view !== 'listen';
  const target = docked ? $('#pcFrame') : $('#frame');
  if (!target || !cur() || !target.offsetParent) { host.hidden = true; hostAt = null; return; }
  const was = host.hidden ? null : host.getBoundingClientRect();
  host.hidden = false;
  const r = target.getBoundingClientRect();
  // YouTube's embed won't play below 200×200, so a smaller home (the phone's player card) gets it scaled down
  const k = Math.min(1, r.width / 200), end = k < 1 ? `scale(${k})` : 'none';
  host.classList.toggle('docked', docked);
  Object.assign(host.style, {
    top: `${docked ? r.top : r.top + scrollY}px`, left: `${docked ? r.left : r.left + scrollX}px`,
    width: `${r.width / k}px`, height: `${r.height / k}px`, transformOrigin: '0 0', transform: k < 1 ? end : '',
  });
  const moved = hostAt && hostAt !== target.id;
  hostAt = target.id;
  if (moved && was && was.width && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
    const s = was.width / (r.width / k);
    host.animate([
      { transformOrigin: '0 0', transform: `translate(${was.left - r.left}px, ${was.top - r.top}px) scale(${s})` },
      { transformOrigin: '0 0', transform: end },
    ], { duration: 420, easing: 'cubic-bezier(.32, .72, 0, 1)' });
  }
}
const ro = new ResizeObserver(() => placeHost());
// the player card rises into place; measure it again once it has landed
addEventListener('animationend', (e) => { if (e.target.id === 'pcard') placeHost(); });
ro.observe(document.body);
addEventListener('resize', () => (PHONE.matches ? layoutStage() : placeHost()));   // a phone's height changes with its address bar

/* ---------- feedback ---------- */
function track(p) { return { vid: p.vid, lane: Q?.key, title: p.title, artist: p.artists?.[0]?.name, artist_id: p.artists?.[0]?.id }; }

async function like(p) {
  const on = fb.get(p.vid) === 'like';
  on ? fb.delete(p.vid) : fb.set(p.vid, 'like');
  paintLikes();
  if (!on) adapt('pos', p);
  try {
    const r = await api('/api/feedback', { ...track(p), action: on ? 'undo' : 'like' });
    if (!on && r.sync === 'queued' && !store.get(acct('syncHint'))) {
      store.set(acct('syncHint'), true);
      toast(t('喜欢会同步到你的 YouTube Music'), [[t('在哪里关'), openSettings]]);
    }
  } catch {
    on ? fb.set(p.vid, 'like') : fb.delete(p.vid);
    paintLikes();
    toast(t('没保存上，稍后再试'));
  }
}
function paintLikes() {
  const p = cur();
  const on = !!p && fb.get(p.vid) === 'like';
  $$('.ib.like[data-k]').forEach((b) => b.classList.toggle('on', on));
  Pip.w && $$('.ib.like', Pip.w.document).forEach((b) => b.classList.toggle('on', on));
  $$('.tr').forEach((r) => $('.ib.like', r)?.classList.toggle('on', fb.get(Q.tracks[+r.dataset.i]?.vid) === 'like'));
}

function nope(p) {
  const idx = Q.tracks.indexOf(p);
  if (idx < 0) return;
  const wasCur = idx === Q.i, wasPlaying = Player.playing;
  fb.set(p.vid, 'dislike');
  Q.tracks.splice(idx, 1);
  if (idx < Q.i) Q.i--;
  renderQueue();
  adapt('neg', p);
  if (wasCur) {
    const go = () => { Q.i = Math.min(Q.i, Q.tracks.length - 1); loadTrack(wasPlaying); };
    Q.i >= Q.tracks.length ? extend(true).then(go) : go();
  }
  api('/api/feedback', { ...track(p), action: 'dislike', scope: 'song' }).catch(() => {});
  toast(t('以后不推〈{s}〉', { s: p.title }), [
    [t('撤销'), () => {
      fb.delete(p.vid);
      api('/api/feedback', { ...track(p), action: 'undo' }).catch(() => {});
      Q.tracks.splice(idx, 0, p);
      if (idx <= Q.i && !wasCur) Q.i++;
      else if (wasCur && idx <= Q.i) Q.i++;
      renderQueue();
    }],
    [t('{a}也不要', { a: spaced(p.artists?.[0]?.name || t('这位歌手')) }), () => blockArtist(p)],
  ]);
}

function blockArtist(p) {
  const a = p.artists?.[0];
  if (!a) return;
  const same = (x) => x.artists?.some((y) => (a.id && y.id === a.id) || y.name === a.name);
  const playingGone = same(cur() || {});
  const before = Q.tracks.length;
  Q.tracks = Q.tracks.filter((x, i) => {
    const drop = same(x);
    if (drop && i < Q.i) Q.i--;
    return !drop;
  });
  for (const q of queues.values()) if (q !== Q) q.tracks = q.tracks.filter((x) => !same(x));
  Q.i = Math.max(0, Math.min(Q.i, Q.tracks.length - 1));
  renderQueue();
  if (playingGone) loadTrack(Player.playing);
  api('/api/feedback', { ...track(p), action: 'dislike', scope: 'artist' }).catch(() => {});
  toast(before - Q.tracks.length > 0 ? t('以后不推 {a}，队列里去掉了 {n} 首', { a: a.name, n: before - Q.tracks.length }) : t('以后不推 {a}', { a: a.name }), [[t('撤销'), () => {
    api('/api/feedback', { ...track(p), action: 'dislike', scope: 'song' }).catch(() => {});
    toast(t('{a} 的其他歌会照常出现', { a: a.name }));
  }]]);
}

/* ---------- listen view ---------- */
function welcomeHTML() {
  const me = S.me, owner = S.owner_name || t('一位朋友');
  if (!me.google.configured) return `<div class="empty"><h2>${me.name ? t('你好，{name}', { name: esc(me.name) }) : t('你好')}</h2><p>${t('{owner}还在设置连接 YouTube Music 的那一步。好了之后，回到这个页面就能开始。', { owner: esc(owner) })}</p></div>`;
  return `<div class="welcome">
    <h1>${me.name ? t('你好，{name}', { name: esc(me.name) }) : t('你好')}</h1>
    <p class="lede">${t('知音从你在 YouTube Music 点过的喜欢出发，每天挑几组你还没听过、但大概会喜欢的歌，每一首都写着为什么挑它。')}</p>
    <a class="btn" href="/auth/google/start">${t('连接 YouTube Music')}</a>
    <dl class="scope">
      <dt>${t('会读取')}</dt><dd>${t('你点过喜欢的歌和视频，只用来给你算推荐')}</dd>
      <dt>${t('会写回')}</dt><dd>${t('你在这里点的喜欢，会成为 YouTube Music 里的喜欢；可以随时关掉')}</dd>
      <dt>${t('不会')}</dt><dd>${t('发布、评论、删除，或碰你的其他 Google 数据')}</dd>
    </dl>
    <p class="fine">${t('Google 会提示「Google 尚未验证此应用」。这是{owner}自己做的小工具，没有拿去申请审核。点「高级」，再点「前往 {host}」就能继续。你的喜欢和反馈存在{owner}的服务器上，随时可以在设置里断开并全部删除。', { owner: esc(owner), host: esc(location.host) })}</p>
  </div>`;
}

function renderListen() {
  if (!Q && S.me?.status === 'new') { $('#view').innerHTML = welcomeHTML(); placeHost(); return; }
  if (!Q && !ready()) {
    $('#view').innerHTML = `<div class="empty"><h2>${S.me.status === 'thin' ? t('先听点什么') : t('马上就能听')}</h2><p>${S.me.status === 'thin' ? t('「先听着」从你最近的喜欢出发。') : t('正在从你最近的喜欢里找第一首歌。')}</p></div>`;
    placeHost();
    return;
  }
  if (!Q) {
    const busy = S.jobs?.refresh?.running;
    $('#view').innerHTML = `<div class="empty"><h2>${busy ? t('第一批电台正在准备') : t('还没有电台')}</h2><p>${busy
      ? t('大约三分钟。好了会自动出现，不用刷新。')
      : S.portrait ? t('点电台旁边的刷新按钮挑第一批。') : t('先在终端运行 <code>uv run zhiyin profile</code> 读一遍你的喜欢。')}</p></div>`;
    placeHost();
    return;
  }
  $('#view').innerHTML = `
  <div class="listen">
    <header class="l-head">
      <div class="ttl"><h2 id="qName"></h2><p id="qWhen"></p></div>
      <div class="views">
        <button class="ib sm" data-k="lyrics" title="${t('歌词（G）')}">${I.lyrics}</button>
        <button class="ib sm" data-k="pip" title="${t('小窗（M）')}">${I.pip}</button>
        <button class="ib sm" data-k="imm" title="${prefs.imm ? t('退出沉浸（F / Esc）') : t('沉浸（F）')}">${prefs.imm ? I.shrink : I.full}</button>
        <button class="ib sm" data-k="stmenu" title="${t('更多')}" aria-haspopup="menu">${I.more}</button>
      </div>
    </header>
    <section class="stage">
      <div class="stage-in">
        <div class="frame" id="frame"></div>
        <div class="meta">
          <h1 class="t-title" id="nTitle"></h1>
          <div class="t-artist" id="nArtist"></div>
          <div class="t-album" id="nAlbum"></div>
          <div class="t-cred" id="nCred"></div>
          <p class="t-why" id="nWhy"></p>
          <div class="prog"><span class="num" id="tCur">0:00</span><div class="bar" id="bar"><i></i></div><span class="num" id="tDur"></span></div>
          <div class="ctl">
            <button class="ib" data-k="prev" title="${t('上一首（P）')}">${I.prev}</button>
            <button class="ib play" data-k="toggle" title="${t('播放 / 暂停（空格）')}">${I.play}${I.pause}</button>
            <button class="ib" data-k="next" title="${t('下一首（N）')}">${I.next}</button>
            <span class="gap"></span>
            <button class="ib like" data-k="like" title="${t('喜欢（L）')}">${I.heart}</button>
            <button class="ib" data-k="nope" title="${t('不要这首（X）')}">${I.x}</button>
            <span class="push"></span>
            <button class="tb" data-k="radio" title="${t('用这首歌的电台接着往下放')}">${I.branch}<span class="lbl">${t('沿着这首继续')}</span></button>
            <a class="ib" id="nOpen" target="_blank" rel="noopener" title="${t('在 YouTube Music 打开')}">${I.ext}</a>
          </div>
        </div>
        <div class="lyr" id="lyrStage"></div>
      </div>
    </section>
    <section class="strip" aria-label="${t('接下来')}">
      <div class="s-head">
        <h3>${t('接下来')}</h3>
        <button class="tb" data-k="calm" title="${t('接下来放安静一点的')}">${t('更安静')}</button><button class="tb" data-k="up" title="${t('接下来放带劲一点的')}">${t('更带劲')}</button><button class="tb" data-k="fresh" title="${t('多放你没收藏过的歌手')}">${t('多些新歌手')}</button>
        <span class="s-note" id="sNote"></span>
      </div>
      <ol class="s-list" id="qList"></ol>
    </section>
  </div>`;
  renderQueue();
  paintNow();
  Lyr.render();
  stageRO.disconnect();
  stageRO.observe($('.stage'));
  stageRO.observe($('.meta'));   // the cover moves when the words under it change height, though the stage keeps its size
  layoutStage();
  if (Pip.w) $$('[data-k="pip"]').forEach((b) => b.classList.add('on'));
  watchFrame();
}

function renderQueue() {
  const list = $('#qList');
  if (!list || !Q) return;
  $('#qName').textContent = Q.st.name;
  paintSteer();
  list.innerHTML = Q.tracks.map((p, i) => `
    <li class="tr ${i === Q.i ? 'cur' : ''} ${i !== Q.i && Q.played.has(p.vid) ? 'done' : ''}" data-i="${i}" title="${esc(p.title)} · ${esc(names(p.artists))}${p.dur ? ` · ${fmt(p.dur)}` : ''}">
      <div class="cv">${imgTag(p, 226)}<span class="eq"><i></i><i></i><i></i></span></div>
      <div class="mid"><div class="tt">${esc(p.title)}</div><div class="ar">${esc(names(p.artists))}</div></div>
      <div class="acts"><button class="ib like ${fb.get(p.vid) === 'like' ? 'on' : ''}" data-a="like" aria-label="${t('喜欢')}">${I.heart}</button><button class="ib" data-a="nope" aria-label="${t('不要')}">${I.x}</button></div>
    </li>`).join('') + `<li class="tile more"><button class="cv" data-k="extend" aria-label="${t('再来几首')}">${I.plus}</button><div class="tt">${t('再来几首')}</div></li>`;
  $$('.st').forEach((b) => b.toggleAttribute('aria-current', b.dataset.st === Q.key));
  keepCurrentRowVisible();
}

let frameIO = null;
function watchFrame() {
  frameIO?.disconnect();
  const f = $('#frame');
  if (!f) return;
  frameIO = new IntersectionObserver(([e]) => { $('#mini').hidden = e.isIntersecting || view !== 'listen' || !cur(); });
  frameIO.observe(f);
}

/* ---------- account ---------- */
const STATUS = () => ({ new: t('还没连接'), importing: t('读取喜欢中'), building: t('准备电台中'), ready: t('在听'), thin: t('喜欢太少'), error: t('出错了') });
const ago = (ts) => (ts ? when(ts) : '');
let friends = null;
let shownLink = null;
const CLAUDE_SRC = {
  worker: (c) => t('用你的 Claude 订阅，在你的 Mac 上跑。') + (c.online ? '' : t('Mac 现在不在线：新一期会等它醒来再做，点歌也要等它在线。')),
  subscription: () => t('用你的 Claude 订阅，在服务器上跑。'),
  key: () => t('用服务器上的 Claude API key，按用量计费。'),
};

function accountHTML() {
  const me = S.me;
  if (!me) return '';
  const g = me.google, sy = me.sync, ls = me.last_sync;
  const rows = [];
  if (!g.configured) {
    rows.push(`<li><span>YouTube Music<small>${t('连接 YouTube Music 需要先在服务器上配置 Google 登录。')}</small></span><span></span></li>`);
  } else if (g.error === 'revoked') {
    rows.push(`<li><span>YouTube Music<small>${t('连接失效了：可能在 Google 账号里移除了授权。重新连接一下。')}</small></span><a class="tb" href="/auth/google/start">${t('重新连接')}</a></li>`);
  } else if (!g.connected) {
    rows.push(`<li><span>YouTube Music<small>${t('还没连接。连接之后，你在这里点的喜欢会同步到账号，你在 YouTube Music 里新点的喜欢也会自动进来。')}</small></span><a class="tb" href="/auth/google/start">${t('连接')}</a></li>`);
  } else {
    const busy = S.jobs?.sync?.running;
    rows.push(`<li><span>YouTube Music<small>${esc(g.email || t('已连接'))}${me.synced ? ` · ${ls?.added ? t('{when} 读过一次，新增 {n} 首', { when: ago(me.synced), n: ls.added }) : t('{when} 读过一次', { when: ago(me.synced) })}` : ''}</small></span><button class="tb" data-k="resync" ${busy ? 'disabled' : ''}>${busy ? t('读取中…') : t('现在读取')}</button></li>`);
    const state = sy.pending ? (sy.error === 'quota' ? t('{n} 首等待同步：今天的额度用完了，{at}后继续', { n: sy.pending, at: quotaReset() }) : sy.error === 'reconnect' ? t('{n} 首等待同步：需要重新连接', { n: sy.pending }) : t('{n} 首等待同步', { n: sy.pending })) : sy.done ? t('已同步 {n} 首', { n: sy.done }) : t('在这里点 ♥，YouTube Music 里也会是喜欢');
    rows.push(`<li><span>${t('把这里的喜欢同步到 YouTube Music')}<small>${esc(state)}${t('。「不要」只记在知音，不会变成 YouTube 上的踩。')}</small></span><button class="sw" role="switch" data-k="synclikes" aria-checked="${me.sync_likes}" aria-label="${t('同步喜欢')}"></button></li>`);
  }
  if (me.mine && me.claude) {
    const c = me.claude;
    rows.push(`<li><span>Claude<small>${CLAUDE_SRC[c.source] ? CLAUDE_SRC[c.source](c) : t('还没配置。没有它，知音选不了歌：见 docs/self-hosting.md。')}</small></span><span>${c.source === 'worker' ? (c.online ? t('在线') : t('离线')) : ''}</span></li>`);
  }
  if (me.auth) {
    if (g.email) rows.push(`<li><span>${t('这个账号的登录书签')}<small>${t('在别的浏览器里想一键进来，就把这个链接存成书签（那里要登着 {email}）。', { email: esc(g.email) })}</small>${linkHTML(`${location.origin}/auth/google/start?mode=login&as=${encodeURIComponent(g.email)}`)}</span><span></span></li>`);
    else rows.push(`<li><span>${t('在另一台设备上登录')}<small>${t('生成一个 14 天内有效的登录链接，发给自己。')}</small>${shownLink?.kind === 'device' ? linkHTML(shownLink.url) : ''}</span><button class="tb" data-k="device">${t('生成链接')}</button></li>`);
    rows.push(`<li><span>${t('退出登录')}<small>${t('只退出这台设备。')}</small></span><button class="tb" data-k="logout">${t('退出')}</button></li>`);
    if (!me.owner) rows.push(`<li><span>${t('断开并删除我的数据')}<small>${t('撤销 Google 授权，删掉你的喜欢、电台和反馈。')}</small></span><button class="tb danger" data-k="delete">${t('删除')}</button></li>`);
  }
  return `<section class="sh-sec"><h3>${t('账号')}</h3><ul class="plain acct">${rows.join('')}</ul></section>${me.owner && me.auth ? friendsHTML() : ''}`;
}

function linkHTML(url) {
  return `<span class="link"><input readonly value="${esc(url)}" aria-label="${t('链接')}"><button class="tb" data-k="copy">${t('复制')}</button></span>`;
}

const FRIEND_KEY_NOTE = () => t('Claude 订阅按 Anthropic 的规定只给订阅者本人用，所以朋友的推荐要走 API key，按用量计费。在你的终端运行 <code>deploy/claude-token.sh --api-key</code>。');

function friendsHTML() {
  if (!friends) { api('/api/users').then((r) => { friends = r.users; renderSheet(); }).catch(() => {}); return ''; }
  const others = S.me.claude?.others;
  const list = friends.map((u) => `<li><span>${esc(u.mine ? u.email || t('你的另一个账号') : u.name)}<small>${u.mine && u.email ? `${t('你的另一个账号')} · ` : ''}${STATUS()[u.status] || u.status}${u.songs ? ` · ${t('{n} 首喜欢', { n: u.songs })}` : ''}${u.usd7 ? ` · ${t('近 7 天 ${usd}', { usd: u.usd7.toFixed(2) })}` : ''}</small></span><span>${u.last_seen ? ago(u.last_seen) : t('还没来过')}</span></li>`).join('');
  const add = others
    ? `<li><form class="invite" id="invite"><input name="name" placeholder="${t('朋友的名字')}" maxlength="20" autocomplete="off"><button class="tb">${t('生成邀请链接')}</button></form>${shownLink?.kind === 'invite' ? linkHTML(shownLink.url) : ''}</li>`
    : `<li><span>${t('邀请朋友前，先配置 Claude API key')}<small>${FRIEND_KEY_NOTE()}</small></span><span></span></li>`;
  const mine = `<li><span>${t('加你自己的另一个账号')}<small>${t('比如你的另一个 YouTube Music 账号：它是一个完全独立的账号，用自己的 Google 登录，喜欢、电台和反馈都分开，只是背后同样用你的 Claude。只给你自己用。')}</small>${shownLink?.kind === 'mine' ? linkHTML(shownLink.url) : ''}</span><button class="tb" data-k="mine">${t('生成登录链接')}</button></li>`;
  return `<section class="sh-sec"><h3>${t('朋友')}</h3><p>${others ? t('每位朋友用自己的 YouTube Music 喜欢算推荐，彼此看不到；他们的推荐用你的 API key 计费。') : t('每位朋友用自己的 YouTube Music 喜欢算推荐，彼此看不到。')}</p>
    <ul class="plain">${list}${add}${mine}</ul></section>`;
}

function langHTML() {
  const busy = S.jobs?.retell?.running;
  return `<section class="sh-sec"><h3>${t('语言')}</h3><ul class="plain acct"><li><span>${t('界面和推荐的语言')}<small>${busy ? t('正在把画像和推荐理由改写成{lang}…', { lang: LANGS[LANG] }) : t('画像和每首歌的推荐理由也用这种语言写。')}</small></span>
    <div class="seg" role="radiogroup" aria-label="${t('语言')}">${Object.entries(LANGS).map(([k, v]) => `<button role="radio" data-lang="${k}" lang="${k}" aria-checked="${k === LANG}">${v}</button>`).join('')}</div></li></ul></section>`;
}

async function setLang(lang) {
  if (lang === LANG) return;
  try {
    await api('/api/account/lang', { lang });
    location.reload();
  } catch (err) { toast(t('没保存上，稍后再试')); }
}

// Claude wrote the portrait and reasons for a reader of the other language (the listener switched since).
function staleLangNote() {
  if (!S.stale_lang) return;
  if (S.jobs?.retell?.running) { toast(t('正在把画像和推荐理由改写成{lang}…', { lang: LANGS[LANG] }), [], 6000); return; }
  toast(t('画像和推荐理由还是用另一种语言写的'), [[t('改写成{lang}', { lang: LANGS[LANG] }), async () => {
    try { S.jobs = await api('/api/account/retell', {}); poll(); toast(t('正在把画像和推荐理由改写成{lang}…', { lang: LANGS[LANG] }), [], 6000); } catch (err) { toast(err.message); }
  }]], 12000);
}

/* ---------- settings: a drawer over the page, the music keeps playing ---------- */
function renderSheet() {
  const d = $('#sheet');
  if (!d.open) return;
  const keep = d.scrollTop;
  d.innerHTML = `<header class="sh-head"><h2>${t('设置')}</h2><button class="ib sm" data-k="closesheet" aria-label="${t('关闭')}">${I.close}</button></header>
    <div class="sh-body">${langHTML()}${accountHTML()}</div>`;
  d.scrollTop = keep;
}
function openSettings() {
  closeMenu();
  const d = $('#sheet');
  if (!d.open) d.showModal();
  renderSheet();
}
$('#sheet').addEventListener('click', (e) => { if (e.target === e.currentTarget) e.currentTarget.close(); });

/* ---------- the account button and its menu ---------- */
const initial = (s) => esc(([...(s || '').trim()][0] || t('你')).toUpperCase());
function renderMe() {
  const me = S.me, g = me?.google || {};
  const name = me?.name || (g.email ? g.email.split('@')[0] : t('你'));
  const sub = g.email && g.email.split('@')[0] !== name ? g.email : me?.owner ? t('主人') : '';
  $('#meBtn').innerHTML = `<span class="av">${initial(name)}</span><span class="who"><b>${esc(name)}</b>${sub ? `<span>${esc(sub)}</span>` : ''}</span>${I.updown}`;
  $('.me-mini').innerHTML = `<span class="av">${initial(name)}</span>`;
}
function closeMenu() { const m = $('#menu'); if (m.matches(':popover-open')) m.hidePopover(); }
// A small popover placed against whatever opened it: above the account button, below the station's ⋯.
function openMenu(anchor, html) {
  const m = $('#menu');
  if (m.matches(':popover-open') && m.dataset.for === anchor.dataset.k) { closeMenu(); return; }
  m.innerHTML = html;
  m.dataset.for = anchor.dataset.k;
  m.showPopover();
  const a = anchor.getBoundingClientRect(), w = m.offsetWidth, h = m.offsetHeight;
  const left = clamp(a.left, 8, innerWidth - w - 8);
  const top = a.top - h - 8 > 8 && a.top > innerHeight / 2 ? a.top - h - 6 : a.bottom + 6;
  Object.assign(m.style, { left: `${left}px`, top: `${Math.min(top, innerHeight - h - 8)}px` });
  anchor.setAttribute('aria-expanded', 'true');
  m.addEventListener('toggle', (e) => { if (e.newState === 'closed') anchor.setAttribute('aria-expanded', 'false'); }, { once: true });
}
function accountMenu(anchor) {
  const me = S.me, g = me?.google || {};
  const name = me?.name || (g.email ? g.email.split('@')[0] : t('你'));
  // Switching is a fresh Google sign-in: accounts never list or reach each other.
  openMenu(anchor, `
    <div class="m-acct"><span class="av">${initial(name)}</span><span><b>${esc(name)}</b><span>${esc(g.email || (me?.owner ? t('主人') : ''))}</span></span></div>
    <hr>
    <button class="m-item" role="menuitem" data-k="settings">${I.gear}${t('设置')}</button>
    <button class="m-item" role="menuitem" data-k="keys">${I.keyb}${t('快捷键')}<kbd>?</kbd></button>
    ${me?.auth && g.configured ? `<a class="m-item" role="menuitem" href="/auth/google/start?mode=login">${I.swap}${t('用另一个账号登录')}</a>` : ''}
    ${me?.auth ? `<button class="m-item" role="menuitem" data-k="logout">${I.out}${t('退出登录')}</button>` : ''}`);
}
function stationMenu(anchor) {
  if (!Q) return;
  openMenu(anchor, `
    <button class="m-item" role="menuitem" data-k="ytm">${I.ext}${t('在 YouTube Music 里接着放')}</button>
    ${S.me?.google?.connected ? `<button class="m-item" role="menuitem" data-k="save">${I.plus}${t('把这个电台存成歌单')}</button>` : ''}
    <button class="m-item" role="menuitem" data-k="radio">${I.branch}${t('沿着这首继续')}</button>`);
}

/* ---------- shortcuts ---------- */
const KEYS = () => [[t('空格'), t('播放 / 暂停')], ['N', t('下一首')], ['P', t('上一首')], ['L', t('喜欢')], ['X', t('不要')], ['← →', t('快退 / 快进 10 秒')],
  ['/', t('点歌')], ['1–9', t('换电台')], ['G', t('歌词')], ['T', t('歌词翻译')], ['R', t('罗马音')], ['[ ]', t('歌词早一点 / 晚一点')], ['F', t('沉浸')], ['M', t('小窗')], ['?', t('快捷键')]];
function openKeys() {
  closeMenu();
  const d = $('#keysD');
  d.innerHTML = `<h2>${t('快捷键')}</h2><dl>${KEYS().map(([k, v]) => `<dt><kbd>${esc(k)}</kbd></dt><dd>${esc(v)}</dd>`).join('')}</dl>`;
  d.showModal();
}
$('#keysD').addEventListener('click', (e) => e.currentTarget.close());

/* ---------- ask: say what you want to hear; it is found in the background ---------- */
const IDEAS = () => ({
  morning: [t('早上通勤，轻快一点'), t('周末早晨煮咖啡'), t('开工前热热身，不要太吵')],
  day: [t('下午写代码，人声少一点'), t('下雨的周日下午'), t('做饭时听的日语 city pop')],
  evening: [t('下班路上，想放松'), t('晚饭后出去散步'), t('和朋友喝一杯')],
  night: [t('深夜一个人开车'), t('睡前，安静的钢琴和人声'), t('失眠的时候')],
});
function composerHTML() {
  const h = new Date().getHours();
  const ideas = IDEAS()[h >= 22 || h < 5 ? 'night' : h < 11 ? 'morning' : h < 17 ? 'day' : 'evening'];
  const asks = (S.asks || []).slice(0, 4);
  return `<div class="c-h">${t('试试')}</div><div class="chips">${ideas.map((x) => `<button class="chip" data-idea="${esc(x)}">${esc(x)}</button>`).join('')}</div>
    ${asks.length ? `<div class="c-h">${t('你点过的')}</div>${asks.map((a) => `<button class="c-row" data-st="ask:${a.created}"><span class="mosaic ${a.picks.length < 4 ? 'one' : ''}">${a.picks.slice(0, 4).map((p) => imgTag(p, 120)).join('')}</span><span><b>${esc(a.intent)}</b><span>${t('你说：{q}', { q: esc(a.q) })}</span></span></button>`).join('')}` : ''}`;
}
function openAsk() {
  closeMenu();
  const d = $('#composer'), input = $('#askInput');
  if (input.disabled) { toast(t('电台准备好之后，就能在这里点歌了')); return; }
  $('#cBody').innerHTML = composerHTML();
  if (!d.open) d.showModal();
  input.focus();
}
$('#composer').addEventListener('click', (e) => {
  if (e.target === e.currentTarget) return e.currentTarget.close();
  const idea = e.target.closest('[data-idea]');
  if (idea) { $('#askInput').value = idea.dataset.idea; submitAsk(); }
});
// The request flies from the composer into the station list, where it waits as a station being made.
function flyAsk(text, a) {
  const row = $('.st.pending .nm');
  if (!row || !a || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const b = row.getBoundingClientRect();
  if (!b.width) return;
  const el = document.createElement('p');
  el.className = 'fly';
  el.textContent = text;
  Object.assign(el.style, { left: `${a.left}px`, top: `${a.top + (a.height - 22) / 2}px` });
  document.body.append(el);
  row.style.opacity = '0';
  const s = 14 / 18;
  el.animate([{ transform: 'none', opacity: 1 }, { transform: `translate(${b.left - a.left}px, ${b.top - a.top - (a.height - 22) / 2 - 2}px) scale(${s})`, opacity: 1 }],
    { duration: 480, easing: 'cubic-bezier(.32, .72, 0, 1)' }).finished.then(() => { el.remove(); row.style.opacity = ''; });
}

/* ---------- ear view ---------- */
// The record: every like is a dot, ring by year (centre = the first like, edge = now), wedge by taste.
let EAR = null, earKey = '', earLoading = false, earRevealed = false, earFailed = false;
const earCol = new Map();
const TRAIL = 0.026;   // half the angle each trail spans, in radians
const E = { hi: null, hover: null, T: Infinity, anim: 0, era: -1, geo: null, pts: [], touch: false, ro: null };

async function loadEar() {
  if (earLoading) return;
  earLoading = true;
  try {
    const d = await api('/api/ear');
    d.list = d.songs.map(([vid, title, artists, album, dur, t, lane, a]) => ({
      vid, title, artists: artists.map((name) => ({ name })), album: album ? { name: album } : null, dur, t, lane, a,
    })).sort((x, y) => x.t - y.t);
    EAR = d;
    if (view === 'ear') renderEar();
    earColors();
  } catch {
    // the page still reads without the record
    earFailed = true;
    if (view === 'ear') renderEar();
  }
  earLoading = false;
}

const yearOf = (t) => Math.floor(t);
const whenLiked = (y) => (EAR?.real_dates ? new Date(yearOf(y), Math.min(11, Math.floor((y - yearOf(y)) * 12))).toLocaleDateString(LANG, { year: 'numeric', month: 'short' }) : t('{y} 年前后', { y: yearOf(y) }));
const songByTitle = (t) => EAR?.list.findLast((s) => s.title === t) || EAR?.list.findLast((s) => s.title.startsWith(t));
// 《title》 (“title” in English) in the portrait and the facts plays that like
const playable = (text) => esc(text).replace(/《([^》]+)》|“([^”]+)”/g, (m, a, b) => {
  const s = songByTitle((a ?? b).replace(/&#39;/g, "'").replace(/&quot;/g, '"').replace(/&amp;/g, '&'));
  // a link, not a button: a button is laid out as one box, so a long title would break away from its sentence
  return s ? `<a class="song" href="#" role="button" data-play="${s.vid}">${m}</a>` : m;
});

// YouTube Data API quotas reset at midnight Pacific time.
function quotaReset() {
  const now = new Date();
  const pt = new Date(now.toLocaleString('en-US', { timeZone: 'America/Los_Angeles' }));
  const at = new Date(now.getTime() + ((24 - pt.getHours()) * 3600 - pt.getMinutes() * 60 - pt.getSeconds()) * 1000);
  const hm = `${at.getHours()}:${String(at.getMinutes()).padStart(2, '0')}`;
  return at.toDateString() === now.toDateString() ? t('今天 {hm}', { hm }) : t('明天 {hm}', { hm });
}

const DISC = () => [[t('少'), 0.2], [t('中'), 0.4], [t('多'), 0.6]];
function laneRow(l, sec) {
  const covers = (sec?.covers || l.covers || []).slice(0, 4).map((v) => `<img src="${px(`https://i.ytimg.com/vi/${v}/mqdefault.jpg`)}" alt="" loading="lazy">`).join('');
  const lv = DISC().reduce((a, b) => (Math.abs(b[1] - l.discovery) < Math.abs(a[1] - l.discovery) ? b : a))[1];
  const playable = ST.some((x) => x.key === l.key && x.tracks.length);
  return `<div class="lrow ${l.enabled ? '' : 'off'}">
    ${playable ? `<button class="lc-play" data-st="${esc(l.key)}" aria-label="${t('放{name}', { name: esc(l.name) })}">${covers}</button>` : `<span class="lc-play">${covers}</span>`}
    <div class="lc-t"><div class="n">${esc(l.name)}<span class="num">${t('{n} 首', { n: l.size })}</span></div><div class="w">${esc(l.when)}</div></div>
    <div class="lc-ctl">
      <button class="sw" role="switch" aria-checked="${l.enabled}" data-lane="${esc(l.key)}" aria-label="${t('把{name}放进推荐', { name: esc(l.name) })}"></button>
      <div class="seg" role="radiogroup" aria-label="${t('没收藏过的歌手占多少')}"><span>${t('新面孔')}</span>${DISC().map(([w, v]) => `<button role="radio" aria-checked="${v === lv}" data-lane="${esc(l.key)}" data-disc="${v}" title="${t('没收藏过的歌手约占 {p}%', { p: Math.round(v * 100) })}">${w}</button>`).join('')}</div>
    </div></div>`;
}

function renderEar() {
  if (!ready() || !S.portrait) {
    $('#view').innerHTML = `<div class="ear-wrap"><div class="ear"><div class="ear-hero"><div>
      <h1>${S.me?.status === 'new' ? t('还没开始') : t('还在了解你')}</h1>
      <p class="lede">${S.library.songs ? t('读到了 {n} 首喜欢。电台准备好之后，这里会写出你的口味：你一直在听什么，它们怎么变过来，你可以怎么调。', { n: S.library.songs }) : t('连接 YouTube Music 之后，这里会写出你的口味。')}</p></div></div></div></div>`;
    placeHost();
    return;
  }
  if (!EAR && !earFailed) loadEar();
  const keep = $('.ear-wrap')?.scrollTop || 0;
  const po = S.portrait;
  const cut = po.headline.search(/[。！？]|[.!?](?=\s)/);   // the first sentence is the heading, in either script
  const head = cut > 0 ? po.headline.slice(0, cut + 1) : po.headline;
  const lede = po.headline.slice(head.length).trim();
  const first = EAR ? yearOf(EAR.span[0]) : (S.timeline.map((p) => p[1]).filter(Boolean).sort()[0] || '').slice(0, 4);
  const fbRows = S.feedback.filter((f) => f.action !== 'known').slice(0, 30);
  const label = (f) => (f.action === 'like' ? t('喜欢') : f.scope === 'artist' ? t('不要这位歌手') : t('不要这首'));
  const sec = (k) => EAR?.sectors.find((x) => x.key === k);
  const on = S.lanes.filter((l) => l.enabled).length;
  const skeleton = `<div class="fact sk"><b class="lead">00%</b><p>${t('正在把你的喜欢按年份排开')}</p></div>`.repeat(3);
  $('#view').innerHTML = `
  <div class="ear-wrap"><div class="ear">
    <header class="ear-hero">
      <div class="hero-t">
        <h1>${esc(head)}</h1>
        ${lede ? `<p class="lede">${esc(lede)}</p>` : ''}
        <p class="meta-line num">${t('{n} 首喜欢 · {y} 年至今 · {k} 种口味', { n: S.library.songs, y: first, k: S.lanes.length })}</p>
        <div class="facts" id="facts">${EAR ? factsHTML() : earFailed ? '' : skeleton}</div>
      </div>
      ${earFailed ? '' : `<div class="rec-l">
        <div class="disc ${EAR ? '' : 'loading'}" id="disc" aria-label="${t('你的喜欢，按年份一圈一圈往外长，按口味分成扇区')}">
          <canvas></canvas><svg class="disc-svg"></svg><div class="hub" id="hub"></div><div class="tip"></div>
        </div>
        <div class="eras2"><button class="replay" data-k="replay" title="${t('从第一首喜欢开始，重放一遍')}">${I.play}<span>${t('回放')}</span></button><div class="eratrack" id="eraTrack"></div></div>
        <p class="era-now" id="eraNow"></p>
      </div>`}
    </header>
    <section class="sec"><h2>${t('你的口味')}<small>${t('{n} 种在推荐里。点封面就放这个口味的电台；关掉的下一批起不再出现；新面孔是没收藏过的歌手占多少。', { n: on })}</small></h2>
      <div class="lanes">${S.lanes.map((l) => laneRow(l, sec(l.key))).join('')}</div></section>
    <section class="sec"><h2>${t('完整的画像')}</h2>
      <div class="portrait">
        <div><div class="prose" id="prose">${po.paragraphs.map((x) => `<p>${playable(x)}</p>`).join('')}</div>
          ${po.paragraphs.length > 1 ? `<button class="tb readmore" data-k="readmore">${t('读完整段')}</button>` : ''}</div>
        ${po.threads.length ? `<div class="threads"><h3>${t('一直没变的')}</h3><ol class="threads">${po.threads.map((x) => `<li>${playable(x)}</li>`).join('')}</ol></div>` : ''}
      </div></section>
    <section class="sec folds">
      ${S.set_aside.length ? `<details class="fold"><summary><b>${t('不算进口味的')}</b><span>${t('{n} 类，留在你的喜欢里，但不拿来推歌', { n: S.set_aside.length })}</span>${I.down}</summary>
        <ul class="plain">${S.set_aside.map((x) => `<li><span>${esc(x.what)}<small>${esc(x.why)}</small></span><span class="num">${t('{n} 首', { n: x.n })}</span></li>`).join('')}</ul></details>` : ''}
      ${fbRows.length ? `<details class="fold"><summary><b>${t('最近的反馈')}</b><span>${t('{n} 条，点错了可以撤销', { n: fbRows.length })}</span>${I.down}</summary>
        <ul class="plain">${fbRows.map((f) => `<li><span>${esc(f.title || f.vid)}<small>${esc(f.artist || '')} · ${label(f)} · ${new Date(f.ts * 1000).toLocaleDateString(LANG, { month: 'short', day: 'numeric' })}</small></span><button class="tb" data-undo="${esc(f.vid)}">${t('撤销')}</button></li>`).join('')}</ul></details>` : ''}
    </section>
  </div></div>`;
  $('.ear-wrap').scrollTop = keep;
  if (EAR) mountDisc();
  paintNow();
  placeHost();
}

function factsHTML() {
  return EAR.facts.map((f, i) => {
    const body = f.groups
      ? f.groups.map((g, j) => `<span class="lg" data-f="${i}" data-g="${j}">${esc(g.label)} <span class="num">${g.pct}%</span></span>`).join('<span class="sep">·</span><wbr>')
      : playable(f.text);
    return `<div class="fact" data-f="${i}"><b class="lead num">${esc(f.lead)}</b><p>${body}</p></div>`;
  }).join('');
}

function mountDisc() {
  const box = $('#disc');
  if (!box) return;
  const W = Math.round(box.clientWidth);
  if (!W) return;
  const dpr = Math.min(2, devicePixelRatio || 1);
  const cv = $('canvas', box);
  cv.width = W * dpr;
  cv.height = W * dpr;
  cv.style.width = cv.style.height = `${W}px`;
  const small = W < 460;
  const pad = small ? 22 : 30;
  const c = W / 2, R1 = c - pad, R0 = Math.max(40, R1 * 0.25);
  const [t0, t1] = EAR.span, span = Math.max(0.5, t1 - t0);
  const rOf = (t) => R0 + 10 + (R1 - R0 - 10) * (t - t0) / span;
  const P = (r, a) => [c + r * Math.sin(a * Math.PI / 180), c - r * Math.cos(a * Math.PI / 180)];
  E.geo = { W, c, R0, R1, rOf, P, dpr, dot: small ? 2 : 2.6, hit: small ? 20 : 13 };
  E.pts = EAR.list.map((s) => { const r = rOf(s.t), [x, y] = P(r, s.a); return { s, x, y, r, th: (s.a - 90) * Math.PI / 180 }; });

  const arc = (r, a0, a1, rev) => {
    const [x0, y0] = P(r, rev ? a1 : a0), [x1, y1] = P(r, rev ? a0 : a1);
    return `M${x0.toFixed(1)} ${y0.toFixed(1)}A${r} ${r} 0 ${a1 - a0 > 180 ? 1 : 0} ${rev ? 0 : 1} ${x1.toFixed(1)} ${y1.toFixed(1)}`;
  };
  let svg = '';
  const gap = 2 * Math.PI / 180 * 8;   // the open wedge at 12 o'clock is 16°
  let lastR = -99;
  for (let y = Math.ceil(t0); y <= t1; y++) {
    const r = rOf(y);
    svg += `<circle class="groove" cx="${c}" cy="${c}" r="${r.toFixed(1)}"/>`;
    if (r * gap >= 24 && r - lastR >= 12) { svg += `<text class="yr" x="${c}" y="${(c - r).toFixed(1)}">${y}</text>`; lastR = r; }
  }
  svg += `<path class="band" id="band"/><circle class="front" id="front" cx="${c}" cy="${c}" r="0"/>`;
  const fs = small ? 11 : 12;
  EAR.sectors.forEach((s, i) => {
    const mid = (s.a0 + s.a1) / 2, low = mid > 120 && mid < 240;
    // a short wedge still gets its name: a size smaller, then reaching a little into the gaps beside it
    const deg = (R1 + 12) * Math.PI / 180, len = deg * (s.a1 - s.a0);
    const need = (f) => [...s.name].length * f * 1.08 + 6;
    const f = len >= need(fs) ? fs : fs - 1.5;
    const ext = Math.min(2.2, Math.max(0, (need(f) - len) / deg / 2));
    const fits = len + 2 * ext * deg >= need(f);
    svg += `<g class="lab" data-sec="${i}"><path class="arc" d="${arc(R1 + 5, s.a0, s.a1)}"/>
      <path id="lp${i}" d="${arc(low ? R1 + 9 + f * 0.8 : R1 + 9, s.a0 - ext, s.a1 + ext, low)}" fill="none"/>
      <path class="hit" d="${arc(R1 + 12, s.a0, s.a1)}"/>
      ${fits ? `<text style="font-size:${f}px"><textPath href="#lp${i}" startOffset="50%" text-anchor="middle">${esc(s.name)}</textPath></text>` : ''}</g>`;
  });
  const sv = $('.disc-svg', box);
  sv.setAttribute('viewBox', `0 0 ${W} ${W}`);
  sv.innerHTML = svg;
  const hub = $('#hub');
  const hr = R0 - 4;
  Object.assign(hub.style, { width: `${hr * 2}px`, height: `${hr * 2}px`, left: `${c - hr}px`, top: `${c - hr}px` });
  const pos = (t) => (t - t0) / span, order = EAR.eras.map((_, i) => i).sort((a, b) => EAR.eras[a].t0 - EAR.eras[b].t0);
  $('#eraTrack').innerHTML = order.map((i, k) => {
    // an era runs until the next one starts, so a short era never lies under its neighbour's label
    const er = EAR.eras[i], next = EAR.eras[order[k + 1]];
    const l = pos(er.t0), r = next ? pos(next.t0) : Math.min(1, Math.max(pos(er.t1), l + 0.3 / span));
    return `<button class="era2" data-era="${i}" aria-label="${esc(er.years)} ${esc(er.label)}" style="left:${(l * 100).toFixed(2)}%;width:${((r - l) * 100).toFixed(2)}%"><span class="y num"><span class="yf">${esc(er.years)}</span><span class="ys">${esc(er.years.split(/[–-]/)[0])}</span></span><span class="l">${esc(er.label)}</span></button>`;
  }).join('');
  // Sized by pixels, not by share of the span: six two-year eras are each a fifth of the track but too narrow for a label.
  $$('.era2').forEach((b) => {
    const px = b.offsetWidth;
    b.classList.toggle('tiny', px < 40);
    b.classList.toggle('narrow', px >= 40 && px < 110);
  });
  showEra(-1);
  bindDisc(box);
  paintHub();
  if (!earRevealed) { earRevealed = true; replay(2600); } else paintDisc();
  if (!E.ro) {
    let w = W;
    E.ro = new ResizeObserver(() => { const b = $('#disc'); if (b && Math.abs(b.clientWidth - w) > 2) { w = b.clientWidth; mountDisc(); } });
  }
  E.ro.disconnect();
  E.ro.observe(box);
}

function paintDisc() {
  const g = E.geo, cv = $('#disc canvas');
  if (!g || !cv) return;
  const x = cv.getContext('2d');
  x.setTransform(g.dpr, 0, 0, g.dpr, 0, 0);
  x.clearRect(0, 0, g.W, g.W);
  const T = E.T, hi = E.hi;
  const draw = (p, on) => {
    const s = p.s;
    let r = g.dot;
    if (T !== Infinity) { const age = T - s.t; if (age < 0.35) r *= 1 + 1.1 * (1 - age / 0.35); }
    if (hi && on) r *= 1.2;
    // each like is a short trail along its ring, like a long exposure of the sky turning around the first one
    const h = TRAIL * (r / g.dot);
    x.globalAlpha = on ? 0.95 : 0.1;
    x.beginPath(); x.arc(g.c, g.c, p.r, p.th - h, p.th + h); x.lineWidth = r * 0.62; x.strokeStyle = earCol.get(s.vid) || 'rgba(255,255,255,.4)'; x.stroke();
  };
  x.lineCap = 'round';
  x.globalCompositeOperation = 'lighter';   // where trails cross they add up, like light on a long exposure
  for (const p of E.pts) if (p.s.t <= T && !(hi && hi.has(p.s.vid))) draw(p, !hi);
  if (hi) for (const p of E.pts) if (p.s.t <= T && hi.has(p.s.vid)) draw(p, true);
  x.globalAlpha = 1;
  x.globalCompositeOperation = 'source-over';
  const ring = (p, w, extra) => { x.beginPath(); x.arc(p.x, p.y, g.dot + extra, 0, 7); x.strokeStyle = '#fff'; x.lineWidth = w; x.stroke(); };
  const now = cur()?.vid;
  if (now && T === Infinity) for (const p of E.pts) if (p.s.vid === now) ring(p, 1.5, 3.5);
  if (E.hover) ring(E.hover, 2, 4);
}

function paintHub() {
  const hub = $('#hub');
  if (!hub || !EAR) return;
  if (E.T !== Infinity) { hub.dataset.u = ''; hub.className = 'hub'; hub.innerHTML = `<b class="num">${yearOf(Math.min(E.T, EAR.span[1]))}</b>`; return; }
  const p = E.hover?.s || cur();
  if (p) {
    const u = px(cover(p, 300));
    if (hub.dataset.u !== u) { hub.dataset.u = u; hub.innerHTML = `<img src="${u}" alt="">`; }
    hub.className = `hub ${E.hover ? '' : 'spin'}`;
    return;
  }
  hub.dataset.u = '';
  hub.className = 'hub';
  hub.innerHTML = `<b class="num">${EAR.list.length}</b><span>${t('首喜欢')}</span>`;
}

function showEra(i) {
  E.era = i;
  const k = i < 0 ? EAR.eras.length - 1 : i;
  const er = EAR.eras[k];
  $$('.era2').forEach((b) => b.classList.toggle('on', +b.dataset.era === k));
  const el = $('#eraNow');
  if (el) el.innerHTML = er ? `<b>${esc(er.years)} · ${esc(er.label)}</b>${playable(er.text)}` : '';
  const band = $('#band');
  if (!band || !E.geo) return;
  if (i < 0) { band.setAttribute('d', ''); return; }
  const { c, rOf } = E.geo, r0 = rOf(er.t0) - 4, r1 = rOf(er.t1) + 4;
  band.setAttribute('d', `M${c - r1} ${c}a${r1} ${r1} 0 1 0 ${2 * r1} 0a${r1} ${r1} 0 1 0 ${-2 * r1} 0ZM${c - r0} ${c}a${r0} ${r0} 0 1 1 ${2 * r0} 0a${r0} ${r0} 0 1 1 ${-2 * r0} 0Z`);
}

function highlight(vids) {
  E.hi = vids ? new Set(vids) : null;
  paintDisc();
}

function nearestDot(e) {
  const b = $('#disc').getBoundingClientRect();
  const mx = e.clientX - b.left, my = e.clientY - b.top;
  let best = null, bd = E.geo.hit;
  for (const p of E.pts) {
    if (p.s.t > E.T || (E.hi && !E.hi.has(p.s.vid))) continue;
    const d = Math.hypot(p.x - mx, p.y - my);
    if (d < bd) { bd = d; best = p; }
  }
  return best;
}

function hoverDot(p) {
  if (p === E.hover) return;
  E.hover = p;
  const tip = $('#disc .tip');
  if (p) {
    tip.innerHTML = `<b>${esc(p.s.title)}</b><span>${esc(names(p.s.artists))} · ${whenLiked(p.s.t)}</span>`;
    tip.style.left = `${p.x}px`;
    tip.style.top = `${p.y}px`;
    tip.style.opacity = 1;
  } else tip.style.opacity = 0;
  paintHub();
  paintDisc();
}

function bindDisc(box) {
  box.onpointerdown = (e) => { E.touch = e.pointerType !== 'mouse'; };
  box.onpointermove = (e) => { if (e.pointerType === 'mouse' && E.T === Infinity) hoverDot(nearestDot(e)); };
  box.onpointerleave = (e) => { if (e.pointerType === 'mouse') hoverDot(null); };
  box.onclick = (e) => {
    const lab = e.target.closest('.lab');
    if (lab) {
      const s = EAR.sectors[+lab.dataset.sec];
      if (ST.some((x) => x.key === s.key)) selectStation(s.key);
      return;
    }
    if (E.anim) return stopReplay();
    const p = nearestDot(e);
    if (!p) return hoverDot(null);
    if (E.touch && E.hover !== p) return hoverDot(p);
    playFromDisc(p);
  };
  $$('.lab', box).forEach((g) => {
    g.onmouseenter = () => { g.classList.add('on'); highlight(EAR.list.filter((s) => s.lane === EAR.sectors[+g.dataset.sec].key).map((s) => s.vid)); };
    g.onmouseleave = () => { g.classList.remove('on'); highlight(null); };
  });
  $$('.era2').forEach((b) => {
    const er = EAR.eras[+b.dataset.era];
    const on = () => { showEra(+b.dataset.era); highlight(EAR.list.filter((s) => s.t >= er.t0 - 0.01 && s.t <= er.t1 + 0.01).map((s) => s.vid)); };
    b.onmouseenter = on;
    b.onfocus = on;
    b.onclick = on;
    b.onmouseleave = () => { showEra(-1); highlight(null); };
  });
  $$('#facts .fact').forEach((f) => {
    const vids = EAR.facts[+f.dataset.f].vids;
    f.onmouseenter = () => { $('#facts').classList.add('dim'); f.classList.add('on'); highlight(vids); };
    f.onmouseleave = () => { $('#facts').classList.remove('dim'); f.classList.remove('on'); highlight(null); };
  });
  $$('#facts .lg').forEach((s) => {
    const g = EAR.facts[+s.dataset.f].groups[+s.dataset.g];
    s.onmouseenter = () => highlight(g.vids);
    s.onmouseleave = () => highlight(EAR.facts[+s.dataset.f].vids);
  });
}

function replay(ms) {
  if (E.anim) return stopReplay();
  if (!E.geo || document.hidden || matchMedia('(prefers-reduced-motion: reduce)').matches) { paintDisc(); return; }
  const [t0, t1] = EAR.span, D = ms || Math.min(12000, 1100 * (t1 - t0)), start = performance.now();
  hoverDot(null);
  $('.replay')?.classList.add('on');
  const front = $('#front');
  const step = (now) => {
    const k = Math.min(1, (now - start) / D);
    const e = k < 0.5 ? 2 * k * k : 1 - (-2 * k + 2) ** 2 / 2;
    E.T = t0 + (t1 - t0) * e + 1e-4;
    if (!ms) {
      const i = EAR.eras.findLastIndex((er) => E.T >= er.t0);
      if (i !== E.era && i >= 0) showEra(i);
    }
    front?.setAttribute('r', E.geo.rOf(E.T).toFixed(1));
    paintHub();
    paintDisc();
    E.anim = k < 1 ? requestAnimationFrame(step) : (stopReplay(), 0);
  };
  E.anim = requestAnimationFrame(step);
  // a hidden tab gets no frames; never leave the record half grown
  clearTimeout(E.end);
  E.end = setTimeout(() => { if (E.anim) stopReplay(); }, D + 500);
}

function stopReplay() {
  clearTimeout(E.end);
  cancelAnimationFrame(E.anim);
  E.anim = 0;
  E.T = Infinity;
  $('#front')?.setAttribute('r', 0);
  $('.replay')?.classList.remove('on');
  showEra(-1);
  paintHub();
  paintDisc();
}

function playFromDisc(p) {
  // the song, then its neighbours on the record: same taste, closest in sound order and in time
  const near = E.pts.filter((q) => q.s.lane === p.s.lane && q !== p)
    .sort((a, b) => Math.hypot(a.x - p.x, a.y - p.y) - Math.hypot(b.x - p.x, b.y - p.y));
  const seen = new Set([p.s.vid]), tracks = [p.s];
  for (const q of near) {
    if (tracks.length >= 25) break;
    if (seen.has(q.s.vid) || fb.get(q.s.vid) === 'dislike') continue;
    seen.add(q.s.vid);
    tracks.push(q.s);
  }
  const sec = EAR.sectors.find((s) => s.key === p.s.lane);
  const st = { key: 'ear', group: 'ear', name: t('{lane} · 从〈{s}〉放起', { lane: sec?.name || t('你的喜欢'), s: p.s.title }), sub: t('你自己的喜欢'), when: t('在「你的耳朵」里点的，接着放它附近的喜欢'), tracks, reserve: [] };
  Q = { key: 'ear', st, tracks, reserve: [], i: 0, played: new Set() };
  if (!$('.dock')) {
    $('#view').insertAdjacentHTML('beforeend', dockHTML());
    document.body.classList.add('has-dock');
  }
  placeHost();
  loadTrack(true);
  hoverDot(null);
}

function playVid(vid) {
  const p = E.pts.find((q) => q.s.vid === vid);
  if (p) playFromDisc(p);
}

// dot colours come from each song's own cover; kept per browser so the record is in colour from the second visit
async function earColors() {
  if (!earCol.size) for (const [v, c] of Object.entries(store.get(acct('earCol')) || {})) earCol.set(v, c);
  const todo = [...new Set(EAR.list.map((s) => s.vid))].filter((v) => !earCol.has(v));
  if (!todo.length) return;
  let i = 0, dirty = false;
  const flush = setInterval(() => { if (dirty && E.T === Infinity) { dirty = false; paintDisc(); } }, 160);
  const work = async () => {
    while (i < todo.length) {
      const v = todo[i++];
      try { earCol.set(v, await dotColor(px(`https://i.ytimg.com/vi/${v}/default.jpg`))); } catch { earCol.set(v, null); }
      dirty = true;
    }
  };
  await Promise.all(Array.from({ length: 6 }, work));
  clearInterval(flush);
  paintDisc();
  store.set(acct('earCol'), Object.fromEntries([...earCol].filter(([, c]) => c)));
}

function dotColor(src) {
  return new Promise((res, rej) => {
    const img = new Image();
    img.onload = () => {
      const c = document.createElement('canvas');
      c.width = c.height = 16;
      const x = c.getContext('2d', { willReadFrequently: true });
      // default.jpg is 4:3 around a 16:9 frame; the middle holds the artwork
      x.drawImage(img, img.width * 0.22, img.height * 0.2, img.width * 0.56, img.height * 0.6, 0, 0, 16, 16);
      const d = x.getImageData(0, 0, 16, 16).data;
      let r = 0, g = 0, b = 0, w = 0, sat = 0;
      for (let k = 0; k < d.length; k += 4) {
        const mx = Math.max(d[k], d[k + 1], d[k + 2]), mn = Math.min(d[k], d[k + 1], d[k + 2]);
        const l = (mx + mn) / 510, s = mx === mn ? 0 : (mx - mn) / (255 - Math.abs(mx + mn - 255));
        const wt = 0.02 + s * s * Math.max(0, 1 - Math.abs(l - 0.5) * 1.6);
        r += d[k] * wt; g += d[k + 1] * wt; b += d[k + 2] * wt; w += wt; sat += s;
      }
      const [h, s] = hueSat(r / w, g / w, b / w);
      // muted covers stay a quiet grey; colourful ones keep their hue at one lightness, so no dot shouts
      res(sat / 256 < 0.12 ? 'hsl(0 0% 64%)' : `hsl(${h} ${Math.round(Math.min(0.62, 0.3 + s * 0.6) * 100)}% 64%)`);
    };
    img.onerror = rej;
    img.src = src;
  });
}

function hueSat(r, g, b) {
  r /= 255; g /= 255; b /= 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2;
  if (mx === mn) return [0, 0];
  const d = mx - mn;
  const s = l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn);
  const h = (mx === r ? (g - b) / d + (g < b ? 6 : 0) : mx === g ? (b - r) / d + 2 : (r - g) / d + 4) * 60;
  return [Math.round(h), s];
}

/* ---------- routing ---------- */
function route() {
  view = location.hash === '#ear' ? 'ear' : 'listen';
  if (view !== 'ear' && E.anim) stopReplay();
  if (view === 'ear' && prefs.imm) immersive(false);
  $('#earLink').toggleAttribute('aria-current', view === 'ear');
  $$('#tabs [data-tab]').forEach((t) => t.toggleAttribute('aria-current', t.dataset.tab === view));
  $('#mini').hidden = true;
  $('#pcard').hidden = view === 'listen' || !cur();
  if (view === 'ear') renderEar(); else renderListen();
  renderStations();
  scrollTo(0, 0);
}
addEventListener('hashchange', route);

/* ---------- actions ---------- */
async function act(k, btn) {
  const p = cur();
  if (k === 'toggle') Player.toggle();
  else if (k === 'next') next();
  else if (k === 'prev') prev();
  else if (k === 'like' && p) like(p);
  else if (k === 'nope' && p) nope(p);
  else if (k === 'radio') { closeMenu(); continueFrom(null); }
  else if (k === 'lyrics') toggleLyrics();
  else if (k === 'calm' || k === 'up' || k === 'fresh') steer(k);
  else if (k === 'pip') Pip.toggle().catch(() => toast(t('小窗打不开')));
  else if (k === 'imm') immersive();
  else if (k === 'lytr' || k === 'lyro') {
    const key = k === 'lytr' ? 'tr' : 'ro';
    Lyr[key] = !Lyr[key];
    store.set(key, Lyr[key]);
    Lyr.render();
    Lyr.sync(true);
  } else if (k === 'extend') { btn.disabled = true; await extend(false); btn.disabled = false; }
  else if (k === 'refresh') startRefresh();
  else if (k === 'setup') { try { await api('/api/setup', {}); await reload(); poll(); } catch (err) { toast(err.message); } }
  else if (k === 'resync') { try { S.jobs = await api('/api/sync', {}); renderSheet(); poll(); } catch (err) { toast(err.message); } }
  else if (k === 'synclikes') {
    const on = btn.getAttribute('aria-checked') !== 'true';
    btn.setAttribute('aria-checked', on);
    S.me = await api('/api/account/sync-likes', { on });
    toast(on ? t('之后的喜欢会同步到 YouTube Music') : t('喜欢只记在知音，不再同步'));
  } else if (k === 'device') { const r = await api('/api/account/device', {}); shownLink = { kind: 'device', url: r.url }; renderSheet(); }
  else if (k === 'mine') { const r = await api('/api/invite', { mine: true }); shownLink = { kind: 'mine', url: r.url }; friends = null; renderSheet(); }
  else if (k === 'copy') {
    const input = btn.parentElement.querySelector('input');
    try { await navigator.clipboard.writeText(input.value); toast(t('已复制')); } catch { input.select(); }
  } else if (k === 'logout') { await api('/auth/logout', {}); location.href = '/login'; }
  else if (k === 'delete') {
    if (!btn.dataset.armed) {
      btn.dataset.armed = '1';
      btn.textContent = t('再点一次确认删除');
      setTimeout(() => { if (btn.isConnected) { delete btn.dataset.armed; btn.textContent = t('删除'); } }, 4000);
      return;
    }
    await api('/api/account/delete', {});
    location.href = '/login';
  }
  else if (k === 'replay') replay();
  else if (k === 'menu') accountMenu(btn);
  else if (k === 'stmenu') stationMenu(btn);
  else if (k === 'settings') openSettings();
  else if (k === 'closesheet') $('#sheet').close();
  else if (k === 'keys') openKeys();
  else if (k === 'ask') openAsk();
  else if (k === 'readmore') { $('#prose').classList.add('open'); btn.remove(); }
  else if (k === 'ytm') {
    closeMenu();
    const vids = Q.tracks.slice(Q.i).map((x) => x.vid);
    const w = window.open('', '_blank');
    try { const r = await api('/api/queue-link', { vids }); Player.pause(); w.location = r.url; } catch (err) { w?.close(); toast(t('打不开：{e}', { e: err.message })); }
  } else if (k === 'save') {
    closeMenu();
    try { const r = await api('/api/playlist', { name: Q.st.name, vids: Q.tracks.map((x) => x.vid) }); toast(t('已存成「知音 · {name}」', { name: Q.st.name }), [[t('打开'), () => window.open(r.url, '_blank')]]); } catch (err) { toast(err.message); }
  }
}

document.addEventListener('click', async (e) => {
  MS.arm();
  const st = e.target.closest('[data-st]');
  if (st) return selectStation(st.dataset.st);
  const line = e.target.closest('.ll[data-i]');
  if (line && Lyr.data) {
    const l = Lyr.data.lines[+line.dataset.i];
    Lyr.hold = 0;
    Player.seekTo(l.t + Lyr.delay);
    if (!Player.playing) Player.play();
    return;
  }
  const tr = e.target.closest('.tr');
  if (tr) {
    const p = Q.tracks[+tr.dataset.i];
    const a = e.target.closest('[data-a]')?.dataset.a;
    if (a === 'like') return like(p);
    if (a === 'nope') return nope(p);
    if (+tr.dataset.i === Q.i) return Player.toggle();
    Q.played.add(cur()?.vid);
    Q.i = +tr.dataset.i;
    return loadTrack(true);
  }
  if (e.target.closest('#ytHost')) return Player.toggle();
  const pl = e.target.closest('[data-play]');
  if (pl) { e.preventDefault(); return playVid(pl.dataset.play); }
  const bar = e.target.closest('.bar');
  if (bar) { const b = bar.getBoundingClientRect(); return Player.seek((e.clientX - b.left) / b.width); }
  const btn = e.target.closest('[data-k]');
  if (btn) act(btn.dataset.k, btn);
});

document.addEventListener('click', (e) => {
  const lb = e.target.closest('button[data-lang]');
  if (lb) { setLang(lb.dataset.lang); return; }
  const seg = e.target.closest('[data-disc][data-lane]');
  if (seg) {
    const v = +seg.dataset.disc, l = S.lanes.find((x) => x.key === seg.dataset.lane);
    $$('button', seg.parentElement).forEach((b) => b.setAttribute('aria-checked', b === seg));
    if (l) l.discovery = v;
    api('/api/settings/lane', { key: seg.dataset.lane, discovery: v }).then(() => toast(t('新面孔约占 {p}%，下一批开始生效', { p: Math.round(v * 100) })));
    return;
  }
  const un = e.target.closest('[data-undo]');
  if (un) {
    const f = S.feedback.find((x) => x.vid === un.dataset.undo);
    un.disabled = true;
    api('/api/feedback', { vid: un.dataset.undo, title: f?.title, artist: f?.artist, action: 'undo' }).then(() => {
      fb.delete(un.dataset.undo);
      S.feedback = S.feedback.filter((x) => x.vid !== un.dataset.undo);
      un.closest('li').classList.add('undone');
      un.textContent = t('已撤销');
      paintLikes();
    }).catch(() => { un.disabled = false; toast(t('没撤销成功，稍后再试')); });
    return;
  }
  const sw = e.target.closest('.sw[data-lane]');
  if (!sw) return;
  const on = sw.getAttribute('aria-checked') !== 'true';
  sw.setAttribute('aria-checked', on);
  sw.closest('.lrow').classList.toggle('off', !on);
  const l = S.lanes.find((x) => x.key === sw.dataset.lane);
  if (l) l.enabled = on;
  api('/api/settings/lane', { key: sw.dataset.lane, enabled: on }).then(() => toast(on ? t('下一批起会出现') : t('下一批起不再出现')));
});

function onKey(e) {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); return $('#composer').open ? $('#composer').close() : openAsk(); }
  if (e.target.closest?.('input, textarea')) { if (e.key === 'Escape' && !e.target.closest('dialog')) e.target.blur(); return; }
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  if (document.querySelector('dialog[open]')) return;
  MS.arm();
  const k = e.key.toLowerCase(), p = cur();
  if (e.code === 'Space') { e.preventDefault(); Player.toggle(); }
  else if (k === 'n') next();
  else if (k === 'p') prev();
  else if (k === 'l' && p) like(p);
  else if (k === 'x' && p) nope(p);
  else if (k === 'g') toggleLyrics();
  else if (k === 'f') immersive();
  else if (k === 'm') Pip.toggle().catch(() => toast(t('小窗打不开')));
  else if (k === 't' && Lyr.data) act('lytr');
  else if (k === 'r' && Lyr.data) act('lyro');
  else if (e.key === '[') Lyr.nudge(-0.25);
  else if (e.key === ']') Lyr.nudge(0.25);
  else if (e.key === 'ArrowRight') Player.seekTo(Player.time()[0] + 10);
  else if (e.key === 'ArrowLeft') Player.seekTo(Player.time()[0] - 10);
  else if (k === '/') { e.preventDefault(); window.focus(); openAsk(); }
  else if (e.key === '?') openKeys();
  else if (/^[1-9]$/.test(e.key)) { const s = ST.filter((x) => !x.pending)[+e.key - 1]; if (s) selectStation(s.key); }
  else if (k === 'escape') { if (prefs.imm) immersive(false); else if (view === 'ear') location.hash = ''; }
}
document.addEventListener('keydown', onKey);

document.addEventListener('submit', async (e) => {
  if (e.target.id !== 'invite') return;
  e.preventDefault();
  const name = e.target.name.value.trim();
  if (!name) return;
  try {
    const r = await api('/api/invite', { name });
    shownLink = { kind: 'invite', url: r.url };
    friends = null;
    renderSheet();
    toast(t('把链接发给{name}，{n} 天内有效', { name, n: r.days }));
  } catch (err) { toast(err.message); }
});

async function submitAsk() {
  const input = $('#askInput'), q = input.value.trim();
  if (!q) return;
  try {
    await api('/api/ask', { q });
    const box = input.getBoundingClientRect();
    pendingAsk = q.length > 16 ? `${q.slice(0, 16)}…` : q;
    input.value = '';
    $('#composer').close();
    buildStations();
    renderStations();
    flyAsk(pendingAsk, box);
    poll();
    toast(t('在找了，一分钟左右。先接着听'));
  } catch (err) {
    toast(err.code === 'busy' ? t('上一个还在找，稍等一下') : t('没发出去：{e}', { e: err.message }));
  }
}
$('#ask').onsubmit = (e) => { e.preventDefault(); submitAsk(); };

async function startRefresh() {
  try { await api('/api/refresh', {}); } catch { /* already running */ }
  S.jobs = await api('/api/jobs');
  renderStations();
  poll();
}

/* ---------- background jobs ---------- */
let polling = false;
async function poll() {
  if (polling) return;
  polling = true;
  const seen = Object.fromEntries(Object.entries(S.jobs || {}).map(([k, j]) => [k, j?.ended]));
  try {
    for (;;) {
      await new Promise((r) => setTimeout(r, 2500));
      const jobs = await api('/api/jobs').catch(() => null);
      if (!jobs) continue;
      const done = Object.entries(jobs).filter(([k, j]) => j && !j.running && j.ended && j.ended !== seen[k]);
      for (const [k, j] of done) seen[k] = j.ended;
      if (done.length) await finished(done);
      S.jobs = jobs;
      renderStations();
      if (!Object.values(jobs).some((j) => j?.running)) break;
    }
  } finally { polling = false; }
}

async function finished(done) {
  const prevEd = S.edition?.id;
  await reload();
  for (const [k, j] of done) {
    if (k === 'ask') {
      pendingAsk = null;
      buildStations();
      renderStations();
      if (j.error) { toast(t('没找到合适的：{e}', { e: j.error.slice(0, 60) })); continue; }
      const a = ST.find((s) => s.group === 'ask');
      if (!a) continue;
      if (!Player.playing) selectStation(a.key, true);
      else toast(t('「{name}」准备好了', { name: a.name }), [[t('现在听'), () => selectStation(a.key)]], 9000);
    }
    if (k === 'setup' && !j.error && ready()) {
      if (!Q || Q.key === 'warm') {
        const d = defaultStation();
        if (Q && Player.playing) toast(t('你的电台准备好了'), [[t('现在听'), () => selectStation(d.key)]], 12000);
        else if (d) { Q = queueOf(d); renderListen(); loadTrack(false); toast(t('你的电台准备好了')); }
      } else toast(t('你的电台准备好了'));
      continue;
    }
    if (k === 'sync' && !j.error) { if (view === 'ear') renderEar(); continue; }
    if (k === 'retell') {
      if (j.error) toast(t('没改写成功：{e}', { e: j.error.slice(0, 60) }));
      else { EAR = null; route(); renderSheet(); toast(t('改写好了')); }
      continue;
    }
    if (k === 'refresh' && !j.error && S.edition?.id !== prevEd) {
      if (!Q) { const d = defaultStation(); if (d) { Q = queueOf(d); renderListen(); loadTrack(false); } }
      toast(t('今天的电台换了新的一批，点电台就能听到'));
    }
  }
}

let warming = false;
async function loadWarm() {
  if (warming) return;
  warming = true;
  try {
    WARM = await api('/api/warmup');
    buildStations();
    renderStations();
    if (!Q && WARM.tracks.length) { Q = queueOf(ST.find((x) => x.key === 'warm')); route(); loadTrack(false); }
  } catch { setTimeout(() => { warming = false; loadWarm(); }, 15000); return; }
  warming = false;
}

async function reload() {
  S = await api('/api/state');
  const k = `${S.profile_built}|${S.library.songs}`;
  if (k !== earKey) { earKey = k; EAR = null; }
  if (!ready() && S.me.status !== 'new' && !WARM) loadWarm();
  if (ready() && Q?.key !== 'warm') WARM = null;
  $('#askInput').disabled = !ready() || !S.portrait;
  $('#askOpen').classList.toggle('wait', $('#askInput').disabled);
  fb.clear();
  for (const f of [...S.feedback].reverse()) fb.set(f.vid, f.action);
  buildStations();
  // a retold or converted edition brings new words for the station that is playing; keep its order and place
  // only the same edition: a new morning's station of the same name holds other songs
  const st = Q && queues.get(`${S.edition?.id}|${Q.key}`) === Q && ST.find((x) => x.key === Q.key);
  if (st) {
    Q.st = st;
    const why = new Map([...st.tracks, ...(st.reserve || [])].map((p) => [p.vid, p.reason]));
    for (const p of [...Q.tracks, ...Q.reserve]) if (why.has(p.vid)) p.reason = why.get(p.vid);
    if (view === 'listen' && $('#qName')) { renderQueue(); paintNow(); }
  }
  renderStations();
  if (view === 'ear') renderEar();
}

function buildMini() {
  $('.pc-ctl').innerHTML = `<button class="ib" data-k="prev" aria-label="${t('上一首')}">${I.prev}</button><button class="ib play" data-k="toggle" aria-label="${t('播放 / 暂停')}">${I.play}${I.pause}</button><button class="ib" data-k="next" aria-label="${t('下一首')}">${I.next}</button><span class="push"></span><button class="ib like" data-k="like" aria-label="${t('喜欢')}">${I.heart}</button>`;
  $('#mini').innerHTML = `<img id="mImg" alt=""><div style="min-width:0"><div class="tt" id="mTitle"></div><div class="ar" id="mArtist"></div></div>
    <button class="ib play" data-k="toggle" aria-label="${t('播放 / 暂停')}">${I.play}${I.pause}</button><button class="ib" data-k="next" aria-label="${t('下一首')}">${I.next}</button>`;
}

async function boot() {
  for (const k of ['last', 'pos', 'syncHint', 'earCol', 'off']) store.del(k);  // from before keys were per account
  buildMini();
  MS.init();
  try {
    await reload();
  } catch (err) {
    $('#view').innerHTML = `<div class="empty"><h2>${t('连不上知音')}</h2><p>${t('{e}。在终端运行 <code>uv run zhiyin serve</code> 后刷新。', { e: esc(err.message) })}</p></div>`;
    return;
  }
  const g = new URLSearchParams(location.search).get('google');
  if (g) {
    history.replaceState(null, '', location.pathname + location.hash);
    const msg = { cancelled: t('没有连接，随时可以再试'), noscope: t('Google 那一步没有勾选 YouTube 的权限，知音读不到你的喜欢。再连接一次，记得勾上'), taken: t('这个 Google 账号已经连在另一位听众名下'), stale: t('连接超时了，再试一次') }[g];
    if (msg) setTimeout(() => toast(msg, [], 7000), 400);
  }
  const last = store.get(acct('last'));
  const first = ST.find((s) => s.key === last && !s.pending && s.tracks.length) || defaultStation();
  if (first) {
    Q = queueOf(first);
    const pos = store.get(acct('pos'));
    if (pos?.ed === S.edition?.id && pos.key === Q.key) Q.i = Math.max(0, Q.tracks.findIndex((p) => p.vid === pos.vid));
  }
  Player.init();
  route();
  if (cur()) { Player.load(cur(), false); trackChanged(); }
  if (Object.values(S.jobs || {}).some((j) => j?.running)) poll();
  setTimeout(staleLangNote, 1200);
}

applyLang();
boot();
