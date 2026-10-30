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
  stage: '<svg viewBox="0 0 24 24"><path d="M7.5 8h9M9 11.5h6"/><rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><rect x="5.5" y="14" width="4" height="3.5" rx=".8" fill="currentColor" stroke="none"/></svg>',
  more: '<svg viewBox="0 0 24 24"><circle cx="6" cy="12" r="1.3" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.3" fill="currentColor" stroke="none"/><circle cx="18" cy="12" r="1.3" fill="currentColor" stroke="none"/></svg>',
  updown: '<svg viewBox="0 0 24 24"><path d="m8 9 4-4 4 4M8 15l4 4 4-4"/></svg>',
  check: '<svg viewBox="0 0 24 24"><path d="m5.5 12.5 4 4 9-9"/></svg>',
  gear: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 3.5v2.2M12 18.3v2.2M20.5 12h-2.2M5.7 12H3.5M18 6l-1.6 1.6M7.6 16.4 6 18M18 18l-1.6-1.6M7.6 7.6 6 6"/></svg>',
  out: '<svg viewBox="0 0 24 24"><path d="M14 5H6.5v14H14M10 12h10M17 8.5 20.5 12 17 15.5"/></svg>',
  keyb: '<svg viewBox="0 0 24 24"><rect x="3.5" y="6.5" width="17" height="11" rx="2"/><path d="M7 10h.01M10.5 10h.01M14 10h.01M17 10h.01M8 14h8"/></svg>',
  down: '<svg viewBox="0 0 24 24"><path d="m7 10 5 5 5-5"/></svg>',
  go: '<svg viewBox="0 0 24 24"><path d="M5 12h14M13 6l6 6-6 6"/></svg>',
  close: '<svg viewBox="0 0 24 24"><path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/></svg>',
  swap: '<svg viewBox="0 0 24 24"><path d="M7 8h12M15.5 4.5 19 8l-3.5 3.5M17 16H5M8.5 12.5 5 16l3.5 3.5"/></svg>',
  share: '<svg viewBox="0 0 24 24"><path d="M12 14.5V4.5M8 8.5l4-4 4 4"/><path d="M7 11H5.5v8.5h13V11H17"/></svg>',
  save: '<svg viewBox="0 0 24 24"><path d="M12 4.5v10M8 10.5l4 4 4-4"/><path d="M5.5 15.5v4h13v-4"/></svg>',
  copy: '<svg viewBox="0 0 24 24"><rect x="8.5" y="8.5" width="11" height="11" rx="2"/><path d="M15.5 5.5v-1h-11v11h1"/></svg>',
  link: '<svg viewBox="0 0 24 24"><path d="M10.5 13.5a3.5 3.5 0 0 0 5 0l3-3a3.5 3.5 0 0 0-5-5l-1 1"/><path d="M13.5 10.5a3.5 3.5 0 0 0-5 0l-3 3a3.5 3.5 0 0 0 5 5l1-1"/></svg>',
};

let S = null;          // server state
let ST = [];           // stations, in display order
let Q = null;          // the queue being played: { key, st, tracks, reserve, i, played }
let view = 'listen';
let pendingAsk = null;
let WARM = null;       // radios from the newest likes, while a new listener's stations are being made
const queues = new Map();
const ready = () => !S.me || S.me.status === 'ready';
// Not signed in: the page plays a made-up listener's stations, read-only. Anything that needs an account opens the
// join sheet instead.
const SAMPLE = () => !!S?.me?.sample;
const NEEDS_ACCOUNT = new Set(['like', 'nope', 'refresh', 'setup', 'resync', 'synclikes', 'device', 'mine', 'delete',
  'settings', 'save', 'stmenu', 'logout', 'relabel']);
const fb = new Map();
const prefs = { lyr: store.get('lyr') ?? true, lyrNarrow: true, imm: false, stage: store.get('stage') ?? false };
const REDUCED = matchMedia('(prefers-reduced-motion: reduce)');

async function api(path, body) {
  // Say which account this page shows, so a tab left open after switching accounts can't write into the other one.
  const headers = S?.me?.uid ? { 'X-Zhiyin-Uid': S.me.uid } : {};
  const r = await fetch(path, body === undefined ? { headers } : { method: 'POST', headers: { ...headers, 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (r.status === 401 && SAMPLE()) { openJoin(); throw new Error(t('需要先加入')); }
  if (r.status === 401) { location.href = '/login'; throw new Error(data.detail || t('需要重新登录')); }
  if (r.status === 409 && data.detail === 'account-changed') { location.reload(); throw new Error(t('这个浏览器已经换了账号')); }
  if (r.status === 409 && data.detail === 'busy') throw Object.assign(new Error(t('上一次还没做完，稍等一下')), { code: 'busy' });
  if (!r.ok) throw new Error(data.detail || r.statusText);
  return data;
}
// counts on the way in (a first listen to the sample, a card shared): how many, never who
const ev = (name) => api('/api/event', { name }).catch(() => {});
// A write that has to arrive even when the page is closing (how the song in progress ended).
function beacon(path, body) {
  const headers = { 'Content-Type': 'application/json', ...(S?.me?.uid ? { 'X-Zhiyin-Uid': S.me.uid } : {}) };
  fetch(path, { method: 'POST', headers, body: JSON.stringify(body), keepalive: true }).catch(() => {});
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
// A record from likes kept in an app: whose, and its covers at about `size` px. NetEase scales a cover by a parameter;
// QQ Music by the file name, and only through this server, since its CDN won't let the page read the pixels.
const appName = (a) => (a === 'qq' ? t('QQ 音乐') : t('网易云音乐'));
const appShort = (a) => (a === 'qq' ? t('QQ 音乐') : t('网易云'));
function appPic(u, size) {
  if (!/\.gtimg\.cn\//.test(u)) return `${u}?param=${size}y${size}`;
  const s = size > 150 ? 300 : 90;
  return px(u.replace(/T002R\d+x\d+M000/, `T002R${s}x${s}M000`));
}
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
  if (p.kind) return mineLine(p);
  if (p.mine) return t('这首是你喜欢过的');
  if (Q?.key === 'ear' && p.t) return EAR?.dates === 'released' ? whenPlaced(p.t) : t('你在 {when}点了喜欢', { when: whenLiked(p.t) });
  if (p.reason) return p.reason;
  return p.near ? t('听感接近你收藏的〈{s}〉', { s: p.near }) : '';
}
// What the page says about the listener next to a pick comes from their data, never from the editor's sentence:
// the one like of theirs it is shown with (play it, then the pick, and judge), and whether they have the artist.
// [text, can be played first] for each fact
function becauseParts(p) {
  if (!p || p.mine || Q?.key === 'ear') return [];
  if (p.kind) return p.bridge ? [[p.bridge === 'near' ? t('下一首新歌听感像这首') : t('下一首新歌是从这首找到的')]] : [];
  const out = [], b = p.because, a = p.artists?.[0]?.name;
  // just heard as the song before: say so, nothing to play first
  const just = b && cur() === p && Q.tracks[Q.i - 1]?.vid === b.vid && Q.played.has(b.vid);
  if (just) out.push([b.how === 'near' ? t('像刚才那首〈{s}〉', { s: b.title }) : t('从刚才那首〈{s}〉找到', { s: b.title })]);
  else if (b) out.push([b.how === 'near' ? t('像你喜欢的〈{s}〉', { s: b.title }) : t('从你喜欢的〈{s}〉找到', { s: b.title }), true]);
  if (a && p.familiar != null) {
    out.push([p.familiar ? t('你收藏过 {a} 的 {n} 首', { a, n: p.familiar }) : p.knows === 'follow' ? t('你在 YouTube 订阅了 {a}', { a })
      : p.knows === 'plays' ? t('你常听 {a}，还没点过喜欢', { a }) : t('你还没收藏过 {a}', { a })]);
  }
  return out;
}
function becauseHTML(p) {
  return becauseParts(p).map(([s, play]) => (play
    ? `<button class="bc-song" data-k="hearmine" title="${t('先放你这首，再回到这首推荐')}">${I.play}<span>${esc(s)}</span></button>`
    : `<span>${esc(s)}</span>`)).join('<span class="sep">·</span>');
}

/* ---------- toast ---------- */
function toast(msg, actions = [], ms) {
  const t = $('#toast');
  t.innerHTML = `<span>${esc(msg)}</span>${actions.length ? `<div class="acts">${actions.map(([l], i) => `<button data-i="${i}">${esc(l)}</button>`).join('')}</div>` : ''}`;
  $$('button', t).forEach((b) => { b.onclick = () => { t.classList.remove('show'); actions[+b.dataset.i][1](); }; });
  t.style.left = t.style.bottom = '';
  t.classList.toggle('many', actions.length > 2);
  t.classList.add('show');
  clearOf(t);
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
    key: `ask:${a.created}`, group: 'ask', name: a.intent || a.q, sub: artistLine(a.picks), when: t('你说：{q}', { q: a.q }), tracks: a.picks, reserve: [],
  }));
  const mix = mixOf(ed);
  if (mix) out.push({ key: 'mix', group: 'lane', name: t('精选'), sub: t('来自全部 {n} 个电台', { n: mix.n }), when: t('每个电台最有把握的几首，轮流放'), tracks: mix.tracks, reserve: mix.reserve });
  // Each morning only the stations someone played from get new songs; mark those until they are opened.
  const partial = (ed?.lanes || []).some((l) => l.fresh === false);
  const seen = store.get(acct('seen')) || {};
  for (const l of ed?.lanes || []) {
    const fresh = partial && l.fresh === ed.id && seen[ed.id]?.[l.key] !== 1;
    out.push({ key: l.key, group: 'lane', name: l.name, sub: artistLine(l.picks), when: l.when, tracks: l.picks, reserve: l.reserve || [], fresh });
  }
  if (ed?.focus?.picks?.length) out.push({ key: 'focus', group: 'lane', name: t('专注'), sub: t('一小时左右的长歌单'), when: ed.focus.when, tracks: ed.focus.picks, reserve: [] });
  ST = out;
}

/* ---------- the first station: the surest songs of every other station, taking turns ---------- */
const MIX_N = 16;
// The order is fixed for an edition within a visit: it starts from the hour, and a reload an hour later mustn't
// reshuffle the queue that is playing.
const mixOrder = new Map();

function mixOf(ed) {
  const lanes = (ed?.lanes || []).filter((l) => l.picks?.length);
  if (lanes.length < 2) return null;
  if (!mixOrder.has(ed.id)) mixOrder.set(ed.id, orderMix(lanes));
  const o = mixOrder.get(ed.id);
  // copies that remember their station: a play or a "not this" counts for the station the song came from
  const by = new Map(lanes.flatMap((l) => l.picks.map((p) => [p.vid, { ...p, from: l.key }])));
  const pick = (vids) => vids.map((v) => by.get(v)).filter(Boolean);
  return { tracks: pick(o.tracks), reserve: pick(o.reserve), n: lanes.length };
}

// How much of the listener's liking each station holds lately: a like's weight halves about every seven months,
// as when the stations were made.
function laneWeights() {
  const now = new Date(), w = {};
  for (const [, at, lane] of S.timeline || []) {
    const [y, m] = (at || '').split('-').map(Number);
    if (!y || !m) continue;
    const age = Math.max(0, (now.getFullYear() - y) * 12 + now.getMonth() + 1 - m);
    w[lane] = (w[lane] || 0) + 0.5 ** (age / 7);
  }
  return w;
}

function orderMix(lanes) {
  const w = laneWeights(), weight = (l) => (w[l.key] || 0) + 0.1;
  const sure = new Map(lanes.map((l) => [l.key, [...l.picks].sort((a, b) => (b.fit || 0) - (a.fit || 0))]));
  // every station once, then more from the ones listened to most, at most three from one
  const slots = new Map(lanes.map((l) => [l.key, 1]));
  let left = Math.min(MIX_N, lanes.reduce((a, l) => a + l.picks.length, 0)) - lanes.length;
  while (left-- > 0) {
    const open = lanes.filter((l) => slots.get(l.key) < Math.min(3, l.picks.length));
    if (!open.length) break;
    const l = open.reduce((a, b) => (slots.get(b.key) / weight(b) < slots.get(a.key) / weight(a) ? b : a));
    slots.set(l.key, slots.get(l.key) + 1);
  }
  const heavy = [...lanes].sort((a, b) => weight(b) - weight(a));
  const want = hourWant(), mid = (k) => { const e = S.lanes?.find((l) => l.key === k)?.energy; return e ? (e[0] + e[1]) / 2 : 3; };
  // Rounds of one song per station. The first song fits the hour; each next one is the station whose song sounds
  // closest to the one before (never the same station twice running), so the turns don't lurch.
  const out = [];
  let prev = null;
  for (let r = 0; ; r++) {
    const round = heavy.filter((l) => slots.get(l.key) > r);
    if (!round.length) break;
    while (round.length) {
      const song = (l) => sure.get(l.key)[r];
      const sim = (l) => { const a = vec(prev?.p), b = vec(song(l)); return a && b ? dot(a, b) : -1; };
      const options = prev && round.length > 1 ? round.filter((l) => l.key !== prev.key) : round;
      const l = prev ? options.reduce((a, b) => (sim(b) > sim(a) ? b : a))
        : options.reduce((a, b) => (Math.abs(mid(b.key) - want) < Math.abs(mid(a.key) - want) ? b : a));
      round.splice(round.indexOf(l), 1);
      prev = { key: l.key, p: song(l) };
      out.push(prev.p.vid);
    }
  }
  // when those run out, the rest of every station's picks, taking turns the same way
  const reserve = [];
  for (let r = 0; r < 8; r++) for (const l of heavy) { const p = sure.get(l.key)[slots.get(l.key) + r]; if (p) reserve.push(p.vid); }
  return { tracks: out, reserve };
}

/* ---------- your own likes, woven in between the new songs (rotation.py) ---------- */
// How many of the listener's likes play between two new songs: familiar, balanced (the default), new only.
const BLEND = { fam: 4, bal: 2, new: 0 };
const BLEND_NOTE = () => ({ fam: t('每 4 首你的收藏放 1 首新歌'), bal: t('每 2 首你的收藏放 1 首新歌'), new: t('只放新歌') });
const HUSH_D = 60;   // "not for a while": rotation.HUSH_D
let MINE = null;   // { songs, by, picks, ed, skew }: each like with how much it is wanted and when it is next due
let mineAt = 0;
const famHeard = new Set();   // likes started this visit, in any station: not again until the next visit
const nowS = () => (Date.now() + (MINE?.skew || 0)) / 1000;
const woven = (st) => st.group === 'lane' && st.key !== 'focus';
const blendOf = (key) => (store.get(acct('blend')) || {})[key] || 'bal';

async function loadMine(force = false) {
  if (!force && Date.now() - mineAt < (MINE ? 3 * 3600e3 : 60e3) && (!MINE || MINE.ed === S?.edition?.id)) return;
  mineAt = Date.now();
  try {
    const r = await api('/api/mine');
    MINE = { songs: r.songs, by: new Map(r.songs.map((x) => [x.vid, x])), picks: r.picks, ed: r.ed, skew: r.now * 1000 - Date.now() };
  } catch { /* until it loads, stations play new songs only */ }
}
// The picks' sound comes packed with the same basis as the likes', so a new song can be placed after the like it
// sounds closest to. Every state load brings fresh pick objects, so this runs after each.
function packPicks() {
  if (!MINE) return;
  for (const l of S.edition?.lanes || []) for (const p of [...l.picks, ...(l.reserve || [])]) {
    const x = MINE.picks[p.vid];
    if (x) { p.v = x.v; if (x.en != null) p.en = x.en; }
  }
}

function seeded(str) {
  let h = 1779033703 ^ str.length;
  for (let i = 0; i < str.length; i++) { h = Math.imul(h ^ str.charCodeAt(i), 3432918353); h = (h << 13) | (h >>> 19); }
  return () => { h = Math.imul(h ^ (h >>> 16), 2246822507); h = Math.imul(h ^ (h >>> 13), 3266489909); return ((h ^= h >>> 16) >>> 0) / 4294967296; };
}

// The likes a station can play, in the order it would play them: each drawn by how much it is wanted, how long since
// it was heard and how well it suits the hour, at random but the same order all day.
function picker(st) {
  if (!MINE) return null;
  const pool = MINE.songs.filter((x) => (st.key === 'mix' || x.lanes.includes(st.key)) && x.due <= nowS());
  if (!pool.length) return null;
  const lw = st.key === 'mix' ? laneWeights() : null, sum = lw ? Object.values(lw).reduce((a, b) => a + b, 0) || 1 : 1;
  const target = (hourWant() - 2.5) * 0.8, now = nowS();
  const score = (x) => {
    let w = x.want * (x.last ? 0.7 + 0.3 * Math.min(1, (now - x.last) / (30 * 86400)) : 1);
    if (typeof x.en === 'number') w *= 0.6 + 0.4 * Math.exp(-((x.en - target) ** 2) / 2);
    if (lw) w *= Math.sqrt((((lw[x.lanes[0]] || 0) / sum) + 0.02) * 8);   // stations liked most lately come round more
    return Math.max(0.01, w);
  };
  const rnd = seeded(`${S.edition?.id}|${st.key}|${new Date().toDateString()}`);
  const order = pool.map((x) => [rnd() ** (1 / score(x)), x]).sort((a, b) => b[0] - a[0]).map((y) => y[1]);
  return { order, taken: new Set() };
}

function famTrack(x, key) {
  return { vid: x.vid, title: x.title, artists: x.artists, album: x.album, dur: x.dur, type: x.type, thumb: x.thumb, v: x.v, en: x.en,
    at: x.at, real: x.real, last: x.last, n30: x.n30, kind: x.again ? 'again' : 'fav', from: key === 'mix' ? x.lanes[0] || null : key };
}
// The next like for a queue: `prefer` (the like a new song was found from) when it is free, else the first free one,
// or, while the listener is steering (quieter, a song kept or skipped), the best of the next few for that.
function take(q, prefer) {
  const pk = q.pk, free = (x) => x && !pk.taken.has(x.vid) && !famHeard.has(x.vid) && !q.played.has(x.vid);
  let x = null;
  if (prefer) {
    x = pk.order.find((y) => y.vid === prefer) || MINE.by.get(prefer);
    if (!free(x) || x.due > nowS()) return null;
  } else {
    const next = [];
    for (const y of pk.order) { if (free(y)) next.push(y); if (next.length >= 6) break; }
    if (!next.length) return null;
    const sess = q.sess;
    x = sess && (sess.steer || sess.pos.length || sess.neg.length) ? next.reduce((a, b) => (sessScore(b, sess) > sessScore(a, sess) ? b : a)) : next[0];
  }
  pk.taken.add(x.vid);
  return famTrack(x, q.key);
}
function sessScore(c, sess) {
  const v = vec(c);
  let sc = 3 * Math.max(0, near(v, sess.pos) - NEAR) - 4 * Math.max(0, near(v, sess.neg) - NEAR);
  if (sess.steer && typeof c.en === 'number') sc += 0.55 * sess.steer * clamp(c.en, -2.5, 2.5);
  return sc;
}

// Lay the likes in between the new songs still to come (`news`, by default the ones already there): `gap` of them
// before each new song, the last of which is the like it was found from, so the two are heard back to back. A station
// opens on one like, the first new song's. Likes already planned go back in the pool first, so laying them again
// after a change keeps the same songs where it can.
function weave(q, { news, from = q.i + 1 } = {}) {
  const head = q.tracks.slice(0, from), tail = q.tracks.slice(from);
  if (q.pk) for (const p of tail) if (p.kind) q.pk.taken.delete(p.vid);
  news ||= tail.filter((p) => !p.kind);
  if (!q.pk || !q.gap) { q.tracks = [...head, ...news]; return; }
  let since = from ? 0 : q.gap - 1, trail = 0;
  for (let j = head.length - 1; j >= 0 && head[j].kind; j--) since++;
  for (let j = tail.length - 1; j >= 0 && tail[j].kind; j--) trail++;   // a station out of new songs goes on with likes
  const out = [];
  for (const n of news) {
    const need = Math.max(0, q.gap - since);
    const br = need && n.because?.vid ? take(q, n.because.vid) : null;
    for (let k = 0; k < need - (br ? 1 : 0); k++) { const f = take(q); if (f) out.push(f); }
    if (br) { br.bridge = n.because.how === 'near' ? 'near' : 'from'; out.push(br); }
    out.push(n);
    since = 0;
  }
  for (let k = 0; k < trail; k++) { const f = take(q); if (f) out.push(f); }
  q.tracks = [...head, ...out];
}
// A woven station's likes, drawn once it has both a queue and the likes (they may arrive after the queue).
function blendQueue(q, from) {
  if (!woven(q.st) || q.pk || !MINE) return;
  q.pk = picker(q.st);
  q.base = q.gap = q.pk ? BLEND[blendOf(q.key)] : 0;
  weave(q, { from });
}
// A new song heard through or loved brings the next one a song sooner; one skipped early pushes it back. Within one
// of the listener's setting below and two above, and back to it on the next visit.
function blendShift(p, d) {
  if (!Q?.pk || !Q.base || p.kind || p.mine) return;
  const g = clamp(Q.gap + d, Math.max(1, Q.base - 1), Q.base + 2);
  if (g === Q.gap) return;
  Q.gap = g;
  weave(Q);
  renderQueue();
  Lyr.prefetch();
}
function setBlend(v) {
  if (!Q?.pk || !(v in BLEND)) return;
  store.set(acct('blend'), { ...(store.get(acct('blend')) || {}), [Q.key]: v });
  Q.base = Q.gap = BLEND[v];
  weave(Q);
  sessionOf(Q).note = BLEND_NOTE()[v];
  renderQueue();
  Lyr.prefetch();
}
// What the page says with one of the listener's own likes: when they liked it, and how it has been heard lately.
function mineLine(p) {
  const [y, m] = (p.at || '').split('-').map(Number);
  const out = [];
  out.push(!y ? t('你收藏的歌') : (p.real || y === new Date().getFullYear()) && m ? t('你 {when}收藏的', { when: new Date(y, m - 1).toLocaleDateString(LANG, { year: 'numeric', month: 'long' }) }) : t('你 {y} 年前后收藏的', { y }));
  if (p.n30 >= 2) out.push(t('近 30 天听完 {n} 次', { n: p.n30 }));
  else if (p.last && nowS() - p.last > 30 * 86400) out.push(t('上次听是 {when}', { when: new Date(p.last * 1000).toLocaleDateString(LANG, { year: 'numeric', month: 'long' }) }));
  return out.join(t('，'));
}

function stHTML(s) {
  const imgs = s.tracks.slice(0, s.tracks.length >= 4 ? 4 : 1).map((p) => imgTag(p, 120)).join('');
  return `<button class="st ${s.pending ? 'pending' : ''}" data-st="${esc(s.key)}" ${Q?.key === s.key ? 'aria-current="true"' : ''} title="${esc(s.when || '')}">
    <span class="mosaic ${s.pending ? 'wait' : ''} ${s.tracks.length < 4 ? 'one' : ''}">${s.pending ? '' : imgs}</span>
    <span class="txt"><span class="nm">${esc(s.name)}${s.fresh ? `<i class="new" title="${t('今天换了新歌')}"></i>` : ''}</span><span class="sb">${esc(s.sub)}</span></span><span class="eqs"><i></i><i></i><i></i></span></button>`;
}

// a station they asked for can go again: × beside it on a wide screen, the station menu everywhere
function askHTML(s) {
  return `<div class="st-w">${stHTML(s)}<button class="st-x" data-k="unask" data-c="${esc(s.key.slice(4))}" title="${t('删掉这个点歌')}" aria-label="${t('删掉这个点歌')}">${I.close}</button></div>`;
}
let unaskArmed = 0;
async function unask(created) {
  // clearing them all takes a second click within a few seconds
  if (created === null && Date.now() - unaskArmed > 4000) { unaskArmed = Date.now(); toast(t('再点一次，清空你点的')); return; }
  try {
    const r = await api('/api/ask/delete', { created });
    S.asks = r.asks;
    buildStations();
    renderStations();
  } catch (e) { toast(e.message); }
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
  if (me.status === 'thin') return `<div class="prep"><b>${t('还不够认识你')}</b><p>${me.netease ? t('你的{app}喜欢里，YouTube Music 上找得到 {n} 首，要 20 首才分得出你的口味。先听「先听着」；在{app}多点几首喜欢，知音每 6 小时会再看一次，够了就自己开始。', { n: me.last_sync?.songs ?? 0, app: appShort(me.netease.app) }) : t('你在 YouTube 点过 {n} 首歌的喜欢，要 20 首才分得出你的口味。先听「先听着」；在 YouTube Music 多点几首喜欢，知音每 6 小时会再看一次，够了就自己开始。', { n: me.last_sync?.songs ?? 0 })}</p><button class="tb" data-k="setup">${t('现在就看一次')}</button></div>`;
  if (me.status === 'error' && me.setup_issue === 'nochannel') return `<div class="prep"><b>${t('这个 Google 账号还没有 YouTube 频道')}</b><p>${t('没有频道，YouTube 不让别的应用读你点过的喜欢。建一个频道只要一分钟，不用发视频；建好回来点「再试一次」。')}</p><div class="prep-acts"><a class="tb" href="https://www.youtube.com/create_channel" target="_blank" rel="noopener">${t('去建频道')}</a><button class="tb" data-k="setup">${t('再试一次')}</button></div></div>`;
  if (me.status === 'error') return `<div class="prep"><b>${t('准备电台时出了问题')}</b><p>${esc((S.jobs?.setup?.error || '').slice(0, 80))}</p><button class="tb" data-k="setup">${t('再试一次')}</button></div>`;
  return '';
}

function renderStations() {
  const asks = ST.filter((s) => s.group === 'ask'), lanes = ST.filter((s) => s.group === 'lane'), warm = ST.filter((s) => s.group === 'warm');
  const busy = S.jobs?.refresh?.running;
  const label = SAMPLE() ? t('示例听众的电台') : busy ? t('正在挑新的一批…') : S.edition ? t('电台 · {when} 更新', { when: when(S.edition.created) }) : '';
  renderMe();
  if (!ready() || !lanes.length) {
    $('#stations').innerHTML = `${prepHTML()}${warm.length ? `<div class="st-h"><span>${t('先听着')}</span></div>` : ''}${warm.map(stHTML).join('')}${lanes.map(stHTML).join('')}`;
    return;
  }
  $('#stations').innerHTML = `${prepHTML()}
    ${asks.length ? `<div class="st-h"><span>${t('你点的')}</span><button data-k="unaskall" title="${t('清空你点的')}" aria-label="${t('清空你点的')}">${I.close}</button></div>${asks.map(askHTML).join('')}` : ''}
    <div class="st-h"><span>${label}</span>${SAMPLE() ? '' : `<button class="${busy ? 'busy' : ''}" data-k="refresh" title="${t('现在重新挑一批')}" ${busy ? 'disabled' : ''}>${I.refresh}</button>`}</div>
    ${lanes.map(stHTML).join('')}
    ${warm.length ? `<div class="st-h"><span>${t('先听着')}</span></div>${warm.map(stHTML).join('')}` : ''}`;
}

// Songs heard in this edition from any station. The first station shares its songs with the others, so one heard
// there doesn't come round again in its own station (and the other way round).
function heard() {
  const h = store.get(acct('heard'));
  return new Set(h?.ed === S.edition?.id ? h.vids : []);
}
function markHeard(vid) {
  const h = heard();
  if (!S.edition || h.has(vid)) return;
  h.add(vid);
  store.set(acct('heard'), { ed: S.edition.id, vids: [...h] });
}

function queueOf(st) {
  const id = `${S.edition?.id}|${st.key}`;
  const h = st.group === 'lane' ? heard() : new Set();
  let q = queues.get(id);
  if (!q) {
    const tracks = st.tracks.filter((p) => fb.get(p.vid) !== 'dislike');
    const fresh = tracks.filter((p) => !h.has(p.vid));
    q = { key: st.key, st, tracks: fresh.length ? fresh : tracks, reserve: (st.reserve || []).filter((p) => !h.has(p.vid)), i: 0, played: new Set() };
    blendQueue(q, 0);
    queues.set(id, q);
  } else if (h.size || famHeard.size) {
    // (songs heard in another station since: a new one is never recommended again, a like waits for the next visit)
    const ahead = q.tracks.slice(q.i + 1).filter((p) => !(p.kind ? famHeard : h).has(p.vid) || q.played.has(p.vid));
    q.tracks = [...q.tracks.slice(0, q.i + 1), ...ahead];
    weave(q);
  }
  q.st = st;
  blendQueue(q);
  return q;
}

function selectStation(key, play = true) {
  const st = ST.find((s) => s.key === key);
  if (!st || st.pending || !st.tracks.length) return;
  const same = Q?.key === key;
  if (!same) { leaving(); startSrc = st.group === 'ask' ? 'ask' : 'station'; }
  Q = queueOf(st);
  store.set(acct('last'), key);
  if (st.fresh && S.edition) {
    st.fresh = false;
    store.set(acct('seen'), { [S.edition.id]: { ...(store.get(acct('seen')) || {})[S.edition.id], [key]: 1 } });
    renderStations();
  }
  if (view !== 'listen') { location.hash = ''; return loadTrack(play); }
  renderStations();
  renderQueue();
  if (!same || play) loadTrack(play);
}

// The energy a visit starts at: something quiet late at night, something with a pulse by day.
function hourWant() {
  const h = new Date().getHours();
  return h >= 22 || h < 5 ? 1.5 : h >= 19 ? 2.5 : h < 11 ? 2 : 3.5;
}
// A visit starts on the first station, whose first song fits the hour; without it, on the station that fits best.
function defaultStation() {
  const mix = ST.find((x) => x.key === 'mix' && x.tracks.length);
  if (mix) return mix;
  const want = hourWant();
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
  placeCard();
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

// Every listen is logged twice: when it starts, with who chose the song and what the page showed with it, and once
// when it ends, however it ends (the next song, another station, a song picked from the list, the page closing).
// What the listens say about taste is worked out on the server (signals.py); a check run by the operator is marked
// so it stays out of every count.
const TEST = (() => { try { return !!navigator.webdriver || localStorage.getItem('zhiyin-test') === '1'; } catch { return false; } })();
let startSrc = 'station';   // who chose the next song to start: see Play.src on the server
let L = null;               // the listen in progress: { p, ended }
let touched = performance.now();
for (const e of ['pointerdown', 'keydown']) addEventListener(e, () => { touched = performance.now(); }, { capture: true, passive: true });

function logPlay(p, ev, pos = 0, extra = {}, send = api) {
  if (p && !['start', 'away', 'replay', 'stop'].includes(ev) && Q?.key !== 'ear' && !p.mine && !p.kind) markHeard(p.vid);
  if (!p || SAMPLE()) return;
  const r = send('/api/play', { vid: p.vid, lane: p.from || Q?.key, ev, pos: Math.round(pos), title: p.title, artist: p.artists?.[0]?.name, test: TEST, ...extra });
  r?.catch?.(() => {});
}
function startListen(p) {
  const shown = p.kind ? { kind: p.kind } : p.mine || Q?.key === 'ear' ? {} : {
    fit: typeof p.fit === 'number' ? p.fit : null, slot: Number.isInteger(p.slot) ? p.slot : null,
    fam: p.familiar == null ? null : p.familiar ? 1 : p.knows ? 2 : 0, probe: p.probe || null };
  L = { p, ended: false };
  if (p.kind) famHeard.add(p.vid);
  logPlay(p, 'start', 0, { src: p.mine ? 'compare' : startSrc, dur: Player.time()[1] || p.dur || null, vis: document.visibilityState, ...shown });
  startSrc = 'auto';
}
function endListen(ev, send = api) {
  if (!L || L.ended) return;
  const [t, d] = Player.time();
  L.ended = true;
  logPlay(L.p, ev, ev === 'done' ? d : t, { dur: d || null, idle: Math.round((performance.now() - touched) / 1000), vis: document.visibilityState }, send);
}

// A song left after the first half minute (or half of a short one) was heard: it is never recommended again. One
// left before then with Next is a skip; left that early any other way (another station, a song from the list, a
// comparison, the page closing) it is only stopped, and stays new.
const heardAt = (d) => Math.min(30, (d || 60) / 2);
function leaving(send = api, skip = false) {
  const [t, d] = Player.time();
  if (L && !L.ended) endListen(t >= heardAt(d) ? 'left' : skip ? 'skip' : 'stop', send);
}

async function next(play = true, by = 'next') {
  if (!Q) return;
  const p = cur();
  if (p) {
    Q.played.add(p.vid);
    const [t, d] = Player.time();
    // Leaving within the first half is the strongest "not now" signal a listener gives without saying anything.
    // (one of your own likes, played to compare with a pick or between new songs, says nothing about the station when
    // you leave it: the server rests it a fortnight)
    if (Player.playing && t < heardAt(d) && !p.mine && !p.kind) { blendShift(p, 1); adapt('neg', p); }
    leaving(api, by === 'next');
  }
  if (Q.i >= Q.tracks.length - 1) await extend(true);
  if (Q.i < Q.tracks.length - 1) { Q.i++; startSrc = by; loadTrack(play); }
}
function prev() {
  if (!Q) return;
  if (Player.time()[0] > 4 || Q.i === 0) {
    if (Player.time()[0] > 4 && L && !L.ended && L.p.vid === cur()?.vid) logPlay(L.p, 'replay', Player.time()[0]);
    return Player.seekTo(0);
  }
  leaving();
  Q.i--;
  startSrc = 'prev';
  loadTrack(true);
}

async function extend(silent) {
  if (!Q) return;
  const n = Q.tracks.length;
  let failed = false;
  if (Q.reserve.length) Q.tracks.push(...Q.reserve.splice(0, Q.gap ? 2 : 4).filter((p) => fb.get(p.vid) !== 'dislike'));
  else {
    const seed = cur() || Q.tracks[Q.tracks.length - 1];
    if (!seed) return;
    try {
      const r = await api(`/api/more?vid=${seed.vid}&exclude=${Q.tracks.map((p) => p.vid).join(',')}`);
      Q.tracks.push(...r.tracks.slice(0, 8));
    } catch { failed = true; }
  }
  weave(Q);
  if (Q.tracks.length === n && Q.gap) for (let k = 0; k < 4; k++) { const f = take(Q); if (f) Q.tracks.push(f); }
  renderQueue();
  if (Q.tracks.length === n && !silent) toast(failed ? t('没取到更多的歌，稍后再试') : t('这条线暂时没有更多了'));
}

async function continueFrom(btn) {
  const p = cur();
  if (!p) return;
  btn && (btn.disabled = true);
  try {
    const r = await api(`/api/more?vid=${p.vid}&exclude=${Q.tracks.map((x) => x.vid).join(',')}`);
    const add = r.tracks.slice(0, 8);
    Q.tracks.splice(Q.i + 1, 0, ...add);
    weave(Q);
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
  const upcoming = Q.tracks.slice(Q.i + 1).filter((c) => !c.kind);
  if (!upcoming.length && !Q.reserve.length) return;
  const score = (c, k, inReserve) => {
    const v = vec(c);
    let sc = inReserve ? -0.45 - 0.02 * k : -0.04 * k;
    sc += 3 * Math.max(0, near(v, s.pos) - NEAR) - 4 * Math.max(0, near(v, s.neg) - NEAR);
    if (s.steer && typeof c.en === 'number') sc += 0.55 * s.steer * clamp(c.en, -2.5, 2.5);
    if (s.fresh) sc += c.familiar || c.knows ? -0.5 : 0.35;
    return sc;
  };
  const pool = [...upcoming.map((c, k) => [c, score(c, k, false)]), ...Q.reserve.map((c, k) => [c, score(c, k, true)])];
  pool.sort((a, b) => b[1] - a[1]);
  const n = Math.max(upcoming.length, Math.min(6, pool.length));
  const keep = pool.slice(0, n).map((x) => x[0]);
  const same = keep.map((c) => c.vid).join() === upcoming.map((c) => c.vid).join();
  Q.reserve = pool.slice(n).map((x) => x[0]);
  if (same && !(Q.pk && !event)) return;   // (a switch flipped still changes which likes come round)
  weave(Q, { news: keep });
  renderQueue();
  Lyr.prefetch();
  if (event && p && !same) s.note = event === 'neg' ? t('少放和〈{s}〉相近的', { s: p.title }) : t('多放和〈{s}〉相近的', { s: p.title });
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
  const bl = $('#qBlend');
  if (bl) {
    bl.hidden = !Q?.pk;
    for (const b of $$('button', bl)) { const on = !!Q?.pk && BLEND[b.dataset.v] === Q.base; b.classList.toggle('on', on); b.setAttribute('aria-checked', on); }
  }
  const w = $('#qWhen'), n = $('#sNote');
  if (w && Q) w.textContent = Q.st.when || '';
  if (n) n.textContent = s.note || '';
  const g = $('#qWent');
  if (g) {
    const v = wentOf(Q), note = laneOf(Q)?.note;
    // each count stays whole when the line wraps on a phone
    g.innerHTML = v.length ? `<span>${esc(t('下一期会参考：{x}', { x: v[0] }))}</span>${v.slice(1).map((x) => ` · <span>${esc(x)}</span>`).join('')}` : '';
    g.title = v.length ? t('挑下一期时，编辑会看到你对这条电台每首歌的反应') : '';
    $('#qNote').textContent = note ? t('你说过「{x}」', { x: note }) : '';
    $('#qNote').title = note || '';
  }
}

// What this station's next editor will read about how its songs went (quality.by_lane), so a reaction visibly counts.
function wentOf(q) {
  if (!q || SAMPLE()) return [];
  const lanes = q.key === 'mix' ? Object.values(S.went || {}) : [S.went?.[q.key]].filter(Boolean);
  const n = lanes.reduce((a, c) => ({ like: a.like + c.like, good: a.good + c.good, early: a.early + c.early, nope: a.nope + c.nope }),
    { like: 0, good: 0, early: 0, nope: 0 });
  return [n.like && `♥ ${n.like}`, n.good && t('听完 {n}', { n: n.good }), n.early && t('秒切 {n}', { n: n.early }),
    n.nope && t('不要 {n}', { n: n.nope })].filter(Boolean);
}

/* ---------- player: one YouTube player ---------- */
// YouTube allows one playing player per page, with nothing drawn over it, so songs don't overlap: the last seconds
// of a song fall away, the song ends, and the next one starts.
const FADE = 2.5;   // seconds a song fades out over at a natural ending

const Player = {
  yt: null, ready: false, vid: null, want: null, cued: false, playing: false, shown: false, used: false, logged: null, timer: null, ramp: 0, ending: false,
  rest: true,   // paused by the listener, or nothing started yet (not the moment between two songs)
  clock: { raw: -1, at: 0 },
  init() {
    window.onYouTubeIframeAPIReady = () => {
      this.yt = new YT.Player('ytA', {
        width: '100%', height: '100%',
        playerVars: { autoplay: 0, controls: 0, disablekb: 1, fs: 0, iv_load_policy: 3, playsinline: 1, rel: 0, origin: location.origin },
        events: {
          onReady: () => {
            this.ready = true;
            if (this.want) { const w = this.want; this.want = null; this.load(w.p, w.play); }
          },
          onStateChange: (e) => this.onState(e.data),
          onError: (e) => this.onError(e.data),
        },
      });
    };
    const s = document.createElement('script');
    s.src = 'https://www.youtube.com/iframe_api';
    s.onerror = () => this.unreachable();
    document.head.append(s);
    // where YouTube is blocked the request just hangs, so silence counts as an answer too
    setTimeout(() => { if (!window.YT?.Player) this.unreachable(); }, 8000);
  },
  down: false,
  unreachable() {
    if (this.down || this.ready) return;
    this.down = true;
    ev('yt_down');
    noYouTube();
  },
  fadeTo(vol, ms, then) {
    clearInterval(this.ramp);
    const from = this.yt.getVolume?.() ?? 100, t0 = performance.now();
    this.ramp = setInterval(() => {
      const x = clamp((performance.now() - t0) / ms);
      this.yt.setVolume(Math.round(from + (vol - from) * x));
      if (x >= 1) { clearInterval(this.ramp); then?.(); }
    }, 30);
  },
  // back to full volume: a seek, pause or skip during the closing fade keeps the song audible
  steady() { clearInterval(this.ramp); this.ending = false; if (this.ready) this.yt.setVolume(100); },
  start(vid, play) {
    this.steady();
    this.vid = vid;
    this.cued = !play;
    this.yt.unMute();
    play ? this.yt.loadVideoById(vid) : this.yt.cueVideoById(vid);
  },
  // the rail's YouTube window opens with the first song played, and is in place before that song starts
  use() { if (!this.used) { this.used = true; placeCard(); placeHost(); } },
  load(p, play) {
    this.settle(!play);
    if (play) this.use();
    if (!this.ready) { this.want = { p, play }; if (play && this.down) noYouTube(); return; }
    // a skip lets the old song drop away for a moment instead of cutting it mid-note
    if (play && this.playing && this.vid !== p.vid) this.fadeTo(0, 180, () => this.start(p.vid, true));
    else this.start(p.vid, play);
  },
  closing(t, d) {
    if (this.ending || !this.playing || d <= 60 || d - t > FADE) return;
    this.ending = true;
    this.fadeTo(0, Math.max(400, (d - t) * 1000));
  },
  onError(code) {
    this.steady();
    // (one of their own likes between the new songs is passed over without a word, and not woven in again)
    if (cur()?.kind) famHeard.add(cur().vid);
    else toast(t('〈{s}〉不允许在网页里播放，已跳过', { s: cur()?.title || '' }));
    // gone, private, or not allowed in other sites: it never will play here, so it isn't recommended again
    if ([100, 101, 150].includes(code)) logPlay(cur(), 'error', 0, { src: startSrc });
    setTimeout(() => next(!this.cued, 'auto'), 400);   // a song only loaded, not started, is replaced by one only loaded
  },
  onState(s) {
    if (this.playing && s !== 1 && s !== 3) this.stopped = performance.now();
    this.playing = s === 1 || s === 3;
    // YouTube's player shows from the moment a song plays until it stops; paused, cued or between songs, the frame shows
    // the song's own cover instead of YouTube's thumbnail, title bar and play button
    if (s === 1) { this.shown = true; this.cued = false; this.use(); }   // a seek also starts a cued song, so any start opens the window
    else if (s !== 3) this.shown = false;
    if (s === 1) this.settle(false);
    // a pause from the headphones or the lock screen; YouTube also reports one for a moment when it changes songs
    if (s === 2) setTimeout(() => { if (this.yt.getPlayerState?.() === 2) this.settle(true); }, 400);
    placeHost();
    document.body.classList.toggle('playing', this.playing);
    Pip.w?.document.body.classList.toggle('playing', this.playing);
    MS.state(this.playing);
    clearInterval(this.timer);
    if (this.playing) this.timer = setInterval(tick, 250);
    tick();
    Lyr.run();
    const p = cur();
    if (s === 1 && p && (this.logged !== p.vid || (L?.ended && L.p.vid === p.vid))) {   // (or the same song again)
      if (SAMPLE() && !this.logged) ev('sample_play');
      this.logged = p.vid; startListen(p); Lyr.prefetch();
    }
    if (s === 0 && p) {
      endListen('done');
      Q.played.add(p.vid);
      // only after the next song is fixed, or the queue could move under it
      next(true, 'auto').then(() => { if (!p.kind) { blendShift(p, -1); adapt('pos', p); } });
    }
  },
  toggle() {
    if (!cur()) return;
    MS.arm();
    if (!this.playing) this.use();
    this.settle(this.playing);   // at the tap, so the card is open by the time the song sounds
    if (!this.ready) { this.want = { p: cur(), play: true }; return; }
    this.steady();
    this.playing ? this.yt.pauseVideo() : this.yt.playVideo();
  },
  settle(rest) { if (this.rest !== rest) { this.rest = rest; restCard(); } },
  play() { if (!this.playing) this.toggle(); },
  pause() { if (this.ready && this.playing) { this.steady(); this.yt.pauseVideo(); } },
  seekTo(sec) { if (!this.ready) return; this.steady(); this.yt.seekTo(Math.max(0, sec), true); this.clock.raw = -1; },
  seek(frac) { const d = this.time()[1]; if (d) this.seekTo(d * frac); },
  time() {
    if (!this.ready) return [0, cur()?.dur || 0];
    return [this.yt.getCurrentTime?.() || 0, this.yt.getDuration?.() || cur()?.dur || 0];
  },
  // YouTube reports the position in coarse steps; extrapolate between them so lyrics can move with the voice.
  now() {
    const [t] = this.time();
    const c = this.clock, n = performance.now();
    if (t !== c.raw) { c.raw = t; c.at = n; }
    return this.playing ? Math.min(c.raw + (n - c.at) / 1000, c.raw + 1) : c.raw;
  },
};

// YouTube's developer policies (III.I.9) forbid playing from a player nobody can see, and phones pause it when the
// page goes to the background. Coming back, one tap carries on from where it stopped.
let awayPlaying = false;
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    awayPlaying = Player.playing || performance.now() - (Player.stopped || -1e9) < 1500;
    if (L && !L.ended) logPlay(L.p, 'away', Player.time()[0], { dur: Player.time()[1] || null, vis: 'hidden' }, beacon);
    return;
  }
  if (awayPlaying && !Player.playing && cur()) toast(t('离开页面时，YouTube 会暂停播放'), [[t('接着放'), () => Player.play()]], 8000);
  awayPlaying = false;
});

addEventListener('pagehide', () => leaving(beacon));

function tick() {
  const [t, d] = Player.time();
  const f = d ? Math.min(1, t / d) : 0;
  $$('.bar').forEach((b) => b.style.setProperty('--p', f));
  Pip.w && $$('.bar', Pip.w.document).forEach((b) => b.style.setProperty('--p', f));
  const c = $('#tCur'), e = $('#tDur');
  if (c) c.textContent = fmt(t);
  if (e) e.textContent = fmt(d);
  Player.closing(t, d);
  if (Player.playing && d - t < 20 && Q && Q.i >= Q.tracks.length - 1 && !extend.busy) {
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
// When the voice reaches a new line the sheet jumps there at once, and every line on screen is drawn back from where it
// was on a spring, each a little after the one above, so the sheet ripples into place instead of sliding as one block.
const SPRING = (() => {
  const k = 120, c = 19, w0 = Math.sqrt(k), z = c / (2 * w0), wd = w0 * Math.sqrt(1 - z * z), T = 0.9;   // stiffness, damping (mass 1)
  const x = (s) => 1 - Math.exp(-z * w0 * s) * (Math.cos(wd * s) + ((z * w0) / wd) * Math.sin(wd * s));
  const pts = Array.from({ length: 31 }, (_, i) => (i === 30 ? 1 : +x((i / 30) * T).toFixed(4)));
  return { ms: T * 1000, easing: CSS.supports('animation-timing-function', 'linear(0, 1)') ? `linear(${pts.join(', ')})` : 'cubic-bezier(.23, 1, .32, 1)' };
})();
const HOLD_S = 1;   // a word sung this long or longer lifts a little as it fills
// Words timed apart but written together ("bed" + ", hmm") stay on one line: a held word is an inline block, which
// would otherwise let the line break between them. Chinese, Japanese and Korean break between any two characters.
const CJK = /[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Hangul}]/u;
const glued = (a, b) => /\S$/.test(a) && /^\S/.test(b) && !CJK.test(a.at(-1)) && !CJK.test(b[0]);
// In the stage view a word's size follows how long it is sung: up to 1.28 times for two seconds or more.
const wordSize = (dur) => +(1 + 0.28 * clamp((dur - 0.5) / 1.5)).toFixed(2);

// Before the first words, in immersive: why this song is here, said from the listener's own data where it can be.
function introHTML(p) {
  const main = p && reasonOf(p);
  if (!main) return '';
  const sub = becauseParts(p).map(([s]) => s).join(' · ');
  return `<span class="intro-c"><span class="i-main">${esc(main)}</span>${sub ? `<span class="i-sub">${esc(sub)}</span>` : ''}</span>`;
}

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
    // before the first words: why the song is here (immersive) or three dots counting in (the panel)
    if (d.lines[0]?.t > 4) lines.push({ t: 0, x: '', gap: true, intro: true });
    for (const l of d.lines) lines.push({ ...l, gap: !l.x });
    lines.forEach((l, i) => { l.end = lines[i + 1]?.t ?? (l.e || l.t + 6); });
    return { ...d, lines };
  },
  html() {
    const d = this.data;
    if (!d) return '';
    const by = [d.source && t('歌词来自{src}', { src: /^[A-Za-z]/.test(d.source) && LANG !== 'en' ? ` ${d.source}` : d.source }), d.tr_by === 'AI' && d.translated && t('翻译由 AI 生成')].filter(Boolean).join(' · ');
    const intro = introHTML(cur());
    return `<div class="ly-scroll"><div class="ly-in ${this.tr ? 'tr-on' : ''} ${this.ro ? 'ro-on' : ''}">${d.lines.map((l, i) => {
      if (l.gap) return `<p class="ll gap ${l.intro && intro ? 'intro' : ''}" data-i="${i}"><span class="dots"><i></i><i></i><i></i></span>${l.intro ? intro : ''}</p>`;
      let main = esc(l.x);
      if (l.w) {
        const runs = [];
        l.w.forEach((w, j) => {
          const z = wordSize(w[1]);
          const span = `<span class="wd${w[1] >= HOLD_S ? ' hold' : ''}"${z > 1 ? ` style="--z:${z}"` : ''}>${esc(w[2])}</span>`;
          j && glued(l.w[j - 1][2], w[2]) ? runs.at(-1).push(span) : runs.push([span]);
        });
        main = runs.map((r) => (r.length > 1 ? `<span class="nb">${r.join('')}</span>` : r[0])).join('');
      }
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
      // reading ahead by hand: the sheet stops following and every line comes into focus until the hand rests
      const stop = () => {
        this.hold = performance.now() + 3500;
        el.classList.add('browse');
        clearTimeout(this.browseT);
        this.browseT = setTimeout(() => { el.classList.remove('browse'); this.sync(true, false); }, 3500);
      };
      sc.addEventListener('wheel', stop, { passive: true });
      sc.addEventListener('touchmove', stop, { passive: true });
    }
    this.lastF = [];
    this.paintPip(true);
  },
  hosts() { return $$('.lyr'); },
  visible() { return !!this.data && (Pip.w || !!$('.room.lyr-on')); },
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
  sync(force, snap = force) {
    if (!this.data) return;
    const t = Player.now() - this.delay + 0.1;
    const k = this.at(t), L = this.data.lines;
    if (k !== this.idx || force) {
      for (const host of this.hosts()) {
        const lines = $$('.ll', host);
        lines.forEach((el, i) => {
          el.classList.toggle('on', i === k);
          el.classList.toggle('prev', i === k - 1);
          el.style.setProperty('--d', Math.min(6, Math.abs(i - k)));
        });
        this.follow(host, lines[k], snap);
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
  follow(host, el, snap) {
    const sc = $('.ly-scroll', host);
    if (!sc || !el || host.classList.contains('one') || performance.now() < this.hold) return;
    // a third of the way down; one too tall for that (a long intro on a short phone) starts where the fade ends
    const at = Math.min(el.offsetTop - sc.clientHeight * 0.36 + el.offsetHeight / 2, el.offsetTop - sc.clientHeight * 0.14);
    const top = Math.round(clamp(at, 0, sc.scrollHeight - sc.clientHeight));
    const dy = top - sc.scrollTop;
    if (Math.abs(dy) < 1) return;
    sc.scrollTop = top;
    if (snap || document.hidden || REDUCED.matches || Math.abs(dy) > sc.clientHeight) return;   // a seek lands at once
    const k = +el.dataset.i;
    for (const line of $$('.ll', host)) {
      const y = line.offsetTop - top;
      if (y + line.offsetHeight < Math.min(0, -dy) - 40 || y > sc.clientHeight + Math.max(0, -dy) + 40) continue;
      let from = dy;
      const running = line.getAnimations();
      if (running.length) {   // still settling from the last line: go on from where it is
        from += new DOMMatrixReadOnly(getComputedStyle(line).transform).m42;
        running.forEach((a) => a.cancel());
      }
      line.animate([{ transform: `translateY(${from}px)` }, { transform: 'translateY(0)' }],
        { duration: SPRING.ms, easing: SPRING.easing, delay: clamp(+line.dataset.i - k + 1, 0, 8) * 40, fill: 'backwards' });
    }
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

/* ---------- the room: lyrics or the programme beside the song ---------- */
function layoutStage() {
  const room = $('.room');
  if (!room) return;
  const has = !!Lyr.data;
  const on = has && (prefs.imm || (PHONE.matches ? prefs.lyrNarrow : prefs.lyr));
  room.classList.toggle('lyr-on', on);
  room.classList.toggle('no-lyr', !has);
  const why = has ? t('歌词（G）') : t('这首没有找到歌词');
  $$('[data-k="tab-lyr"]').forEach((b) => { b.setAttribute('aria-selected', on); b.toggleAttribute('aria-disabled', !has); b.title = why; });
  $$('[data-k="tab-q"]').forEach((b) => b.setAttribute('aria-selected', !on));
  $$('[data-k="lyrics"]').forEach((b) => { b.classList.toggle('on', on); b.toggleAttribute('aria-disabled', !has); b.title = why; });
  // Immersive on a wide screen can give the words the whole room, YouTube's player in a corner. A song timed word by
  // word is then shown a line at a time, each word as it is sung.
  const stage = on && prefs.imm && prefs.stage && !PHONE.matches;
  document.body.classList.toggle('stage', stage);
  $$('.lyr').forEach((h) => h.classList.toggle('one', stage && !!Lyr.data?.lines.some((l) => l.w)));
  room.classList.toggle('has-intro', !!(Lyr.data?.lines[0]?.intro && introHTML(cur())));
  $$('[data-k="stage"]').forEach((b) => {
    b.classList.toggle('on', prefs.stage);
    b.toggleAttribute('aria-disabled', !has);
    b.title = has ? (prefs.stage ? t('封面和歌词（S）') : t('只看歌词（S）')) : why;
  });
  // A phone scrolls the page under the station strip and the tab bar: size the cover so play is on the first screen.
  // From the smallest height the screen has (toolbar showing), not the current one, or the cover grows and pushes
  // the page down when the toolbar folds away mid-scroll.
  const fr = $('.frame', room), meta = $('.meta', room);
  if (PHONE.matches && fr && meta) {
    const used = $('#tabs').offsetHeight + (fr.getBoundingClientRect().top + scrollY) + meta.offsetHeight + 32;
    room.style.setProperty('--fit', `max(120px, calc(100svh - ${Math.round(used)}px))`);
  } else room.style.removeProperty('--fit');
  placeHost();
  if (on) { Lyr.sync(true); Lyr.run(); }
}
function toggleLyrics(want) {
  const room = $('.room');
  if (!room || prefs.imm) return;
  if (!Lyr.data) { toast(t('这首没有找到歌词')); return; }
  const on = want ?? !room.classList.contains('lyr-on');
  if (PHONE.matches) prefs.lyrNarrow = on;
  else { prefs.lyr = on; store.set('lyr', on); }
  layoutStage();
}
function toggleStage() {
  if (!prefs.imm || PHONE.matches) return;
  if (!Lyr.data) { toast(t('这首没有找到歌词')); return; }
  const parts = [$('#frame'), $('#ytHost')], was = parts.map((e) => e?.getBoundingClientRect());
  prefs.stage = !prefs.stage;
  store.set('stage', prefs.stage);
  layoutStage();
  parts.forEach((e, i) => e && flyFrom(e, was[i]));
}
const stageRO = new ResizeObserver(() => layoutStage());
const PHONE = matchMedia('(max-width: 899px)');
PHONE.addEventListener('change', () => { if (view === 'listen') { watchFrame(); placeCard(); placeHost(); } });

/* ---------- immersive: just the song, the cover and the words ---------- */
function immersive(on = !prefs.imm) {
  if (view !== 'listen' || !cur()) return;
  prefs.imm = on;
  document.body.classList.toggle('imm', on);
  $$('[data-k="imm"]').forEach((b) => { b.innerHTML = on ? I.shrink : I.full; b.title = on ? t('退出沉浸（F / Esc）') : t('沉浸（F）'); });
  on ? Flow.start() : Flow.stop();
  wake();
  paintBackdrop();
  placeCard();
  requestAnimationFrame(() => { layoutStage(); placeHost(); });
}
// a resting pointer hides with the controls, entered by key or mouse alike
let idleT = 0;
function wake() {
  document.body.classList.remove('idle');
  clearTimeout(idleT);
  if (prefs.imm) idleT = setTimeout(() => document.body.classList.add('idle'), 2600);
}
addEventListener('mousemove', () => { if (prefs.imm) wake(); });

// The cover lights the room. Two layers crossfade so a new song washes in instead of cutting.
function paintBackdrop() {
  const p = cur(), el = $('#backdrop');
  if (!p || !el) return;
  const u = px(cover(p, 120).replace('maxresdefault', 'mqdefault'));
  Flow.set(u);
  if (el.dataset.u === u) return;
  el.dataset.u = u;
  if ($$('i', el).length < 2) el.insertAdjacentHTML('afterbegin', '<i></i><i></i>');
  const [a, b] = $$('i', el), nx = a.classList.contains('on') ? b : a, old = nx === a ? b : a;
  const img = new Image();
  img.onload = () => {
    if (el.dataset.u !== u) return;
    nx.style.backgroundImage = `url("${u}")`;
    nx.classList.add('on');
    old.classList.remove('on');
  };
  img.src = u;
}

/* ---------- immersive: the cover's colours, slowly flowing ---------- */
// One small WebGL canvas at an eighth of the window, drawn at most 30 times a second and stretched to fill it: the
// cover seen through three slowly turning, warped lenses, so its colours drift around the room (one turn in 30-50 s).
// A new song's cover crossfades in over 700 ms. Reduced motion gets a still frame; without WebGL the blurred cover stays.
const FLOW_FS = `precision mediump float;
varying vec2 uv;
uniform sampler2D a, b;
uniform float mixv, time;
uniform vec2 res;
vec2 rot(vec2 p, float r) { float c = cos(r), s = sin(r); return vec2(c * p.x - s * p.y, s * p.x + c * p.y); }
vec3 paint(sampler2D s, vec2 c, float t) {
  vec3 col = vec3(0.);
  for (int i = 0; i < 3; i++) {
    float f = float(i);
    vec2 q = rot(c, t * (.6 + .25 * f) + f * 2.1) * (.62 + .16 * f);
    q += .16 * vec2(sin(t * (.9 + .3 * f) + f * 1.7), cos(t * (.7 + .2 * f) + f * 2.9));
    q += .07 * vec2(sin(q.y * 5. + t * 1.3), cos(q.x * 4. - t * 1.1));
    col += texture2D(s, q + .5, 2.5).rgb;
  }
  return col / 3.;
}
void main() {
  vec2 c = uv - .5;
  c.x *= res.x / res.y;
  float t = time * .19635;
  vec3 col = mix(paint(a, c, t), paint(b, c, t), mixv);
  float l = dot(col, vec3(.2126, .7152, .0722));
  // bright covers are pressed down harder, so a white sleeve doesn't put a grey cloud behind white words
  col = mix(vec3(l), col, 1.35) * .42 / (1. + max(0., l - .45) * 1.6);
  col *= 1. - .35 * dot(c, c);
  gl_FragColor = vec4(col, 1.);
}`;
const Flow = {
  gl: null, cv: null, u: null, tex: [], front: 0, from: 0, to: 0, mixAt: -1e9, url: '', want: '', raf: 0, last: 0, on: false, t0: performance.now(),
  init() {
    if (this.gl !== null) return !!this.gl;
    this.gl = false;
    const cv = document.createElement('canvas');
    const gl = cv.getContext('webgl', { alpha: false, antialias: false, depth: false, stencil: false, powerPreference: 'low-power' });
    if (!gl) return false;
    const sh = (type, src) => { const x = gl.createShader(type); gl.shaderSource(x, src); gl.compileShader(x); return gl.getShaderParameter(x, gl.COMPILE_STATUS) ? x : null; };
    const vs = sh(gl.VERTEX_SHADER, 'attribute vec2 p; varying vec2 uv; void main() { uv = p * .5 + .5; gl_Position = vec4(p, 0., 1.); }');
    const fs = sh(gl.FRAGMENT_SHADER, FLOW_FS);
    if (!vs || !fs) return false;
    const pr = gl.createProgram();
    gl.attachShader(pr, vs);
    gl.attachShader(pr, fs);
    gl.linkProgram(pr);
    if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) return false;
    gl.useProgram(pr);
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);   // one triangle over the screen
    const at = gl.getAttribLocation(pr, 'p');
    gl.enableVertexAttribArray(at);
    gl.vertexAttribPointer(at, 2, gl.FLOAT, false, 0, 0);
    this.u = Object.fromEntries(['a', 'b', 'mixv', 'time', 'res'].map((n) => [n, gl.getUniformLocation(pr, n)]));
    gl.uniform1i(this.u.a, 0);
    gl.uniform1i(this.u.b, 1);
    this.tex = [0, 1].map((i) => {
      const x = gl.createTexture();
      gl.activeTexture(gl.TEXTURE0 + i);
      gl.bindTexture(gl.TEXTURE_2D, x);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 1, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array([11, 11, 12, 255]));
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.MIRRORED_REPEAT);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.MIRRORED_REPEAT);
      return x;
    });
    cv.addEventListener('webglcontextlost', (e) => { e.preventDefault(); this.stop(); cv.remove(); this.gl = false; });
    cv.className = 'flow';
    cv.setAttribute('aria-hidden', 'true');
    $('#backdrop').append(cv);
    this.gl = gl;
    this.cv = cv;
    return true;
  },
  set(u) {
    this.want = u;
    if (!this.on || !u || u === this.url) return;
    const img = new Image();
    img.onload = () => {
      if (this.want !== u || !this.gl) return;
      const c = document.createElement('canvas');
      c.width = c.height = 64;
      c.getContext('2d').drawImage(img, 0, 0, 64, 64);
      const gl = this.gl, first = !this.url, back = first ? this.front : 1 - this.front;
      gl.activeTexture(gl.TEXTURE0 + back);
      gl.bindTexture(gl.TEXTURE_2D, this.tex[back]);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, c);
      gl.generateMipmap(gl.TEXTURE_2D);
      this.url = u;
      this.from = first ? back : this.front;
      this.to = back;
      this.front = back;
      this.mixAt = first || REDUCED.matches ? -1e9 : performance.now();
      document.body.classList.add('flow');
      this.loop();
    };
    img.src = u;
  },
  size() {
    if (!this.gl) return;
    const w = Math.max(32, Math.round(innerWidth / 8)), h = Math.max(18, Math.round(innerHeight / 8));
    if (this.cv.width !== w || this.cv.height !== h) { this.cv.width = w; this.cv.height = h; }
    this.gl.viewport(0, 0, w, h);
    this.gl.uniform2f(this.u.res, w, h);
    this.draw(performance.now());
  },
  draw(now) {
    const gl = this.gl, f = clamp((now - this.mixAt) / 700);
    gl.uniform1f(this.u.time, REDUCED.matches ? 0 : (now - this.t0) / 1000);
    gl.uniform1f(this.u.mixv, this.from + (this.to - this.from) * (f * f * (3 - 2 * f)));
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  },
  loop() {
    cancelAnimationFrame(this.raf);
    if (!this.on || !this.gl) return;
    const step = (now) => {
      if (!this.on) return;
      if (now - this.last >= 32) { this.last = now; this.draw(now); }
      // still frames once the crossfade is done, if motion is reduced; nothing while the tab is away
      if (!document.hidden && (!REDUCED.matches || now - this.mixAt < 800)) this.raf = requestAnimationFrame(step);
    };
    this.raf = requestAnimationFrame(step);
  },
  start() {
    if (!this.init()) return;
    this.on = true;
    this.size();
    if (this.url) document.body.classList.add('flow');
    this.set(this.want);
    this.loop();
  },
  stop() {
    this.on = false;
    cancelAnimationFrame(this.raf);
    document.body.classList.remove('flow');
  },
};
addEventListener('resize', () => Flow.on && Flow.size());
document.addEventListener('visibilitychange', () => { if (!document.hidden && Flow.on) Flow.loop(); });

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
  const set = (id, v, doc = document) => { const el = $(id, doc); if (el) el.textContent = v; };
  set('#nTitle', p.title);
  set('#nArtist', names(p.artists));
  set('#nAlbum', [p.album?.name && p.album.name !== p.title ? p.album.name : '', p.year].filter(Boolean).join(' · '));
  set('#nWhy', reasonOf(p));
  $$('[data-k="nope"]').forEach((b) => { b.title = p.kind ? t('这阵子先不听（X）') : t('不要这首（X）'); });
  const bc = $('#nBc');
  if (bc) bc.innerHTML = becauseHTML(p);
  set('#dTitle', p.title);
  set('#dArtist', names(p.artists));
  paintArt(p);
  paintCredits();
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

// The cover in the room and in the player card. A music video keeps its own shape, as its player shows it; an audio
// track is square art even when only YouTube's 16:9 frame of it is at hand, so that frame is cut to its square.
function paintArt(p) {
  const big = cover(p, 1200);
  for (const [id, u] of [['#nArt', big], ['#dArt', cover(p, 480)]]) {
    const el = $(id);
    if (!el) continue;
    if (el.getAttribute('src') !== px(u)) el.src = px(u);
    el.classList.toggle('mv', !isGoogleArt(u) && p.type !== 'ATV');
  }
  const nx = Q?.tracks[Q.i + 1];
  if (nx) new Image().src = px(cover(nx, 1200));   // so the next cover is there the moment the song changes
}

// Scroll only the programme's own list; on phones the list is part of the page and must not drag the page along.
function keepCurrentRowVisible() {
  const list = $('#qList'), row = $('.tr.cur');
  if (!list || !row || list.scrollHeight <= list.clientHeight + 2) return;
  const a = list.getBoundingClientRect(), b = row.getBoundingClientRect();
  if (b.top < a.top + 4 || b.bottom > a.bottom - 40) list.scrollBy({ top: b.top - a.top - row.offsetHeight, behavior: document.hidden ? 'auto' : 'smooth' });
}

// One player, two homes. YouTube draws its own title bar, buttons and logo over a playing player whenever it is touched
// and may not be covered, so on a wide screen the big cover stays the song's own art and the player sits in the card at
// the foot of the rail. A phone has no room for both: there the cover is the player, and it moves to the card above the
// tabs once it scrolls away. When it changes home it flies there, so the song never looks like it vanished.
const onHero = () => view === 'listen' && (prefs.imm || (PHONE.matches && !frameAway));
let hostAt = null;
function placeHost() {
  if (cardMoving) return;
  const host = $('#ytHost');
  const docked = !onHero();
  const target = docked ? $('#pcFrame') : $('#frame');
  if (!target || !cur() || !target.offsetParent) { host.hidden = true; hostAt = null; return; }
  const was = host.hidden ? null : host.getBoundingClientRect();
  host.hidden = false;
  host.classList.toggle('off', !Player.shown);
  const r = target.getBoundingClientRect();
  host.classList.toggle('docked', docked);
  // The card is held to the bottom of the screen, so its YouTube window is too: when a phone's toolbar folds away
  // mid-scroll the two move together (measured from the top, the window trailed the card by the toolbar's height
  // until the scroll ended).
  Object.assign(host.style, docked
    ? { top: 'auto', bottom: `${innerHeight - r.bottom}px`, left: `${r.left}px` }
    : { top: `${r.top + scrollY}px`, bottom: 'auto', left: `${r.left + scrollX}px` },
  { width: `${target.offsetWidth}px`, height: `${target.offsetHeight}px` });
  for (const d of $$('dialog[open]')) spare(d);
  if ($('#toast').classList.contains('show')) clearOf($('#toast'));   // a note shown before the player appeared
  const moved = hostAt && hostAt !== target.id;
  hostAt = target.id;
  if (moved) flyFrom(host, was);
}
// The element flies from where it was (a rect taken before the layout changed) to where it is now.
function flyFrom(el, was) {
  const r = el.getBoundingClientRect();
  if (!was?.width || !r.width || REDUCED.matches || (Math.abs(was.left - r.left) < 1 && Math.abs(was.top - r.top) < 1 && Math.abs(was.width - r.width) < 1)) return;
  el.animate([
    { transformOrigin: '0 0', transform: `translate(${was.left - r.left}px, ${was.top - r.top}px) scale(${was.width / r.width}, ${was.height / r.height})` },
    { transformOrigin: '0 0', transform: 'none' },
  ], { duration: 420, easing: 'cubic-bezier(.32, .72, 0, 1)' });
}
const ro = new ResizeObserver(() => placeHost());
// the player card rises into place; measure it again once it has landed
addEventListener('animationend', (e) => { if (e.target.id === 'pcard') placeHost(); });
ro.observe(document.body);
addEventListener('resize', () => (PHONE.matches ? layoutStage() : placeHost()));   // a phone's height changes with its address bar

/* ---------- feedback ---------- */
function track(p) { return { vid: p.vid, lane: p.from || Q?.key, title: p.title, artist: p.artists?.[0]?.name, artist_id: p.artists?.[0]?.id }; }

async function like(p) {
  if (SAMPLE()) return openJoin('like');
  if (p.kind) return toast(t('这首已经在你的喜欢里'));
  const on = fb.get(p.vid) === 'like';
  on ? fb.delete(p.vid) : fb.set(p.vid, 'like');
  paintLikes();
  if (!on) { blendShift(p, -1); adapt('pos', p); }
  try {
    const r = await api('/api/feedback', { ...track(p), action: on ? 'undo' : 'like' });
    if (!on && r.sync === 'queued' && !store.get(acct('syncHint'))) {
      store.set(acct('syncHint'), true);
      toast(t('喜欢会同步到你的 YouTube Music'), [[t('在哪里关'), openSettings]]);
    } else if (!on && r.sync === 'read-only' && !store.get(acct('syncHint'))) {
      store.set(acct('syncHint'), true);
      toast(t('这首记在知音了。也想让 ♥ 出现在 YouTube Music 里，可以在设置里打开'), [[t('去设置'), openSettings]], 7000);
    }
  } catch {
    on ? fb.set(p.vid, 'like') : fb.delete(p.vid);
    paintLikes();
    toast(t('没保存上，稍后再试'));
  }
}
const liked = (p) => !!p && (!!p.kind || fb.get(p.vid) === 'like');
function paintLikes() {
  const on = liked(cur());
  $$('.ib.like[data-k]').forEach((b) => b.classList.toggle('on', on));
  Pip.w && $$('.ib.like', Pip.w.document).forEach((b) => b.classList.toggle('on', on));
  // (a row keeps its heart lit for a song liked here; one of their own likes shows it only under the pointer)
  $$('.tr').forEach((r) => $('.ib.like', r)?.classList.toggle('on', fb.get(Q.tracks[+r.dataset.i]?.vid) === 'like'));
}

function nope(p) {
  if (SAMPLE()) return openJoin('nope');
  if (p.kind) return hushMine(p);
  if (p.mine || Q.key === 'ear') return notMe(p);
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
    // a song that's fine but in the wrong station is a different lesson for that station's editor (rank.outcomes)
    ...(Q.key.startsWith('ask:') ? [] : [[t('只是不该在这个电台'), () => {
      api('/api/feedback', { ...track(p), action: 'dislike', scope: 'song', reason: t('只是不该在这个电台') }).catch(() => {});
      toast(t('记下了，这个电台的编辑下一期会看到'));
    }]]),
  ]);
}

// Take a track out of the queue as "not for me" does, and say how to bring it back.
function dropFromQueue(p) {
  const idx = Q.tracks.indexOf(p);
  if (idx < 0) return null;
  const wasCur = idx === Q.i, wasPlaying = Player.playing;
  Q.tracks.splice(idx, 1);
  if (idx < Q.i) Q.i--;
  renderQueue();
  if (wasCur) {
    const go = () => { Q.i = Math.min(Q.i, Q.tracks.length - 1); loadTrack(wasPlaying); };
    Q.i >= Q.tracks.length ? extend(true).then(go) : go();
  }
  return () => { Q.tracks.splice(idx, 0, p); if (idx <= Q.i && !wasCur) Q.i++; else if (wasCur && idx <= Q.i) Q.i++; renderQueue(); };
}

async function setNotMe(body) {
  const r = await api('/api/notme', body);
  S.not_me = r.not_me;
  earStale = true;
  if (view === 'ear') renderEar();
}

function notMe(p) {
  const put = dropFromQueue(p);
  const a = p.artists?.[0]?.name;
  setNotMe({ vid: p.vid, on: true }).catch(() => toast(t('没保存上，稍后再试')));
  toast(t('〈{s}〉不算进你的口味了，仍在你的喜欢里', { s: p.title }), [
    [t('撤销'), () => { put?.(); setNotMe({ vid: p.vid, on: false }).catch(() => {}); }],
    ...(a ? [[t('{a}的都不算', { a: spaced(a) }), () => {
      setNotMe({ artist: a, on: true }).then(() => toast(t('{a} 的歌都不算进你的口味了，也不会推给你', { a }), [[t('撤销'), () => setNotMe({ artist: a, on: false })]]))
        .catch(() => toast(t('没保存上，稍后再试')));
    }]] : []),
  ]);
}

// One of their likes between the new songs, "not for a while": out of every station for two months. Only when they
// say so is it "not my taste" too; it stays liked on YouTube either way.
function hushMine(p) {
  const put = dropFromQueue(p), m = MINE?.by.get(p.vid), was = { due: m?.due, heard: famHeard.has(p.vid) };
  famHeard.add(p.vid);
  if (m) m.due = nowS() + HUSH_D * 86400;
  const hush = (days) => api('/api/mine/hush', { vid: p.vid, days });
  hush(HUSH_D).catch(() => toast(t('没保存上，稍后再试')));
  toast(t('〈{s}〉这阵子先不放，两个月后再回来', { s: p.title }), [
    [t('撤销'), () => {
      put?.();
      if (!was.heard) famHeard.delete(p.vid);
      if (m) m.due = was.due;
      hush(0).catch(() => {});
    }],
    [t('已经不是我的口味'), () => {
      setNotMe({ vid: p.vid, on: true })
        .then(() => toast(t('〈{s}〉不算进你的口味了，仍在你的喜欢里', { s: p.title }), [[t('撤销'), () => setNotMe({ vid: p.vid, on: false })]]))
        .catch(() => toast(t('没保存上，稍后再试')));
    }],
  ]);
}

// Hear the like a pick is shown with, then the pick again from its start: the listener judges the likeness.
function hearMine(p) {
  const b = p?.because;
  if (!b) return;
  const i = Q.tracks.indexOf(p);
  if (i < 0) return;
  leaving();
  startSrc = 'compare';
  Q.tracks.splice(i, 0, { vid: b.vid, title: b.title, artists: [{ name: b.artist }], mine: true });
  Q.i = i;
  renderQueue();
  loadTrack(true);
  toast(t('先放你喜欢的〈{s}〉，接着回到〈{p}〉', { s: b.title, p: p.title }));
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
    <p class="lede">${t('知音从你在 YouTube Music 点过的喜欢出发，每周挑几组你还没听过、但大概会喜欢的歌，每一首都写着为什么挑它。')}</p>
    <a class="btn" href="/auth/google/start">${t('连接 YouTube Music')}</a>
    ${me.google.verified ? '' : `<p class="fine">${UNVERIFIED()}</p>`}
    <dl class="scope">
      <dt>${t('会读取')}</dt><dd>${t('你喜欢和不喜欢的音乐、订阅的音乐频道、自建歌单，用来做推荐')}</dd>
      <dt>${t('可以写回')}</dt><dd>${t('同步你在这里点的喜欢，或保存电台为私人歌单。要你在设置里打开，Google 会再问一次')}</dd>
      <dt>${t('不会')}</dt><dd>${t('发布、评论、删除，或碰你的其他 Google 数据')}</dd>
    </dl>
    <p class="fine">${t('连接后，知音会把从 Google 读取的歌名、歌手、喜欢时间及其他音乐偏好发送给 Anthropic（Claude），用于生成你的电台和口味画像；不发送 Google 邮箱或访问凭证。继续连接即同意这些处理，详情见隐私政策。')} <a href="/privacy">${t('知音怎么用你的数据')}</a></p>
    <p class="fine">${t('你的喜欢和反馈存在{owner}的服务器上，随时可以在设置里断开并全部删除。', { owner: esc(owner) })}</p>
    <form class="w-163" id="neForm" autocomplete="off"><h2>${t('不用 YouTube Music？')}</h2>
      <p>${t('用网易云或 QQ 音乐里的喜欢也行，复制链接贴进来。电台照样在 YouTube 上播放。')}</p>
      ${howHTML()}
      <div class="mk-row"><input name="link" type="text" inputmode="url" enterkeyhint="go" spellcheck="false" placeholder="${t('粘贴网易云或 QQ 音乐的链接')}" aria-label="${t('网易云或 QQ 音乐的链接')}"><button class="btn" type="submit">${t('从这份歌单开始')}</button></div>
      <p class="mk-err" role="alert"></p>
      <p class="fine">${t('知音会读这份歌单（网易云的还有公开的听歌排行），之后每 6 小时重读一次；歌名、歌手和喜欢时间会发给 Anthropic（Claude）来挑歌。随时可以在设置里全部删除。')}</p></form>
  </div>`;
}

function renderListen() {
  if (!Q && S.me?.status === 'new') { $('#view').innerHTML = welcomeHTML(); placeHost(); return; }
  if (!Q && !ready()) {
    const st = S.me.status === 'error' && S.me.setup_issue === 'nochannel' ? 'nochannel' : S.me.status;
    const [h, p] = { thin: [t('先听点什么'), t('「先听着」从你最近的喜欢出发。')],
      nochannel: [t('还读不到你的喜欢'), t('建好 YouTube 频道，再点「再试一次」，就从你点过的喜欢开始。')],
      error: [t('第一批电台没做成'), t('点「再试一次」重新准备，读到的喜欢都还在。')] }[st] || [t('马上就能听'), t('正在从你最近的喜欢里找第一首歌。')];
    $('#view').innerHTML = `<div class="empty"><h2>${h}</h2><p>${p}</p></div>`;
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
    ${SAMPLE() ? `<button class="s-bar" data-k="join"><span>${t('示例听众的电台')}</span><b>${t('用你自己的收藏开始')}</b>${I.go}</button>` : ''}
    <header class="l-head">
      <div class="ttl"><h2 id="qName"></h2><p id="qWhen"></p><p class="went" id="qNote"></p><p class="went" id="qWent"></p></div>
      <div class="views">
        <button class="ib sm" data-k="lyrics" title="${t('歌词（G）')}">${I.lyrics}</button>
        <button class="ib sm" data-k="pip" title="${t('小窗（M）')}">${I.pip}</button>
        <button class="ib sm ${prefs.stage ? 'on' : ''}" data-k="stage" title="${t('只看歌词（S）')}">${I.stage}</button>
        <button class="ib sm" data-k="imm" title="${prefs.imm ? t('退出沉浸（F / Esc）') : t('沉浸（F）')}">${prefs.imm ? I.shrink : I.full}</button>
        <button class="ib sm" data-k="stmenu" title="${t('更多')}" aria-haspopup="menu">${I.more}</button>
      </div>
    </header>
    <section class="room"><div class="room-in">
      <div class="now">
        <div class="frame" id="frame" data-k="toggle" role="button" aria-label="${t('播放 / 暂停（空格）')}"><img class="art" id="nArt" alt=""></div>
        <div class="meta">
          <h1 class="t-title" id="nTitle"></h1>
          <div class="t-artist" id="nArtist"></div>
          <div class="t-fine"><span id="nAlbum"></span><span id="nCred"></span></div>
          <p class="t-why" id="nWhy"></p>
          <p class="t-bc" id="nBc"></p>
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
      </div>
      <div class="side">
        <div class="side-tabs" role="tablist">
          <button role="tab" data-k="tab-lyr">${t('歌词')}</button><button role="tab" data-k="tab-q">${t('接下来')}</button>
        </div>
        <div class="lyr" id="lyrStage" role="tabpanel"></div>
        <section class="queue" role="tabpanel" aria-label="${t('接下来')}">
          <div class="s-head">
            <h3>${t('接下来')}</h3>
            <span class="blend" id="qBlend" role="radiogroup" aria-label="${t('收藏和新歌')}" hidden>${Object.entries({ fam: t('熟悉'), bal: t('平衡'), new: t('全新') }).map(([v, l]) => `<button class="tb" role="radio" data-k="blend" data-v="${v}" title="${BLEND_NOTE()[v]}">${l}</button>`).join('')}</span>
            <span class="steer"><button class="tb" data-k="calm" title="${t('接下来放安静一点的')}">${t('更安静')}</button><button class="tb" data-k="up" title="${t('接下来放带劲一点的')}">${t('更带劲')}</button><button class="tb" data-k="fresh" title="${t('多放你没收藏过的歌手')}">${t('多些新歌手')}</button></span>
            <span class="s-note" id="sNote"></span>
          </div>
          <p class="q-promise" id="qPromise"></p>
          <ol class="s-list" id="qList"></ol>
        </section>
      </div>
    </div></section>
  </div>`;
  renderQueue();
  paintNow();
  Lyr.render();
  stageRO.disconnect();
  stageRO.observe($('.room'));
  stageRO.observe($('.meta'));   // the cover moves when the words under it change height, though the room keeps its size
  layoutStage();
  if (Pip.w) $$('[data-k="pip"]').forEach((b) => b.classList.add('on'));
  watchFrame();
}

function renderQueue() {
  const list = $('#qList');
  if (!list || !Q) return;
  $('#qName').textContent = Q.st.name;
  // the promise every station but your own likes keeps (candidates.Known)
  $('#qPromise').textContent = Q.key === 'ear' ? '' : Q.gap ? t('带圆点的是新歌，都不在你的喜欢里，听过的也不会再推；其余是你自己的收藏。') : t('这里的歌都不在你的喜欢里，你听过的也不会再推。');
  paintSteer();
  list.innerHTML = Q.tracks.map((p, i) => `
    <li class="tr ${i === Q.i ? 'cur' : ''} ${i !== Q.i && Q.played.has(p.vid) ? 'done' : ''}" data-i="${i}" title="${esc(p.title)} · ${esc(names(p.artists))}${p.dur ? ` · ${fmt(p.dur)}` : ''}">
      <div class="cv">${imgTag(p, 226)}<span class="eq"><i></i><i></i><i></i></span></div>
      <div class="mid"><div class="tt">${Q.gap && !p.kind && !p.mine ? `<i class="nw" title="${t('新歌')}"></i>` : ''}${esc(p.title)}</div><div class="ar">${esc(names(p.artists))}</div></div>
      <div class="end"><span class="d num">${p.dur ? fmt(p.dur) : ''}</span><span class="acts"><button class="ib like ${fb.get(p.vid) === 'like' ? 'on' : p.kind ? 'mine' : ''}" data-a="like" aria-label="${t('喜欢')}">${I.heart}</button><button class="ib" data-a="nope" aria-label="${p.kind ? t('这阵子先不听') : t('不要')}">${I.x}</button></span></div>
    </li>`).join('') + `<li class="tile more"><button data-k="extend"><span class="cv">${I.plus}</span><span class="tt">${t('再来几首')}</span></button></li>`;
  $$('.st').forEach((b) => b.toggleAttribute('aria-current', b.dataset.st === Q.key));
  keepCurrentRowVisible();
}

// A phone scrolls the stage away under the station strip. Nothing may cover YouTube's player and it must stay in
// sight while it plays, so as soon as any of the cover slips under the strip or the tabs it moves into the card.
let frameIO = null, frameAway = false;
function watchFrame() {
  frameIO?.disconnect();
  const f = $('#frame');
  if (!f || !PHONE.matches) { if (frameAway) { frameAway = false; placeCard(); } return; }
  frameIO = new IntersectionObserver(([e]) => {
    const away = e.intersectionRatio < 0.99;
    if (away === frameAway) return;
    frameAway = away;
    placeCard();
    placeHost();
  }, { threshold: [0.99], rootMargin: `-${getComputedStyle($('#rail')).position === 'sticky' ? $('#rail').offsetHeight : 0}px 0px -${$('#tabs').offsetHeight}px 0px` });
  frameIO.observe(f);
}
function placeCard() {
  const c = $('#pcard');
  const bare = view === 'listen' && !PHONE.matches;   // the room already shows the song and its controls
  c.hidden = !cur() || onHero() || (bare && !Player.used);
  c.classList.toggle('bare', bare);
  c.classList.toggle('rest', PHONE.matches && Player.rest);
}

// Paused, or before anything has played, a phone's card is a one-line bar: YouTube's player isn't showing, so there is
// no 208px window to keep open over the page. Play, and the cover grows back into the window the player then takes.
let cardMoving = null;
function restCard() {
  const c = $('#pcard');
  const rest = PHONE.matches && Player.rest;
  if (c.classList.contains('rest') === rest) return;
  if (c.hidden || matchMedia('(prefers-reduced-motion: reduce)').matches) { c.classList.toggle('rest', rest); return placeHost(); }
  cardMoving?.cancel();
  const parts = [c, $('#pcFrame'), c.querySelector('.pc-txt'), c.querySelector('.pc-ctl')];
  const was = parts.map((e) => e.getBoundingClientRect());
  c.classList.toggle('rest', rest);
  const now = parts.map((e) => e.getBoundingClientRect());
  const o = { duration: 300, easing: 'cubic-bezier(.32, .72, 0, 1)' };
  // the card grows from its foot; each part starts where it sat in the card before
  const from = (i) => `translate(${was[i].left - was[0].left - (now[i].left - now[0].left)}px, ${was[i].top - was[0].top - (now[i].top - now[0].top)}px)`;
  const anims = [
    c.animate([{ height: `${was[0].height}px` }, { height: `${now[0].height}px` }], o),
    parts[1].animate([{ transformOrigin: '0 0', transform: `${from(1)} scale(${was[1].width / now[1].width}, ${was[1].height / now[1].height})` }, { transformOrigin: '0 0', transform: 'none' }], o),
    parts[2].animate([{ transform: from(2) }, { transform: 'none' }], o),
    parts[3].animate([{ transform: from(3) }, { transform: 'none' }], o),
  ];
  const mine = cardMoving = anims[0];
  // YouTube's window opens once the cover has grown into it (a resume can start sounding a moment before)
  mine.finished.then(() => { if (cardMoving === mine) { cardMoving = null; placeHost(); } }, () => {});
  mine.oncancel = () => anims.forEach((a) => a.cancel());
}

/* ---------- account ---------- */
const STATUS = () => ({ new: t('还没连接'), importing: t('读取喜欢中'), building: t('准备电台中'), ready: t('在听'), thin: t('喜欢太少'), error: t('出错了') });
const ago = (ts) => (ts ? when(ts) : '');
let friends = null;
let shownLink = null;
const CLAUDE_SRC = {
  worker: (c) => t('用你的 Claude 订阅，在你的 Mac 上跑。') + (c.online ? '' : t('Mac 现在不在线：新一期会等它醒来再做，点歌也要等它在线。')),
  subscription: () => t('用你的 Claude 订阅，在服务器上跑。'),
  key: () => t('用你的 Claude API key，按用量计费。'),
};
// what their own Claude use came to (llm.used): they pay for it
function usedLine(u) {
  if (!u) return '';
  const n = (x) => new Intl.NumberFormat(LANG, { notation: 'compact', maximumFractionDigits: 1 }).format(x);
  return ' ' + t('今天 {calls} 次调用，读 {in}、写 {out} token，${usd}；近 7 天 ${week}。', {
    calls: u.today.calls, in: n(u.today.in), out: n(u.today.out), usd: u.today.usd.toFixed(2), week: u.week.usd.toFixed(2) });
}

function accountHTML() {
  const me = S.me;
  if (!me) return '';
  const g = me.google, sy = me.sync, ls = me.last_sync;
  const rows = [];
  if (me.netease) {
    const ne = me.netease, busy = S.jobs?.sync?.running;
    rows.push(`<li><span>${t('{app}「我喜欢」', { app: appName(ne.app) })}<small>${t('{n} 首喜欢', { n: ne.n ?? ls?.videos ?? 0 })}${ne.unmatched ? ` · ${t('其中 {n} 首在 YouTube Music 上没找到：不在电台里放，也不会再推荐给你', { n: ne.unmatched })}` : ''}${me.synced ? ` · ${t('{when} 读过一次', { when: ago(me.synced) })}` : ''}</small><small>${t('每 6 小时重读一次，在{app}新点的喜欢会自动进来。', { app: appShort(ne.app) })}</small></span><button class="tb" data-k="resync" ${busy ? 'disabled' : ''}>${busy ? t('读取中…') : t('现在读取')}</button></li>`);
  } else if (!g.configured) {
    rows.push(`<li><span>YouTube Music<small>${t('连接 YouTube Music 需要先在服务器上配置 Google 登录。')}</small></span><span></span></li>`);
  } else if (g.error === 'revoked') {
    rows.push(`<li><span>YouTube Music<small>${t('连接失效了：可能在 Google 账号里移除了授权。重新连接一下。')}</small></span><a class="tb" href="/auth/google/start">${t('重新连接')}</a></li>`);
  } else if (!g.connected) {
    rows.push(`<li><span>YouTube Music<small>${t('还没连接。连接之后，知音读你在 YouTube Music 点过的喜欢，之后新点的也会自动进来。')}</small></span><a class="tb" href="/auth/google/start">${t('连接')}</a></li>`);
  } else {
    const busy = S.jobs?.sync?.running;
    const rd = me.read;
    rows.push(`<li><span>YouTube Music<small>${esc(g.email || t('已连接'))}${me.synced ? ` · ${ls?.added ? t('{when} 读过一次，新增 {n} 首', { when: ago(me.synced), n: ls.added }) : t('{when} 读过一次', { when: ago(me.synced) })}` : ''}</small>${rd && ls?.songs ? `<small>${t('读到 {l}、{d}、{f}、{s}：不推荐你踩过或已经存着的歌，也认得出你订阅的歌手。', { l: t('{n} 首喜欢', { n: ls.songs }), d: t('{n} 首不喜欢', { n: rd.disliked }), f: t('{n} 个订阅的音乐频道', { n: rd.follows }), s: t('{n} 首自建歌单里的歌', { n: rd.saved }) })}</small>` : ''}</span><button class="tb" data-k="resync" ${busy ? 'disabled' : ''}>${busy ? t('读取中…') : t('现在读取')}</button></li>`);
    const state = !me.writes_back ? t('打开后，这里点的 ♥（包括之前点过的）会写进 YouTube Music，电台也能存成私人歌单；Google 会再问你一次') : sy.pending ? (sy.error === 'quota' ? t('{n} 首等待同步：今天的额度用完了，{at}后继续', { n: sy.pending, at: quotaReset() }) : sy.error === 'reconnect' ? t('{n} 首等待同步：需要重新连接', { n: sy.pending }) : t('{n} 首等待同步', { n: sy.pending })) : sy.done ? t('已同步 {n} 首', { n: sy.done }) : t('在这里点 ♥，YouTube Music 里也会是喜欢');
    rows.push(`<li><span>${t('把这里的喜欢同步到 YouTube Music')}<small>${esc(state)}${t('。「不要」只记在知音。')}</small></span><button class="sw" role="switch" data-k="synclikes" aria-checked="${me.sync_likes}" aria-label="${t('同步喜欢')}"></button></li>`);
  }
  if (me.mine && me.claude) {
    const c = me.claude;
    rows.push(`<li><span>Claude<small>${CLAUDE_SRC[c.source] ? CLAUDE_SRC[c.source](c) + usedLine(c.used) : t('还没配置。没有它，知音选不了歌：见 docs/self-hosting.md。')}</small></span><span>${c.source === 'worker' ? (c.online ? t('在线') : t('离线')) : ''}</span></li>`);
  }
  if (me.auth) {
    // (a bookmark per account is for switching between your own accounts; everyone else just signs in with Google)
    if (g.email && me.mine) rows.push(`<li><span>${t('这个账号的登录书签')}<small>${t('在别的浏览器里想一键进来，就把这个链接存成书签（那里要登着 {email}）。', { email: esc(g.email) })}</small>${linkHTML(`${location.origin}/auth/google/start?mode=login&as=${encodeURIComponent(g.email)}`)}</span><span></span></li>`);
    else if (!g.email) rows.push(`<li><span>${t('在另一台设备上登录')}<small>${t('生成一个 14 天内有效的登录链接，发给自己。')}</small>${shownLink?.kind === 'device' ? linkHTML(shownLink.url) : ''}</span><button class="tb" data-k="device">${t('生成链接')}</button></li>`);
    rows.push(`<li><span>${t('退出登录')}<small>${t('只退出这台设备。')}</small></span><button class="tb" data-k="logout">${t('退出')}</button></li>`);
    if (!me.owner) rows.push(`<li><span>${t('断开并删除我的数据')}<small>${t('撤销 Google 授权，删掉你的喜欢、电台和反馈。')}</small></span><button class="tb danger" data-k="delete">${t('删除')}</button></li>`);
  }
  return `<section class="sh-sec"><h3>${t('账号')}</h3><ul class="plain acct">${rows.join('')}</ul>${g.configured && !g.connected && !me.netease ? `<p class="fine">${t('连接后，知音会把从 Google 读取的歌名、歌手、喜欢时间及其他音乐偏好发送给 Anthropic（Claude），用于生成你的电台和口味画像；不发送 Google 邮箱或访问凭证。继续连接即同意这些处理，详情见隐私政策。')} <a href="/privacy">${t('知音怎么用你的数据')}</a></p>` : ''}</section>${me.owner && me.auth ? friendsHTML() : ''}`;
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
  if (SAMPLE()) { location.href = `/lang?to=${lang}&back=${encodeURIComponent(location.pathname + location.hash)}`; return; }
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
  spare(d);
}
$('#sheet').addEventListener('click', (e) => { if (e.target === e.currentTarget) e.currentTarget.close(); });

/* ---------- joining, from the sample listener ---------- */
// Until Google finishes reviewing the app, its sign-in warns first and asks to tick YouTube: said before, not after.
const UNVERIFIED = () => t('Google 会先提示「尚未验证此应用」，因为知音还在 Google 的审核中：点「高级」，再点「转至…（不安全）」；下一页记得勾上 YouTube。');
const G_LOGO = '<svg class="g" viewBox="0 0 48 48" aria-hidden="true"><path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9.1 3.6l6.8-6.8C35.8 2.4 30.3 0 24 0 14.6 0 6.6 5.4 2.7 13.3l7.9 6.2C12.5 13.6 17.8 9.5 24 9.5z"/><path fill="#4285F4" d="M46.1 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.4c-.5 2.9-2.2 5.3-4.6 6.9l7.4 5.8c4.3-4 6.9-9.9 6.9-17.2z"/><path fill="#FBBC05" d="M10.5 28.5c-.5-1.4-.8-2.9-.8-4.5s.3-3.1.8-4.5l-7.9-6.2C1 16.6 0 20.2 0 24s1 7.4 2.7 10.7l7.8-6.2z"/><path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.4-5.8c-2.1 1.4-4.8 2.3-8.5 2.3-6.2 0-11.5-4.1-13.4-9.9l-7.9 6.2C6.6 42.6 14.6 48 24 48z"/></svg>';
function openJoin(why) {
  closeMenu();
  const me = S.me, d = $('#join');
  const full = me.join === 'full', invite = me.join === 'invite' || !me.google?.configured;
  const title = full ? t('名额暂时满了') : invite ? t('现在要有邀请才能加入')
    : { like: t('点一下喜欢，它就更懂你一点'), nope: t('说「不要」，它就更懂你一点'), ask: t('用自己的话点歌，要先有你自己的知音') }[why] || t('用你自己的收藏开始');
  const steps = full ? [t('每个人的电台都由 Claude 来挑，名额跟着额度走。先用 Google 登记，空出位置之后，再来就能直接进。')]
    : invite ? [t('已经加入的话，用 Google 登录就能回到你的电台。')]
    : [t('连上你的 YouTube Music：知音只读你的喜欢和不喜欢、订阅、歌单，不改动任何东西。'),
      me.google?.verified ? t('不用安装，也不用你自己的 Claude。') : UNVERIFIED(), t('几分钟后出第一批电台，等的时候可以先听着。')];
  d.innerHTML = `<div class="j-in" tabindex="-1" autofocus>
    <button class="ib sm j-x" data-k="closejoin" aria-label="${t('关闭')}">${I.close}</button>
    <svg class="j-mark" viewBox="8 26 84 52" aria-hidden="true"><path d="M14 70 C21 70 26 36 37 36 C48 36 49 70 61 70 C75 70 86 62 86 49 C86 37 77 30 67 33"/><circle cx="69" cy="52" r="7"/></svg>
    <h2>${title}</h2>
    <ol class="${steps.length > 1 ? 'steps' : ''}">${steps.map((x) => `<li>${x}</li>`).join('')}</ol>
    ${!full && !invite ? `<p class="fine">${t('连接后，知音会把从 Google 读取的歌名、歌手、喜欢时间及其他音乐偏好发送给 Anthropic（Claude），用于生成你的电台和口味画像；不发送 Google 邮箱或访问凭证。继续连接即同意这些处理，详情见隐私政策。')}</p>` : ''}
    ${invite ? `<a class="btn j-go" href="/auth/google/start?mode=login">${G_LOGO}${t('用 Google 登录')}</a>`
      : `<a class="btn j-go" href="/auth/google/start?mode=join">${G_LOGO}${full ? t('用 Google 登记') : t('用 Google 继续')}</a>`}
    ${SAMPLE() ? `<p class="j-163">${t('不用 YouTube Music？')}<button class="lnk" data-k="tomaker">${t('用网易云或 QQ 音乐歌单画一张唱片')}</button></p>` : ''}
    <div class="j-alt">${invite ? '<span></span>' : `<a href="/auth/google/start?mode=login">${t('已经加入过？登录')}</a>`}<a href="/about">${t('知音是什么')}</a><a href="/privacy">${t('知音怎么用你的数据')}</a></div>
    <div class="j-lang">${Object.entries(LANGS).map(([k, v]) => `<button data-lang="${k}" ${k === LANG ? 'aria-current="true"' : ''}>${v}</button>`).join('')}</div>
  </div>`;
  if (!d.open) d.showModal();
  spare(d);
}
$('#join').addEventListener('click', (e) => {
  if (e.target === e.currentTarget || e.target.closest('[data-k="closejoin"]')) e.currentTarget.close();
});

/* ---------- the account button and its menu ---------- */
const initial = (s) => esc(([...(s || '').trim()][0] || t('你')).toUpperCase());
function renderMe() {
  if (SAMPLE()) {
    $('#meBtn').classList.add('cta');
    $('#meBtn').innerHTML = `<span class="who"><b>${t('用你自己的收藏开始')}</b><span>${t('现在听的是一位示例听众')}</span></span>${I.go}`;
    $('.me-mini').classList.add('cta');
    $('.me-mini').textContent = t('开始');
    return;
  }
  const me = S.me, g = me?.google || {};
  const name = me?.name || (g.email ? g.email.split('@')[0] : t('你'));
  const sub = g.email && g.email.split('@')[0] !== name ? g.email : me?.owner ? t('主人') : '';
  $('#meBtn').innerHTML = `<span class="av">${initial(name)}</span><span class="who"><b>${esc(name)}</b>${sub ? `<span>${esc(sub)}</span>` : ''}</span>${I.updown}`;
  $('.me-mini').innerHTML = `<span class="av">${initial(name)}</span>`;
}
function closeMenu() { const m = $('#menu'); if (m.matches(':popover-open')) m.hidePopover(); }
// A small popover placed against whatever opened it: above the account button, below the station's ⋯. Where that
// would cover YouTube's player it opens beside the button instead, or above the tabs.
function openMenu(anchor, html) {
  const m = $('#menu');
  if (m.matches(':popover-open') && m.dataset.for === anchor.dataset.k) { closeMenu(); return; }
  m.innerHTML = html;
  m.dataset.for = anchor.dataset.k;
  m.showPopover();
  const a = anchor.getBoundingClientRect(), w = m.offsetWidth, h = m.offsetHeight, yt = playerRect();
  const at = (left, top) => ({ left: clamp(left, 8, innerWidth - w - 8), top: clamp(top, 8, innerHeight - h - 8) });
  const spots = [
    at(a.left, a.top - h - 8 > 8 && a.top > innerHeight / 2 ? a.top - h - 6 : a.bottom + 6),
    a.right + 8 + w < innerWidth - 8 && at(a.right + 8, a.bottom - h),
    at(innerWidth - w - 8, innerHeight - $('#tabs').offsetHeight - h - 8),
  ].filter(Boolean);
  const p = spots.find((r) => !yt || !overlaps({ ...r, right: r.left + w, bottom: r.top + h }, yt)) || spots[0];
  Object.assign(m.style, { left: `${p.left}px`, top: `${p.top}px` });
  spare(m);
  anchor.setAttribute('aria-expanded', 'true');
  onClosed(m, () => anchor.setAttribute('aria-expanded', 'false'));
}
// a popover's opening also fires 'toggle', after this point, so wait for the one that closes it
function onClosed(el, fn) {
  if (el.tagName === 'DIALOG') return el.addEventListener('close', fn, { once: true });
  const h = (e) => { if (e.newState === 'closed') { el.removeEventListener('toggle', h); fn(); } };
  el.addEventListener('toggle', h);
}

// A note goes above the player, else below it, else beside it: it is never drawn on YouTube's player.
function clearOf(t) {
  const yt = playerRect();
  if (!yt) return;
  const w = t.offsetWidth, h = t.offsetHeight, x = t.offsetLeft - w / 2, y = t.offsetTop;   // centred by translate(-50%)
  if (!overlaps({ left: x, top: y, right: x + w, bottom: y + h }, yt)) return;
  if (yt.top - h - 8 >= 4) t.style.bottom = `${innerHeight - yt.top + 8}px`;
  else if (yt.bottom + h + 8 <= innerHeight - 4) t.style.bottom = `${innerHeight - yt.bottom - h - 8}px`;
  else if (yt.right + 8 + w <= innerWidth - 4) t.style.left = `${yt.right + 8 + w / 2}px`;
  else if (yt.left - 8 - w >= 4) t.style.left = `${yt.left - 8 - w / 2}px`;
  else t.classList.remove('show');   // no room anywhere: the note gives way
}

// Nothing may be drawn over YouTube's player while it shows. A dialog that leaves the player clear cuts a window for
// it in its dimmed backdrop; one that would cover it pauses the song, which hides the player, until it closes.
function playerRect() {
  const h = $('#ytHost');
  return h.hidden || h.classList.contains('off') ? null : h.getBoundingClientRect();
}
const respare = () => { for (const d of $$('dialog[open]')) spare(d); };
addEventListener('scroll', respare, { passive: true });
visualViewport?.addEventListener('resize', respare);
function overlaps(a, b) { return a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom; }
function spare(el) {
  const yt = playerRect();
  el.style.removeProperty('--hole');
  if (!yt) return;
  // laid-out position, not mid-animation
  const box = { left: el.offsetLeft, top: el.offsetTop, right: el.offsetLeft + el.offsetWidth, bottom: el.offsetTop + el.offsetHeight };
  if (overlaps(box, yt)) {
    Player.pause();
    onClosed(el, () => Player.play());
    return;
  }
  const { left: l, top: t, right: r, bottom: b } = yt;
  el.style.setProperty('--hole', `polygon(evenodd, 0 0, 100% 0, 100% 100%, 0 100%, 0 0, ${l}px ${t}px, ${r}px ${t}px, ${r}px ${b}px, ${l}px ${b}px, ${l}px ${t}px)`);
}
function accountMenu(anchor) {
  if (SAMPLE()) return openJoin();
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
    ${S.me?.writes_back ? `<button class="m-item" role="menuitem" data-k="save">${I.plus}${t('把这个电台存成歌单')}</button>` : ''}
    <button class="m-item" role="menuitem" data-k="radio">${I.branch}${t('沿着这首继续')}</button>
    ${laneOf(Q) && !SAMPLE() ? `<button class="m-item" role="menuitem" data-k="lanenote">${I.lyrics}${t('告诉这个电台…')}</button>` : ''}
    ${Q.key.startsWith('ask:') && !Q.key.endsWith(':pending') ? `<button class="m-item" role="menuitem" data-k="unaskcur">${I.close}${t('删掉这个点歌')}</button>` : ''}`);
}

// Their own words for a station ("less trap drums, more 90s"): its screen and editor follow them from then on.
const laneOf = (q) => (q && S.lanes?.find((l) => l.key === q.key)) || null;
function openLaneNote() {
  closeMenu();
  const l = laneOf(Q), d = $('#noteD');
  if (!l) return;
  d.innerHTML = `<form class="nd-in" id="ndForm">
    <h2>${t('告诉「{s}」', { s: esc(l.name) })}</h2>
    <p>${t('用你自己的话说想多听什么、少听什么。这个电台以后挑歌都会照着做。')}</p>
    <textarea id="ndText" maxlength="300" rows="3" placeholder="${t('比如：少点 trap 鼓点，多点九十年代的')}">${esc(l.note || '')}</textarea>
    <div class="nd-acts"><button class="tb" type="button" data-k="ndclose">${t('取消')}</button>
      <button class="tb" type="submit" value="save">${t('保存')}</button>
      <button class="btn" type="submit" value="again">${t('保存并重挑')}</button></div>
  </form>`;
  if (!d.open) d.showModal();
  spare(d);
  $('#ndText').focus();
}
$('#noteD').addEventListener('click', (e) => {
  if (e.target === e.currentTarget || e.target.closest('[data-k="ndclose"]')) e.currentTarget.close();
});
$('#noteD').addEventListener('submit', async (e) => {
  e.preventDefault();
  const l = laneOf(Q), again = e.submitter?.value === 'again', note = $('#ndText').value.trim();
  if (!l) return;
  try {
    await api('/api/settings/lane', { key: l.key, note });
    l.note = note;
    $('#noteD').close();
    paintSteer();
    if (!again) return toast(note ? t('记下了，下一期「{s}」会照着挑', { s: l.name }) : t('清掉了'));
    try { await api('/api/refresh', { lanes: [l.key] }); } catch (err) { return toast(err.message); }
    toast(t('正在按你的话重挑「{s}」，好了会自动换上', { s: l.name }), [], 5000);
    S.jobs = await api('/api/jobs');
    renderStations();
    poll();
  } catch (err) { toast(err.message); }
});

/* ---------- share card: the record, the name of the taste, and a number a friend can hold against their own ---------- */
const LOGO = new Path2D('M14 70 C21 70 26 36 37 36 C48 36 49 70 61 70 C75 70 86 62 86 49 C86 37 77 30 67 33');
const NO_START = /^[，。、；：！？）」』》〉,.;:!?)’”]/;

// A headline on two balanced lines at most, broken between words (Chinese words too), preferring a pause.
function headLines(x, text, maxW, prose = false) {
  const toks = [];
  for (const { segment: g } of new Intl.Segmenter(LANG, { granularity: 'word' }).segment(text)) {
    if (toks.length && (NO_START.test(g) || /^\s+$/.test(g))) toks[toks.length - 1] += g; else toks.push(g);
  }
  const w = (v) => x.measureText(v.trim()).width;
  if (w(text) <= maxW) return [text];
  let best = null;
  for (let i = 1; i < toks.length; i++) {
    const a = toks.slice(0, i).join('').trim(), b = toks.slice(i).join('').trim(), m = Math.max(w(a), w(b));
    if (m > maxW) continue;
    // a pause reads best; in a name, then a break before 的 or after 和, which Chinese readers take as a joint, not a
    // cut. A sentence (prose) breaks at its pause whenever the pause leaves both lines fitting.
    const pause = /[，、；：。,;:.\s]$/.test(toks[i - 1]);
    const k = prose ? m * (pause ? 0.6 : 1) : m * (pause ? 0.8 : /^[的之]/.test(toks[i]) || /[和与跟或]$/.test(toks[i - 1]) ? 0.9 : 1);
    if (!best || k < best[0]) best = [k, [a, b]];
  }
  return best?.[1] || null;
}

// Text on as many lines as it needs, broken between words (Chinese words too).
function wrapLines(x, text, maxW) {
  const out = [];
  let cur = '';
  for (const { segment: g } of new Intl.Segmenter(LANG, { granularity: 'word' }).segment(text)) {
    if (cur.trim() && !NO_START.test(g) && x.measureText((cur + g).trim()).width > maxW) { out.push(cur.trim()); cur = g; }
    else cur += g;
  }
  if (cur.trim()) out.push(cur.trim());
  return out;
}

// The hue the covers share, for the light behind the record.
function coverHue() {
  let cx = 0, cy = 0, n = 0;
  for (const s of EAR.list) {
    const m = /hsl\((\d+(?:\.\d+)?) (\d+)%/.exec(earCol.get(s.vid) || '');
    if (!m || +m[2] === 0) { n++; continue; }
    const a = +m[1] * Math.PI / 180, w = +m[2] / 100;
    cx += Math.cos(a) * w; cy += Math.sin(a) * w; n++;
  }
  const r = Math.hypot(cx, cy) / Math.max(1, n);
  return { h: Math.round((Math.atan2(cy, cx) * 180 / Math.PI + 360) % 360), s: Math.round(Math.min(60, 20 + r * 120)) };
}

function arcText(x, str, c, r, mid, low, spacing) {
  const ch = [...str], ws = ch.map((k) => x.measureText(k).width);
  const total = ws.reduce((a, b) => a + b, 0) + spacing * (ch.length - 1);
  // the top half reads clockwise along the outside; the bottom half reads left to right, upright
  let a = mid * Math.PI / 180 + (low ? 1 : -1) * total / 2 / r;
  ch.forEach((k, i) => {
    const step = ws[i] / 2 / r;
    a += low ? -step : step;
    x.save();
    x.translate(c.x, c.y);
    x.rotate(low ? a - Math.PI : a);
    x.fillText(k, 0, low ? r : -r);
    x.restore();
    a += (low ? -1 : 1) * (step + spacing / r);
  });
  return total;
}

async function cardCanvas() {
  await document.fonts.ready;
  if (EAR.list.some((s) => !earCol.has(s.vid))) await Promise.race([earColors(), new Promise((r) => setTimeout(r, 3000))]);
  const W = 1080, H = 1440, M = 80;
  const cv = Object.assign(document.createElement('canvas'), { width: W, height: H });
  const x = cv.getContext('2d');
  const fam = getComputedStyle(document.body).fontFamily;
  const font = (wt, px) => { x.font = `${wt} ${px}px ${fam}`; };
  const INK = 'rgba(255,255,255,.92)', INK2 = 'rgba(255,255,255,.62)', INK3 = 'rgba(255,255,255,.42)';
  x.fillStyle = '#0b0b0c';
  x.fillRect(0, 0, W, H);

  // the mark, and where to find it
  const ls = 34 / 52;
  x.save();
  x.translate(M - 8 * ls, M - 26 * ls);
  x.scale(ls, ls);
  x.lineCap = x.lineJoin = 'round';
  x.lineWidth = 8.5;
  x.strokeStyle = INK;
  x.stroke(LOGO);
  x.fillStyle = '#E9A55B';
  x.beginPath(); x.arc(69, 52, 7, 0, 7); x.fill();
  x.restore();
  x.textBaseline = 'middle';
  font(600, 30);
  x.fillStyle = INK;
  x.fillText(t('知音'), M + 84 * ls + 12, M + 17);
  font(400, 24);
  x.fillStyle = INK3;
  x.textAlign = 'right';
  x.fillText(location.host, W - M, M + 17);
  x.textAlign = 'left';

  // the name of the taste, as big as two lines allow
  const name = EAR.label || t('你的喜欢');
  let size = 88, lines = null;
  for (size of [88, 78, 68, 60, 52]) { font(600, size); if ((lines = headLines(x, name, W - 2 * M))) break; }
  lines ||= [name];
  x.textBaseline = 'alphabetic';
  x.fillStyle = INK;
  let y = M + 96;
  for (const l of lines) { y += size * 0.96; x.fillText(l, M, y); y += size * 0.2; }
  const songs = EAR.list.length, first = yearOf(EAR.span[0]), liked = EAR.n ?? (S.library.songs || songs);
  const kinds = EAR.sectors.length ? S.lanes.length : 0;
  if (EAR.roast) {
    // Claude's line about the taste takes the counts' place: the record's centre and rings carry those
    y += 58;
    font(500, 24);
    x.fillStyle = INK3;
    x.fillText(t('Claude 锐评'), M, y);
    let rl = null, rs = 38;
    for (rs of [38, 34]) { font(400, rs); if ((rl = headLines(x, EAR.roast, W - 2 * M, true))) break; }
    if (!rl) { font(400, rs = 32); rl = wrapLines(x, EAR.roast, W - 2 * M).slice(0, 3); }
    x.fillStyle = INK2;
    for (const l of rl) { y += rs * 1.45; x.fillText(l, M, y); }
  } else {
    font(400, 28);
    x.fillStyle = INK3;
    y += 50;
    x.fillText([t('{n} 首喜欢', { n: liked }), sinceText(first), kinds ? t('{n} 种口味', { n: kinds }) : ''].filter(Boolean).join('  ·  '), M, y);
  }

  // the number, at the foot: how mainstream a NetEase record is, else the year half the songs had come out by
  const pop = EAR.pop ?? null;
  const lead = pop !== null ? `${pop}%` : EAR.center || first;
  const said = pop !== null ? t('歌单大众度，热歌榜是 100%') : EAR.center ? t('你喜欢的歌，有一半是这一年或更早的') : t('这一年点了第一首喜欢');
  const footY = H - M;
  font(600, 112);
  x.fillStyle = INK;
  x.fillText(String(lead), M - 4, footY);
  const nw = x.measureText(String(lead)).width;
  font(400, 34);
  x.fillStyle = INK2;
  // two short lines beside the number read as its caption; one long one reads as a footnote
  const sl = headLines(x, said, Math.min(W - 2 * M - nw - 44, x.measureText(said).width * 0.62)) || headLines(x, said, W - 2 * M - nw - 44) || [said];
  sl.forEach((l, i) => x.fillText(l, M + nw + 44, footY - 4 - (sl.length - 1 - i) * 46));

  // the record, centred in what is left
  const top = y + 40, bottom = footY - 112 - 44, D = Math.min(W - 2 * M + 40, bottom - top);
  const c = { x: W / 2, y: top + (bottom - top) / 2 }, Rt = D / 2 - 12, R1 = Rt - 30, R0 = Math.max(40, R1 * 0.25);
  const hue = coverHue();
  const glow = x.createRadialGradient(c.x, c.y, R0, c.x, c.y, Rt * 1.35);
  glow.addColorStop(0, `hsla(${hue.h} ${hue.s}% 50% / .26)`);
  glow.addColorStop(0.55, `hsla(${hue.h} ${hue.s}% 50% / .09)`);
  glow.addColorStop(1, `hsla(${hue.h} ${hue.s}% 50% / 0)`);
  x.fillStyle = glow;
  x.fillRect(0, 0, W, H);

  const [t0, t1] = EAR.span, span = Math.max(0.5, t1 - t0);
  const rOf = (tt) => R0 + 14 + (R1 - R0 - 14) * (tt - t0) / span;
  const P = (r, a) => [c.x + r * Math.sin(a * Math.PI / 180), c.y - r * Math.cos(a * Math.PI / 180)];
  x.lineWidth = 1.2;
  x.strokeStyle = 'rgba(255,255,255,.06)';
  font(500, 15);
  x.textAlign = 'center';
  x.textBaseline = 'middle';
  // a groove per year, open at twelve o'clock where the years are written, as on the page
  x.fillStyle = INK3;
  let lastR = -99;
  for (let yr = Math.ceil(t0); yr <= t1; yr++) {
    const r = rOf(yr), open = Math.min(0.5, 26 / r);
    x.beginPath(); x.arc(c.x, c.y, r, -Math.PI / 2 + open, 1.5 * Math.PI - open); x.stroke();
    if (r - lastR >= 19) { x.fillText(yr, c.x, c.y - r); lastR = r; }
  }
  // the names of the stations, or the months while there are none yet
  x.strokeStyle = 'rgba(255,255,255,.18)';
  x.lineWidth = 1.5;
  x.fillStyle = INK2;
  if (EAR.sectors.length) {
    for (const s of EAR.sectors) {
      const mid = (s.a0 + s.a1) / 2, low = mid > 120 && mid < 240;
      x.beginPath(); x.arc(c.x, c.y, R1 + 9, (s.a0 + 0.8 - 90) * Math.PI / 180, (s.a1 - 0.8 - 90) * Math.PI / 180); x.stroke();
      const room = (Rt - 2) * (s.a1 - s.a0 + 4) * Math.PI / 180;
      for (const f of [21, 18]) {
        font(500, f);
        const need = [...s.name].reduce((a, k) => a + x.measureText(k).width, 0) + 1.3 * ([...s.name].length - 1);
        if (need <= room) { arcText(x, s.name, c, Rt - 4, mid, low, 1.3); break; }
      }
    }
  } else {
    font(500, 19);
    for (let m = 0; m < 12; m++) {
      const a = 8 + 344 * m / 12, [x0, y0] = P(R1 + 6, a), [x1, y1] = P(R1 + 13, a);
      x.beginPath(); x.moveTo(x0, y0); x.lineTo(x1, y1); x.stroke();
      if (m % 3 === 0) {
        const mid = a + 344 / 24;
        arcText(x, new Date(2000, m).toLocaleDateString(LANG, { month: 'short' }), c, Rt - 4, mid, mid > 120 && mid < 240, 0.5);
      }
    }
  }
  // every like, a short trail along its year's ring; where they cross they add up like light
  const dot = 5.4;
  x.lineCap = 'round';
  x.globalCompositeOperation = 'lighter';
  for (const s of EAR.list) {
    const r = rOf(s.t), th = (s.a - 90) * Math.PI / 180;
    x.globalAlpha = s.off ? 0.2 : 0.95;
    x.beginPath(); x.arc(c.x, c.y, r, th - TRAIL * 1.2, th + TRAIL * 1.2);
    x.lineWidth = dot * 0.62;
    x.strokeStyle = earCol.get(s.vid) || 'rgba(255,255,255,.4)';
    x.stroke();
  }
  x.globalAlpha = 1;
  x.globalCompositeOperation = 'source-over';
  const hr = R0 - 4;
  x.fillStyle = '#141416';
  x.beginPath(); x.arc(c.x, c.y, hr, 0, 7); x.fill();
  x.strokeStyle = 'rgba(255,255,255,.07)';
  x.stroke();
  font(600, Math.round(hr * 0.5));
  x.fillStyle = INK;
  x.fillText(liked, c.x, c.y - hr * 0.1);
  font(400, Math.round(hr * 0.2));
  x.fillStyle = INK3;
  x.fillText(t('首喜欢'), c.x, c.y + hr * 0.34);
  return cv;
}

let card = null;
const WECHAT = /MicroMessenger/i.test(navigator.userAgent);
// links this browser made, so it can take them down again: [{ id, key, url, label }]
const myLinks = () => store.get('cards') || [];
// The link already made for the card on screen: per name for an account, per record for a NetEase one.
const linkFor = () => (guest() ? GUEST.shared : myLinks().find((c) => c.uid === S.me?.uid && c.label === EAR.label)) || null;
function cardLinkHTML(l) {
  return l ? `<div class="sc-link"><span class="sc-url">${esc(l.url.replace(/^https?:\/\//, ''))}</span>
      <button class="tb" data-k="copylink">${I.copy}<span>${t('复制链接')}</span></button>
      <button class="tb" data-k="unlink">${t('收回')}</button></div>`
    : `<button class="tb" data-k="cardlink">${I.link}<span>${t('生成链接')}</span></button>`;
}
async function shareCard(btn) {
  btn.disabled = true;
  try {
    const cv = await cardCanvas();
    const blob = await new Promise((res) => cv.toBlob(res, 'image/png'));
    if (card?.url) URL.revokeObjectURL(card.url);
    const file = new File([blob], 'zhiyin.png', { type: 'image/png' });
    card = { blob, file, cv, url: URL.createObjectURL(blob) };
    const d = $('#shareD');
    const phone = !WECHAT && navigator.canShare?.({ files: [file] }) && matchMedia('(pointer: coarse)').matches;
    // the sample listener's card can be saved, not linked: a link is someone's own record
    const linkable = guest() || !SAMPLE();
    d.innerHTML = `<div class="sc-in">
      <img class="sc-img" src="${card.url}" alt="${esc(EAR.label || t('你的喜欢'))}" width="1080" height="1440">
      ${WECHAT ? `<p class="sc-hint">${t('长按图片，保存或发给朋友')}</p>` : ''}
      <div class="sc-acts">
        ${phone ? `<button class="btn" data-k="sharenow">${I.share}<span>${t('分享')}</span></button>` : ''}
        ${WECHAT ? '' : `<button class="${phone ? 'tb' : 'btn'}" data-k="savecard">${I.save}<span>${t('保存图片')}</span></button>`}
        ${!phone && !WECHAT && window.ClipboardItem ? `<button class="tb" data-k="copycard">${I.copy}<span>${t('复制图片')}</span></button>` : ''}
        ${linkable ? `<span class="sc-ln" id="scLn">${cardLinkHTML(linkFor())}</span>` : ''}
        <button class="ib sm sc-x" data-k="closeshare" aria-label="${t('关闭')}">${I.close}</button>
      </div></div>`;
    if (!d.open) { d.showModal(); ev('share_open'); }
    spare(d);
  } catch { toast(t('图片没做出来，再试一次')); }
  btn.disabled = false;
}
async function makeLink(b) {
  b.disabled = true;
  $('span', b).textContent = t('正在生成…');
  try {
    const jpg = await new Promise((res) => card.cv.toBlob(res, 'image/jpeg', 0.9));
    const g = guest();
    const r = await fetch(`/api/card/share${g ? `?token=${encodeURIComponent(GUEST.token)}` : ''}`, {
      method: 'POST', body: jpg, headers: { 'Content-Type': 'image/jpeg', ...(g || !S.me?.uid ? {} : { 'X-Zhiyin-Uid': S.me.uid }) } });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.detail || t('链接没生成，再试一次'));
    const l = { id: d.id, key: d.key, url: d.url, label: EAR.label || '', uid: g ? null : S.me?.uid };
    store.set('cards', [l, ...myLinks()].slice(0, 40));
    if (g) { GUEST.shared = l; store.set('guest', GUEST); }
    $('#scLn').innerHTML = cardLinkHTML(l);
  } catch (e) {
    if (b.isConnected) { b.disabled = false; $('span', b).textContent = t('生成链接'); }
    toast(e.message);
  }
}
async function cardAct(k, btn) {
  if (!card) return;
  const l = linkFor();
  // the link rides along where the app keeps text with an image (Messages, X, LINE); ?ref=card counts who it brings
  if (k === 'sharenow') {
    try { await navigator.share({ files: [card.file], text: `${EAR.label || t('你的喜欢')}${guest() && EAR.roast ? `\n${t('Claude 锐评')}：${EAR.roast}` : ''}\n${l ? l.url : `${location.origin}/card?ref=card`}` }); ev('share_send'); } catch {}
    return;
  }
  if (k === 'cardlink') return makeLink(btn);
  if (k === 'copylink' && l) {
    try { await navigator.clipboard.writeText(l.url); $('span', btn).textContent = t('链接已复制'); } catch { toast(l.url, [], 8000); }
    setTimeout(() => { if (btn.isConnected) $('span', btn).textContent = t('复制链接'); }, 2400);
    return;
  }
  if (k === 'unlink' && l) {
    try {
      await api('/api/card/delete', { id: l.id, key: l.key });
    } catch (e) { if (!/card/.test(e.message)) return toast(e.message); }   // already gone is gone
    store.set('cards', myLinks().filter((c) => c.id !== l.id));
    if (guest()) { delete GUEST.shared; store.set('guest', GUEST); }
    $('#scLn').innerHTML = cardLinkHTML(null);
    toast(t('链接收回了，打开它只会看到「这张卡已经收回」'));
    return;
  }
  if (k === 'savecard') { Object.assign(document.createElement('a'), { href: card.url, download: 'zhiyin.png' }).click(); ev('share_save'); return; }
  const b = $('#shareD [data-k="copycard"] span');
  try { await navigator.clipboard.write([new ClipboardItem({ 'image/png': card.blob })]); b.textContent = t('图片已复制'); ev('share_copy'); } catch { b.textContent = t('没复制上，可以先保存'); }
  setTimeout(() => { if (b.isConnected) b.textContent = t('复制图片'); }, 2400);
}
$('#shareD').addEventListener('click', (e) => {
  if (e.target === e.currentTarget || e.target.closest('[data-k="closeshare"]')) { e.currentTarget.close(); return; }
  const b = e.target.closest('[data-k]');
  if (b) { e.stopPropagation(); cardAct(b.dataset.k, b); }
});

/* ---------- shortcuts ---------- */
const KEYS = () => [[t('空格'), t('播放 / 暂停')], ['N', t('下一首')], ['P', t('上一首')], ['L', t('喜欢')], ['X', t('不要')], ['← →', t('快退 / 快进 10 秒')],
  ['/', t('点歌')], ['1–9', t('换电台')], ['G', t('歌词')], ['T', t('歌词翻译')], ['R', t('罗马音')], ['[ ]', t('歌词早一点 / 晚一点')], ['F', t('沉浸')], ['S', t('只看歌词')], ['M', t('小窗')], ['?', t('快捷键')]];
function openKeys() {
  closeMenu();
  const d = $('#keysD');
  d.innerHTML = `<h2>${t('快捷键')}</h2><dl>${KEYS().map(([k, v]) => `<dt><kbd>${esc(k)}</kbd></dt><dd>${esc(v)}</dd>`).join('')}</dl>`;
  d.showModal();
  spare(d);
}
$('#keysD').addEventListener('click', (e) => e.currentTarget.close());

/* ---------- ask: say what you want to hear; it is found in the background ---------- */
const IDEAS = () => ({
  morning: [t('早上通勤，轻快一点'), t('周末早晨煮咖啡'), t('开工前热热身，不要太吵')],
  day: [t('下午写代码，人声少一点'), t('下雨的周日下午'), t('做饭时听的日语 city pop')],
  evening: [t('下班路上，想放松'), t('晚饭后出去散步'), t('和朋友喝一杯')],
  night: [t('深夜一个人开车'), t('睡前，安静的钢琴和人声'), t('失眠的时候')],
});
// Asking for a station needs the stations; finding one of their own likes only needs the likes.
const canAsk = () => SAMPLE() || (ready() && !!S.portrait);
const canFind = () => !SAMPLE() && (S.library?.songs || 0) > 0;
function composerHTML() {
  if (!canAsk()) return `<p class="c-hint">${t('电台准备好之后，还能用一句话点一组新歌。现在可以先搜你喜欢过的歌。')}</p>`;
  const h = new Date().getHours();
  const ideas = IDEAS()[h >= 22 || h < 5 ? 'night' : h < 11 ? 'morning' : h < 17 ? 'day' : 'evening'];
  const asks = (S.asks || []).slice(0, 4);
  return `<div class="c-h">${t('试试')}</div><div class="chips">${ideas.map((x) => `<button class="chip" data-idea="${esc(x)}">${esc(x)}</button>`).join('')}</div>
    ${asks.length ? `<div class="c-h">${t('你点过的')}</div>${asks.map((a) => `<button class="c-row" data-st="ask:${a.created}"><span class="mosaic ${a.picks.length < 4 ? 'one' : ''}">${a.picks.slice(0, 4).map((p) => imgTag(p, 120)).join('')}</span><span><b>${esc(a.intent || a.q)}</b><span>${t('你说：{q}', { q: esc(a.q) })}</span></span></button>`).join('')}` : ''}`;
}
// What they type is looked up in their own likes as they type: a title or a singer plays at once, and Enter still
// asks for a station in those words.
let FOUND = [], findSeq = 0, findT = 0;
function paintComposer() {
  const q = $('#askInput').value.trim();
  if (!q) { $('#cBody').innerHTML = composerHTML(); return; }
  // (what Enter does comes first: below eight likes it would be out of sight)
  $('#cBody').innerHTML = (canAsk() ? `<p class="c-hint">${t('按 ↵，照这句话挑一组你没听过的歌')}</p>` : '')
    + (FOUND.length ? `<div class="c-h">${t('你的喜欢')}</div>${FOUND.map((x, i) => `<button class="c-row" data-find="${i}"><span class="mosaic one">${imgTag(x, 120)}</span><span><b>${esc(x.title)}</b><span>${esc(names(x.artists))}</span></span></button>`).join('')}`
      : canAsk() || !canFind() ? '' : `<p class="c-hint">${t('你的喜欢里没有找到')}</p>`);
}
async function findMine() {
  const q = $('#askInput').value.trim(), seq = ++findSeq;
  FOUND = [];
  if (q && canFind()) {
    try { const r = await api(`/api/find?q=${encodeURIComponent(q)}`); if (seq === findSeq) FOUND = r.songs; } catch { /* nothing found then */ }
  }
  if (seq === findSeq && $('#composer').open) paintComposer();
}
function findSoon(e) {
  if (e.isComposing) return;   // pinyin still being typed
  clearTimeout(findT);
  findT = setTimeout(findMine, 120);
}
$('#askInput').addEventListener('input', findSoon);
$('#askInput').addEventListener('compositionend', findSoon);
$('#composer').addEventListener('keydown', (e) => {
  if ((e.key !== 'ArrowDown' && e.key !== 'ArrowUp') || e.isComposing) return;   // (arrows pick pinyin candidates)
  const rows = $$('#cBody [data-find]'), at = rows.indexOf(document.activeElement);
  if (!rows.length) return;
  e.preventDefault();
  const to = e.key === 'ArrowDown' ? Math.min(rows.length - 1, at + 1) : at - 1;
  (to < 0 ? $('#askInput') : rows[to]).focus();
});
// One of their own likes, found in the ask box, plays now; the station carries on after it.
function playFound(x) {
  const p = famTrack(MINE?.by.get(x.vid) || x, 'mix');
  $('#composer').close();
  if (!Q) {
    const st = { key: 'ear', group: 'ear', name: t('你的喜欢'), sub: t('你自己的喜欢'), when: '', tracks: [p], reserve: [] };
    Q = { key: 'ear', st, tracks: [p], reserve: [], i: 0, played: new Set() };
  } else {
    leaving();
    if (cur()) Q.played.add(cur().vid);
    Q.tracks = Q.tracks.filter((y, i) => i <= Q.i || y.vid !== p.vid);
    Q.tracks.splice(Q.i + 1, 0, p);
    Q.i++;
  }
  startSrc = 'find';
  if (view !== 'listen') { location.hash = ''; return loadTrack(true); }
  renderQueue();
  loadTrack(true);
}
function openAsk() {
  closeMenu();
  const d = $('#composer'), input = $('#askInput');
  if (input.disabled) { toast(t('电台准备好之后，就能在这里点歌了')); return; }
  paintComposer();
  if (!d.open) d.showModal();
  spare(d);
  input.focus();
  if (input.value.trim()) findMine();
}
$('#composer').addEventListener('click', (e) => {
  if (e.target === e.currentTarget) return e.currentTarget.close();
  const f = e.target.closest('[data-find]');
  if (f) return playFound(FOUND[+f.dataset.find]);
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
let EAR = null, earKey = '', earLoading = false, earRevealed = false, earFailed = false, earStale = false;
const earCol = new Map();
const TRAIL = 0.026;   // half the angle each trail spans, in radians
const E = { hi: null, hover: null, T: Infinity, anim: 0, era: -1, geo: null, pts: [], touch: false, ro: null };

async function loadEar() {
  if (earLoading) return;
  earLoading = true;
  earStale = false;
  let d = null;
  try {
    d = earOf(await api('/api/ear'));
  } catch {
    earFailed = true;   // the page still reads without the record
  } finally {
    earLoading = false;
  }
  if (d) {
    // A new listener's record is laid out by time of year until their stations exist; then every song travels
    // from where it was to its station's wedge.
    if (EAR?.list.length && d.list.length && EAR.stage !== d.stage && d.sectors.length) E.morph = new Map(EAR.list.map((x) => [x.ll || x.vid, x.a]));
    EAR = d;
    earFailed = false;
  }
  if (view === 'ear') renderEar();
  if (d) earColors();
}

function earOf(raw) {
  const d = { songs: [], sectors: [], span: [0, 0], eras: [], facts: [], ...raw };
  d.list = d.songs.map(([vid, title, artists, album, dur, t, lane, a, ll, off]) => ({
    vid, title, artists: artists.map((name) => ({ name })), album: album ? { name: album } : null, dur, t, lane, a, ll, off: !!off,
  })).sort((x, y) => x.t - y.t);
  return d;
}

/* ---------- a record from someone's public NetEase or QQ Music likes, before (or instead of) an account ---------- */
// It lives in this browser only: the server draws it, names it and forgets the songs (cards.py).
let GUEST = store.get('guest');
let MAKE = false;   // came in on /card: the box to paste a link into is what the page is for
// the box outlives the page being redrawn under it (the sample's record arriving, colours, polls)
const MK = { link: '', busy: '', err: '' };
const guest = () => !!(SAMPLE() && GUEST?.songs);
function useGuest(fresh) {
  EAR = earOf(GUEST);
  earFailed = false;
  if (fresh) earRevealed = false;   // a new record grows in once, as a new listener's does
}

function toMaker() {
  MAKE = !guest();
  if (location.hash !== '#ear') location.hash = '#ear';
  else { if (MAKE) EAR = null; renderEar(); }
}

// a visitor who can't reach YouTube (mainland China, a school network) can still get a record of their own
function noYouTube() {
  if (view === 'ear' && guest()) renderEar();   // the way on to weekly stations needs YouTube
  if (!SAMPLE() || (view === 'ear' && !guest())) return;
  toast(t('这里连不上 YouTube。贴一个网易云或 QQ 音乐歌单，也能画一张你的唱片'),
    [[guest() ? t('看我的唱片') : t('去画一张'), toMaker]], 15000);
}

// Where each app keeps the link to the likes: one paste box takes either, so nobody has to say which app first
function howHTML() {
  return `<dl class="mk-how"><dt>${t('网易云')}</dt><dd>${t('打开「我喜欢的音乐」→ 分享 → 复制链接')}</dd>
    <dt>${t('QQ 音乐')}</dt><dd>${t('点头像进主页 → 右上角「···」→ 分享 → 复制链接')}</dd></dl>`;
}

function makerHTML() {
  return `<form class="maker" id="maker" autocomplete="off">
    <div class="mk-t"><p class="mk-k">${t('下面是一位示例听众的唱片')}</p><h2>${t('让 Claude 锐评你的歌单')}</h2>
      <p class="mk-sub">${t('贴上你在网易云或 QQ 音乐的喜欢，十秒出一张唱片：Claude 给你的口味起个名字，再锐评一句。')}</p>${howHTML()}</div>
    <div class="mk-f"><div class="mk-row"><input id="mkLink" name="link" type="text" inputmode="url" enterkeyhint="go" spellcheck="false"
      placeholder="${t('粘贴网易云或 QQ 音乐的链接')}" aria-label="${t('网易云或 QQ 音乐的链接')}" value="${esc(MK.link)}"><button class="btn" type="submit"${MK.busy ? ' disabled' : ''}>${esc(MK.busy || t('锐评一下'))}</button></div>
      <p class="mk-err" id="mkErr" role="alert">${esc(MK.err)}</p>
      <p class="mk-alt">${t('用 YouTube Music 的话，')}<button type="button" class="lnk" data-k="join">${t('用 Google 登录')}</button>${t('：唱片会按你的口味分区，每周还有几组新歌。')}</p></div>
  </form>`;
}

function guestNextHTML() {
  const follow = followHTML();
  return `<section class="sec g-next"><h2>${GUEST.pop != null ? t('发给朋友，看谁更大众') : t('发给朋友，比比谁的歌更老')}<small>${t('朋友点开你的卡，就能锐评他自己的。')}</small></h2>
    <div class="g-acts"><button class="btn" data-k="share">${I.share}<span>${t('分享这张卡')}</span></button>
      <button class="tb" data-k="gnew">${I.swap}<span>${t('换一份歌单')}</span></button>
      ${follow ? '' : `<button class="tb" data-k="join">${I.go}<span>${t('用 YouTube Music 每周听新歌')}</span></button>`}</div></section>${follow}`;
}

// The card's songs as the start of weekly stations: Google only says who they are, the likes stay in the app.
function followHTML() {
  const j = S.me?.join;
  if (!GUEST?.link || !j || j === 'invite' || !S.me.google?.configured) return '';
  const full = j === 'full';
  // Google sign-in doesn't open where YouTube doesn't either: no button that leads nowhere
  if (Player.down) return `<section class="sec g-next g-follow"><h2>${t('按这些歌，每周给你挑新歌')}<small>${t('电台在 YouTube 上播放，可你这里现在打不开 YouTube。换到能打开它的网络，再回到这一页就能开始，这份歌单会一直留着。')}</small></h2></section>`;
  return `<section class="sec g-next g-follow"><h2>${t('按这些歌，每周给你挑新歌')}<small>${full ? t('名额暂时满了。先用 Google 登记，空出位置之后再来，就从这份歌单直接开始。') : t('几分钟后出第一批电台：每首都是你没听过的，写着为什么挑它，在 YouTube 上播放。Google 只用来确认是你，不读你的 YouTube。')}</small></h2>
    <div class="g-acts"><button class="btn" data-k="follow">${G_LOGO}<span>${full ? t('用 Google 登记') : t('用 Google 继续')}</span></button></div>
    <p class="mk-alt">${t('用 YouTube Music 的话，')}<button type="button" class="lnk" data-k="join">${t('用 Google 登录')}</button>${t('：唱片会按你的口味分区，每周还有几组新歌。')}</p>
    <p class="fine">${GUEST.source === 'qq' ? t('知音会读这份歌单，之后每 6 小时重读一次；歌名、歌手和估出来的喜欢时间会发给 Anthropic（Claude）来挑歌。随时可以在设置里全部删除。') : t('知音会读这份歌单和公开的听歌排行，之后每 6 小时重读一次；歌名、歌手、喜欢时间会发给 Anthropic（Claude）来挑歌。随时可以在设置里全部删除。')} <a href="/privacy">${t('知音怎么用你的数据')}</a></p></section>`;
}

async function follow(btn) {
  btn.disabled = true;
  try {
    const r = await api('/api/card/follow', { link: GUEST.link });
    location.href = r.go;
  } catch (e) {
    toast(e.message);
    btn.disabled = false;
  }
}

function paintMaker() {
  const b = $('#maker button[type=submit]'), err = $('#mkErr');
  if (b) { b.disabled = !!MK.busy; b.textContent = MK.busy || t('锐评一下'); }
  if (err) err.textContent = MK.err;
}

async function makeCard(link, again) {
  if (!again) Object.assign(MK, { link, err: '', busy: t('正在读你的歌单…') });
  paintMaker();
  const slow = setTimeout(() => { if (MK.busy) { MK.busy = t('Claude 正在听…'); paintMaker(); } }, 2600);
  try {
    const d = await api('/api/card/make', { link, again: !!again });
    MK.link = '';
    GUEST = { ...d, link };
    store.set('guest', GUEST);
    useGuest(!again);
    if (again && !d.why) toast(t('换了个说法'));
    if (again && d.why) toast(d.why);
    renderEar();
    if (!again) { $('.ear-wrap').scrollTop = 0; scrollTo(0, 0); }
  } catch (e) {
    if (again || !$('#mkErr')) toast(e.message); else MK.err = e.message;
  } finally {
    clearTimeout(slow);
    MK.busy = '';
    paintMaker();
  }
}

async function followOn(link) {
  if (GUEST?.link !== link) await makeCard(link);
  if (GUEST?.link === link) $('.g-follow')?.scrollIntoView({ block: 'center' });
}

function leaveGuest() {
  GUEST = null;
  store.del('guest');
  EAR = null;
  earRevealed = false;
  renderEar();
  $('#mkLink')?.focus();
}

const yearOf = (t) => Math.floor(t);
const monthIn = (y) => new Date(yearOf(y), Math.min(11, Math.floor((y - yearOf(y)) * 12))).toLocaleDateString(LANG, { year: 'numeric', month: 'short' });
const whenLiked = (y) => (EAR?.real_dates ? monthIn(y) : t('{y} 年前后', { y: yearOf(y) }));
// a record placed by release date (QQ Music, which shows nobody when a song was liked) says when each came out instead
const whenPlaced = (y) => (EAR?.dates === 'released' ? t('{when}发行', { when: monthIn(y) }) : whenLiked(y));
const sinceText = (first) => (EAR?.dates === 'released' ? t('{a}–{b} 年的歌', { a: first, b: yearOf(EAR.span[1]) }) : t('{y} 年至今', { y: first }));
const songByTitle = (t) => EAR?.list.findLast((s) => s.title === t) || EAR?.list.findLast((s) => s.title.startsWith(t));
// 《title》 (“title” in English) in the portrait and the facts plays that like
const playable = (text) => (EAR?.pics ? esc(text) : esc(text).replace(/《([^》]+)》|“([^”]+)”/g, (m, a, b) => {
  const s = songByTitle((a ?? b).replace(/&#39;/g, "'").replace(/&quot;/g, '"').replace(/&amp;/g, '&'));
  // a link, not a button: a button is laid out as one box, so a long title would break away from its sentence
  return s ? `<a class="song" href="#" role="button" data-play="${s.vid}">${m}</a>` : m;
}));

// YouTube Data API quotas reset at midnight Pacific time.
function quotaReset() {
  const now = new Date();
  const pt = new Date(now.toLocaleString('en-US', { timeZone: 'America/Los_Angeles' }));
  const at = new Date(now.getTime() + ((24 - pt.getHours()) * 3600 - pt.getMinutes() * 60 - pt.getSeconds()) * 1000);
  const hm = `${at.getHours()}:${String(at.getMinutes()).padStart(2, '0')}`;
  return at.toDateString() === now.toDateString() ? t('今天 {hm}', { hm }) : t('明天 {hm}', { hm });
}

const DISC = () => [[t('少'), 0.2], [t('中'), 0.4], [t('多'), 0.6]];
/* ---------- what the listening says: songs played often without a like, a YouTube Music history, how picks fare ---------- */
const LOVES_SHOWN = 8;
let lovesAll = false, histBusy = '', QUAL = null, qualAt = 0;

function listenedHTML() {
  const loves = EAR?.loves || [];
  if (SAMPLE() && !loves.length) return '';
  const shown = lovesAll ? loves : loves.slice(0, LOVES_SHOWN);
  const head = loves.length
    ? `<h2>${t('常听，但没点喜欢')}<small>${t('从你的播放和歌单里读出来的，已经算进你的口味。点 ♥ 收进喜欢；不是的，点「不算」。')}</small></h2>`
    : `<h2>${t('从播放里读口味')}<small>${S.me?.netease ? t('没点喜欢、却一直在听的歌，会列在这里，也算进你的口味。在知音里听得越多越准。') : t('没点喜欢、却一直在听的歌，会列在这里，也算进你的口味。在知音里听得越多越准；导入 YouTube Music 的播放记录，马上就有。')}</small></h2>`;
  return `<section class="sec" id="listened">${head}
    ${loves.length ? `<div class="lv-list">${shown.map((r, i) => loveRow(r, i)).join('')}</div>
      ${loves.length > LOVES_SHOWN ? `<button class="tb lv-more" data-k="lovesmore">${lovesAll ? t('收起') : t('再看 {n} 首', { n: loves.length - LOVES_SHOWN })}</button>` : ''}` : ''}
    ${historyHTML(EAR?.history)}</section>`;
}

function loveRow(r, i) {
  const a = r.artists?.[0]?.name || '';
  const note = r.days ? t('{n} 天里放过', { n: r.days }) : t('在你自己的歌单里');
  return `<div class="lvrow">
    <button class="lv-play" data-love="${i}" aria-label="${t('放{name}', { name: esc(r.title) })}"><img src="${px(cover(r, 120))}" alt="" loading="lazy"></button>
    <div class="lc-t"><div class="n">${esc(r.title)}</div><div class="w">${esc(a)}<span class="sep">·</span>${note}</div></div>
    <div class="lv-ctl"><button class="ib like" data-love-like="${i}" title="${t('收进喜欢')}" aria-label="${t('收进喜欢')}">${I.heart}</button><button class="tb" data-love-drop="${i}">${t('不算')}</button></div>
  </div>`;
}

const monthOf = (d) => (d ? new Date(`${d}T12:00:00`).toLocaleDateString(LANG, { year: 'numeric', month: 'short' }) : '');
function historyHTML(h) {
  if (SAMPLE() || S.me?.netease) return '';
  const pick = `<label class="tb">${h ? t('重新导入') : t('选择文件')}<input type="file" data-hist accept=".zip,.json,.html,application/zip,application/json,text/html" hidden></label>`;
  const busy = histBusy || (S.jobs?.history?.running ? t('正在从播放记录里找你常听的歌') : '');
  if (busy) return `<div class="hist"><div><b>${t('YouTube Music 播放记录')}</b><p class="busy">${esc(busy)}</p></div></div>`;
  if (h) {
    const n = (h.entries || 0).toLocaleString(LANG), m = (h.songs || 0).toLocaleString(LANG);
    const said = h.span?.[0] ? t('{a} 至 {b}，{n} 次播放，其中 {s} 首放过两次以上。这些歌不会再推给你。', { a: monthOf(h.span[0]), b: monthOf(h.span[1]), n, s: m })
      : t('{n} 次播放，其中 {s} 首放过两次以上。这些歌不会再推给你。', { n, s: m });
    return `<div class="hist"><div><b>${t('已导入 YouTube Music 播放记录')}</b><p>${said}</p></div>
      <div class="hist-acts">${pick}<button class="tb" data-k="histdel">${t('删除')}</button></div></div>`;
  }
  return `<div class="hist"><div><b>${t('导入 YouTube Music 播放记录')}</b><p>${t('在 Google Takeout 只选「YouTube 和 YouTube Music」里的历史记录，导出后把下载的 zip 放进来。文件只在你的浏览器里读；知音只收到放过两次以上的歌：歌名、歌手、放了几次、在几天里放过、第一次和最近一次的日期。')}</p></div>
    <div class="hist-acts">${pick}<a class="tb" href="https://takeout.google.com/settings/takeout/custom/youtube" target="_blank" rel="noopener">${t('打开 Google Takeout')}</a></div></div>`;
}

function playLove(i) {
  const loves = EAR?.loves || [];
  if (!loves[i]) return;
  leaving();
  const tracks = loves.map((r) => ({ ...r }));
  const st = { key: 'ear', group: 'ear', name: t('常听，但没点喜欢'), sub: t('从你的播放里读出来的'), when: '', tracks, reserve: [] };
  Q = { key: 'ear', st, tracks, reserve: [], i, played: new Set() };
  startSrc = 'ear';
  placeHost();
  loadTrack(true);
}

async function likeLove(i, btn) {
  const r = EAR?.loves?.[i];
  if (!r) return;
  btn.classList.add('on');
  btn.disabled = true;
  const lane = r.lane?.[0] && r.lane[0] !== 'none' ? r.lane[0] : null;
  try {
    const res = await api('/api/feedback', { vid: r.vid, action: 'like', lane, title: r.title, artist: r.artists?.[0]?.name, artist_id: r.artists?.[0]?.id });
    fb.set(r.vid, 'like');
    EAR.loves.splice(EAR.loves.indexOf(r), 1);
    renderEar();
    toast(res.sync === 'queued' ? t('收进喜欢了，也会出现在 YouTube Music') : t('收进喜欢了'));
  } catch {
    btn.classList.remove('on');
    btn.disabled = false;
    toast(t('没保存上，稍后再试'));
  }
}

async function dropLove(i) {
  const r = EAR?.loves?.[i];
  if (!r) return;
  try {
    S.not_me = (await api('/api/notme', { vid: r.vid, on: true })).not_me;
    const at = EAR.loves.indexOf(r);
    EAR.loves.splice(at, 1);
    renderEar();
    toast(t('以后不当成你的口味了'), [[t('撤销'), async () => {
      S.not_me = (await api('/api/notme', { vid: r.vid, on: false })).not_me;
      EAR.loves.splice(at, 0, r);
      renderEar();
    }]]);
  } catch (err) { toast(err.message); }
}

// A Google Takeout export of YouTube Music history is read here, in the browser. What goes to the server is, for each
// song played at least twice: [vid, plays, days, first day, last day, recency-weighted days, title, artist].
async function importHistory(file) {
  histBusy = t('正在读 {name}', { name: file.name });
  renderEar();
  let r = null;
  try { r = await readTakeout(file); } catch (err) { console.warn('takeout', err); }
  if (!r?.songs.length) {
    histBusy = '';
    renderEar();
    toast(r?.entries ? t('这份记录里没有放过两次以上的歌') : t('这个文件里没有找到 YouTube Music 的播放记录'), [], 7000);
    return;
  }
  histBusy = t('发送 {n} 首歌的统计', { n: r.songs.length.toLocaleString(LANG) });
  renderEar();
  try {
    const res = await api('/api/history', r);
    S.jobs = res.jobs;
    EAR.history = { at: Date.now() / 1000, span: r.span, entries: r.entries, songs: res.songs };
    poll();
    toast(t('读到 {e} 次播放，正在找你常听的歌', { e: r.entries.toLocaleString(LANG) }), [], 6000);
  } catch (err) { toast(err.message); }
  histBusy = '';
  renderEar();
}

async function readTakeout(file) {
  const texts = /\.zip$/i.test(file.name) || /zip/.test(file.type) ? await zipTexts(file) : [await file.text()];
  let best = null;
  for (const txt of texts) {
    const r = parseHistory(txt);
    if (r.entries && (!best || r.entries > best.entries)) best = r;
  }
  return best;
}

// The few lines of ZIP a Takeout archive needs: the central directory, then each JSON or HTML file under YouTube,
// inflated by the browser. (No ZIP64: a history-only export is far from 4 GB.)
async function zipTexts(file) {
  const buf = new Uint8Array(await file.arrayBuffer()), dv = new DataView(buf.buffer);
  let e = buf.length - 22;
  while (e >= 0 && dv.getUint32(e, true) !== 0x06054b50) e--;
  if (e < 0) throw new Error('not a zip');
  const n = dv.getUint16(e + 10, true), dec = new TextDecoder();
  let o = dv.getUint32(e + 16, true);
  const out = [];
  for (let i = 0; i < n; i++) {
    const method = dv.getUint16(o + 10, true), size = dv.getUint32(o + 20, true), nl = dv.getUint16(o + 28, true);
    const xl = dv.getUint16(o + 30, true), cl = dv.getUint16(o + 32, true), at = dv.getUint32(o + 42, true);
    const name = dec.decode(buf.subarray(o + 46, o + 46 + nl));
    o += 46 + nl + xl + cl;
    if (!/youtube/i.test(name) || !/\.(json|html?)$/i.test(name) || (method !== 0 && method !== 8)) continue;
    const start = at + 30 + dv.getUint16(at + 26, true) + dv.getUint16(at + 28, true);
    const raw = buf.subarray(start, start + size);
    out.push(method === 0 ? dec.decode(raw) : await new Response(new Blob([raw]).stream().pipeThrough(new DecompressionStream('deflate-raw'))).text());
  }
  return out;
}

const MON = { jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5, jul: 6, aug: 7, sep: 8, oct: 9, nov: 10, dec: 11 };
const DAY = 864e5, DAY_START = 5 * 3600e3;   // a listening day starts at 5 am, so a late night counts with its evening
// A date as the HTML export prints it, in whatever language: "Oct 25, 2026, …", "25 Oct 2026, …", "2026年10月25日 …".
function htmlDay(x) {
  x = x.replace(/&nbsp;|[  ]/g, ' ');
  let m = /(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日/.exec(x) || /(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})/.exec(x);
  if (m) return Math.floor(Date.UTC(+m[1], +m[2] - 1, +m[3]) / DAY);
  m = /\b([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})/.exec(x);
  if (m && m[1].toLowerCase() in MON) return Math.floor(Date.UTC(+m[3], MON[m[1].toLowerCase()], +m[2]) / DAY);
  m = /\b(\d{1,2})\s+([A-Za-z]{3})[a-z]*\.?\s+(\d{4})/.exec(x);
  if (m && m[2].toLowerCase() in MON) return Math.floor(Date.UTC(+m[3], MON[m[2].toLowerCase()], +m[1]) / DAY);
  return NaN;
}
const unhtml = (x) => new DOMParser().parseFromString(x, 'text/html').documentElement.textContent;
const channelArtist = (c) => c.replace(/\s*-\s*(Topic|主題|主题)$/, '').replace(/VEVO$/, '').trim();

function parseHistory(txt) {
  const items = [];   // [vid, title, channel, day]
  const s = txt.trimStart();
  if (s[0] === '[') {
    let arr;
    try { arr = JSON.parse(s); } catch { return { entries: 0, songs: [] }; }
    const music = arr.filter((e) => /^https:\/\/music\.youtube\.com\/watch/.test(e.titleUrl || '') || e.header === 'YouTube Music');
    // titles read "Watched <title>" or "<title> を視聴しました" in the export's language: cut the words every entry
    // starts or ends with, once there are enough different songs to tell them from a title's own words
    const sample = [...new Set(music.slice(0, 600).map((e) => e.title || ''))].slice(0, 300);
    let cut = 0, cutEnd = 0;
    for (let k = 1; k <= 24 && sample.length >= 12; k++) {
      const pre = sample[0].slice(0, k), suf = sample[0].slice(-k);
      if (/\s$/.test(pre) && sample.filter((x) => x.startsWith(pre)).length >= sample.length * 0.95) cut = k;
      if (/^\s/.test(suf) && sample.filter((x) => x.endsWith(suf)).length >= sample.length * 0.95) cutEnd = k;
    }
    const words = (x) => (sample.length >= 12 ? x.slice(cut, x.length - cutEnd)
      : x.replace(/^(Watched|已观看|已觀看|观看了|觀看了)\s+/, '').replace(/\s+(を視聴しました|을\(를\) 시청했습니다)$/, ''));
    for (const e of music) {
      const m = /[?&]v=([\w-]{11})/.exec(e.titleUrl || '');
      if (!m) continue;
      const ms = Date.parse(e.time);
      items.push([m[1], words(e.title || ''), e.subtitles?.[0]?.name || '',
        Number.isNaN(ms) ? NaN : Math.floor((ms - new Date(ms).getTimezoneOffset() * 6e4 - DAY_START) / DAY)]);
    }
  } else {
    const re = /href="https:\/\/music\.youtube\.com\/watch\?v=([\w-]{11})[^"]*">([^<]*)<\/a>(?:<br>\s*<a href="[^"]*">([^<]*)<\/a>)?<br>([^<]{6,80})<br>/g;
    for (const m of s.matchAll(re)) items.push([m[1], unhtml(m[2]), unhtml(m[3] || ''), htmlDay(m[4])]);
  }
  const by = new Map();
  let lo = Infinity, hi = -Infinity;
  for (const [v, title, ch, day] of items) {
    let x = by.get(v);
    if (!x) by.set(v, (x = { n: 0, days: new Set(), title, ch }));
    x.n++;
    if (Number.isFinite(day)) { x.days.add(day); lo = Math.min(lo, day); hi = Math.max(hi, day); }
  }
  const today = Math.floor(Date.now() / DAY), iso = (d) => (Number.isFinite(d) ? new Date(d * DAY).toISOString().slice(0, 10) : '');
  const songs = [...by].filter(([, x]) => x.n >= 2).map(([v, x]) => {
    const ds = [...x.days];
    const rw = ds.reduce((a, d) => a + 0.5 ** (Math.max(0, today - d) / 365), 0);
    return [v, x.n, ds.length, iso(ds.length ? Math.min(...ds) : NaN), iso(ds.length ? Math.max(...ds) : NaN), +rw.toFixed(3),
      x.title.slice(0, 200), channelArtist(x.ch).slice(0, 120)];
  }).sort((a, b) => b[5] - a[5] || b[1] - a[1]).slice(0, 30000);
  return { songs, span: [iso(lo), iso(hi)], entries: items.length };
}

async function loadQuality() {
  if (SAMPLE() || Date.now() - qualAt < 60e3) return;
  qualAt = Date.now();
  try { QUAL = await api('/api/quality?days=14'); } catch { return; }
  const f = $('#qualFold');
  if (f && view === 'ear') f.outerHTML = qualityHTML();
}

// How the recommendations fared, from the first time each one played: the evidence for changing the engine.
function qualityHTML() {
  const g = QUAL?.groups, all = g?.all?.all;
  const known = (x) => x.n - x.unknown - x.error;
  if (!all || known(all) < 5) return '<div id="qualFold"></div>';
  const pct = (x, k = 'good') => (known(x) > 0 ? Math.round((100 * x[k]) / known(x)) : null);
  const row = (name, x) => `<li><span>${esc(name)}<small>${t('{n} 首', { n: x.n })}<span class="sep">·</span>${t('早跳 {p}%', { p: pct(x, 'early') ?? 0 })}${x.like ? `<span class="sep">·</span>${t('点了喜欢 {n}', { n: x.like })}` : ''}</small></span><span class="num">${pct(x) ?? '–'}%</span></li>`;
  const block = (title, rows) => (rows.length ? `<h4 class="fold-h">${title}</h4><ul class="plain">${rows.join('')}</ul>` : '');
  const lanes = Object.entries(g.lane || {}).filter(([k]) => QUAL.names[k]).sort((a, b) => b[1].n - a[1].n).map(([k, x]) => row(QUAL.names[k], x));
  const FIT = { '0.9+': t('编辑很有把握（0.9 以上）'), '0.8-0.9': t('比较有把握（0.8–0.9）'), '0.7-0.8': t('值得一试（0.7–0.8）'), probe: t('编辑本来不会推的（对照）'), unvetted: t('备用的歌，没经过编辑') };
  const ART = { new: t('没收藏过的歌手'), liked: t('收藏过的歌手'), known: t('订阅过或常听的歌手') };
  const fits = Object.keys(FIT).filter((k) => g.fit?.[k]).map((k) => row(FIT[k], g.fit[k]));
  const arts = Object.keys(ART).filter((k) => g.artist?.[k]).map((k) => row(ART[k], g.artist[k]));
  return `<details class="fold" id="qualFold"><summary><b>${t('推荐准不准')}</b><span>${t('最近 {d} 天第一次听的 {n} 首推荐里，{p}% 听完了', { d: QUAL.days, n: all.n, p: pct(all) })}</span>${I.down}</summary>
    <p class="fold-note">${t('听完：放完或听到八成，没按「不要」。早跳：十秒内按了下一首。每首只算第一次听；右边是听完的比例。')}</p>
    ${block(t('按电台'), lanes)}${block(t('按编辑的把握'), fits)}${block(t('按歌手'), arts)}</details>`;
}

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
  if (S.me?.status === 'new') {
    $('#view').innerHTML = `<div class="ear-wrap"><div class="ear"><div class="ear-hero"><div>
      <h1>${t('还没开始')}</h1><p class="lede">${t('连接 YouTube Music 之后，这里会写出你的口味。')}</p></div></div></div></div>`;
    placeHost();
    return;
  }
  const g = guest();
  if (g && EAR?.token !== GUEST.token) useGuest(true);
  else if (!g && EAR?.token) EAR = null;   // back to the sample listener's record
  if ((!EAR || earStale) && !earFailed) loadEar();
  const keep = $('.ear-wrap')?.scrollTop || 0;
  const typing = $('#mkLink');
  if (typing) MK.link = typing.value;
  const refocus = typing && document.activeElement === typing;
  const po = S.portrait, full = !!(po && S.lanes.length) && !g;
  // The name of their taste heads the page; Claude's portrait sentence follows it. Before the name exists (or
  // without one) the portrait's first sentence heads it, as it always did.
  const name = EAR?.label;
  const songs = EAR?.list.length || 0, n = g ? EAR.n : S.library.songs || songs;
  let head = name || '', lede = !name ? '' : g ? EAR.roast || '' : po?.headline || '';
  if (g && !name) { head = t('你的喜欢'); lede = EAR.why || ''; }
  else if (!name && po) {
    const cut = po.headline.search(/[。！？]|[.!?](?=\s)/);   // the first sentence is the heading, in either script
    head = cut > 0 ? po.headline.slice(0, cut + 1) : po.headline;
    lede = po.headline.slice(head.length).trim();
  }
  // the strip says how setup is going and offers music meanwhile; this page only fills in as the record arrives
  const naming = (!name && S.jobs?.label?.running) || !songs;

  const first = songs ? yearOf(EAR.span[0]) : (S.timeline.map((p) => p[1]).filter(Boolean).sort()[0] || '').slice(0, 4);
  const meta = [g ? appName(EAR.source) : SAMPLE() ? t('示例听众') : '', n ? t('{n} 首喜欢', { n }) : '', first ? sinceText(first) : '',
    full ? t('{n} 种口味', { n: S.lanes.length }) : ''].filter(Boolean).map((x) => `<span class="nw">${esc(x)}</span>`).join(' · ');
  const canShare = songs && (name || g);
  const fbRows = S.feedback.filter((f) => f.action !== 'known').slice(0, 30);
  const label = (f) => (f.action === 'like' ? t('喜欢') : f.scope === 'artist' ? t('不要这位歌手') : t('不要这首'));
  const sec = (k) => EAR?.sectors.find((x) => x.key === k);
  const on = S.lanes.filter((l) => l.enabled).length;
  const skeleton = `<div class="fact sk"><b class="lead">00%</b><p>${t('正在把你的喜欢按年份排开')}</p></div>`.repeat(3);
  const nm = S.not_me || { songs: [], artists: [] };
  const offN = EAR?.list.filter((x) => x.off).length || 0;
  const asideN = S.set_aside.reduce((a, x) => a + x.n, 0) + offN;
  $('#view').innerHTML = `
  <div class="ear-wrap"><div class="ear">
    ${SAMPLE() && !g ? makerHTML() : ''}
    <header class="ear-hero">
      <div class="hero-t">
        <h1 class="${naming ? 'sk' : ''}">${naming ? t('正在给你的口味起个名字') : name && g ? relabelable(name, 'grelabel') : name && !SAMPLE() ? relabelable(name) : esc(head || t('你的喜欢'))}</h1>
        ${lede ? `<p class="lede${g && EAR.roast ? ' roast' : ''}">${g && EAR.roast ? `<span class="rk">${t('Claude 锐评')}</span>` : ''}${esc(lede)}</p>` : ''}
        <div class="meta-row"><p class="meta-line num">${meta}</p>${canShare ? `<button class="tb share" data-k="share">${I.share}<span>${t('分享')}</span></button>` : ''}</div>
      </div>
      <div class="facts" id="facts">${EAR?.list.length ? factsHTML() : earFailed ? '' : skeleton}</div>
      ${earFailed ? '' : `<div class="rec-l">
        <div class="disc ${songs ? '' : 'loading'}" id="disc" aria-label="${t('你的喜欢，按年份一圈一圈往外长，按口味分成扇区')}">
          <canvas></canvas><svg class="disc-svg"></svg><div class="hub" id="hub"></div><div class="tip"></div>
        </div>
        ${EAR?.eras?.length ? `<div class="eras2"><button class="replay" data-k="replay" title="${t('从第一首喜欢开始，重放一遍')}">${I.play}<span>${t('回放')}</span></button><div class="eratrack" id="eraTrack"></div></div>
        <p class="era-now" id="eraNow"></p>` : songs ? `<div class="eras2"><button class="replay" data-k="replay" title="${EAR?.dates === 'released' ? t('从最老的一首开始，重放一遍') : t('从第一首喜欢开始，重放一遍')}">${I.play}<span>${t('回放')}</span></button><p class="disc-key">${EAR?.dates === 'released' ? t('每一圈是一年，越往外越新；位置是每首歌的发行时间：{app}不显示你哪天点的喜欢。', { app: appName(EAR.source) }) : EAR?.real_dates ? t('每一圈是一年，越往外越近；角度是你在一年里的哪个月点的喜欢。') : t('每一圈是一年，越往外越近；点喜欢的时间是估的，只看得出大概哪一年。')}</p></div>` : ''}
      </div>`}
    </header>
    ${g ? guestNextHTML() : ''}
    ${full ? `<section class="sec"><h2>${t('你的口味')}<small>${t('{n} 种在推荐里。点封面就放这个口味的电台；关掉的下一批起不再出现；新面孔是没收藏过的歌手占多少。', { n: on })}</small></h2>
      <div class="lanes">${S.lanes.map((l) => laneRow(l, sec(l.key))).join('')}</div></section>
    ${listenedHTML()}
    <section class="sec"><h2>${t('完整的画像')}</h2>
      <div class="portrait">
        <div><div class="prose" id="prose">${po.paragraphs.map((x) => `<p>${playable(x)}</p>`).join('')}</div>
          ${po.paragraphs.length > 1 ? `<button class="tb readmore" data-k="readmore">${t('读完整段')}</button>` : ''}</div>
        ${po.threads.length ? `<div class="threads"><h3>${t('一直没变的')}</h3><ol class="threads">${po.threads.map((x) => `<li>${playable(x)}</li>`).join('')}</ol></div>` : ''}
      </div></section>
    <section class="sec folds">
      ${qualityHTML()}
      <details class="fold"><summary><b>${t('不算进口味的')}</b><span>${asideN ? t('{n} 首，留在你的喜欢里，但不拿来推歌', { n: asideN }) : t('留在你的喜欢里，但不拿来推歌')}</span>${I.down}</summary>
        <p class="fold-note">${t('在这页放你自己的歌时按「不要」，那首（或那位歌手）就不再代表你的口味，但仍在你的喜欢里。')}</p>
        <ul class="plain">${S.set_aside.map((x) => `<li><span>${esc(x.what)}<small>${esc(x.why)}</small></span><span class="num">${t('{n} 首', { n: x.n })}</span></li>`).join('')}${nm.artists.map((x) => `<li><span>${esc(x.name)}<small>${t('你说这位歌手的歌不算你的口味')}</small></span><button class="tb" data-notme-artist="${esc(x.key)}">${t('放回来')}</button></li>`).join('')}${nm.songs.map((x) => `<li><span>${esc(x.title)}<small>${esc(x.artist)} · ${t('你说这首不算你的口味')}</small></span><button class="tb" data-notme-song="${esc(x.vid)}">${t('放回来')}</button></li>`).join('')}</ul></details>
      ${fbRows.length ? `<details class="fold"><summary><b>${t('最近的反馈')}</b><span>${t('{n} 条，点错了可以撤销', { n: fbRows.length })}</span>${I.down}</summary>
        <ul class="plain">${fbRows.map((f) => `<li><span>${esc(f.title || f.vid)}<small>${esc(f.artist || '')} · ${label(f)} · ${new Date(f.ts * 1000).toLocaleDateString(LANG, { month: 'short', day: 'numeric' })}</small></span><button class="tb" data-undo="${esc(f.vid)}">${t('撤销')}</button></li>`).join('')}</ul></details>` : ''}
    </section>` : ''}
  </div></div>`;
  $('.ear-wrap').scrollTop = keep;
  if (songs) mountDisc();
  if (g) earColors();
  paintNow();
  placeHost();
  if (full) loadQuality();
  if (refocus) $('#mkLink')?.focus({ preventScroll: true });
  if (MAKE && $('#mkLink')) { MAKE = false; if (matchMedia('(pointer: fine)').matches) $('#mkLink').focus({ preventScroll: true }); }
}

// the re-roll button rides on the name's last word (or character), so it never wraps onto a line by itself
function relabelable(name, k = 'relabel') {
  const [, a, b] = name.match(/^(.*?)([A-Za-z0-9’'.-]{1,24}|.)$/su);
  return `${esc(a)}<span class="nw">${esc(b)}<button class="ib sm relabel" data-k="${k}" title="${t('换个说法')}" aria-label="${t('换个说法')}">${I.refresh}</button></span>`;
}

async function relabel(btn) {
  btn.disabled = true;
  try { S.jobs = await api('/api/ear/label', {}); renderEar(); poll(); } catch (err) { toast(err.message); btn.disabled = false; }
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
  if (!EAR.sectors.length) {
    // laid out by time of year until the stations exist: the months take the place of the station names
    for (let m = 0; m < 12; m++) {
      const a = 8 + 344 * m / 12, [x0, y0] = P(R1 + 2, a), [x1, y1] = P(R1 + 7, a);
      svg += `<path class="tick" d="M${x0.toFixed(1)} ${y0.toFixed(1)}L${x1.toFixed(1)} ${y1.toFixed(1)}"/>`;
      if (m % 3 === 0) {
        const [x, y] = P(R1 + 18, a + 344 / 24);
        svg += `<text class="mon" x="${x.toFixed(1)}" y="${y.toFixed(1)}">${esc(new Date(2000, m).toLocaleDateString(LANG, { month: 'short' }))}</text>`;
      }
    }
  }
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
  const et = $('#eraTrack');
  if (et) et.innerHTML = order.map((i, k) => {
    // an era runs until the next one starts, so a short era never lies under its neighbour's label
    const er = EAR.eras[i], next = EAR.eras[order[k + 1]];
    const l = pos(er.t0), r = next ? pos(next.t0) : Math.min(1, Math.max(pos(er.t1), l + 0.3 / span));
    return `<button class="era2" data-era="${i}" aria-label="${esc(er.years)} ${esc(er.label)}" style="left:${(l * 100).toFixed(2)}%;width:${((r - l) * 100).toFixed(2)}%"><span class="y num"><span class="yf">${esc(er.years)}</span><span class="ys">${esc((er.years.match(/\d{4}/) || [er.years])[0])}</span></span><span class="l">${esc(er.label)}</span></button>`;
  }).join('');
  // Sized by pixels, not by share of the span: six two-year eras are each a fifth of the track but too narrow for a label.
  $$('.era2').forEach((b) => {
    const px = b.offsetWidth;
    b.classList.toggle('tiny', px < 40);
    b.classList.toggle('narrow', px >= 40 && px < 110);
    const y = b.querySelector('.y');
    if (y.scrollWidth > y.clientWidth) b.classList.add('tiny');
  });
  showEra(-1);
  bindDisc(box);
  paintHub();
  cancelAnimationFrame(E.mo);   // a morph in flight moved the points this replaced
  E.mo = 0;
  if (!earRevealed) { earRevealed = true; E.morph = null; replay(2600); } else if (E.morph) morph(); else paintDisc();
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
    x.globalAlpha = on ? (s.off ? 0.2 : 0.95) : 0.1;   // a like that isn't their taste stays on the record, faint
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

// The songs leave their months for their stations' wedges, each a little after the one before it around the circle.
function morph() {
  const from = E.morph, g = E.geo;
  E.morph = null;
  cancelAnimationFrame(E.mo);
  const set = (p, a) => { [p.x, p.y] = g.P(p.r, a); p.th = (a - 90) * Math.PI / 180; };
  const pts = E.pts;
  for (const p of pts) { p.a1 = p.s.a; p.a0 = from.get(p.s.ll || p.s.vid) ?? p.s.a; }
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) { paintDisc(); return; }
  $('.disc-svg')?.classList.add('arrive');
  const D = 1500, LAG = 500;
  let start = 0;
  const step = (now) => {
    start ||= now;   // from the first frame drawn, so the page being rebuilt around it can't eat the start
    let busy = false;
    for (const p of pts) {
      const k = Math.min(1, Math.max(0, (now - start - LAG * p.a1 / 360) / D));
      busy ||= k < 1;
      set(p, p.a0 + (p.a1 - p.a0) * (1 - (1 - k) ** 4));
    }
    paintDisc();
    E.mo = busy ? requestAnimationFrame(step) : 0;
  };
  for (const p of pts) set(p, p.a0);
  E.mo = requestAnimationFrame(step);
}

function paintHub() {
  const hub = $('#hub');
  if (!hub || !EAR) return;
  if (E.T !== Infinity) { hub.dataset.u = ''; hub.className = 'hub'; hub.innerHTML = `<b class="num">${yearOf(Math.min(E.T, EAR.span[1]))}</b>`; return; }
  const p = E.hover?.s || (EAR.pics ? null : cur());
  const u = p && (EAR.pics ? (EAR.pics[p.vid] ? appPic(EAR.pics[p.vid], 300) : '') : px(cover(p, 300)));
  if (u) {
    if (hub.dataset.u !== u) { hub.dataset.u = u; hub.innerHTML = `<img src="${u}" alt="">`; }
    hub.className = `hub ${E.hover ? '' : 'spin'}`;
    return;
  }
  hub.dataset.u = '';
  hub.className = 'hub';
  hub.innerHTML = `<b class="num">${EAR.n ?? EAR.list.length}</b><span>${t('首喜欢')}</span>`;
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
    tip.innerHTML = `<b>${esc(p.s.title)}</b><span>${esc(names(p.s.artists))} · ${whenPlaced(p.s.t)}</span>`;
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
    if (EAR.pics) return hoverDot(E.touch && E.hover === p ? null : p);
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
  leaving();
  const sec = EAR.sectors.find((s) => s.key === p.s.lane);
  const st = { key: 'ear', group: 'ear', name: t('{lane} · 从〈{s}〉放起', { lane: sec?.name || t('你的喜欢'), s: p.s.title }), sub: t('你自己的喜欢'), when: t('在「你的耳朵」里点的，接着放它附近的喜欢'), tracks, reserve: [] };
  Q = { key: 'ear', st, tracks, reserve: [], i: 0, played: new Set() };
  startSrc = 'ear';
  placeHost();
  loadTrack(true);
  hoverDot(null);
}

function playVid(vid) {
  const p = E.pts.find((q) => q.s.vid === vid);
  if (p) playFromDisc(p);
}

// dot colours come from each song's own cover; kept per browser so the record is in colour from the second visit
function earColors() {
  E.colouring ||= colourDots().finally(() => { E.colouring = null; });
  return E.colouring;
}
async function colourDots() {
  const pics = EAR.pics;
  if (!earCol.size && !pics) for (const [v, c] of Object.entries(store.get(acct('earCol')) || {})) earCol.set(v, c);
  const todo = [...new Set(EAR.list.map((s) => s.vid))].filter((v) => !earCol.has(v));
  if (!todo.length) return;
  // a record from an app: songs share their album's cover, one look per cover
  const byPic = new Map();
  const colorOf = (v) => {
    if (!pics) return dotColor(px(`https://i.ytimg.com/vi/${v}/default.jpg`));
    const u = pics[v];
    if (!u) return Promise.reject();
    if (!byPic.has(u)) byPic.set(u, dotColor(appPic(u, 40), true));
    return byPic.get(u);
  };
  let i = 0, dirty = false;
  const flush = setInterval(() => { if (dirty && E.T === Infinity) { dirty = false; paintDisc(); } }, 160);
  const work = async () => {
    while (i < todo.length) {
      const v = todo[i++];
      try { earCol.set(v, await colorOf(v)); } catch { earCol.set(v, null); }
      dirty = true;
    }
  };
  await Promise.all(Array.from({ length: pics ? 8 : 6 }, work));
  clearInterval(flush);
  paintDisc();
  if (!pics) store.set(acct('earCol'), Object.fromEntries([...earCol].filter(([, c]) => c)));
}

function dotColor(src, square) {
  return new Promise((res, rej) => {
    const img = new Image();
    if (square) img.crossOrigin = 'anonymous';
    img.onload = () => {
      const c = document.createElement('canvas');
      c.width = c.height = 16;
      const x = c.getContext('2d', { willReadFrequently: true });
      // default.jpg is 4:3 around a 16:9 frame; the middle holds the artwork. An album cover is all artwork.
      if (square) x.drawImage(img, 0, 0, 16, 16);
      else x.drawImage(img, img.width * 0.22, img.height * 0.2, img.width * 0.56, img.height * 0.6, 0, 0, 16, 16);
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
  frameAway = false;
  placeCard();
  if (view === 'ear') renderEar(); else renderListen();
  renderStations();
  scrollTo(0, 0);
}
addEventListener('hashchange', route);
document.addEventListener('change', (e) => {
  const f = e.target.closest?.('input[data-hist]');
  if (f?.files?.[0]) importHistory(f.files[0]);
});

/* ---------- actions ---------- */
async function act(k, btn) {
  const p = cur();
  if (k === 'join' || (SAMPLE() && NEEDS_ACCOUNT.has(k))) return openJoin(k);
  if (k === 'toggle') Player.toggle();
  else if (k === 'next') next();
  else if (k === 'prev') prev();
  else if (k === 'like' && p) like(p);
  else if (k === 'nope' && p) nope(p);
  else if (k === 'hearmine' && p) hearMine(p);
  else if (k === 'share') shareCard(btn);
  else if (k === 'relabel') relabel(btn);
  else if (k === 'radio') { closeMenu(); continueFrom(null); }
  else if (k === 'lanenote') openLaneNote();
  else if (k === 'unaskcur') { closeMenu(); unask(+Q.key.slice(4)); }
  else if (k === 'lyrics') toggleLyrics();
  else if (k === 'tab-lyr') toggleLyrics(true);
  else if (k === 'tab-q') { if (Lyr.data) toggleLyrics(false); }
  else if (k === 'calm' || k === 'up' || k === 'fresh') steer(k);
  else if (k === 'blend') setBlend(btn.dataset.v);
  else if (k === 'pip') Pip.toggle().catch(() => toast(t('小窗打不开')));
  else if (k === 'imm') immersive();
  else if (k === 'stage') toggleStage();
  else if (k === 'lytr' || k === 'lyro') {
    const key = k === 'lytr' ? 'tr' : 'ro';
    Lyr[key] = !Lyr[key];
    store.set(key, Lyr[key]);
    Lyr.render();
    Lyr.sync(true);
  } else if (k === 'extend') { btn.disabled = true; await extend(false); btn.disabled = false; }
  else if (k === 'refresh') startRefresh();
  else if (k === 'unask') unask(+btn.dataset.c);
  else if (k === 'unaskall') unask(null);
  else if (k === 'setup') { try { await api('/api/setup', {}); await reload(); poll(); } catch (err) { toast(err.message); } }
  else if (k === 'resync') { try { S.jobs = await api('/api/sync', {}); renderSheet(); poll(); } catch (err) { toast(err.message); } }
  else if (k === 'synclikes') {
    const on = btn.getAttribute('aria-checked') !== 'true';
    btn.setAttribute('aria-checked', on);
    const r = await api('/api/account/sync-likes', { on });
    if (r.grant) { location.href = r.grant; return; }
    S.me = r;
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
  else if (k === 'grelabel' && GUEST) { btn.disabled = true; await makeCard(GUEST.link, true); }
  else if (k === 'gnew') leaveGuest();
  else if (k === 'follow' && GUEST) follow(btn);
  else if (k === 'tomaker') { $('#join').close(); toMaker(); }
  else if (k === 'lovesmore') { lovesAll = !lovesAll; renderEar(); }
  else if (k === 'histdel') {
    try { const r = await api('/api/history/delete', {}); S.jobs = r.jobs; EAR.history = null; renderEar(); poll(); toast(t('播放记录删掉了')); } catch (err) { toast(err.message); }
  }
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
  const line = e.target.closest('.ll[data-i]:not(.gap)');
  if (line && Lyr.data) {
    const l = Lyr.data.lines[+line.dataset.i];
    Lyr.hold = 0;
    Player.seekTo(l.t + Lyr.delay);
    if (!Player.playing) Player.play();
    return;
  }
  const lv = e.target.closest('[data-love],[data-love-like],[data-love-drop]');
  if (lv) {
    if (lv.dataset.loveLike != null) return likeLove(+lv.dataset.loveLike, lv);
    if (lv.dataset.loveDrop != null) return dropLove(+lv.dataset.loveDrop);
    return playLove(+lv.dataset.love);
  }
  const tr = e.target.closest('.tr');
  if (tr) {
    const p = Q.tracks[+tr.dataset.i];
    const a = e.target.closest('[data-a]')?.dataset.a;
    if (a === 'like') return like(p);
    if (a === 'nope') return nope(p);
    if (+tr.dataset.i === Q.i) return Player.toggle();
    leaving();
    Q.played.add(cur()?.vid);
    Q.i = +tr.dataset.i;
    startSrc = 'pick';
    return loadTrack(true);
  }
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
  const back = e.target.closest('[data-notme-song], [data-notme-artist]');
  if (back) {
    back.disabled = true;
    const body = back.dataset.notmeSong ? { vid: back.dataset.notmeSong, on: false } : { key: back.dataset.notmeArtist, on: false };
    setNotMe(body).catch(() => { back.disabled = false; toast(t('没保存上，稍后再试')); });
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
  else if (k === 's') toggleStage();
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
  if (e.target.id === 'maker') {
    e.preventDefault();
    const link = e.target.link.value.trim();
    if (!link) e.target.link.focus();
    else if (!MK.busy) makeCard(link);
    return;
  }
  if (e.target.id === 'neForm') {
    e.preventDefault();
    const f = e.target, link = f.link.value.trim(), b = f.querySelector('button'), err = f.querySelector('.mk-err');
    if (!link) { f.link.focus(); return; }
    b.disabled = true;
    err.textContent = '';
    try {
      const r = await api('/api/netease', { link });
      S.jobs = r.jobs;
      await reload();
      poll();
    } catch (x) {
      err.textContent = x.message;
      b.disabled = false;
    }
    return;
  }
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
  if (SAMPLE()) { $('#composer').close(); return openJoin('ask'); }
  const input = $('#askInput'), q = input.value.trim();
  if (!q) return;
  if (!canAsk()) return toast(t('电台准备好之后，才能用一句话点歌'));
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
      // a new listener watches their record fill in: the liked videos, then the songs, then the stations
      if (view === 'ear' && jobs.setup?.running && EAR?.stage !== 'full' && ++earTick % 2 === 0) loadEar();
      if (!Object.values(jobs).some((j) => j?.running)) break;
    }
  } finally { polling = false; }
}

let earTick = 0;
async function finished(done) {
  const prevEd = S.edition?.id;
  await reload();
  for (const [k, j] of done) {
    if (k === 'label') {
      if (j.error) toast(t('这次没起好名字，稍后再试'));
      loadEar();
      continue;
    }
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
    if (k === 'setup' && !j.error && ready() && view === 'ear') {
      toast(t('你的电台准备好了'), [[t('去听'), () => { location.hash = ''; const d = defaultStation(); if (d) selectStation(d.key); }]], 12000);
      continue;
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
    if (k === 'history') {
      if (j.error) toast(t('没读完播放记录：{e}', { e: j.error.slice(0, 60) }));
      else toast(j.result?.loves ? t('找到 {n} 首你常听、没点喜欢的歌', { n: j.result.loves }) : t('播放记录里没有特别常听、又没点喜欢的歌'), [], 6000);
      loadEar();
      continue;
    }
    if (k === 'retell') {
      if (j.error) toast(t('没改写成功：{e}', { e: j.error.slice(0, 60) }));
      else { EAR = null; route(); renderSheet(); toast(t('改写好了')); }
      continue;
    }
    if (k === 'refresh' && !j.error && S.edition?.id !== prevEd) {
      if (!Q) { const d = defaultStation(); if (d) { Q = queueOf(d); renderListen(); loadTrack(false); } }
      toast(t('这周的电台换了新的一批，点电台就能听到'));
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
  const [s] = await Promise.all([api('/api/state'), loadMine()]);
  S = s;
  if (MINE && MINE.ed !== S.edition?.id) await loadMine(true);
  packPicks();
  const k = `${S.profile_built}|${S.library.songs}`;
  if (k !== earKey) { earKey = k; earStale = true; }
  if (!ready() && S.me.status !== 'new' && !WARM) loadWarm();
  if (ready() && Q?.key !== 'warm') WARM = null;
  $('#askInput').disabled = SAMPLE() ? !(ready() && S.portrait) : !canAsk() && !canFind();
  $('#askInput').placeholder = SAMPLE() ? t('想听点什么？说说场景或心情') : canAsk() ? t('搜你的喜欢，或说说想听什么') : t('搜你喜欢过的歌');
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
    blendQueue(Q);
    if (view === 'listen' && $('#qName')) { renderQueue(); paintNow(); }
  }
  renderStations();
  if (view === 'ear') renderEar();
}

function buildMini() {
  $('.pc-ctl').innerHTML = `<button class="ib" data-k="prev" aria-label="${t('上一首')}">${I.prev}</button><button class="ib play" data-k="toggle" aria-label="${t('播放 / 暂停')}">${I.play}${I.pause}</button><button class="ib" data-k="next" aria-label="${t('下一首')}">${I.next}</button><span class="push"></span><button class="ib like" data-k="like" aria-label="${t('喜欢')}">${I.heart}</button>`;
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
    if (pos?.ed === S.edition?.id && pos.key === Q.key) { Q.i = Math.max(0, Q.tracks.findIndex((p) => p.vid === pos.vid)); startSrc = 'resume'; }
  }
  Player.init();
  // a listener who just joined lands on their record, which is drawn within seconds; stations take a while
  if (!location.hash && ['importing', 'building'].includes(S.me?.status)) history.replaceState(null, '', '#ear');
  // ?ne= is a NetEase card coming back from an app's own browser, where Google wouldn't sign in
  const ne = location.pathname === '/card' && SAMPLE() ? new URLSearchParams(location.search).get('ne') : null;
  if (location.pathname === '/card') { MAKE = SAMPLE() && !GUEST && !ne; history.replaceState(null, '', '/#ear'); }
  route();
  if (ne) followOn(ne);
  if (cur()) { Player.load(cur(), false); trackChanged(); }
  if (Object.values(S.jobs || {}).some((j) => j?.running)) poll();
  setTimeout(staleLangNote, 1200);
}

applyLang();
boot();
